"""Session storage.

A session is one explanation, stored as a directory of plain files. Claude Code writes
the plan and the sections; the page reads them; the page writes review comments, which
reach the Claude Code session through the inbox.

    <home>/sessions/<slug>/
        plan.json       title, question, kind, workflow, outline, lexicon  (written by Claude)
        sections/<id>.md  the prose of one outline section         (written by Claude)
        audit.json      vocabulary-audit findings                  (written by Claude)
        status.json     what Claude is doing now: phase, section    (written by `status`)
        changes.json    model changes accepted in a branch review       (written by `change`)
        questions.json  Claude questions put to the user, with their answers  (`question`, server)
        comments.json   every batch sent from the page, with status (server + CLI)
        inbox.jsonl     one line per batch, appended by the server  (read by `watch`)
        .watch_cursor   byte offset of the inbox already delivered  (written by `watch`)
        watch.json      the watch's heartbeat: pid, time of its last check  (written by `watch`)
        claude.json     the Claude Code session driving this one     (written by `new`, `open`)
        seen.json       the text of each section the user last read  (server)
        threads/<id>.json  a side thread: messages, its own Claude session id  (server)

A section is one element of the `outline` list in plan.json: {id, title, earns}, plus
`kind: "question"` (with `from`, the comments it answers) for a section added during the
review. A refactor section, marked `part: 2`, belongs to Part 2 of a branch review or a
refactor and is shown in the refactor tab; every other section is an explanation
section, shown in the Explanation tab. A refactor section about one item of the diff
carries its item fields under `item`: {files, verdict (one of the keys of the session
workflow's list in verdicts.yaml, next to this module), batch? (a short label or
number), implements, note, relations: [{to, kind, from?}]}, where the optional `from`
names which of the item's files a relation starts from (by default the first).
One with `kind: "finding"` and `items: [<section ids>]` is a finding across items.

The session workflow, `workflow` in plan.json, is the skill that drives the session:
view-concept, view-branch or view-refactor (a triage of existing code). It picks the
verdict set the page shows: verdicts.yaml holds one list per workflow, and each verdict
carries the `tone` the page colours it with. A session created before workflows existed
has no workflow and gets view-branch's list.

A side thread is a separate headless Claude conversation, forked from the session in
claude.json, that the user opens from the page to discuss a passage without changing
anything (see threads.py). Only a comment batch reaches the main session.

Claude is "listening" while a watch runs for the session: the watch rewrites watch.json
every HEARTBEAT_EVERY seconds, and a heartbeat older than LISTENING_FOR seconds (or none)
means no watch runs. The margin covers the seconds between a Monitor expiry and the re-arm.

A Claude question is a question Claude puts to the user in the page rather than in the
terminal: {id: q1…, text, options, multi (several options may be picked), status:
"open" | "answered", asked, answer?: {choices, text, at}}. Asking one sets the phase
"awaiting-answer"; the page shows each open one as a card in the review pane. The user's
answer reaches the session as a batch whose action is "answer", carrying
`answers: [{question, choices, text}]`.

seen.json maps a section id to the markdown the user last marked as read. A section
whose file differs from it is "updated": the page highlights what changed since then.
The first text of a section is recorded as read when the page first loads it, so a
first write is never an update.
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
# "awaiting-model" (set by the view-branch skill only) « Approve model », and "awaiting-review"
# (set by the view-branch skill at the end of model matching) « Review code ».
# "awaiting-answer" (set by `question`) waits on a Claude question shown in the review pane.
PHASES = (
    "scoping",
    "planning",
    "awaiting-approval",
    "awaiting-model",
    "awaiting-review",
    "awaiting-answer",
    "writing",
    "audit",
    "revising",
    "idle",
)
ACTIONS = ("", "approve-plan", "approve-model", "review-code", "answer")
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
    def claude_path(self) -> Path:
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
        self, text: str, options: list[str] | None = None, multi: bool = False
    ) -> dict[str, Any]:
        """Put a Claude question to the user, and wait for the answer: the phase becomes
        "awaiting-answer"."""
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
        questions.append(q)
        _write_json(self.questions_path, questions)
        self.write_status("awaiting-answer")
        return q

    def answer_question(self, qid: str, choices: list[str], text: str = "") -> dict[str, Any]:
        """Record the user's answer to an open Claude question and send it at once, as a
        batch whose action is "answer". Returns the batch."""
        questions = self.read_questions()
        q = next((q for q in questions if q["id"] == qid), None)
        if q is None:
            raise SessionError(f"no question {qid!r}")
        if q["status"] != "open":
            raise SessionError(f"{qid} is already answered")
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

    def read_seen(self, sections: dict[str, str]) -> dict[str, str]:
        """The text the user last read of each section, recording the current text of
        any section seen for the first time."""
        seen = _read_json(self.seen_path, {})
        new = {k: v for k, v in sections.items() if k not in seen}
        if new:
            seen.update(new)
            _write_json(self.seen_path, seen)
        return seen

    def mark_seen(self, sections: dict[str, str]) -> None:
        """Record `sections` (id -> the markdown the page showed) as read."""
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

    # ---- the main Claude Code session ----
    def read_parent(self) -> str:
        """Id of the Claude Code session that drives this one, "" when unknown."""
        return str(_read_json(self.claude_path, {}).get("parent", ""))

    def bind_parent(self, parent: str) -> bool:
        """Record the driving session. Returns True when it changed (a resumed session
        runs in a new Claude Code conversation, so threads fork from the new one)."""
        if not parent or parent == self.read_parent():
            return False
        _write_json(self.claude_path, {"parent": parent, "since": now_iso()})
        return True

    # ---- side threads ----
    def read_threads(self) -> list[dict[str, Any]]:
        if not self.threads_dir.is_dir():
            return []
        threads = [_read_json(p, None) for p in self.threads_dir.glob("t*.json")]
        return sorted((t for t in threads if t), key=lambda t: int(t["id"][1:]))

    def read_thread(self, tid: str) -> dict[str, Any]:
        t = _read_json(self.thread_path(tid), None)
        if t is None:
            raise SessionError(f"no thread {tid!r}")
        return t

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
            "claude_id": "",
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
        branch review (so the implementation starts), "review-code" that they asked to start the
        code review once the implementation is done, with the comments as last
        corrections, "answer" that they answered Claude questions (`answers`, see
        `answer_question`)."""
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
        return batch

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


def format_batch(
    slug: str,
    batch: dict[str, Any],
    outline: list[dict[str, Any]],
    questions: list[dict[str, Any]] | None = None,
) -> str:
    """How a batch appears in the Claude Code session (one Monitor event). `questions`
    gives the text of the Claude questions an answer batch answers."""
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
    if batch.get("action") == "review-code":
        lines.append("action: review-code (the user asked to start the code review from the page)")
    if batch.get("action") == "answer":
        asked = {q["id"]: q["text"] for q in questions or []}
        ids = ", ".join(a["question"] for a in batch.get("answers", []))
        lines.append(f"action: answer (the user answered Claude question {ids} from the page)")
        for a in batch.get("answers", []):
            text = " ".join(asked.get(a["question"], "").split())
            head = f"answer to {a['question']}" + (f" « {text} »" if text else "")
            answer = " — ".join(p for p in [", ".join(a["choices"]), a["text"]] if p)
            lines.append(f"{head}: {answer}")
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
