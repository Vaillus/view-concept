"""Session storage.

A session is one explanation, stored as a directory of plain files. The agent writes
the plan and the sections; the page reads them; the page writes review comments, which
reach the agent session through the inbox.

    <home>/sessions/<slug>/
        plan.json       title, question, kind, workflow, outline, lexicon  (written by the agent)
        sections/<id>.md  the prose of one outline section         (written by the agent)
        audit.json      vocabulary-audit findings       (written by the agent and `check`)
        status.json     what the agent is doing now: phase, section    (written by `status`)
        changes.json    model changes accepted in a branch review       (written by `change`)
        questions.json  agent questions put to the user, with their answers  (`question`, server)
        comments.json   every batch sent from the page, with status (server + CLI)
        inbox.jsonl     one line per batch, appended by the server  (read by `watch`)
        .watch_cursor   byte offset of the inbox already delivered  (written by `watch`)
        watch.json      the watch's heartbeat: pid, time of its last check  (written by `watch`)
        agent.json     the agent session driving this one     (written by `new`, `open`)
        seen.json       the highlight baseline: each section's text   (server)
        threads/<id>.json  a side thread: messages, its own agent session id  (server)

A section is one element of the `outline` list in plan.json: {id, title, earns}. An
answer to a comment that belongs in the explanation amends a section or adds one at its
place in the outline; a `kind: "question"` left by an older session is ignored, and the
section reads as any other. A refactor section, marked `part: 2`, belongs to Part 2 of
a branch review or a refactor and is shown in the refactor tab; every other section is
an explanation section, shown in the Explanation tab. A refactor section about one item
of the diff carries its item fields under `item`: {files, verdict (one of the keys of
the session workflow's list in verdicts.yaml, next to this module), batch? (a short
label or number), implements, note, relations: [{to, kind, from?}]}, where the optional
`from` names which of the item's files a relation starts from (by default the first).
One with `kind: "finding"` and `items: [<section ids>]` is a finding across items.

The session workflow, `workflow` in plan.json, is the skill that drives the session:
view-concept, view-branch or view-refactor (a triage of existing code). It picks the
verdict set the page shows: verdicts.yaml holds one list per workflow, and each verdict
carries the `tone` the page colours it with. A session created before workflows existed
has no workflow and gets view-branch's list.

A side thread is a separate headless agent conversation, forked from the session in
agent.json, that the user opens from the page to discuss a passage without changing
anything (see threads.py). Only a comment batch reaches the main session.

The agent is "listening" while a watch runs for the session: the watch rewrites watch.json
every HEARTBEAT_EVERY seconds, and a heartbeat older than LISTENING_FOR seconds (or none)
means no watch runs. The margin covers the seconds between a Monitor expiry and the re-arm.

An agent question is a question the agent puts to the user in the page rather than in the
terminal: {id: q1…, text, options, multi (several options may be picked), recommended?
(the answer the agent suggests: an option, which the page preselects, or a text it
pre-fills), status: "open" | "answered" | "skipped", asked, answer?: {choices, text, at,
from?}, skipped? (when)}. Asking one sets the phase "awaiting-answer", except during
scoping: in the phase "scoping" the agent keeps asking without waiting, so the phase
stays. The page shows each open one in the scope block at the top of the Plan tab. The
user's answer reaches the session as a batch whose action is "answer", carrying
`answers: [{question, choices, text}]`. A skipped question (the user leaves it to the
agent's default) is sent the same way, its entry `{question, skipped: true}`. When the
user answers in the terminal instead, the agent runs `answered`: the question is marked
answered with `from: "terminal"`, empty choices and the user's words as text, and no
batch is sent, since the agent already has the answer; the phase is left to the agent.

Scoping ends when the user clicks « Plan »: a batch whose action is "plan", after which
every question still open is marked skipped (the agent treats them as skipped and writes
the plan, or the model in a branch review). « Grill me » sends a batch whose action is
"grill" (the agent asks every open design decision as a question with a recommended
answer, until none is left) and « Stop grill » one whose action is "stop-grill". A grill
runs while the latest "grill" batch is not resolved (the agent resolves it with a reply
when no decision is left) and no "stop-grill" or "approve-model" batch follows it
(`is_grilling`).

seen.json holds the highlight baseline: it maps a section id to the markdown the section
had when the user sent the last batch (any batch: comments, an approval, an answer), or
marked that section read later. A section whose file differs from its baseline is
"updated": the page highlights what changed since then, so after the agent handles a batch
the highlights show what it changed for that batch. The first text of a section is its
first baseline, recorded when the page first loads it, so a first write is never an
update.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

HOME = Path(os.environ.get("VIEW_CONCEPT_HOME", Path.home() / ".view-concept"))
SESSIONS = HOME / "sessions"
VAULT_DIR = Path(
    os.environ.get("VIEW_CONCEPT_VAULT", Path.home() / "Documents" / "Vault" / "explanations")
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
# What the page shows in its status indicator; "awaiting-approval" also shows « Approve plan »,
# "awaiting-model" (set by the view-branch skill only) « Approve model », and "awaiting-pr"
# (set by the view-branch skill once refactoring is written) « Create PR ».
# "awaiting-answer" (set by `question`, outside scoping) waits on an agent question shown in
# the scope block at the top of the Plan tab.
PHASES = (
    "scoping",
    "planning",
    "awaiting-approval",
    "awaiting-model",
    "awaiting-pr",
    "awaiting-answer",
    "writing",
    "audit",
    "revising",
    "idle",
)
ACTIONS = (
    "",
    "approve-plan",
    "approve-model",
    "create-pr",
    "answer",
    "plan",
    "grill",
    "stop-grill",
)
# "code": the explanation is about a repository — citations link into it, and the
# model changes it leads to are what outlive it. "explanation": understanding for its own sake.
KINDS = ("explanation", "code")
# The session workflow: which skill drives the session. It picks the verdict set the page
# shows (see verdicts.yaml). view-branch and view-refactor review code, so their sessions
# are code sessions. A session created before workflows existed has none.
WORKFLOWS = ("view-concept", "view-branch", "view-refactor")
# The workflow of a session created without --workflow, by kind.
DEFAULT_WORKFLOW = {"explanation": "view-concept", "code": "view-branch"}
THREAD_ID_RE = re.compile(r"^t[0-9]{1,6}$")
HEARTBEAT_EVERY = 2.5  # seconds between two heartbeats of a running watch
LISTENING_FOR = 15.0  # seconds a heartbeat proves a watch runs


class SessionError(Exception):
    pass


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80] or "explanation"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        raise SessionError(f"{path.name} is not valid JSON: {e}") from e


def _write_json(path: Path, data: Any) -> None:
    """Atomic write: the page may read while the CLI writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# Text the page never marks terms in: fenced code (and Mermaid), inline code, maths.
