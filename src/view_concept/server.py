"""The local web server: serves the page, streams file changes, receives comment batches,
runs side threads."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import frame, launch, publish, threads
from .render import md
from .store import Session, SessionError, list_sessions

STATIC = Path(__file__).parent / "static"
# The verdicts an item can get, by session workflow, each list in the review table's order:
# {key, meaning, tone, sends_to?}. The view-branch and view-refactor skills read the same file.
VERDICTS: dict[str, list[dict[str, str]]] = yaml.safe_load(
    (Path(__file__).parent / "verdicts.yaml").read_text(encoding="utf-8")
)
# A session created before workflows existed was a branch review or had no items.
LEGACY_WORKFLOW = "view-branch"

app = FastAPI(title="view-concept")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def get_session(slug: str) -> Session:
    try:
        s = Session(slug)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    if not s.exists():
        raise HTTPException(404, f"no session {slug!r}")
    return s


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC / "home.html")


@app.get("/s/{slug}")
def session_page(slug: str) -> FileResponse:
    get_session(slug)
    return FileResponse(STATIC / "session.html")


@app.get("/api/sessions")
def sessions() -> list[dict[str, Any]]:
    return list_sessions()


# The open pages listening to the global event stream: one queue each, where `focus`
# puts the session to show.
_pages: set[asyncio.Queue[str]] = set()


@app.get("/api/events")
async def global_events(request: Request) -> StreamingResponse:
    """What every open page hears, whatever session it shows: `sessions` when the session
    list changed (the sidebar reloads it) and `focus` when a session should be shown."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    _pages.add(queue)

    async def stream():
        try:
            last = await asyncio.to_thread(list_sessions)
            yield "event: hello\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    slug = await asyncio.wait_for(queue.get(), 2)
                    yield f"event: focus\ndata: {json.dumps({'slug': slug})}\n\n"
                except TimeoutError:
                    rows = await asyncio.to_thread(list_sessions)
                    yield "event: sessions\ndata: {}\n\n" if rows != last else ": ping\n\n"
                    last = rows
        finally:
            _pages.discard(queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@app.post("/api/focus/{slug}")
async def focus(slug: str) -> dict[str, int]:
    """Show session `slug` in the open pages (the last one the user was on takes it).
    `pages` is how many were told: with none, `view-concept open` opens the browser."""
    get_session(slug)
    for queue in _pages:
        queue.put_nowait(slug)
    return {"pages": len(_pages)}


class LaunchIn(BaseModel):
    project: str
    request: str
    skill: str = launch.SKILLS[0]
    worktree: str = ""


@app.get("/api/skills")
def skills() -> list[str]:
    return list(launch.SKILLS)


@app.post("/api/launch")
def launch_session(body: LaunchIn) -> dict[str, str]:
    """Start a new agent session in a project: a terminal window opens there and starts
    Claude Code on the skill; the session shows in the page once the agent opens it."""
    try:
        line = launch.command(body.skill, body.request, body.worktree)
        launch.open_terminal(body.project, line)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"command": line}


@app.get("/api/s/{slug}")
def state(slug: str) -> dict[str, Any]:
    s = get_session(slug)
    try:
        plan = s.read_plan()
        sections = s.read_sections()
        html_sections = s.html_sections()
        audit = s.read_audit()
        comments = s.read_comments()
        status = s.shown_status()
        activity = s.last_activity()
        batch = s.batch_progress()
        changes = s.read_changes()
        implemented = s.implemented_through()
        unimplemented = [d["id"] for d in s.unimplemented_changes()]
        questions = s.read_questions()
        grilling = s.is_grilling()
        seen = s.read_seen(sections)
        published = published_view(s)
    except SessionError as e:
        raise HTTPException(422, str(e)) from e
    # The hover text of a term: its developed `tip` when the agent wrote one, else the
    # one-line definition. Rendered here so it can carry emphasis, code and maths.
    for t in plan["lexicon"]:
        t["tip_html"] = md.renderInline(str(t.get("tip") or t.get("definition") or ""))
    return {
        "slug": slug,
        "plan": plan,
        "listening": s.is_listening(),
        "workflow": plan.get("workflow", ""),
        "status": status,
        "sections": {
            k: section_view(v, seen[k], html=k in html_sections) for k, v in sections.items()
        },
        # What the banner adds to the status: the last session file the agent wrote, and
        # where the last batch sent stands.
        "activity": activity,
        "batch": batch,
        "audit": audit,
        "comments": comments,
        "changes": changes,
        # How far the code carries the model in a branch review: the last change an
        # implementer took into account, and the changes logged after it.
        "implemented": implemented,
        "unimplemented": unimplemented,
        "questions": questions,
        "grilling": grilling,
        "verdicts": VERDICTS.get(plan.get("workflow") or LEGACY_WORKFLOW, []),
        "published": published,
    }


