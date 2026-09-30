"""Session storage.

A session is one explanation, stored as a directory of plain files. Claude Code writes
the plan and the sections; the page reads them; the page writes review comments, which
reach the Claude Code session through the inbox.

    <home>/sessions/<slug>/
        plan.json       title, question, outline, lexicon          (written by Claude)
        sections/<id>.md  the prose of one outline section         (written by Claude)
        audit.json      vocabulary-audit findings                  (written by Claude)
        status.json     what Claude is doing now: phase, section    (written by `status`)
        decisions.json  decisions taken about the code              (written by `decide`)
        comments.json   every batch sent from the page, with status (server + CLI)
        inbox.jsonl     one line per batch, appended by the server  (read by `watch`)
        .watch_cursor   byte offset of the inbox already delivered  (written by `watch`)
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

HOME = Path(os.environ.get("EXPLAIN_VIEW_HOME", Path.home() / ".explain-view"))
SESSIONS = HOME / "sessions"
VAULT_DIR = Path(
    os.environ.get("EXPLAIN_VIEW_VAULT", Path.home() / "Documents" / "Vault" / "explanations")
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
# What the page shows in its status indicator; "awaiting-approval" also shows « Approve plan ».
PHASES = ("scoping", "planning", "awaiting-approval", "writing", "audit", "revising", "idle")
ACTIONS = ("", "approve-plan")
# "code": the explanation is about a repository — citations link into it, and the
# decisions it leads to are what outlives it. "explanation": understanding for its own sake.
KINDS = ("explanation", "code")


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
    def decisions_path(self) -> Path:
        return self.dir / "decisions.json"

    @property
    def inbox_path(self) -> Path:
        return self.dir / "inbox.jsonl"

    @property
    def cursor_path(self) -> Path:
        return self.dir / ".watch_cursor"

    def exists(self) -> bool:
        return self.plan_path.exists()

    # ---- creation ----
    def create(
        self, title: str, question: str = "", kind: str = "explanation", repo: str = ""
    ) -> bool:
        """Create the session. Returns False when it already existed (left untouched)."""
        if kind not in KINDS:
            raise SessionError(f"unknown kind {kind!r}; one of {', '.join(KINDS)}")
        if kind == "code" and not repo:
            raise SessionError("a code session needs --repo")
        if self.exists():
            return False
        self.sections_dir.mkdir(parents=True, exist_ok=True)
        plan: dict[str, Any] = {
            "title": title,
            "question": question,
            "kind": kind,
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

    def read_decisions(self) -> list[dict[str, Any]]:
        return _read_json(self.decisions_path, [])

    def add_decision(
        self, decision: str, why: str = "", instead: str = "", files: list[str] | None = None
    ) -> dict[str, Any]:
        """Append a decision. `instead` is the alternative that was rejected."""
        if not decision.strip():
            raise SessionError("empty decision")
        decisions = self.read_decisions()
        d = {
            "id": f"d{len(decisions) + 1}",
            "decision": decision.strip(),
            "why": why.strip(),
            "instead": instead.strip(),
            "files": files or [],
            "date": date.today().isoformat(),
        }
        decisions.append(d)
        _write_json(self.decisions_path, decisions)
        return d

    def read_status(self) -> dict[str, Any]:
        return _read_json(self.status_path, {"phase": "idle"})

    def write_status(self, phase: str, section: str = "", message: str = "") -> dict[str, Any]:
        if phase not in PHASES:
            raise SessionError(f"unknown phase {phase!r}; one of {', '.join(PHASES)}")
        status = {"phase": phase, "section": section, "message": message, "since": now_iso()}
        _write_json(self.status_path, status)
        return status

    def signature(self) -> tuple:
        """Changes whenever anything the page displays changes."""
        paths = [
            self.plan_path,
            self.audit_path,
            self.comments_path,
            self.status_path,
            self.decisions_path,
        ]
        if self.sections_dir.is_dir():
            paths += sorted(self.sections_dir.glob("*.md"))
        sig = []
        for p in paths:
            try:
                st = p.stat()
                sig.append((p.name, st.st_mtime_ns, st.st_size))
            except FileNotFoundError:
                sig.append((p.name, None, None))
        return tuple(sig)

    # ---- comments ----
    def add_batch(
        self, comments: list[dict[str, Any]], note: str = "", action: str = ""
    ) -> dict[str, Any]:
        """Record a batch sent from the page and append it to the inbox.

        `action` is a decision taken with the batch: "approve-plan" means the user
        approved the plan from the page, with the comments as last corrections."""
        if action not in ACTIONS:
            raise SessionError(f"unknown action {action!r}")
        note = note.strip()
        comments = [c for c in comments if str(c.get("text", "")).strip()]
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
                    "text": str(c["text"]).strip(),
                    "status": "sent",
                }
                for i, c in enumerate(comments)
            ],
        }
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
        if path.exists() and f"explain-view: {self.slug}\n" not in path.read_text(encoding="utf-8"):
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
            f"explain-view: {self.slug}",
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
        decisions = self.read_decisions()
        if decisions:
            lines += ["## Decisions", "", format_decisions(decisions), ""]
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


def format_batch(slug: str, batch: dict[str, Any], outline: list[dict[str, Any]]) -> str:
    """How a batch appears in the Claude Code session (one Monitor event)."""
    number = {s["id"]: i + 1 for i, s in enumerate(outline)}
    n = len(batch["comments"])
    lines = [f"explain-view · {slug} · batch {batch['id']} · {n} comment{'s' * (n != 1)}"]
    if batch.get("action") == "approve-plan":
        lines.append("action: approve-plan (the user approved the plan from the page)")
    if batch.get("note"):
        lines.append(f"note: {batch['note']}")
    for c in batch["comments"]:
        sec = c["section"]
        where = f"§{number[sec]} ({sec})" if sec in number else f"({sec or 'no section'})"
        quote = " ".join(c["quote"].split())
        lines.append(f"[{c['id']}] {where} « {quote} »" if quote else f"[{c['id']}] {where}")
        lines += [f"    {line}" for line in c["text"].splitlines()]
    return "\n".join(lines)


def format_decisions(decisions: list[dict[str, Any]]) -> str:
    """Markdown bullets, in the shape of a PR description's Decisions section."""
    out = []
    for d in decisions:
        line = f"- {d['decision']}"
        if d.get("instead"):
            line += f", rather than {d['instead']}"
        if d.get("why"):
            line += f". {d['why']}"
        if d.get("files"):
            line += f" ({', '.join(f'`{f}`' for f in d['files'])})"
        out.append(line)
    return "\n".join(out)
