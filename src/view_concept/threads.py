"""Side threads: headless agent conversations the user opens from the page.

A thread discusses a passage without changing anything. On an agent that can fork its
conversation (Claude Code, Codex), its first turn forks the main session, so it starts
knowing the whole conversation so far while the main session stays untouched; every later
turn resumes the thread's own session. In a coordinated session (build-feature) the main
session only coordinates subagents, so a thread never forks it: its first turn carries the
context a subagent gets (`view-concept context --role thread`), and later turns resume the
thread's own session as usual. On any other agent (a program that answers a prompt
on stdin, such as `jazz run`) every turn restates where the explanation is and what the
thread has said. Each turn is one process, run by the server in a background Python thread;
its reply streams into threads/<id>.json, which the server's event stream watches like the
other session files. `agents.py` holds what differs between agents.

A thread opened on a doc of the Doc tab (section `doc:<path>`) gets that doc's text, read
from the worktree, in place of a section; one on the doc set list (`doc:` alone) gets the doc
set. One opened on a pin's box (section `pin:<id>`) is told the pin's kind and sentence,
and gets the scoping section; its conclusion, sent with « → batch », reaches the scoper as
a comment attached to that pin.

A thread opened on an agent question (`question`) helps the user understand it before
answering it from its box. Its « use as answer » turn (`draft`) asks for the answer, which
the server keeps as the reply's `draft` ({choices, text}); the page fills the question's
box with it. On Claude the turn is held to a JSON schema whose choices can only be the
question's options; another agent writes the answer in a fixed text form, read back here.
The answer the user sends names the question's threads.

Threads are read-only, whatever the agent: its read-only tool set or sandbox, no approvals
asked. Read-only still reaches far: on Claude a thread reads any file, searches and reads
the web, and runs the shell commands that only read (git history, the view-concept
commands that print). A change the discussion leads to goes to the main session as a
comment of the next batch (the comment carries the thread id).
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .agents import Backend, TurnState, resolve
from .context import build, doc_passage
from .store import (
    DOC_KEY,
    DOC_SET_ANCHOR,
    MOVES_KEY,
    TRIAGE_KEY,
    Session,
    SessionError,
    now_iso,
    now_iso_ms,
    pin_anchor,
)

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


def create(
    s: Session,
    section: str,
    quote: str,
    prefix: str,
    text: str,
    question: str = "",
    fact: str = "",
) -> dict[str, Any]:
    """Open a side thread on a passage (`fact`: the id of the missing fact it quotes), an
    agent question or nothing, and start the turn that answers its first message."""
    if not text.strip():
        raise SessionError("empty message")
    with _lock:
        thread = s.new_thread(section, quote, prefix, question, fact)
    return send(s, thread["id"], text)


def send(s: Session, tid: str, text: str, draft: bool = False) -> dict[str, Any]:
    """Add the user's message and start the turn that answers it. A `draft` turn, on a
    thread opened on an open agent question, asks for the user's answer to it instead."""
    with _lock:
        if is_running(s, tid):
            raise ThreadBusy(f"{tid} is still answering")
        thread = s.read_thread(tid)
        question = _draft_question(s, thread) if draft else None
        text = f"Draft my answer to {question['id']}" if question else text.strip()
        if not text:
            raise SessionError("empty message")
        try:
            backend = resolve(s)
        except ValueError as e:
            raise SessionError(str(e)) from e
        first = not thread["agent_session"]
        args = backend.args(s, thread)
        if question and backend.structured:
            args += backend.schema_args(_draft_schema(question))
        asked = _draft_request(question, backend.structured) if question else text
        prompt = backend.prompt(thread, _briefing(s, thread, backend), asked)
        thread["messages"] += [
            {"role": "user", "text": text, "at": now_iso(), **({"draft": True} if draft else {})},
            {"role": "assistant", "text": "", "at": now_iso()},
        ]
        if first and backend.forks:
            thread["forked_from"] = s.fork_parent()
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
    args = (s, thread, backend, proc, prompt, question)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return thread


def _draft_question(s: Session, thread: dict[str, Any]) -> dict[str, Any]:
    """The open agent question a « use as answer » turn drafts the answer to."""
    qid = thread.get("question", "")
    if not qid:
        raise SessionError(f"{thread['id']} is not about an agent question")
    q = next((q for q in s.read_questions() if q["id"] == qid), None)
    if not q or q["status"] != "open":
        raise SessionError(f"{qid} is no longer open")
    return q


def _draft_schema(q: dict[str, Any]) -> dict[str, Any]:
    """The JSON schema of a structured « use as answer » turn: only the question's options
    can be chosen, one unless it takes several."""
    choices: dict[str, Any] = {"type": "array", "items": {"type": "string", "enum": q["options"]}}
    if not q["options"]:
        choices = {"type": "array", "maxItems": 0}
    elif not q.get("multi"):
        choices["maxItems"] = 1
    return {
        "type": "object",
        "properties": {"choices": choices, "text": {"type": "string"}},
        "required": ["choices", "text"],
        "additionalProperties": False,
    }


