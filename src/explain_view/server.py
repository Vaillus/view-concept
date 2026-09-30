"""The local web server: serves the page, streams file changes, receives comment batches."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pydantic import BaseModel

from .store import Session, SessionError, list_sessions

HOST = "127.0.0.1"
PORT = int(os.environ.get("EXPLAIN_VIEW_PORT", "5080"))
STATIC = Path(__file__).parent / "static"

md = (
    MarkdownIt("commonmark", {"html": True})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, double_inline=True)
)

app = FastAPI(title="explain-view")
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
        decisions = s.read_decisions()
    except SessionError as e:
        raise HTTPException(422, str(e)) from e
    # The hover text of a term: its developed `tip` when Claude wrote one, else the
    # one-line definition. Rendered here so it can carry emphasis, code and maths.
    for t in plan["lexicon"]:
        t["tip_html"] = md.renderInline(str(t.get("tip") or t.get("definition") or ""))
    return {
        "slug": slug,
        "plan": plan,
        "status": status,
        "sections": {k: {"md": v, "html": md.render(v)} for k, v in sections.items()},
        "audit": audit,
        "comments": comments,
        "decisions": decisions,
    }


@app.get("/api/s/{slug}/events")
async def events(slug: str, request: Request) -> StreamingResponse:
    s = get_session(slug)

    async def stream():
        last = s.signature()
        yield "event: hello\ndata: {}\n\n"
        ticks = 0
        while not await request.is_disconnected():
            await asyncio.sleep(0.4)
            sig = s.signature()
            if sig != last:
                last = sig
                yield "event: changed\ndata: {}\n\n"
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
    text: str


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


@app.post("/api/s/{slug}/export")
def export(slug: str) -> dict[str, str]:
    path = get_session(slug).export()
    return {"path": str(path), "name": path.name}


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
