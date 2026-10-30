"""The context a subagent of a coordinated session starts from.

In a coordinated session (the build-feature workflow) the main session only coordinates:
the work is done by subagents, each started fresh, and a side thread starts the same way.
None of them sees the main conversation, so each one starts from the session folder, as
`build` prints it: the base context (where the feature stands now) plus the trigger (the
events that started this run).

The files keep everything; the context loads only the recent part of each log, the
CONTEXT_RECENT most recent entries. Three parts are always loaded in full: the request
(below), the open and deferred questions and the trigger's events, however old. An older
closed question still shows as one line (no answer), so a settled question is not asked again.
The context names the folder, so an agent that needs an older entry opens the file.

The request part is the initial request (the user's first message), or, when the review
follows a conversation (request.md, the request transcript), that whole conversation for
the scoper, the planner and the writer, the roles that shape the model; the implementer, the
documenter, the reviewer and a side thread get the initial request and the transcript's
path, and open it when a comment needs the user's reasons.

Roles:

- `scoper`: owns the scoping section of a feature (the drawing of the problem, an HTML
  section with `"part": "scoping"`) and its pins, until « End scoping », and again when a
  later agent's pin sends the session back to scoping. Gets the scoping sections and the
  pins (pins.json): the open ones, then the recent closed ones with their note.
- `planner`: owns the outline and the lexicon during scoping, or, in a feature with a
  scoping section, writes them at « End scoping » by converting the drawing. Gets the
  scoping sections and the pins; no other section exists yet.
- `writer`: owns the modeling part (its sections), the to-do list (the section `todo`,
  in the refactoring part) and, from « Write model » on, the outline and the lexicon.
  Gets every section and the pins.
- `implementer`: owns the code, from « Approve model » on, and never touches the docs.
  Gets the modeling part, the to-do list, and the sections its trigger names (the
  reviewer's items it must act on).
- `documenter`: owns the doc set and the docs, from « Write docs » on: the doc pass's
  role that prepares it (the doc set, the lexicons, the write order) and ends it (the docs
  that are not READMEs, the reports of the skill agents, the commit). Gets the modeling
  part, the to-do list, and the sections its trigger names.
- `reviewer`: owns the rest of the refactoring part, which checks the code against the
  model. Gets every section.
- `thread`: a side thread, read-only. Gets the section its passage belongs to; it reads
  the others on demand. A passage of the Doc tab gets its doc, read from the worktree
  (`doc:<path>`), or the doc set (`doc:` alone), in place of a section; a pin's box
  (`pin:<id>`) its pin and the scoping sections.

An HTML section is loaded by its visible text, the words a reader sees in it, not its HTML
source; its heading names its file, for an agent that needs the source.

In a code session every role also gets the code map (code-map.md): which modules carry
the feature and where each concept lives, as the planner wrote it and the implementer
keeps it, so a run does not explore the same code again. The writer, the documenter and
the reviewer also get the doc set (doc-set.json: each doc's path and reason in the write
order, its minor class, a README's failure indicator, the docs the user removed) and the
stale passages still shown: the writer writes the first doc set, the documenter
refreshes it at the doc pass, the reviewer flags the stale passages. The documenter also
gets the missing facts of each README (missing-facts.json: what its old text said and no
README written says any more, after a full rewrite, a restructuring or a rewritten folder
model), with the state of the user's decision on each: it applies the comments on them.
The documenter and the reviewer also get the concept triage (concept-triage.json: whether
each concept of the model enters the docs): the doc pass follows it, the reviewer checks
the docs against it; and the move plans (moves.json: where each passage of the folder
model of a restructured README goes). The implementer gets none of these: it writes the
code only. A side thread on a doc gets that doc's missing facts with its text; one on a
row of the concept triage gets the triage, one on a row of a move plan the move plans.
The docs themselves are files of the repository, read there.

Once the model is approved, every role also sees which changes of the model the code does
not carry yet, in full however old: the implementer acts on them, the others must know the
code lags behind them.
"""

from __future__ import annotations

import re
from typing import Any

from .store import (
    DOC_KEY,
    DOC_SET_ANCHOR,
    MOVES_KEY,
    SCOPING_PART,
    TRIAGE_KEY,
    Session,
    SessionError,
    format_batch,
    format_comment,
    format_doc,
    format_fact,
    format_move,
    format_triage,
    pin_anchor,
    pin_elements,
)