def _draft_request(q: dict[str, Any], structured: bool) -> str:
    """The message of a « use as answer » turn: the answer the discussion leads to, held
    to `_draft_schema` on a structured backend, else in a form `_read_draft` reads back."""
    ask = (
        f"Write my answer to {q['id']} as this discussion leads me to give it, in my voice,"
        " to the agent who asked."
    )
    if structured:
        return (
            f"{ask} `choices`: the option(s) it picks, none when no option fits. `text`: one"
            " or two sentences, what I want and why, or what the chosen option leaves out;"
            " empty when the option says it all."
        )
    options = (
        "On one line each, the option(s) it picks, copied exactly from the list, as"
        f" « choice: <option> »{' (several allowed)' if q.get('multi') else ''}; none when"
        " no option fits. Options: " + " | ".join(q["options"]) + "\n"
        if q["options"]
        else ""
    )
    return (
        f"{ask} Reply with these lines only, no other text:\n"
        f"{options}"
        "Then one line « answer: <one or two sentences> »: what I want and why, or what the"
        " chosen option leaves out. Write « answer: » with nothing after it when the option"
        " says it all."
    )


def _read_draft(text: str, q: dict[str, Any]) -> dict[str, Any]:
    """The answer a « use as answer » reply drafts: the options it names (only real ones,
    one unless the question takes several) and its text."""
    choices: list[str] = []
    answer: list[str] = []
    for line in text.splitlines():
        key, _, value = line.strip().strip("*`").partition(":")
        value = value.strip().strip("*`").strip()
        if key.strip().lower() == "choice" and value in q["options"] and value not in choices:
            choices.append(value)
        elif key.strip().lower() == "answer":
            answer.append(value)
        elif answer and line.strip():
            answer.append(line.strip())
    if not q.get("multi"):
        choices = choices[:1]
    return {"choices": choices, "text": " ".join(a for a in answer if a)}


def _structured_draft(answer: Any, q: dict[str, Any]) -> dict[str, Any]:
    """The answer a structured « use as answer » turn returned, checked against the
    question all the same."""
    answer = answer if isinstance(answer, dict) else {}
    raw = answer.get("choices")
    choices = [c for c in dict.fromkeys(raw if isinstance(raw, list) else []) if c in q["options"]]
    if not q.get("multi"):
        choices = choices[:1]
    return {"choices": choices, "text": str(answer.get("text", "")).strip()}


def _draft_text(draft: dict[str, Any]) -> str:
    """A drafted answer as the thread shows it."""
    lines = [f"**Choice:** {', '.join(draft['choices'])}"] if draft["choices"] else []
    return "\n\n".join(lines + ([draft["text"]] if draft["text"] else []))


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


def _vocabulary(lexicon: list[dict[str, Any]], number: dict[str, int], upto: int | None) -> str:
    """The lexicon terms the user has read when they reach the passage: those whose home
    section is at or before the passage's (every term for a question with no passage)."""
    known = [
        t
        for t in lexicon
        if t.get("term") and (upto is None or number.get(t.get("section", ""), upto + 1) <= upto)
    ]
    if not known:
        return ""
    terms = "; ".join(f"{t['term']} ({t.get('definition', '')})" for t in known)
    read = "the whole document" if upto is None else f"the document up to section {upto}"
    later = (
        ""
        if upto is None
        else " A term introduced after it is new to the user: say the idea"
        " in plain words, or define the term in one clause."
    )
    return (
        f"- Vocabulary: the user has read {read}. Use these terms as the lexicon defines"
        f" them, and no other technical term without defining it: {terms}.{later}"
    )