UNMARKED_RE = re.compile(r"```.*?```|`[^`\n]*`|\$\$.*?\$\$|\$[^$\n]+\$", re.S)


def _strip_unmarked(markdown: str) -> str:
    return UNMARKED_RE.sub(" ", markdown)


def _uses(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match, as the page's wrapTerm: the term is neither
    preceded nor followed by a letter or a digit (`[^\\W_]`, the Python spelling of
    `[\\p{L}\\p{N}]`)."""
    pattern = rf"(?<![^\W_]){re.escape(term.strip())}(?![^\W_])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def precedence_audit_entry(p: dict[str, Any]) -> dict[str, Any]:
    """The audit.json entry of one precedence-check problem; sections by number."""
    if p["issue"] == "forward":
        verb = "use" if " and " in p["field"] else "uses"
        note = f"{p['field']} {verb} «{p['other']}» (section {p['at']})"
    else:
        note = f"introduced in section {p['home']}"
    return {"term": p["term"], "section": p["section"], "issue": p["issue"], "note": note}


def format_precedence(p: dict[str, Any]) -> str:
    """One terminal line for a precedence-check problem."""
    head = f"{p['issue']:8} {p['term']} ({p['home']})"
    if p["issue"] == "forward":
        verb = "use" if " and " in p["field"] else "uses"
        return f"{head}  {p['field']} {verb} «{p['other']}» ({p['at']})"
    return f"{head}  used in section {p['at']}"


class Session:
    def __init__(self, slug: str, root: Path | None = None) -> None:
        if not SLUG_RE.match(slug):
            raise SessionError(f"invalid slug {slug!r}: lowercase letters, digits and dashes")
        self.slug = slug
        self.dir = (root or SESSIONS) / slug

    # ---- paths ----
    @property
    def plan_path(self) -> Path:
        return self.dir / "plan.json"

    @property
    def sections_dir(self) -> Path:
        return self.dir / "sections"

    @property
    def audit_path(self) -> Path:
        return self.dir / "audit.json"

    @property
    def comments_path(self) -> Path:
        return self.dir / "comments.json"

    @property
    def status_path(self) -> Path:
        return self.dir / "status.json"

    @property
    def changes_path(self) -> Path:
        return self.dir / "changes.json"

    @property
    def questions_path(self) -> Path:
        return self.dir / "questions.json"

    @property
    def inbox_path(self) -> Path:
        return self.dir / "inbox.jsonl"

    @property
    def cursor_path(self) -> Path:
        return self.dir / ".watch_cursor"

    @property
    def watch_path(self) -> Path:
        return self.dir / "watch.json"

    @property
    def agent_path(self) -> Path:
        return self.dir / "agent.json"

    @property
    def legacy_claude_path(self) -> Path:
        """What agent.json was called before sessions could run on other agents."""
        return self.dir / "claude.json"

    @property
    def seen_path(self) -> Path:
        return self.dir / "seen.json"

    @property
    def threads_dir(self) -> Path:
        return self.dir / "threads"

    def thread_path(self, tid: str) -> Path:
        if not THREAD_ID_RE.match(tid):
            raise SessionError(f"invalid thread id {tid!r}")
        return self.threads_dir / f"{tid}.json"

    def exists(self) -> bool:
        return self.plan_path.exists()

    # ---- creation ----
    def create(
        self,
        title: str,
        question: str = "",
        kind: str = "explanation",
        repo: str = "",
        workflow: str = "",
    ) -> bool:
        """Create the session. Returns False when it already existed (left untouched).
        `workflow` defaults by kind (DEFAULT_WORKFLOW)."""
        if kind not in KINDS:
            raise SessionError(f"unknown kind {kind!r}; one of {', '.join(KINDS)}")
        if kind == "code" and not repo:
            raise SessionError("a code session needs --repo")
        workflow = workflow or DEFAULT_WORKFLOW[kind]
        if workflow not in WORKFLOWS:
            raise SessionError(f"unknown workflow {workflow!r}; one of {', '.join(WORKFLOWS)}")
        if workflow != "view-concept" and kind != "code":
            raise SessionError(f"a {workflow} session is a code session: pass --kind code")
        if self.exists():
            return False
        self.sections_dir.mkdir(parents=True, exist_ok=True)
        plan: dict[str, Any] = {
            "title": title,
            "question": question,
            "kind": kind,
            "workflow": workflow,
            "created": date.today().isoformat(),
            "outline": [],
            "lexicon": [],
        }
        if repo:
            plan["repo"] = str(Path(repo).expanduser().resolve())
        _write_json(self.plan_path, plan)
        return True

    # ---- reads ----
    def read_plan(self) -> dict[str, Any]:
        plan = _read_json(self.plan_path, {})
        plan.setdefault("title", self.slug)
        plan.setdefault("outline", [])
        plan.setdefault("lexicon", [])
        return plan

    def read_sections(self) -> dict[str, str]:
        if not self.sections_dir.is_dir():
            return {}
        return {
            p.stem: p.read_text(encoding="utf-8") for p in sorted(self.sections_dir.glob("*.md"))
        }

    def read_audit(self) -> list[dict[str, Any]]:
        return _read_json(self.audit_path, [])

    def check_precedence(self, write: bool = True) -> list[dict[str, Any]]:
        """The precedence check: every forward reference and early use of the lexicon.

        A term's home section is the outline section its lexicon entry names; an entry
        whose section is not in the outline is skipped. A forward reference is an
        entry's definition or tip using another term whose home section comes later;
        an early use is a term found in the prose of a section before its home
        section. Returns one problem per finding: {issue, term, section (the id the
        audit entry points at), home (1-based position of the term's home section),
        at (position of the later home section, or of the early section), field,
        other}. With `write`, replaces the forward and early entries of audit.json
        and keeps every other entry, so a rerun is idempotent."""
        plan = self.read_plan()
        pos = {sec["id"]: i + 1 for i, sec in enumerate(plan["outline"])}
        order = [sec["id"] for sec in plan["outline"]]
        entries = [
            e for e in plan["lexicon"] if e.get("term", "").strip() and e.get("section") in pos
        ]
        prose = {sid: _strip_unmarked(text) for sid, text in self.read_sections().items()}
        problems: list[dict[str, Any]] = []
        for e in entries:
            home = pos[e["section"]]
            for f in entries:
                later = pos[f["section"]]
                if later <= home or f["term"].lower() == e["term"].lower():
                    continue
                fields = [k for k in ("definition", "tip") if _uses(e.get(k) or "", f["term"])]
                if fields:
                    problems.append({
                        "issue": "forward", "term": e["term"], "section": e["section"],
                        "home": home, "at": later, "field": " and ".join(fields),
                        "other": f["term"],
                    })  # fmt: skip
            for sid in order[: home - 1]:
                if _uses(prose.get(sid, ""), e["term"]):
                    problems.append({
                        "issue": "early", "term": e["term"], "section": sid,
                        "home": home, "at": pos[sid], "field": "", "other": "",
                    })  # fmt: skip
        if write:
            kept = [a for a in self.read_audit() if a.get("issue") not in ("forward", "early")]
            _write_json(self.audit_path, kept + [precedence_audit_entry(p) for p in problems])
        return problems

    def read_comments(self) -> dict[str, Any]:
        return _read_json(self.comments_path, {"batches": []})

    def read_changes(self) -> list[dict[str, Any]]:
        return _read_json(self.changes_path, [])

    def add_change(
        self, change: str, why: str = "", instead: str = "", files: list[str] | None = None
    ) -> dict[str, Any]:
        """Append a model change: one correction of the model the user accepted, written
        as an instruction an agent can execute. `instead` is what the PR does now."""
        if not change.strip():
            raise SessionError("empty model change")
        changes = self.read_changes()
        d = {
            "id": f"m{len(changes) + 1}",
            "change": change.strip(),
            "why": why.strip(),
            "instead": instead.strip(),
            "files": files or [],
            "date": date.today().isoformat(),
        }
        changes.append(d)
        _write_json(self.changes_path, changes)
        return d

    def read_questions(self) -> list[dict[str, Any]]:
        return _read_json(self.questions_path, [])

    def add_question(
        self,
        text: str,
        options: list[str] | None = None,
        multi: bool = False,
        recommended: str = "",
    ) -> dict[str, Any]:
        """Put an agent question to the user, and wait for the answer: the phase becomes
        "awaiting-answer". During scoping nothing waits: the phase stays "scoping".
        `recommended` is the answer the agent suggests."""
        if not text.strip():
            raise SessionError("empty question")
        questions = self.read_questions()
        q = {
            "id": f"q{len(questions) + 1}",
            "text": text.strip(),
            "options": [o.strip() for o in options or [] if o.strip()],
            "multi": multi,
            "status": "open",
            "asked": now_iso(),
        }
        if recommended.strip():
            q["recommended"] = recommended.strip()
        questions.append(q)
        _write_json(self.questions_path, questions)
        if self.read_status().get("phase") != "scoping":
            self.write_status("awaiting-answer")
        return q

    def _open_question(self, questions: list[dict[str, Any]], qid: str) -> dict[str, Any]:
        """The open agent question `qid` of `questions`."""
        q = next((q for q in questions if q["id"] == qid), None)
        if q is None:
            raise SessionError(f"no question {qid!r}")
        if q["status"] != "open":
            raise SessionError(f"{qid} is already {q['status']}")
        return q

    def answer_question(self, qid: str, choices: list[str], text: str = "") -> dict[str, Any]:
        """Record the user's answer to an open agent question and send it at once, as a
        batch whose action is "answer". Returns the batch."""
        questions = self.read_questions()
        q = self._open_question(questions, qid)
        choices = [c for c in choices if c]
        unknown = [c for c in choices if c not in q["options"]]
        if unknown:
            raise SessionError(f"not an option of {qid}: {', '.join(unknown)}")
        if len(choices) > 1 and not q.get("multi"):
            raise SessionError(f"{qid} takes one choice")
        text = text.strip()
        if not choices and not text:
            raise SessionError("empty answer")
        batch = self.add_batch(
            [], action="answer", answers=[{"question": qid, "choices": choices, "text": text}]
        )
        q["status"] = "answered"
        q["answer"] = {"choices": choices, "text": text, "at": batch["sent"]}
        _write_json(self.questions_path, questions)
        return batch

    def answered_in_terminal(self, qid: str, text: str = "") -> dict[str, Any]:
        """Mark an open agent question answered in the terminal: the user answered it there,
        so the agent already has the answer and no batch is sent. `text` is the answer as
        the user gave it. The phase is left alone. Returns the question."""
        questions = self.read_questions()
        q = self._open_question(questions, qid)
        q["status"] = "answered"
        q["answer"] = {"choices": [], "text": text.strip(), "at": now_iso(), "from": "terminal"}
        _write_json(self.questions_path, questions)
        return q

    def skip_question(self, qid: str) -> dict[str, Any]:
        """Skip an open agent question: the user leaves it to the agent's default. Sent at
        once, as an answer batch whose entry is `{question, skipped: true}`. Returns the
        batch."""
        questions = self.read_questions()
        q = self._open_question(questions, qid)
        batch = self.add_batch([], action="answer", answers=[{"question": qid, "skipped": True}])
        q["status"] = "skipped"
        q["skipped"] = batch["sent"]
        _write_json(self.questions_path, questions)
        return batch

    def read_seen(self, sections: dict[str, str]) -> dict[str, str]:
        """The highlight baseline of each section, recording the current text of any
        section seen for the first time."""
        seen = _read_json(self.seen_path, {})
        new = {k: v for k, v in sections.items() if k not in seen}
        if new:
            seen.update(new)
            _write_json(self.seen_path, seen)
        return seen

    def mark_seen(self, sections: dict[str, str]) -> None:
        """Set the baseline of `sections` (id -> the markdown the page showed): « mark read »."""
        seen = _read_json(self.seen_path, {})
        seen.update(sections)
        _write_json(self.seen_path, seen)

    def read_status(self) -> dict[str, Any]:
        return _read_json(self.status_path, {"phase": "idle"})

    def write_status(self, phase: str, section: str = "", message: str = "") -> dict[str, Any]:
        if phase not in PHASES:
            raise SessionError(f"unknown phase {phase!r}; one of {', '.join(PHASES)}")
        status = {"phase": phase, "section": section, "message": message, "since": now_iso()}
        _write_json(self.status_path, status)
        return status

    # ---- the watch's heartbeat ----
    def write_heartbeat(self) -> None:
        _write_json(self.watch_path, {"pid": os.getpid(), "at": now_iso()})

    def is_listening(self, now: datetime | None = None) -> bool:
        """Whether a watch runs for this session now: its heartbeat is recent."""
        try:
            at = datetime.fromisoformat(str(_read_json(self.watch_path, {}).get("at", "")))
        except (SessionError, ValueError):
            return False
        return ((now or datetime.now(UTC)) - at).total_seconds() < LISTENING_FOR

    def signature(self) -> tuple:
        """Changes whenever a file the page renders changes, threads excepted (see
        `thread_signature`). The heartbeat is left out too: the server reads it on its
        own, so a heartbeat never re-renders the page."""
        paths = [
            self.plan_path,
            self.audit_path,
            self.comments_path,
            self.status_path,
            self.changes_path,
            self.questions_path,
        ]
        if self.sections_dir.is_dir():
            paths += sorted(self.sections_dir.glob("*.md"))
        return _stat_signature(paths)

    def thread_signature(self) -> tuple:
        """Changes whenever a thread changes. Kept apart from `signature` so a streaming
        reply refreshes the threads without re-rendering the explanation."""
        if not self.threads_dir.is_dir():
            return ()
        return _stat_signature(sorted(self.threads_dir.glob("t*.json")))

    # ---- the main agent session ----
    def read_agent(self) -> dict[str, str]:
        """What agent.json records: `agent` (claude, codex, jazz), `parent` (its conversation
        id, "" when it has none to fork) and `name` (the agent's own name, for Jazz). A
        session created before agent.json has claude.json instead, which only held `parent`."""
        if not self.agent_path.exists() and self.legacy_claude_path.exists():
            parent = str(_read_json(self.legacy_claude_path, {}).get("parent", ""))
            return {"agent": "claude", "parent": parent} if parent else {}
        return {key: str(value) for key, value in _read_json(self.agent_path, {}).items()}

    def read_parent(self) -> str:
        """Id of the agent conversation that drives this one, "" when unknown."""
        return self.read_agent().get("parent", "")

    def bind_agent(self, agent: str, parent: str = "", name: str = "") -> bool:
        """Record the agent driving the session. Returns True when it changed (a resumed
        session runs in a new agent conversation, so threads fork from the new one)."""
        if not agent:
            return False
        current = self.read_agent()
        record = {"agent": agent, "parent": parent, "name": name or current.get("name", "")}
        if all(current.get(key) == value for key, value in record.items()):
            return False
        _write_json(self.agent_path, {**record, "since": now_iso()})
        return True

    # ---- side threads ----
    def read_threads(self) -> list[dict[str, Any]]:
        if not self.threads_dir.is_dir():
            return []
        threads = [_read_json(p, None) for p in self.threads_dir.glob("t*.json")]
        return sorted((_upgrade_thread(t) for t in threads if t), key=lambda t: int(t["id"][1:]))

    def read_thread(self, tid: str) -> dict[str, Any]:
        t = _read_json(self.thread_path(tid), None)
        if t is None:
            raise SessionError(f"no thread {tid!r}")
        return _upgrade_thread(t)

    def write_thread(self, thread: dict[str, Any]) -> None:
        _write_json(self.thread_path(thread["id"]), thread)

    def new_thread(self, section: str = "", quote: str = "", prefix: str = "") -> dict[str, Any]:
        """Create an empty thread, anchored to a passage like a comment, or to nothing."""
        n = max((int(t["id"][1:]) for t in self.read_threads()), default=0) + 1
        thread = {
            "id": f"t{n}",
            "created": now_iso(),
            "section": section,
            "quote": quote,
            "prefix": prefix,
            "agent_session": "",
            "forked_from": "",
            "state": "idle",
            "activity": "",
            "error": "",
            "messages": [],
        }
        self.write_thread(thread)
        return thread

    def delete_thread(self, tid: str) -> None:
        """Delete a thread that led to nothing. One a sent comment points to is kept: the
        session reads it to act on that comment."""
        path = self.thread_path(tid)
        if not path.exists():
            raise SessionError(f"no thread {tid!r}")
        sent = (c for b in self.read_comments()["batches"] for c in b["comments"])
        if any(c.get("thread") == tid for c in sent):
            raise SessionError(f"{tid} was sent in a batch")
        path.unlink()

    # ---- comments ----
    def add_batch(
        self,
        comments: list[dict[str, Any]],
        note: str = "",
        action: str = "",
        answers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Record a batch sent from the page and append it to the inbox.

        `action` is what the user does with the batch: "approve-plan" means the user
        approved the plan from the page, "approve-model" that they approved the model of a
        branch review (so the implementation starts), "create-pr" that they asked the agent to
        open the branch's PR once the refactoring is written, with the comments as last
        corrections, "answer" that they answered or skipped agent questions (`answers`, see
        `answer_question` and `skip_question`), "plan" that they ended scoping (every open
        question is then marked skipped), "grill" that they started a grill and
        "stop-grill" that they stopped it."""
        if action not in ACTIONS:
            raise SessionError(f"unknown action {action!r}")
        if (action == "answer") != bool(answers):
            raise SessionError("an answer batch, and only one, carries answers")
        note = note.strip()
        # A comment from a side thread may have no text: the thread's conclusion is the comment.
        comments = [c for c in comments if str(c.get("text", "")).strip() or c.get("thread")]
        if not comments and not note and not action:
            raise SessionError("empty batch")
        data = self.read_comments()
        batches = data["batches"]
        n_comments = sum(len(b["comments"]) for b in batches)
        batch = {
            "id": f"b{len(batches) + 1}",
            "sent": now_iso(),
            "note": note,
            "action": action,
            "comments": [
                {
                    "id": f"c{n_comments + i + 1}",
                    "section": str(c.get("section", "")),
                    "quote": str(c.get("quote", "")),
                    "prefix": str(c.get("prefix", "")),
                    "text": str(c.get("text", "")).strip(),
                    "thread": str(c.get("thread", "")),
                    "status": "sent",
                }
                for i, c in enumerate(comments)
            ],
        }
        if answers:
            batch["answers"] = answers
        batches.append(batch)
        _write_json(self.comments_path, data)
        with self.inbox_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(batch, ensure_ascii=False) + "\n")
        # Highlights show what changed since the last batch: every baseline moves here.
        self.mark_seen(self.read_sections())
        if action == "plan":
            self._skip_open_questions(batch["sent"])
        return batch

    def _skip_open_questions(self, at: str) -> None:
        """Mark every open agent question skipped: scoping ended without their answers."""
        questions = self.read_questions()
        open_ = [q for q in questions if q["status"] == "open"]
        for q in open_:
            q["status"] = "skipped"
            q["skipped"] = at
        if open_:
            _write_json(self.questions_path, questions)

    def is_grilling(self) -> bool:
        """Whether a grill runs: the latest "grill" batch is not resolved (the agent resolves
        it when no decision is left) and no "stop-grill" or "approve-model" batch follows it.
        A batch without comments is resolved once it has a reply, one with comments once
        all of them are."""
        batches = self.read_comments()["batches"]
        starts = [i for i, b in enumerate(batches) if b.get("action") == "grill"]
        if not starts:
            return False
        grill = batches[starts[-1]]
        comments = grill["comments"]
        if comments and all(c["status"] == "resolved" for c in comments):
            return False
        if not comments and grill.get("reply"):
            return False
        later = batches[starts[-1] + 1 :]
        return not any(b.get("action") in ("stop-grill", "approve-model") for b in later)

    def resolve(self, ids: list[str], reply: str = "") -> list[str]:
        """Mark comments (c…) or whole batches (b…) resolved. Returns the comment ids touched."""
        data = self.read_comments()
        wanted = set(ids)
        touched = []
        for b in data["batches"]:
            for c in b["comments"]:
                if c["id"] in wanted or b["id"] in wanted:
                    c["status"] = "resolved"
                    if reply:
                        c["reply"] = reply
                    touched.append(c["id"])
            if b["id"] in wanted and reply and not b["comments"]:
                b["reply"] = reply
        unknown = wanted - set(touched) - {b["id"] for b in data["batches"]}
        if unknown:
            raise SessionError(f"unknown id(s): {', '.join(sorted(unknown))}")
        _write_json(self.comments_path, data)
        return touched

    # ---- export ----
    def export(self, vault_dir: Path | None = None) -> Path:
        """Write the explanation as one Obsidian note. Re-exporting overwrites the same note."""
        vault_dir = vault_dir or VAULT_DIR
        vault_dir.mkdir(parents=True, exist_ok=True)
        plan = self.read_plan()
        title = str(plan["title"]).strip() or self.slug
        base = re.sub(r'[\\/:*?"<>|#^\[\]]', "", title).strip() or self.slug
        path = vault_dir / f"{base}.md"
        if path.exists() and f"view-concept: {self.slug}\n" not in path.read_text(encoding="utf-8"):
            path = vault_dir / f"{base} ({self.slug}).md"
        path.write_text(self.render_markdown(plan), encoding="utf-8")
        return path

    def render_markdown(self, plan: dict[str, Any] | None = None) -> str:
        plan = plan or self.read_plan()
        sections = self.read_sections()
        title = str(plan["title"]).strip() or self.slug
        question = str(plan.get("question", "")).replace('"', "'")
        lines = [
            "---",
            "type: explanation",
            f'question: "{question}"',
            f"created: {plan.get('created', date.today().isoformat())}",
            f"updated: {date.today().isoformat()}",
            "tags:",
            "  - explanation",
            f"view-concept: {self.slug}",
            "---",
            "",
            f"# {title}",
            "",
        ]
        ordered = [s["id"] for s in plan["outline"]]
        titles = {s["id"]: s.get("title", s["id"]) for s in plan["outline"]}
        for sid in ordered + [k for k in sections if k not in ordered]:
            if sid not in sections:
                continue
            lines += [f"## {titles.get(sid, sid)}", "", sections[sid].strip(), ""]
        if plan["lexicon"]:
            number = {sid: i + 1 for i, sid in enumerate(ordered)}

            def cell(v: Any) -> str:
                return str(v).replace("|", "\\|").replace("\n", " ")

            lines += ["## Lexicon", "", "| Term | Section | Definition |", "|---|---|---|"]
            for t in plan["lexicon"]:
                sec = t.get("section", "")
                where = titles.get(sec, sec)
                if sec in number:
                    where = f"{number[sec]}. {where}"
                term, definition = cell(t.get("term", "")), cell(t.get("definition", ""))
                lines.append(f"| {term} | {cell(where)} | {definition} |")
            lines.append("")
        changes = self.read_changes()
        if changes:
            lines += ["## Model changes", "", format_changes(changes), ""]
        return "\n".join(lines)


def list_sessions(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or SESSIONS
    out = []
    if not root.is_dir():
        return out
    for d in root.iterdir():
        if not (d / "plan.json").exists() or not SLUG_RE.match(d.name):
            continue
        s = Session(d.name, root)
        try:
            plan = s.read_plan()
        except SessionError:
            plan = {"title": d.name}
        mtime = max(st[1] or 0 for st in s.signature())
        pending = sum(
            1 for b in s.read_comments()["batches"] for c in b["comments"] if c["status"] == "sent"
        )
        out.append(
            {
                "slug": d.name,
                "title": plan.get("title", d.name),
                "updated": datetime.fromtimestamp(mtime / 1e9, UTC).isoformat(timespec="seconds"),
                "pending": pending,
                "kind": plan.get("kind", "explanation"),
                "repo": plan.get("repo", ""),
            }
        )
    return sorted(out, key=lambda r: r["updated"], reverse=True)


def _stat_signature(paths: list[Path]) -> tuple:
    sig = []
    for p in paths:
        try:
            st = p.stat()
            sig.append((p.name, st.st_mtime_ns, st.st_size))
        except FileNotFoundError:
            sig.append((p.name, None, None))
    return tuple(sig)


def _upgrade_thread(thread: dict[str, Any]) -> dict[str, Any]:
    """A thread written before sessions could run on other agents keeps its conversation id
    under `claude_id`: read it as `agent_session`, so the thread still resumes."""
    if "agent_session" not in thread:
        thread["agent_session"] = str(thread.pop("claude_id", "") or "")
    return thread


def format_batch(
    slug: str,
    batch: dict[str, Any],
    outline: list[dict[str, Any]],
    questions: list[dict[str, Any]] | None = None,
) -> str:
    """How a batch appears in the agent session (one event of the comment channel). `questions`
    gives the text of the agent questions an answer batch answers."""
    number = {s["id"]: i + 1 for i, s in enumerate(outline)}
    n = len(batch["comments"])
    lines = [f"view-concept · {slug} · batch {batch['id']} · {n} comment{'s' * (n != 1)}"]
    if batch.get("action") == "approve-plan":
        lines.append("action: approve-plan (the user approved the plan from the page)")
    if batch.get("action") == "approve-model":
        lines.append(
            "action: approve-model (the user approved the model from the page: "
            "start the implementation)"
        )
    if batch.get("action") == "create-pr":
        lines.append("action: create-pr (the user asked to open the PR from the page)")
    if batch.get("action") == "plan":
        lines.append(
            "action: plan (the user ended scoping from the page: treat open questions as "
            "skipped and write the plan, or the model in a branch review)"
        )
    if batch.get("action") == "grill":
        lines.append(
            "action: grill (the user started a grill: ask every open design decision as a "
            "question with a recommended answer, until none is left)"
        )
    if batch.get("action") == "stop-grill":
        lines.append("action: stop-grill (the user stopped the grill)")
    if batch.get("action") == "answer":
        asked = {q["id"]: q["text"] for q in questions or []}
        answers = batch.get("answers", [])
        ids = ", ".join(a["question"] for a in answers)
        verb = "skipped" if all(a.get("skipped") for a in answers) else "answered"
        lines.append(f"action: answer (the user {verb} agent question {ids} from the page)")
        for a in answers:
            text = " ".join(asked.get(a["question"], "").split())
            quoted = f" « {text} »" if text else ""
            if a.get("skipped"):
                lines.append(f"{a['question']} skipped{quoted} (no answer: use your default)")
                continue
            parts = [", ".join(a.get("choices", [])), a.get("text", "")]
            answer = " — ".join(p for p in parts if p)
            lines.append(f"answer to {a['question']}{quoted}: {answer}")
    if batch.get("note"):
        lines.append(f"note: {batch['note']}")
    for c in batch["comments"]:
        sec = c["section"]
        where = f"§{number[sec]} ({sec})" if sec in number else f"({sec or 'no section'})"
        quote = " ".join(c["quote"].split())
        lines.append(f"[{c['id']}] {where} « {quote} »" if quote else f"[{c['id']}] {where}")
        lines += [f"    {line}" for line in c["text"].splitlines()]
        if c.get("thread"):
            lines.append(f"    (from side thread {c['thread']}: threads/{c['thread']}.json)")
    return "\n".join(lines)


def format_changes(changes: list[dict[str, Any]]) -> str:
    """Markdown bullets, in the shape of a PR description's Decisions section."""
    out = []
    for d in changes:
        line = f"- {d['change']}"
        if d.get("instead"):
            line += f", rather than {d['instead']}"
        if d.get("why"):
            line += f". {d['why']}"
        if d.get("files"):
            line += f" ({', '.join(f'`{f}`' for f in d['files'])})"
        out.append(line)
    return "\n".join(out)