CONTEXT_RECENT = 20  # entries of each log loaded into the context
ROLES = ("scoper", "planner", "writer", "implementer", "documenter", "reviewer", "thread")
# The roles that read the request transcript whole.
TRANSCRIPT_ROLES = ("scoper", "planner", "writer")
# The roles that keep the doc set or work on its docs: the writer writes the first one,
# the documenter refreshes it at the doc pass, the reviewer flags stale passages.
DOC_SET_ROLES = ("writer", "documenter", "reviewer")
# The roles that get the missing facts: the documenter applies the user's decisions.
FACT_ROLES = ("documenter",)
# The roles that get the concept triage and the move plans: the doc pass follows them, the
# reviewer checks the docs against them.
TRIAGE_ROLES = ("documenter", "reviewer")
# The roles that get the pins: the scoper opens and closes them, the planner reads the
# settled ones as decisions and facts, the planner and the writer open one when they find
# a point only the user can settle.
PIN_ROLES = ("scoper", "planner", "writer")

QUESTION_ID = re.compile(r"^q\d+$")
PIN_ID = re.compile(r"^[ph]\d+$")
COMMENT_ID = re.compile(r"^c\d+$")
BATCH_ID = re.compile(r"^b\d+$")
MESSAGE_ID = re.compile(r"^tm\d+$")
CHANGE_ID = re.compile(r"^m\d+$")


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
    out += ["", *_request(s, role, str(request).strip())]
    out += ["", "## Trigger", *_trigger(s, trigger or [], outline, questions)]
    if s.is_grilling():
        out.append("A grill is running: ask every open decision, each with its recommended answer.")
    out += ["", "## Outline (as it is now)", *_outline(outline)]
    out += ["", "## Lexicon (as it is now)", *_lexicon(plan["lexicon"], outline)]
    if plan.get("repo"):
        out += ["", "## Code map", s.read_code_map() or "(none written yet)"]
    if plan.get("repo") and role in DOC_SET_ROLES:
        out += ["", *_doc_tab(s, role)]
    out += ["", *_change_history(s)]
    out += ["", *_questions(questions)]
    if role in PIN_ROLES:
        out += ["", *_pins(s)]
    out += ["", *_recent("Terminal messages", s.read_terminal_messages(), _message_line)]
    html = s.html_sections()
    # An HTML section is read by its visible text, not its HTML source.
    sections = {**s.read_sections(), **{k: v for k, v in s.read_prose().items() if k in html}}
    if role in ("writer", "reviewer"):
        out += ["", "## Sections", *_sections(outline, sections, None, html=html)]
    elif role in ("scoper", "planner"):
        scoping = {sec["id"] for sec in outline if _scoping(sec)}
        out += ["", "## Scoping (the drawing; its source is the HTML file)"]
        out += _sections(outline, sections, None, scoping, html)
    elif role in ("implementer", "documenter"):
        named = set(trigger or [])
        # The to-do list is part of the model, though it sits in the refactoring part.
        named.add("todo")
        wanted = {sec["id"] for sec in outline if not _refactoring(sec) or sec["id"] in named}
        head = "## Sections (the modeling part, the to-do list, and the sections the trigger names)"
        out += ["", head]
        out += _sections(outline, sections, None, wanted, html)
    elif role == "thread" and section:
        if section.startswith(DOC_KEY):  # a doc, or the doc set (DOC_SET_ANCHOR)
            out += ["", *doc_passage(s, section)]
        elif section.startswith(TRIAGE_KEY):  # a row of the concept triage
            out += ["", *_triage(s)]
        elif section.startswith(MOVES_KEY):  # a row of a move plan
            out += ["", *_moves(s)]
        elif pid := pin_anchor(section):  # a pin's box: the pin, on the drawing
            pin = [_pin_line(p, set()) for p in s.read_pins() if p["id"] == pid]
            out += ["", "## The pin", *pin]
            scoping = {sec["id"] for sec in outline if _scoping(sec)}
            out += ["", "## Scoping (the drawing the pin is on)"]
            out += _sections(outline, sections, None, scoping, html)
        else:
            sec = _sections(outline, sections, section, html=html)
            out += ["", "## Section of the passage", *sec]
    return "\n".join(out).rstrip() + "\n"


