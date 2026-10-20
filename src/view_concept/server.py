"""The local web server: serves the page, streams file changes, receives comment batches,
runs side threads."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import frame, gate, launch, metrics, publish, push, threads
from .render import md
from .store import DOC_KEY, Session, SessionError, list_sessions

STATIC = Path(__file__).parent / "static"
# The verdicts an item can get, by session workflow, each list in the review table's order:
# {key, meaning, tone, sends_to?}. The view-branch and view-refactor skills read the same file.
VERDICTS: dict[str, list[dict[str, str]]] = yaml.safe_load(
    (Path(__file__).parent / "verdicts.yaml").read_text(encoding="utf-8")
)
# A session created before workflows existed was a branch review or had no items.
LEGACY_WORKFLOW = "view-branch"

# How often the server looks for sessions that started waiting for the user (push.py).
NOTICE_EVERY = 5.0


async def _notice_loop() -> None:
    while True:
        await asyncio.sleep(NOTICE_EVERY)
        try:
            await asyncio.to_thread(push.check_and_send)
        except Exception as e:  # a bad session file or the network: try again next time
            print(f"view-concept: notices: {e}", file=sys.stderr)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_notice_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="view-concept", lifespan=lifespan)
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


# The home-screen app: the page added to a phone's home screen opens from its own icon,
# full screen (no address bar, no toolbar), on the home page and its list of sessions.
# No offline copy: away from the server, the phone shows its own page for a site it
# cannot reach. The icon is « vc » in the accent colour on the default theme's background.
MANIFEST = {
    "name": "view-concept",
    "short_name": "view-concept",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#1a1b26",
    "theme_color": "#1a1b26",
    "icons": [
        {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}


@app.get("/manifest.webmanifest")
def manifest() -> Response:
    return Response(json.dumps(MANIFEST), media_type="application/manifest+json")


# ---- the notice when the agent is done (push.py) ----


@app.get("/sw.js")
def service_worker() -> FileResponse:
    """The home-screen app's service worker: it receives the notices while the app is
    closed. Served from the root, so it covers every page."""
    return FileResponse(
        STATIC / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/api/push/key")
def push_key() -> dict[str, str]:
    try:
        return {"key": push.public_key()}
    except push.PushError as e:
        raise HTTPException(503, str(e)) from e


class UnsubscribeIn(BaseModel):
    endpoint: str


@app.post("/api/push/subscribe")
def push_subscribe(body: dict[str, Any]) -> dict[str, bool]:
    """Turn notices on for a phone: keep its subscription."""
    try:
        push.subscribe(body)
    except push.PushError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: UnsubscribeIn) -> dict[str, bool]:
    push.unsubscribe(body.endpoint)
    return {"ok": True}


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
    list or the pending launches changed (the sidebar reloads them) and `focus` when a
    session should be shown."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    _pages.add(queue)

    def snapshot() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows = list_sessions()
        return rows, launch.pending(rows)

    async def stream():
        try:
            last = await asyncio.to_thread(snapshot)
            yield "event: hello\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    slug = await asyncio.wait_for(queue.get(), 2)
                    yield f"event: focus\ndata: {json.dumps({'slug': slug})}\n\n"
                except TimeoutError:
                    rows = await asyncio.to_thread(snapshot)
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
def launch_session(body: LaunchIn) -> dict[str, Any]:
    """Start a new agent session in a project: a terminal window opens there and starts
    Claude Code on the skill, in auto mode. From now until the agent opens the session,
    every page's sidebar shows it as a pending launch (launch.py)."""
    try:
        line = launch.command(body.skill, body.request, body.worktree)
        launch.open_terminal(body.project, line)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"command": line, "launch": launch.add_pending(body.project, body.request, body.skill)}


@app.get("/api/launches")
def launches() -> dict[str, Any]:
    """The pending launches, and after how many seconds one reads « not started »."""
    return {"launches": launch.pending(list_sessions()), "pending_for": launch.PENDING_FOR}


