"""The context a subagent of a coordinated session starts from.

In a coordinated session (the view-branch workflow) the main session only coordinates:
the work is done by subagents, each started fresh, and a side thread starts the same way.
None of them sees the main conversation, so each one starts from the session folder, as
`build` prints it: the base context (where the feature stands now) plus the trigger (the
events that started this run).

The files keep everything; the context loads only the recent part of each log, the
CONTEXT_RECENT most recent entries. Three parts are always loaded in full: the initial
request, the open questions and the trigger's events, however old. An older closed
question still shows as one line (no answer), so a settled question is not asked again.
The context names the folder, so an agent that needs an older entry opens the file.

Roles:

- `planner`: owns the outline and the lexicon during scoping. No sections exist yet.
- `writer`: owns the modeling part (its sections) and, from « Write model » on, the
  outline and the lexicon. Gets every section.
- `thread`: a side thread, read-only. Gets the section its passage belongs to; it reads
  the others on demand.
"""

from __future__ import annotations

import re
from typing import Any

from .store import Session, SessionError, format_batch, format_comment

CONTEXT_RECENT = 20  # entries of each log loaded into the context
ROLES = ("planner", "writer", "thread")

QUESTION_ID = re.compile(r"^q\d+$")
COMMENT_ID = re.compile(r"^c\d+$")
BATCH_ID = re.compile(r"^b\d+$")
MESSAGE_ID = re.compile(r"^tm\d+$")


def build(s: Session, role: str, trigger: list[str] | None = None, section: str = "") -> str:
    if role not in ROLES:
        raise SessionError(f"unknown role {role!r}; one of {', '.join(ROLES)}")
    if not s.exists():
        raise SessionError(f"no session {s.slug!r}")
    plan = s.read_plan()
    outline = plan["outline"]
    questions = s.read_questions()
    request = plan.get("initial_request", plan.get("question", ""))
    out = [
        f"# view-concept context · {s.slug} · role {role}",
        f"Session folder: {s.dir}. Its files hold everything; this context loads only the"
        f" {CONTEXT_RECENT} most recent entries of each log. Open a file when you need an"
        " older entry.",
    ]
    if plan.get("repo"):
        base = f" · base branch: {plan['base']}" if plan.get("base") else ""
        out.append(f"Repository: {plan['repo']}{base}. Read the code there.")
    out += ["", "## Initial request", str(request).strip() or "(none recorded)"]
    out += ["", "## Trigger", *_trigger(s, trigger or [], outline, questions)]
    if s.is_grilling():
        out.append("A grill is running: ask every open decision, each with its recommended answer.")
    out += ["", "## Outline (as it is now)", *_outline(outline)]
    out += ["", "## Lexicon (as it is now)", *_lexicon(plan["lexicon"], outline)]
    out += ["", *_recent("Change history", s.read_changes(), _change_line)]
    out += ["", *_questions(questions)]
    out += ["", *_recent("Terminal messages", s.read_terminal_messages(), _message_line)]
    sections = s.read_sections()
    if role == "writer":
        out += ["", "## Sections", *_sections(outline, sections, None)]
    elif role == "thread" and section:
        out += ["", "## Section of the passage", *_sections(outline, sections, section)]
    return "\n".join(out).rstrip() + "\n"


def _number(outline: list[dict[str, Any]]) -> dict[str, int]:
    return {sec["id"]: i + 1 for i, sec in enumerate(outline)}