def doc_passage(s: Session, anchor: str) -> list[str]:
    """What a side thread on the Doc tab gets in place of a section: the doc its passage
    is in, read from the worktree, or the doc set for a passage of the doc set list."""
    if anchor == DOC_SET_ANCHOR:
        return ["## Doc set of the passage", *_doc_set(s)]
    path = anchor.removeprefix(DOC_KEY)
    file = s.doc_file(path)
    text = file.read_text("utf-8", errors="replace") if file and file.is_file() else None
    where = f"read from the worktree: {file}" if file else "the session has no repo"
    facts = _missing_facts(s, path)  # a passage may be one of its missing facts
    return [
        f"## Doc of the passage: {path} ({where})",
        (text or "(missing)").strip(),
        *(["", *facts] if facts else []),
    ]


def _doc_tab(s: Session, role: str) -> list[str]:
    """The doc set and the stale passages still shown, for the roles that work on them;
    the missing facts too for the documenter, who applies the user's decisions on them."""
    lines = [
        "## Doc set",
        "The repo docs the Doc tab shows, in the write order. Each one is a file of the"
        " repository: read it there.",
        *_doc_set(s),
        "",
        "## Stale passages (flagged, still found in their doc)",
    ]
    flags = s.shown_stale()
    if not flags:
        lines.append("(none)")
    for f in flags:
        section = f" (contradicts {f['section']})" if f.get("section") else ""
        quote = " ".join(f["quote"].split())
        lines.append(f"- {f['id']} {f['doc']} « {quote} »{section}: {f['note']}")
    if role in FACT_ROLES:
        lines += ["", *_missing_facts(s)]
    if role in TRIAGE_ROLES:
        lines += ["", *_triage(s), "", *_moves(s)]
    return lines


def _moves(s: Session) -> list[str]:
    """The move plan of each restructured README of the doc set, one line per passage."""
    listed = {d["path"] for d in s.read_doc_set()["docs"]}
    plans = {p: rows for p, rows in s.read_moves().items() if p in listed}
    lines = [
        "## Move plans (each passage of a restructured README's folder model: the README it"
        " goes to, what it becomes there)"
    ]
    if not plans:
        return [*lines, "(none)"]
    for p, rows in plans.items():
        lines += [f"{p}:", *(f"- {format_move(r)}" for r in rows)]
    return lines


def _triage(s: Session) -> list[str]:
    """The concept triage, one line per concept of the model."""
    rows = s.read_triage()
    return [
        "## Concept triage (whether each concept of the model enters the docs: who ignores"
        " it would get what wrong?)",
        *([f"- {format_triage(r)}" for r in rows] or ["(none written yet)"]),
    ]


def _missing_facts(s: Session, path: str = "") -> list[str]:
    """The missing facts of each README of the doc set (or of `path` alone): what its old
    text said and no README written says any more, after a full rewrite, a restructuring or
    a rewritten folder model, each with its proposal and the state of the user's decision."""
    listed = {d["path"] for d in s.read_doc_set()["docs"]}
    facts = {p: f for p, f in s.read_missing_facts().items() if p in listed}
    if path:
        facts = {p: f for p, f in facts.items() if p == path}
        if not facts:
            return []
    lines = [
        "## Missing facts (what a README's old text said and no README written says any more,"
        " after a full rewrite, a restructuring or a rewritten folder model; the README takes"
        " back only those the user keeps)"
    ]
    if not facts:
        return [*lines, "(none)"]
    for p, entries in facts.items():
        lines += [f"{p}:", *(f"- {format_fact(f)}" for f in entries)]
    return lines


def _doc_set(s: Session) -> list[str]:
    """The doc set, one line per doc with its reason (and its minor class, the failure
    indicator of a README), then the docs the user removed."""
    data = s.read_doc_set()
    if not data["docs"] and not data["removed"]:
        return ["(none written yet)"]
    lines = [f"- {format_doc(d)}" for d in data["docs"]]
    if data["removed"]:
        lines.append(
            f"Removed by the user (never add them back unless the user asks):"
            f" {', '.join(data['removed'])}"
        )
    return lines