@app.delete("/api/launches/{lid}")
def drop_launch(lid: str) -> dict[str, bool]:
    """× on a pending launch: it leaves every page's sidebar."""
    launch.remove_pending(lid)
    return {"ok": True}


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
        docs = s.read_docs()
        doc_texts = {DOC_KEY + p: t for p, t in docs.items() if t is not None}
        seen = s.read_seen({**sections, **doc_texts})
        published = published_view(s)
        doc_tab = docs_view(s, docs, seen)
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
        # The Doc tab: the doc set and each doc read from the worktree.
        "docs": doc_tab,
    }


def docs_view(s: Session, docs: dict[str, str | None], seen: dict[str, str]) -> dict[str, Any]:
    """The Doc tab as the page reads it: {set: [{path, reason, stale (how many of its
    stale passages are shown)}], removed, views: {path: view}, stale (the stale passages
    shown), reference (the reference model, or None)}. A doc's view is its section view
    (the file rendered as Markdown, `updated` against its highlight baseline
    `doc:<path>`) with `exists` and the base mark's input: `base_html`, the doc at the
    merge base rendered (None when it was not there, or when git cannot tell), and `new`,
    whether the branch created it. A doc missing from the worktree is `{exists: false}`
    only."""
    data = s.read_doc_set()
    commit = s.merge_base() if any(t is not None for t in docs.values()) else ""
    views: dict[str, dict[str, Any]] = {}
    for path, text in docs.items():
        if text is None:
            views[path] = {"exists": False}
            continue
        base = s.base_text(path, commit) if commit else None
        views[path] = {
            "exists": True,
            **section_view(text, seen.get(DOC_KEY + path, text)),
            "base_html": md.render(base) if base is not None else None,
            "new": bool(commit) and base is None,
        }
    stale = [
        {k: f.get(k, "") for k in ("id", "doc", "quote", "section", "note")}
        for f in s.shown_stale(docs)
    ]
    return {
        "set": [
            {
                "path": d["path"],
                "reason": d.get("reason", ""),
                "stale": sum(f["doc"] == d["path"] for f in stale),
            }
            for d in data["docs"]
        ],
        "removed": data["removed"],
        "views": views,
        "stale": stale,
        "reference": reference_view(s),
    }


def reference_view(s: Session) -> dict[str, Any] | None:
    """The reference model as the page reads it: {slug, title, url (its session's page),
    lexicon (each term with its hover text rendered, `tip_html`)}; None without one."""
    ref = s.reference_model()
    if ref is None:
        return None
    lexicon = [
        {**t, "tip_html": md.renderInline(str(t.get("tip") or t.get("definition") or ""))}
        for t in ref["lexicon"]
    ]
    return {**ref, "url": f"/s/{ref['slug']}", "lexicon": lexicon}


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
        last_drafts = s.drafts_signature()
        listening = s.is_listening()
        yield "event: hello\ndata: {}\n\n"
        ticks = 0
        while not await request.is_disconnected():
            await asyncio.sleep(0.4)
            sig, sig_threads = s.signature(), s.thread_signature()
            if sig != last:
                last = sig
                yield "event: changed\ndata: {}\n\n"
            if (sig_drafts := s.drafts_signature()) != last_drafts:
                last_drafts = sig_drafts
                yield "event: drafts\ndata: {}\n\n"
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
    # « Write docs and create PR »: the doc pass, then the PR with no pause (write-docs only).
    then_pr: bool = False
    # The ids of the drafts the batch carries: once sent, they leave the drafts file.
    drafts: list[str] = []


@app.post("/api/s/{slug}/batch")
def send_batch(slug: str, body: BatchIn) -> dict[str, Any]:
    s = get_session(slug)
    try:
        comments = [c.model_dump() for c in body.comments]
        batch = s.add_batch(comments, body.note, body.action, then_pr=body.then_pr)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    s.clear_sent_drafts(body.drafts)
    return batch


# ---- the drafts file (store.py): what every page open on the session shows ----


class DraftIn(BaseModel):
    section: str = ""
    quote: str = ""
    prefix: str = ""
    text: str = ""
    thread: str = ""


