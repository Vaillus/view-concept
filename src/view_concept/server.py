"""The local web server: serves the page, streams file changes, receives comment batches,
runs side threads."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pydantic import BaseModel

from . import threads
from .store import Session, SessionError, list_sessions

STATIC = Path(__file__).parent / "static"
# The verdicts an item can get, by session workflow, each list in the review table's order:
# {key, meaning, tone, sends_to?}. The view-branch and view-refactor skills read the same file.
VERDICTS: dict[str, list[dict[str, str]]] = yaml.safe_load(
    (Path(__file__).parent / "verdicts.yaml").read_text(encoding="utf-8")
)
# A session created before workflows existed was a branch review or had no items.
LEGACY_WORKFLOW = "view-branch"

md = (
    MarkdownIt("commonmark", {"html": True})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, double_inline=True)
)

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


@app.get("/api/s/{slug}")
def state(slug: str) -> dict[str, Any]:
    s = get_session(slug)
    try:
        plan = s.read_plan()
        sections = s.read_sections()
        audit = s.read_audit()
        comments = s.read_comments()
        status = s.read_status()
        changes = s.read_changes()
        questions = s.read_questions()
        seen = s.read_seen(sections)
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
        "sections": {k: section_view(v, seen[k]) for k, v in sections.items()},
        "audit": audit,
        "comments": comments,
        "changes": changes,
        "questions": questions,
        "verdicts": VERDICTS.get(plan.get("workflow") or LEGACY_WORKFLOW, []),
    }


def section_view(text: str, seen: str) -> dict[str, Any]:
    """A section as the page renders it. An updated section (its text differs from its
    highlight baseline, the text at the last batch or « mark read ») also carries the
    HTML of the baseline, which the page diffs against to highlight what changed."""
    view: dict[str, Any] = {"md": text, "html": md.render(text), "updated": text != seen}
    if view["updated"]:
        view["seen_html"] = md.render(seen)
    return view


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
        return {"forkable": bool(s.read_parent()), "threads": rows}
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


@app.post("/api/s/{slug}/export")
def export(slug: str) -> dict[str, str]:
    path = get_session(slug).export()
    return {"path": str(path), "name": path.name}


def run(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