def published_view(s: Session) -> dict[str, Any] | None:
    """The publish record as the page reads it: {url, at, out_of_date}, None when the
    session is not published."""
    record = s.read_published()
    if not record:
        return None
    return {"url": record.get("url"), "at": record.get("at"), "out_of_date": s.is_out_of_date()}


def section_view(text: str, seen: str, html: bool = False) -> dict[str, Any]:
    """A section as the page renders it. An updated section (its text differs from its
    highlight baseline, the text at the last batch or « mark read ») also carries the
    HTML of the baseline, which the page diffs against to highlight what changed.

    An HTML section is drawn in a section frame, which loads its file from the server
    (`section_document`): its view carries no rendered HTML but `version`, a hash of its
    text, so the page reloads the frame only when the file changed. An updated one
    carries its baseline file as `seen`: the page compares the visible text of both and
    sends the frame the passages added (the changes frame message)."""
    if html:
        version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        view = {"md": text, "kind": "html", "version": version, "updated": text != seen}
        if view["updated"]:
            view["seen"] = seen
        return view
    view: dict[str, Any] = {"md": text, "html": md.render(text), "updated": text != seen}
    if view["updated"]:
        view["seen_html"] = md.render(seen)
    return view


# The head the page writes into an HTML section: its theme tokens, then frame.js.
FRAME_HEAD = (
    '<link rel="stylesheet" href="/frame/tokens.css"><script src="/static/frame.js"></script>'
)


# Sent with a section frame's document and its media files: the frame's sandbox flags as
# a header, so the browser gives them an origin of their own wherever they are opened
# (a new tab, their address), not only inside the page's <iframe>.
FRAME_SANDBOX_HEADER = {"Content-Security-Policy": f"sandbox {frame.SANDBOX}"}


@app.get("/frame/tokens.css")
def frame_tokens() -> Response:
    """The theme tokens of a section frame (frame.py)."""
    return Response(frame.tokens_css(), media_type="text/css")


@app.get("/s/{slug}/sections/{name}")
def section_document(slug: str, name: str) -> HTMLResponse:
    """The document a section frame loads: the HTML section's file, with the frame's head
    (frame.py) written in. Its relative addresses resolve against /s/<slug>/sections/."""
    s = get_session(slug)
    sid = name.removesuffix(".html")
    if not name.endswith(".html") or sid not in s.html_sections():
        raise HTTPException(404, f"no HTML section {name!r}")
    text = s.section_files()[sid].read_text(encoding="utf-8")
    return HTMLResponse(
        frame.inject(text, FRAME_HEAD),
        headers={"Cache-Control": "no-store", **FRAME_SANDBOX_HEADER},
    )


class SeenIn(BaseModel):
    sections: dict[str, str]


@app.post("/api/s/{slug}/seen")
def mark_seen(slug: str, body: SeenIn) -> dict[str, bool]:
    """Mark sections as read (set their highlight baseline): the body carries the
    markdown the page showed, so a rewrite that arrived meanwhile stays highlighted."""
    get_session(slug).mark_seen(body.sections)
    return {"ok": True}


@app.get("/api/s/{slug}/events")
async def events(slug: str, request: Request) -> StreamingResponse:
    s = get_session(slug)

    async def stream():
        last, last_threads = s.signature(), s.thread_signature()
        listening = s.is_listening()
        yield "event: hello\ndata: {}\n\n"
        ticks = 0
        while not await request.is_disconnected():
            await asyncio.sleep(0.4)
            sig, sig_threads = s.signature(), s.thread_signature()
            if sig != last:
                last = sig
                yield "event: changed\ndata: {}\n\n"
            if sig_threads != last_threads:
                last_threads = sig_threads
                yield "event: threads\ndata: {}\n\n"
            # A heartbeat goes stale without any file changing: compare with the clock.
            if s.is_listening() != listening:
                listening = not listening
                yield f"event: listening\ndata: {json.dumps({'listening': listening})}\n\n"
            ticks += 1
            if ticks % 40 == 0:
                yield ": ping\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


class CommentIn(BaseModel):
    section: str = ""
    quote: str = ""
    prefix: str = ""
    text: str = ""
    thread: str = ""


