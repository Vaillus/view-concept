"""Side threads: headless agent conversations the user opens from the page.

A thread discusses a passage without changing anything. On an agent that can fork its
conversation (Claude Code, Codex), its first turn forks the main session, so it starts
knowing the whole conversation so far while the main session stays untouched; every later
turn resumes the thread's own session. On any other agent (a program that answers a prompt
on stdin, such as `jazz run`) every turn restates where the explanation is and what the
thread has said. Each turn is one process, run by the server in a background Python thread;
its reply streams into threads/<id>.json, which the server's event stream watches like the
other session files. `agents.py` holds what differs between agents.

Threads are read-only, whatever the agent: its read-only tool set or sandbox, no approvals
asked. A change the discussion leads to goes to the main session as a comment of the next
batch (the comment carries the thread id).
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .agents import Backend, TurnState, resolve
from .store import Session, SessionError, now_iso

FLUSH_EVERY = 0.25  # seconds between writes of a streaming reply

# (session dir, thread id) -> the running process. A thread whose file says "running"
# but has no entry here was cut off by a server restart.
_running: dict[tuple[str, str], subprocess.Popen] = {}
_stopping: set[tuple[str, str]] = set()  # stopped from the page: not an error
_lock = threading.Lock()


class ThreadBusy(SessionError):
    pass


def is_running(s: Session, tid: str) -> bool:
    return (str(s.dir), tid) in _running


def view(s: Session, thread: dict[str, Any]) -> dict[str, Any]:
    """The thread as the page shows it: one left "running" by a previous server process
    reads as an "interrupted" error."""
    if thread["state"] == "running" and not is_running(s, thread["id"]):
        return {**thread, "state": "error", "activity": "", "error": "interrupted"}
    return thread


def create(s: Session, section: str, quote: str, prefix: str, text: str) -> dict[str, Any]:
    if not text.strip():
        raise SessionError("empty message")
    with _lock:
        thread = s.new_thread(section, quote, prefix)
    return send(s, thread["id"], text)


def send(s: Session, tid: str, text: str) -> dict[str, Any]:
    """Add the user's message and start the turn that answers it."""
    text = text.strip()
    if not text:
        raise SessionError("empty message")
    with _lock:
        if is_running(s, tid):
            raise ThreadBusy(f"{tid} is still answering")
        thread = s.read_thread(tid)
        try:
            backend = resolve(s)
        except ValueError as e:
            raise SessionError(str(e)) from e
        first = not thread["agent_session"]
        args = backend.args(s, thread)
        prompt = backend.prompt(thread, _briefing(s, thread, backend), text)
        thread["messages"] += [
            {"role": "user", "text": text, "at": now_iso()},
            {"role": "assistant", "text": "", "at": now_iso()},
        ]
        if first and backend.forks:
            thread["forked_from"] = s.read_parent()
        try:
            proc = subprocess.Popen(
                args,
                cwd=_cwd(s),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as e:
            thread.update(state="error", activity="", error=f"could not start {args[0]}: {e}")
            s.write_thread(thread)
            return thread
        _running[(str(s.dir), tid)] = proc
        thread.update(state="running", activity="starting", error="")
        s.write_thread(thread)
    threading.Thread(target=_run, args=(s, thread, backend, proc, prompt), daemon=True).start()
    return thread


def stop(s: Session, tid: str) -> None:
    proc = _running.get((str(s.dir), tid))
    if proc:
        _stopping.add((str(s.dir), tid))
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()


def delete(s: Session, tid: str) -> None:
    with _lock:
        if is_running(s, tid):
            raise ThreadBusy(f"{tid} is still answering")
        s.delete_thread(tid)


def _cwd(s: Session) -> Path:
    """The repo of a code session (the thread may read it), else the session dir."""
    repo = Path(s.read_plan().get("repo", "") or s.dir)
    return repo if repo.is_dir() else s.dir


def _briefing(s: Session, thread: dict[str, Any], backend: Backend) -> str:
    outline = s.read_plan()["outline"]
    number = {sec["id"]: i + 1 for i, sec in enumerate(outline)}
    titles = {sec["id"]: sec.get("title", sec["id"]) for sec in outline}
    sec = thread["section"]
    if sec:
        where = f"§{number.get(sec, '?')} {titles.get(sec, sec)} ({sec})"
        anchor = f"{where}: « {thread['quote']} »" if thread["quote"] else f"the whole of {where}"
    else:
        anchor = "none (a general question about the explanation)"
    if backend.forks and s.read_parent():
        origin = (
            "It is a separate conversation forked from the main one: you know everything said"
            " so far, but the main session will not see what is said here."
        )
    else:
        origin = (
            "There is no main conversation to start from: read plan.json and sections/ in"
            " the session directory to know the explanation."
        )
    return "\n".join(
        [
            f"[view-concept side thread {thread['id']}]",
            f"The user opened a side thread from the view-concept page of the session"
            f" {s.slug!r} ({s.dir}). {origin}",
            "- Answer and discuss. Your tools are read-only: do not try to edit files or"
            " run view-concept commands, and do not resolve comments.",
            "- This is a conversation, not the explanation: the formats of the skills loaded"
            " above (sections, lexicon, tables) do not apply here. Answer in a few sentences"
            " of plain prose, without tables, headings or bullet lists unless the user asks"
            " for them.",
            "- Answer the question asked, and only that one. When it opens a larger point,"
            " name it in one sentence and let the user decide whether to go there.",
            f"- The explanation may have changed since this conversation started: the"
            f" current text of a section is in {s.sections_dir}/<id>.md.",
            "- When the discussion leads to a change (to the explanation or to the code),"
            " say so plainly. The user sends it to the main session from the page.",
            f"Passage: {anchor}",
        ]
    )


def _run(
    s: Session, thread: dict[str, Any], backend: Backend, proc: subprocess.Popen, prompt: str
) -> None:
    key = (str(s.dir), thread["id"])
    reply = thread["messages"][-1]
    turn = TurnState()
    last_flush = 0.0
    try:
        assert proc.stdin and proc.stdout
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except BrokenPipeError:
            turn.noise.append("the agent closed its input before reading the prompt")
        for line in proc.stdout:
            changed = backend.feed(line, thread, reply, turn)
            if changed and time.monotonic() - last_flush > FLUSH_EVERY:
                s.write_thread(thread)
                last_flush = time.monotonic()
        code = proc.wait()
        backend.close(thread, reply, turn, code)
    finally:
        with _lock:
            # an agent exits 143 on SIGTERM: the exit code alone can't tell a stop from a crash
            if key in _stopping:
                _stopping.discard(key)
                thread.update(state="idle", error="")
                reply["stopped"] = True
            elif turn.failed or not turn.finished:
                detail = turn.error or "\n".join(turn.noise[-5:])
                thread.update(state="error", error=detail or f"exit code {proc.returncode}")
            else:
                thread.update(state="idle", error="")
                if not reply["text"].strip():
                    reply["text"] = turn.final_text
            thread["activity"] = ""
            s.write_thread(thread)
            # Only once the final state is on disk: a reader that sees the thread no longer
            # running must also read its final state, not "running" (shown as interrupted).
            _running.pop(key, None)