def _request(s: Session, role: str, initial: str) -> list[str]:
    """The request transcript whole to the roles that shape the model; the initial request
    and the transcript's path to the others, or the initial request alone without one."""
    transcript = s.read_request()
    if transcript and role in TRANSCRIPT_ROLES:
        return [
            "## Request transcript",
            "The conversation that led to this review, every message verbatim and in order."
            " The agent's messages are proposals, not decisions.",
            "",
            transcript,
        ]
    lines = ["## Initial request", initial or "(none recorded)"]
    if transcript:
        lines.append(
            f"The whole conversation that led to this review is in {s.request_path}:"
            " open it when a comment needs the user's reasons."
        )
    return lines


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
    pins = s.read_pins()
    by_pin = {p["id"]: p for p in pins}
    # An old session's pins moved from questions.json keep their question id.
    by_pin |= {p["question"]: p for p in pins if p.get("question")}
    waiting = s.waiting_pins()
    batches = s.read_comments()["batches"]
    comments = {c["id"]: c for b in batches for c in b["comments"]}
    messages = {m["id"]: m for m in s.read_terminal_messages()}
    changes = {d["id"]: d for d in s.read_changes()}
    number = _number(outline)
    titles = {sec["id"]: sec.get("title", sec["id"]) for sec in outline}
    lines = []
    for event in ids:
        if QUESTION_ID.match(event) and event in by_question:
            lines.append(_question_line(by_question[event], full=True))
        elif (PIN_ID.match(event) or QUESTION_ID.match(event)) and event in by_pin:
            lines.append(_pin_line(by_pin[event], waiting))
        elif COMMENT_ID.match(event) and event in comments:
            lines.append(format_comment(comments[event], _number(outline), s.move_readmes(), pins))
        elif BATCH_ID.match(event):
            batch = next((b for b in batches if b["id"] == event), None)
            if batch is None:
                raise SessionError(f"no batch {event!r}")
            lines.append(format_batch(s.slug, batch, outline, questions, s.move_readmes(), pins))
        elif MESSAGE_ID.match(event) and event in messages:
            lines.append(_message_line(messages[event]))
        elif CHANGE_ID.match(event) and event in changes:
            lines.append(_change_line(changes[event]))
        elif event in number:
            lines.append(f"- section {number[event]}. {titles[event]} ({event}), below")
        elif re.match(r"^(q|h|p|c|tm|m)\d+$", event):
            raise SessionError(f"no {event!r} in this session")
        else:
            lines.append(event)
    return lines


def _refactoring(sec: dict[str, Any]) -> bool:
    return sec.get("part") in ("refactoring", 2)


def _scoping(sec: dict[str, Any]) -> bool:
    return sec.get("part") == SCOPING_PART


def _change_history(s: Session) -> list[str]:
    """The recent changes of the model; once it is approved, how far the code carries it,
    and every change not implemented yet, even one older than the recent ones."""
    changes = s.read_changes()
    lines = _recent("Change history", changes, _change_line)
    if not s.coordinated or not s.model_approved():
        return lines
    through = s.implemented_through()
    pending = s.unimplemented_changes()
    lines.append(
        f"The code carries the model up to {through}." if through else "No implementer has run."
    )
    if not pending:
        return [*lines, "Every change of the model is implemented."]
    lines.append(f"Not implemented yet: {', '.join(d['id'] for d in pending)}.")
    shown = {d["id"] for d in changes[-CONTEXT_RECENT:]}
    return lines + [_change_line(d) for d in pending if d["id"] not in shown]


def _outline(outline: list[dict[str, Any]]) -> list[str]:
    if not outline:
        return ["(empty: no plan yet)"]
    lines = []
    for i, sec in enumerate(outline, 1):
        part = " [refactoring part]" if _refactoring(sec) else ""
        part += " [overview]" if sec.get("overview") is True else ""
        earns = f": {sec['earns']}" if sec.get("earns") else ""
        lines.append(f"{i}. {sec.get('title', sec['id'])} ({sec['id']}){part}{earns}")
    return lines