def _trigger(
    s: Session, ids: list[str], outline: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> list[str]:
    """Each event in full: a question with its answer, a comment, a whole batch, a terminal
    message. Anything else (« Write model », a note) is printed as given."""
    if not ids:
        return ["none: the first run of this role"]
    by_question = {q["id"]: q for q in questions}
    batches = s.read_comments()["batches"]
    comments = {c["id"]: c for b in batches for c in b["comments"]}
    messages = {m["id"]: m for m in s.read_terminal_messages()}
    lines = []
    for event in ids:
        if QUESTION_ID.match(event) and event in by_question:
            lines.append(_question_line(by_question[event], full=True))
        elif COMMENT_ID.match(event) and event in comments:
            lines.append(format_comment(comments[event], _number(outline)))
        elif BATCH_ID.match(event):
            batch = next((b for b in batches if b["id"] == event), None)
            if batch is None:
                raise SessionError(f"no batch {event!r}")
            lines.append(format_batch(s.slug, batch, outline, questions))
        elif MESSAGE_ID.match(event) and event in messages:
            lines.append(_message_line(messages[event]))
        elif re.match(r"^(q|c|tm)\d+$", event):
            raise SessionError(f"no {event!r} in this session")
        else:
            lines.append(event)
    return lines


def _outline(outline: list[dict[str, Any]]) -> list[str]:
    if not outline:
        return ["(empty: no plan yet)"]
    lines = []
    for i, sec in enumerate(outline, 1):
        part = " [refactoring part]" if sec.get("part") in ("refactoring", 2) else ""
        earns = f": {sec['earns']}" if sec.get("earns") else ""
        lines.append(f"{i}. {sec.get('title', sec['id'])} ({sec['id']}){part}{earns}")
    return lines


def _lexicon(lexicon: list[dict[str, Any]], outline: list[dict[str, Any]]) -> list[str]:
    if not lexicon:
        return ["(empty)"]
    number = _number(outline)
    return [
        f"- {t.get('term', '')} (section {number.get(t.get('section', ''), '?')}):"
        f" {t.get('definition', '')}"
        for t in lexicon
    ]


def _recent(title: str, entries: list[dict[str, Any]], line: Any) -> list[str]:
    if not entries:
        return [f"## {title}", "(none)"]
    shown = entries[-CONTEXT_RECENT:]
    head = f"## {title}" + (
        f" ({len(shown)} most recent of {len(entries)})" if len(shown) < len(entries) else ""
    )
    return [head, *map(line, shown)]


def _change_line(d: dict[str, Any]) -> str:
    by = f" by {d['by']}" if d.get("by") else ""
    cause = f" (cause: {', '.join(d['cause'])})" if d.get("cause") else ""
    return f"- {d['id']}{by}: {d['change']}{cause}"


def _message_line(m: dict[str, Any]) -> str:
    phase = f" ({m['phase']})" if m.get("phase") else ""
    return f"- {m['id']}{phase}: {m['text']}"


def _question_line(q: dict[str, Any], full: bool) -> str:
    text = " ".join(q.get("text", "").split())
    line = f"- {q['id']} [{q['status']}] {text}"
    if q["status"] == "open":
        if q.get("options"):
            line += f" (options: {' / '.join(q['options'])})"
        if q.get("recommended"):
            line += f" (recommended: {q['recommended']})"
    elif full and q["status"] == "skipped":
        line += " → skipped: the default was taken"
    elif full:
        a = q.get("answer") or {}
        answer = " — ".join(p for p in [", ".join(a.get("choices", [])), a.get("text", "")] if p)
        line += f" → {answer or '(empty answer)'}"
    return line


def _questions(questions: list[dict[str, Any]]) -> list[str]:
    """Every open question; the most recent closed ones with their answer, the older ones
    as one line each."""
    if not questions:
        return ["## Questions", "(none)"]
    open_ = [q for q in questions if q["status"] == "open"]
    closed = [q for q in questions if q["status"] != "open"]
    recent, older = closed[-CONTEXT_RECENT:], closed[:-CONTEXT_RECENT]
    lines = ["## Questions"]
    lines += ["Open:", *(_question_line(q, True) for q in open_)] if open_ else ["Open: none"]
    if recent:
        lines += ["Answered or skipped:", *(_question_line(q, True) for q in recent)]
    if older:
        lines += ["Older, answer not loaded:", *(_question_line(q, False) for q in older)]
    return lines


def _sections(
    outline: list[dict[str, Any]], sections: dict[str, str], only: str | None
) -> list[str]:
    number = _number(outline)
    ids = [
        sec["id"]
        for sec in outline
        if sec["id"] in sections and (only is None or sec["id"] == only)
    ]
    if not ids:
        return ["(none written yet)"]
    titles = {sec["id"]: sec.get("title", sec["id"]) for sec in outline}
    lines = []
    for sid in ids:
        lines += [f"### {number[sid]}. {titles[sid]} ({sid})", sections[sid].strip(), ""]
    return lines