def _briefing(s: Session, thread: dict[str, Any], backend: Backend) -> str:
    plan = s.read_plan()
    outline = plan["outline"]
    number = {sec["id"]: i + 1 for i, sec in enumerate(outline)}
    titles = {sec["id"]: sec.get("title", sec["id"]) for sec in outline}
    reviews = ("build-feature", "triage-code", "review-docs")
    doc = "review" if plan.get("workflow") in reviews else "explanation"
    sec = thread["section"]
    qid = thread.get("question", "")
    on_doc = sec.startswith(DOC_KEY)  # a doc, or the doc set (DOC_SET_ANCHOR)
    if qid:
        anchor = _question_anchor(s, qid, number, titles)
    elif sec:
        if sec == DOC_SET_ANCHOR:
            where = "the doc set (the list of repo docs the Doc tab shows)"
        elif sec.startswith(DOC_KEY):
            where = f"the doc {sec.removeprefix(DOC_KEY)} (a file of the repository)"
        elif sec.startswith(TRIAGE_KEY):
            where = f"row {sec.removeprefix(TRIAGE_KEY)} of the concept triage (the Doc tab)"
        elif pid := pin_anchor(sec):
            pin = next((p for p in s.read_pins() if p["id"] == pid), None)
            kind = pin["kind"] if pin else "pin"
            said = f" « {pin['text']} »" if pin else ""
            where = f"the {kind} {pid}{said}, an open point of the drawing (the scoping section)"
        elif sec.startswith(MOVES_KEY):
            row = sec.removeprefix(MOVES_KEY)
            readme = s.move_readmes().get(row, "a README")
            where = f"row {row} of the move plan of {readme} (the Doc tab)"
        else:
            where = f"§{number.get(sec, '?')} {titles.get(sec, sec)} ({sec})"
        anchor = f"{where}: « {thread['quote']} »" if thread["quote"] else f"the whole of {where}"
    else:
        anchor = f"none (a general question about the {doc})"
    if s.coordinated:
        origin = (
            "The main session only coordinates subagents, so this thread starts from the"
            " session folder: the context below is where the feature stands now."
        )
    elif backend.forks and s.read_parent():
        origin = (
            "It is a separate conversation forked from the main one: you know everything said"
            " so far, but the main session will not see what is said here."
        )
    else:
        origin = (
            "There is no main conversation to start from: read plan.json and sections/ in"
            f" the session directory to know the {doc}."
        )
    lines = [
        f"[view-concept side thread {thread['id']}]",
        f"The user opened a side thread from the view-concept page of the session"
        f" {s.slug!r} ({s.dir}). {origin}",
        "- Answer and discuss. Your tools are read-only: you may read any file, search"
        " the web, read git history (log, show, diff, blame) and run the view-concept"
        " commands that print (context, changes, pending, list), but do not try to"
        " edit files or run other commands, and do not resolve comments.",
        f"- This is a conversation, not a section of the {doc}: answer in a few sentences"
        " of plain prose, without tables, headings or bullet lists unless the user asks"
        " for them.",
        _question_rule(qid, doc),
        "- Answer the question asked, and only that one. When it opens a larger point,"
        " name it in one sentence and let the user decide whether to go there.",
        f"- The {doc} may have changed since this conversation started: the"
        f" current text of a section is in {s.sections_dir}/<id>.md, or <id>.html for"
        " an HTML section.",
        f"- When the discussion leads to a change (to the {doc} or to the code),"
        " say so plainly. The user sends it to the main session from the page.",
        "- A doc of the Doc tab is a file of the repository: its current text is that file."
        if on_doc
        else "",
        _vocabulary(plan["lexicon"], number, number.get(sec) if sec else None),
        f"Passage: {anchor}",
    ]
    lines = [line for line in lines if line]
    if s.coordinated:
        lines += [
            "",
            build(s, "thread", ["the user's message below, about the passage above"], sec),
        ]
    elif on_doc and not qid:
        # A doc is not in the session folder: the thread gets it here, read from the worktree.
        lines += ["", *doc_passage(s, sec)]
    return "\n".join(lines)


def _question_anchor(s: Session, qid: str, number: dict[str, int], titles: dict[str, str]) -> str:
    """The agent question a thread was opened on, as its box shows it to the user."""
    q = next((q for q in s.read_questions() if q["id"] == qid), None)
    if not q:
        return f"the agent question {qid}"
    lines = [f"the agent question {qid}: « {q['text']} »"]
    if q.get("section"):
        sec = q["section"]
        lines.append(f"  asked about §{number.get(sec, '?')} {titles.get(sec, sec)} ({sec})")
    if q["options"]:
        several = " (several allowed)" if q.get("multi") else ""
        lines.append(f"  options{several}: " + " | ".join(q["options"]))
    if q.get("recommended"):
        lines.append(f"  recommended: {q['recommended']}")
    if q.get("background"):
        lines.append(f"  background: {' '.join(q['background'].split())}")
    return "\n".join(lines)


def _question_rule(qid: str, doc: str) -> str:
    if not qid:
        return ""
    return (
        f"- The user opened this thread on the agent question {qid}, below, to understand it"
        " before answering it. Explain what it asks, what each option would change and what"
        f" the {doc} says about it; give your view when asked. The user answers from the"
        " question's box, and the answer reaches the main session with this thread."
    )


def _run(
    s: Session,
    thread: dict[str, Any],
    backend: Backend,
    proc: subprocess.Popen,
    prompt: str,
    question: dict[str, Any] | None = None,
) -> None:
    """Stream the turn's reply into the thread. The reply keeps its turn's start (`at`)
    and gains `first_text`, when its first words reached the page, and `ended`, when the
    turn ended: a turn's timing, for the run metrics."""
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
            if reply["text"] and "first_text" not in reply:
                reply["first_text"] = now_iso_ms()
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
                if question and turn.structured is not None:
                    reply["draft"] = _structured_draft(turn.structured, question)
                    reply["text"] = _draft_text(reply["draft"])
                elif question:
                    reply["draft"] = _read_draft(reply["text"], question)
            reply["ended"] = now_iso_ms()
            if reply["text"] and "first_text" not in reply:
                reply["first_text"] = reply["ended"]
            thread["activity"] = ""
            s.write_thread(thread)
            # Only once the final state is on disk: a reader that sees the thread no longer
            # running must also read its final state, not "running" (shown as interrupted).
            _running.pop(key, None)