def _lexicon(lexicon: list[dict[str, Any]], outline: list[dict[str, Any]]) -> list[str]:
    """One line per term, with its home section and its term kind (core without one)."""
    if not lexicon:
        return ["(empty)"]
    number = _number(outline)
    return [
        f"- {t.get('term', '')} (section {number.get(t.get('section', ''), '?')},"
        f" {t.get('kind') or 'core'}): {t.get('definition', '')}"
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
    waiting = q["status"] in ("open", "deferred")
    if waiting:
        if q.get("options"):
            line += f" (options: {' / '.join(q['options'])})"
        if q.get("recommended"):
            line += f" (recommended: {q['recommended']})"
    if q.get("section"):
        line += f" (anchor section: {q['section']})"
    if waiting or full:
        # Each « I don't understand », with what the user said was missing.
        for u in q.get("unclear", []):
            line += f" → unclear{': ' + u['note'] if u.get('note') else ''}"
    if waiting or not full:
        return line
    if q["status"] == "skipped":
        line += " → skipped: the default was taken"
    else:
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
    deferred = [q for q in questions if q["status"] == "deferred"]
    closed = [q for q in questions if q["status"] not in ("open", "deferred")]
    recent, older = closed[-CONTEXT_RECENT:], closed[:-CONTEXT_RECENT]
    lines = ["## Questions"]
    lines += ["Open:", *(_question_line(q, True) for q in open_)] if open_ else ["Open: none"]
    if deferred:
        lines += [
            "Deferred (the user didn't understand them: ask each again with `reask` once its "
            "anchor section is written):",
            *(_question_line(q, True) for q in deferred),
        ]
    if recent:
        lines += ["Answered or skipped:", *(_question_line(q, True) for q in recent)]
    if older:
        lines += ["Older, answer not loaded:", *(_question_line(q, False) for q in older)]
    return lines


def _pin_line(p: dict[str, Any], waiting: set[str]) -> str:
    """One pin: its id, kind, state, elements and sentence, a lead's sources; once closed,
    the note that says how it was settled."""
    state = "open, waiting for the scoper" if p["id"] in waiting else p["status"]
    on = pin_elements(p)
    element = f" (element{'s' * (len(on) > 1)}: {', '.join(on)})" if on else " (no element)"
    line = f"- {p['id']} [{p['kind']} · {state}]{element} {p['text']}"
    if p.get("sources"):
        line += f" (sources: {'; '.join(p['sources'])})"
    if p.get("question"):
        line += f" (was question {p['question']})"
    if p["status"] == "closed" and p.get("note"):
        line += f" → {p['note']}"
    return line


def _pins(s: Session) -> list[str]:
    """Every open pin, then the most recent closed ones with their note. An open pin waits
    for the scoper when a sent comment attached to it, or to its element, is not resolved
    yet."""
    pins = s.read_pins()
    if not pins:
        return ["## Pins", "(none)"]
    waiting = s.waiting_pins()
    open_ = [p for p in pins if p["status"] == "open"]
    closed = [p for p in pins if p["status"] != "open"]
    recent, older = closed[-CONTEXT_RECENT:], closed[:-CONTEXT_RECENT]
    lines = ["## Pins"]
    lines += ["Open:", *(_pin_line(p, waiting) for p in open_)] if open_ else ["Open: none"]
    if recent:
        lines += ["Closed:", *(_pin_line(p, waiting) for p in recent)]
    if older:
        lines.append(f"Older closed pins: {len(older)}, in {s.pins_path}")
    return lines


def _sections(
    outline: list[dict[str, Any]],
    sections: dict[str, str],
    only: str | None,
    among: set[str] | None = None,
    html: set[str] | None = None,
) -> list[str]:
    number = _number(outline)
    ids = [
        sec["id"]
        for sec in outline
        if sec["id"] in sections
        and (only is None or sec["id"] == only)
        and (among is None or sec["id"] in among)
    ]
    if not ids:
        return ["(none written yet)"]
    titles = {sec["id"]: sec.get("title", sec["id"]) for sec in outline}
    lines = []
    for sid in ids:
        kind = ""
        if sid in (html or ()):
            kind = f" · HTML section, its visible text (sections/{sid}.html)"
        lines += [f"### {number[sid]}. {titles[sid]} ({sid}){kind}", sections[sid].strip(), ""]
    return lines