class BatchIn(BaseModel):
    comments: list[CommentIn] = []
    note: str = ""
    action: str = ""


@app.post("/api/s/{slug}/batch")
def send_batch(slug: str, body: BatchIn) -> dict[str, Any]:
    s = get_session(slug)
    try:
        return s.add_batch([c.model_dump() for c in body.comments], body.note, body.action)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


class AnswerIn(BaseModel):
    choices: list[str] = []
    text: str = ""


@app.post("/api/s/{slug}/questions/{qid}/answer")
def answer_question(slug: str, qid: str, body: AnswerIn) -> dict[str, Any]:
    """Answer an agent question: sent to the session at once, as an answer batch."""
    s = get_session(slug)
    try:
        return s.answer_question(qid, body.choices, body.text)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/s/{slug}/questions/{qid}/skip")
def skip_question(slug: str, qid: str) -> dict[str, Any]:
    """Skip an agent question: sent to the session at once, as an answer batch."""
    s = get_session(slug)
    try:
        return s.skip_question(qid)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


class UnclearIn(BaseModel):
    note: str = ""


@app.post("/api/s/{slug}/questions/{qid}/unclear")
def unclear_question(slug: str, qid: str, body: UnclearIn) -> dict[str, Any]:
    """« I don't understand » an agent question: sent to the session at once, as an answer
    batch; the question is deferred until the agent asks it again."""
    s = get_session(slug)
    try:
        return s.unclear_question(qid, body.note)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


class ThreadIn(BaseModel):
    section: str = ""
    quote: str = ""
    prefix: str = ""
    text: str


class MessageIn(BaseModel):
    text: str


def thread_view(s: Session, t: dict[str, Any]) -> dict[str, Any]:
    t = threads.view(s, t)
    messages = [{**m, "html": md.render(m["text"])} for m in t["messages"]]
    return {**t, "messages": messages}


@app.get("/api/s/{slug}/threads")
def list_threads(slug: str) -> dict[str, Any]:
    s = get_session(slug)
    try:
        rows = [thread_view(s, t) for t in s.read_threads()]
        # A coordinated session's threads start from the folder: they need no fork.
        return {"forkable": bool(s.fork_parent()) or s.coordinated, "threads": rows}
    except SessionError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/s/{slug}/threads")
def new_thread(slug: str, body: ThreadIn) -> dict[str, Any]:
    s = get_session(slug)
    try:
        return thread_view(s, threads.create(s, body.section, body.quote, body.prefix, body.text))
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/s/{slug}/threads/{tid}")
def thread_message(slug: str, tid: str, body: MessageIn) -> dict[str, Any]:
    s = get_session(slug)
    try:
        return thread_view(s, threads.send(s, tid, body.text))
    except threads.ThreadBusy as e:
        raise HTTPException(409, str(e)) from e
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/s/{slug}/threads/{tid}")
def thread_delete(slug: str, tid: str) -> dict[str, bool]:
    s = get_session(slug)
    try:
        threads.delete(s, tid)
    except threads.ThreadBusy as e:
        raise HTTPException(409, str(e)) from e
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@app.post("/api/s/{slug}/threads/{tid}/stop")
def thread_stop(slug: str, tid: str) -> dict[str, bool]:
    threads.stop(get_session(slug), tid)
    return {"ok": True}


@app.get("/s/{slug}/sections/{sid}/{path:path}")
def section_media(slug: str, sid: str, path: str) -> FileResponse:
    """A file of an HTML section's media folder, sections/<id>/: the media the agent
    produced for it, which the section loads by a relative address."""
    s = get_session(slug)
    folder = s.media_folder(sid).resolve()
    file = (folder / path).resolve()
    if sid not in s.html_sections() or not file.is_relative_to(folder) or not file.is_file():
        raise HTTPException(404, f"no media file {sid}/{path}")
    return FileResponse(file, headers=FRAME_SANDBOX_HEADER)


@app.post("/api/s/{slug}/export")
def export(slug: str) -> dict[str, str]:
    path = get_session(slug).export()
    return {"path": str(path), "name": path.name}


# Sync handlers: FastAPI runs them in a threadpool, and publishing runs git and gh.
@app.post("/api/s/{slug}/publish")
def publish_session(slug: str) -> dict[str, str]:
    s = get_session(slug)
    try:
        url = publish.publish(s)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"url": url}


@app.post("/api/s/{slug}/unpublish")
def unpublish_session(slug: str) -> dict[str, bool]:
    s = get_session(slug)
    try:
        publish.unpublish(s)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


def run(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