class NoteIn(BaseModel):
    note: str = ""


class DraftsImportIn(BaseModel):
    drafts: list[dict[str, Any]] = []
    note: str = ""


@app.get("/api/s/{slug}/drafts")
def drafts(slug: str) -> dict[str, Any]:
    s = get_session(slug)
    try:
        data = s.read_drafts()
    except SessionError as e:
        raise HTTPException(422, str(e)) from e
    return {"drafts": data["drafts"], "note": data["note"]}


@app.put("/api/s/{slug}/drafts/{did}")
def save_draft(slug: str, did: str, body: DraftIn) -> dict[str, bool]:
    """Add or edit a draft: the last edit wins. `saved` is false when the draft was
    deleted meanwhile (on another page), and the edit is dropped."""
    s = get_session(slug)
    try:
        return {"saved": s.save_draft({**body.model_dump(), "id": did})}
    except SessionError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/s/{slug}/drafts/{did}")
def delete_draft(slug: str, did: str) -> dict[str, bool]:
    get_session(slug).delete_drafts([did])
    return {"ok": True}


@app.put("/api/s/{slug}/note")
def save_note(slug: str, body: NoteIn) -> dict[str, bool]:
    get_session(slug).save_note(body.note)
    return {"ok": True}


@app.post("/api/s/{slug}/drafts/import")
def import_drafts(slug: str, body: DraftsImportIn) -> dict[str, bool]:
    """Move the drafts and the note a browser kept before the drafts file."""
    s = get_session(slug)
    try:
        s.import_drafts(body.drafts, body.note)
    except SessionError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


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
    question: str = ""
    text: str


@app.get("/api/s/{slug}/metrics")
def session_metrics(slug: str) -> dict[str, Any]:
    """The metrics report of a branch review (the Metrics tab): its runs, waiting and
    quality signals, and every branch review of its repository by variant. 404 for a
    session of another workflow."""
    s = get_session(slug)
    try:
        if s.read_plan().get("workflow") != "view-branch":
            raise HTTPException(404, f"{slug!r} is not a branch review")
        return metrics.session_metrics(s)
    except SessionError as e:
        raise HTTPException(422, str(e)) from e


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
        t = threads.create(s, body.section, body.quote, body.prefix, body.text, body.question)
        return thread_view(s, t)
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


@app.post("/api/s/{slug}/threads/{tid}/draft")
def thread_draft(slug: str, tid: str) -> dict[str, Any]:
    """« use as answer »: a turn of a thread opened on an agent question that drafts the
    user's answer to it (the reply's `draft`), which the page puts in the question's box."""
    s = get_session(slug)
    try:
        return thread_view(s, threads.send(s, tid, "", draft=True))
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


@app.get("/s/{slug}/repo/{path:path}")
def repo_file(slug: str, path: str) -> FileResponse:
    """A file of the session's repo: the images and links a doc gives by a relative path,
    which the page resolves against the doc's folder. Nothing outside the repo, nothing of
    its .git folder."""
    file = get_session(slug).doc_file(path)
    if file is None or ".git" in Path(path).parts or not file.is_file():
        raise HTTPException(404, f"no repo file {path}")
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


def run(host: str, port: int, remote: int | None = None) -> None:
    """Serve the page on the local port `port` and, behind the tailnet gate, on the remote
    port `remote` (gate.py), both in this one process: a batch sent through either reaches
    the same sessions."""
    import uvicorn

    remote = gate.remote_port() if remote is None else remote
    if remote == port:
        raise SystemExit(f"VIEW_CONCEPT_REMOTE_PORT must differ from the local port ({port})")
    target = gate.TailnetGate(app, remote, gate.owner_login())
    config = uvicorn.Config(target, host=host, port=port, log_level="warning")
    sockets = [
        config.bind_socket(),
        uvicorn.Config(target, host=host, port=remote, log_level="warning").bind_socket(),
    ]
    uvicorn.Server(config).run(sockets=sockets)
