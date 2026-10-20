"""Session storage.

A session is one explanation, stored as a directory of plain files. The agent writes
the plan and the sections; the page reads them; the page writes review comments, which
reach the agent session through the inbox.

    <home>/sessions/<slug>/
        plan.json       title, initial_request, kind, workflow, repo, base, pr, variant,
                        outline, lexicon
        sections/<id>.md  the prose of one outline section         (written by the agent)
        sections/<id>.html  an HTML section instead: a self-contained HTML document
        sections/<id>/  its media folder: media files the agent produced for it
        audit.json      vocabulary-audit findings       (written by the agent and `check`)
        status.json     what the agent is doing now: phase, its writing run (start, run
                        set), the scoping done mark, the section files it saw  (`status`)
        phase-history.jsonl  each change of the phase, with its time  (`status`)
        change-history.json  every change of the model, oldest first     (written by `change`)
        terminal-messages.json  the user's later terminal messages      (written by `message`)
        implemented.json     the last model change each implementer run took into account
                                                            (written by `implemented`)
        code-map.md     where the feature lives in the code: its modules, where each
                        concept is implemented    (written by the planner and the implementer)
        request.md      the request transcript: the conversation that led to a review,
                        one `## User` or `## Agent` heading per message  (written by `request`)
        questions.json  agent questions put to the user, with their answers  (`question`, server)
        comments.json   every batch sent from the page, with status (server + CLI)
        inbox.jsonl     one line per batch, appended by the server  (read by `watch`)
        .watch_cursor   byte offset of the inbox already delivered  (written by `watch`)
        deliveries.jsonl  when each batch was handed to the agent  (`watch`, `wait`)
        watch.json      the watch's heartbeat: pid, time of its last check  (written by `watch`)
        agent.json     the agent session driving this one     (written by `new`, `open`)
        seen.json       the highlight baseline: each section's text, each doc's under
                        `doc:<path>`                                       (server)
        drafts.json     the drafts and the general note, shared by every page (server)
        threads/<id>.json  a side thread: messages, its own agent session id  (server)
        published.json  the publish record: link, time, fingerprint  (written by `publish`)
        doc-set.json    the doc set: the repo docs the Doc tab shows, each with its reason,
                        and the docs the user removed                    (`doc-set`)
        stale.json      the stale passages: doc passages the model contradicts  (`stale`)

A section is one element of the `outline` list in plan.json: {id, title, earns}: `earns`
is the one sentence the user reads under the title (what the section gives them, at most
EARNS_MAX characters). An optional `"overview": true` marks an overview section, which
names terms the sections after it introduce: the precedence check reports no early use
in it. A `brief` left in an older session's entry stays in the file, and
nothing reads it. Its text is one file of sections/, whose extension alone says which
kind of section it is: Markdown in <id>.md, or an HTML section in <id>.html, a
self-contained HTML document (its HTML, CSS and JavaScript) which may hold prose and
visuals alike, as an artifact does. A section has one file; when both exist (an agent
switched the kind and left the old file), every reader takes the .html file, and `check`
reports the pair. An HTML section's media folder, sections/<id>/, holds the media files
the agent produced for it (a manim render, a GIF), which have no web address: the
section loads them by a relative address (<id>/<file>), the page serves them, and the
published page and the vault export copy them along. An answer to a comment that belongs
in the explanation amends a section or adds one at its place in the outline; a `kind:
"question"` left by an older session is ignored, and the section reads as any other. A
refactor section, marked `part: "refactoring"`, belongs to the refactoring part of a
branch review or a refactor and is shown in the code tab; every other section is an
explanation section, shown in the Explanation tab. A refactor section about one item of
the diff carries its item fields under `item`: {files, verdict (one of the keys of the
session workflow's list in verdicts.yaml, next to this module), batch? (a short label or
number), implements, note, relations: [{to, kind, from?}]}, where the optional `from`
names which of the item's files a relation starts from (by default the first). One with
`kind: "finding"` and `items: [<section ids>]` is a finding across items.

The session workflow, `workflow` in plan.json, is the skill that drives the session:
view-concept, view-branch or view-refactor (a triage of existing code). It picks the
verdict set the page shows: verdicts.yaml holds one list per workflow, and each verdict
carries the `tone` the page colours it with. A session created before workflows existed
has no workflow and gets view-branch's list.

A side thread is a separate headless agent conversation that the user opens from the page
to discuss a passage without changing anything (see threads.py). Only a comment batch
reaches the main session.

A coordinated session (the view-branch workflow) is driven by a main session that only
coordinates: subagents do the work, each started from the session folder as
`view-concept context` prints it (context.py). The initial request is the user's first
message, kept verbatim in plan.json. When the review follows a conversation about the
feature, request.md, the request transcript, holds all of it: every message from the
first one about the feature, the user's and the agent's, verbatim and in order, under a
`## User` or `## Agent` heading each; messages only, no tool call or tool output. The
change history logs every change of the model: {id: m1…, at, by (planner or writer),
change (a few words), cause (the ids of the questions, comments or terminal messages
that led to it, or "own judgment")}. A session written before it has changes.json
instead, read as its change history. The terminal messages are the user's later messages
about the feature, typed in the terminal: {id: tm1…, at, phase (the phase when it was
recorded), text}. The code map is free Markdown that says which modules carry the
feature and where each concept lives, so a fresh agent does not explore the same code
again: the planner writes it in scoping, the implementer updates it when it moves code,
and every context loads it.

The agent is "listening" while a watch runs for the session: the watch rewrites watch.json
every HEARTBEAT_EVERY seconds, and a heartbeat older than LISTENING_FOR seconds (or none)
means no watch runs. The margin covers the seconds between a Monitor expiry and the re-arm.

An agent question is a question the agent puts to the user in the page rather than in the
terminal: {id: q1…, text, options, multi (several options may be picked), recommended?
(the answer the agent suggests: an option, which the page preselects, or a text it
pre-fills), background? (what the user needs to know to answer in scoping, before the model
exists: the mechanism as it is today, the trade-offs of each option; the page shows it
folded under the question, and no agent reads it; a question asked at the end of a section
carries none, and `reask` removes it),
section? (its anchor section: the section after which it is asked), status: "open" |
"answered" | "skipped" | "deferred", asked, answer?: {choices, text, at, from?}, skipped?
(when), unclear?: [{note, at}] (each « I don't understand »)}. Asking one sets the phase
"awaiting-answer", except during scoping: in the phase "scoping" the agent keeps asking
without waiting, so the phase stays. The page shows each open one in the scope block at
the top of the Plan tab, or, when it has an anchor section that is written, at the end of
that section. The user's answer reaches the session as a batch whose action is "answer",
carrying `answers: [{question, choices, text}]`; an entry also carries `threads`, the
side threads the user opened on the question from its box, when there are any. A skipped
question (the user leaves it to the agent's default) is sent the same way, its entry
`{question, skipped: true}`. An
unclear answer (« I don't understand »: the user cannot answer before the model explains
what the question needs) too, its entry `{question, unclear: true, note}`: the question
becomes "deferred", the agent anchors it to the section that will explain what it needs
(`anchor`), and asks it again once that section is written (`reask`: deferred → open). When the
user answers in the terminal instead, the agent runs `answered`: the question is marked
answered with `from: "terminal"`, empty choices and the user's words as text, and no
batch is sent, since the agent already has the answer; the phase is left to the agent.

Scoping ends when the user clicks « Write plan » (« Write model » in a branch review or
a refactor): a batch whose action is "plan", after which
every question still open is marked skipped (the agent treats them as skipped and writes
the plan, or the model in a branch review), except a section question (one with an anchor
section) whose section is not written yet: it stays open, and the page shows it at the end
of its section once written. A deferred question stays deferred: it is asked
again after its anchor section. During a pause of a branch review (the writer
stopped after a section whose questions are open, with sections left to write), « Go on »
sends a batch whose action is "go-on": the writer goes on, and the pause's questions stay
open; still open once every section is written, they hold back « Approve model » until
each is answered, skipped or deferred. « Grill me » sends a batch whose action is
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

drafts.json holds the drafts of the session (the comments written in the page that wait
for Send) and the general note, so every page open on the session, on any device, shows
the same ones. Each change a page makes (a draft added, edited or deleted, the note)
writes it, and the server tells the other pages (the session's live updates, event
`drafts`). The last edit of a draft wins, whichever page made it; a deleted draft's id
stays in `deleted`, so an edit to it arriving later is dropped. A batch clears the drafts
it carried and the note. Like seen.json, it is the page's write: it never counts as the
agent's activity.

The doc set is the list of repo docs the Doc tab shows: {docs: [{path, reason}],
removed: [paths]}. `path` is relative to the repo root (plan.json `repo`), `reason` the one
line that says why the doc is listed. An agent keeps it (`doc-set add` and `remove`); a
doc the user removed by a comment goes to `removed`, and an agent's refresh never adds it
back unless the user asks (`--user`). A doc of the set is a doc section: its text is the
file read from the worktree at each render, never copied into the session, so the user's
own edits show as the agent's do; a doc missing there reads as missing. Its highlight
baseline is kept in seen.json under `doc:<path>` and moves with every batch, like a
section's. A comment, a draft or a side thread on a doc's text is anchored to `doc:<path>`
(a batch prints it `(doc <path>)`), one on the doc set list to `doc-set`. The doc
sections stay out of the published page, the vault export, the publish
fingerprint and `check`, which read the outline's sections only. The base mark compares
a doc's worktree file (uncommitted changes included) with the same doc at the merge base
of the branch and its base branch (`merge_base`, `base_text`); a doc absent there was
created on the branch.

A stale passage is a passage of a doc of the doc set that the model contradicts: {id: s1…,
doc (its path), quote (the passage's exact text in the file), section (the model section
it contradicts, a reference model's, or ""), note (one line: why), at}. The reviewer
flags them (`stale`), and drops one fixed or dismissed. A flag whose quote is no longer
found in its doc's current text is not shown, and stays in the file.

A branch review's PR, once the agent opened it, is recorded in plan.json as `pr`: {url,
at} (written by `pr`). The page links it at the top and at the end of the code tab.

published.json is the publish record, what the session remembers of its last publish
(see publish.py): {url (the published page's link), at (when), fingerprint}. The
fingerprint is a hash of what a published page shows: the title, the published sections
(the explanation sections that are written, in outline order) and the lexicon. The
session is "out of date" when its fingerprint now differs from the recorded one;
comments, threads and highlights do not count, since a published page does not show them.
Unpublishing deletes the record.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any

from . import frame
from .render import md

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
    "go-on",
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
# The role agents a branch review's coordinator starts; a variant sets a model per role.
AGENT_ROLES = ("planner", "writer", "implementer", "reviewer")
THREAD_ID_RE = re.compile(r"^t[0-9]{1,6}$")
# A draft's id: the page makes it (a UUID). Its fields, as a batch comment takes them.
DRAFT_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
DRAFT_FIELDS = ("section", "quote", "prefix", "text", "thread")
# The pages of every session write the drafts file from the server's threadpool.
_DRAFTS_LOCK = threading.Lock()
# The key prefix of a doc's highlight baseline in seen.json, and of the anchor of a comment,
# a draft or a side thread on its text: `doc:<path>`. A comment on the doc set list is
# anchored to DOC_SET_ANCHOR.
DOC_KEY = "doc:"
DOC_SET_ANCHOR = "doc-set"
# The longest `earns` an outline entry may have: one sentence, read in the page's outline.
EARNS_MAX = 200
# The term kind of a lexicon entry (its optional `kind`): a core concept is one the model
# introduces or changes, defined in its home section's prose; a peripheral concept is any
# other term that is not plain language, which gets a tip only. Without one, core. Only
# the agents see it (the page draws every entry the same way). Not to be confused with an
# outline entry's `"kind": "finding"`.
TERM_KINDS = ("core", "peripheral")
HEARTBEAT_EVERY = 2.5  # seconds between two heartbeats of a running watch
LISTENING_FOR = 15.0  # seconds a heartbeat proves a watch runs
# The size an HTML section file stays under, embedded media included (the visual rule of the
# skills); its media folder does not count. `check` reports a file over it.
HTML_SECTION_LIMIT = 2 * 2**20


class SessionError(Exception):
    pass


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80] or "explanation"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def now_iso_ms() -> str:
    """Now, to the millisecond: for the records the run metrics compare (a pickup takes
    a few seconds)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """The records of an append-only file; a line cut by a crash is skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError):
            if isinstance(record := json.loads(line), dict):
                out.append(record)
    return out


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


def format_section_problem(p: dict[str, Any]) -> str:
    """One terminal line for a section problem of the check."""
    return f"{p['issue']:10} §{p['at']} ({p['section']})  {p['note']}"


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
    def change_history_path(self) -> Path:
        return self.dir / "change-history.json"

    @property
    def legacy_changes_path(self) -> Path:
        """What the change history was called when it only held accepted model changes."""
        return self.dir / "changes.json"

    @property
    def terminal_messages_path(self) -> Path:
        return self.dir / "terminal-messages.json"

    @property
    def implemented_path(self) -> Path:
        return self.dir / "implemented.json"

    @property
    def code_map_path(self) -> Path:
        return self.dir / "code-map.md"

    @property
    def request_path(self) -> Path:
        return self.dir / "request.md"

    @property
    def phase_history_path(self) -> Path:
        return self.dir / "phase-history.jsonl"

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
    def deliveries_path(self) -> Path:
        return self.dir / "deliveries.jsonl"

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
    def drafts_path(self) -> Path:
        return self.dir / "drafts.json"

    @property
    def threads_dir(self) -> Path:
        return self.dir / "threads"

    @property
    def published_path(self) -> Path:
        return self.dir / "published.json"

    @property
    def doc_set_path(self) -> Path:
        return self.dir / "doc-set.json"

    @property
    def stale_path(self) -> Path:
        return self.dir / "stale.json"

    def media_folder(self, sid: str) -> Path:
        """The media folder of section `sid`: sections/<sid>/."""
        if not sid or "/" in sid or sid in (".", ".."):
            raise SessionError(f"invalid section id {sid!r}")
        return self.sections_dir / sid

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
        initial_request: str = "",
        kind: str = "explanation",
        repo: str = "",
        workflow: str = "",
        base: str = "",
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
            "initial_request": initial_request,
            "kind": kind,
            "workflow": workflow,
            "created": date.today().isoformat(),
            "outline": [],
            "lexicon": [],
        }
        if repo:
            plan["repo"] = str(Path(repo).expanduser().resolve())
        if base:
            plan["base"] = base
        _write_json(self.plan_path, plan)
        return True

    # ---- reads ----
    def read_plan(self) -> dict[str, Any]:
        plan = _read_json(self.plan_path, {})
        plan.setdefault("title", self.slug)
        plan.setdefault("outline", [])
        plan.setdefault("lexicon", [])
        return plan

    def write_plan(
        self,
        outline: list[dict[str, Any]] | None = None,
        lexicon: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Replace the outline, the lexicon or both, and leave every other field of plan.json
        as it is (the initial request, the base branch, the workflow...)."""
        if outline is None and lexicon is None:
            raise SessionError("nothing to write: give an outline, a lexicon or both")
        plan = self.read_plan()
        if outline is not None:
            ids = [str(sec.get("id", "")) for sec in outline]
            if not all(ids) or any(not sec.get("title") for sec in outline):
                raise SessionError("every outline entry needs an id and a title")
            if len(set(ids)) != len(ids):
                raise SessionError("outline ids must be unique")
            long = [sec["id"] for sec in outline if len(str(sec.get("earns", ""))) > EARNS_MAX]
            if long:
                raise SessionError(
                    f"earns over {EARNS_MAX} characters: {', '.join(long)}. It is one "
                    "sentence for the user"
                )
            odd = [sec["id"] for sec in outline if sec.get("overview", False) not in (True, False)]
            if odd:
                raise SessionError(f"overview is true or false: {', '.join(odd)}")
            plan["outline"] = outline
        if lexicon is not None:
            if any(not t.get("term") or not t.get("section") for t in lexicon):
                raise SessionError("every lexicon entry needs a term and a section")
            odd = [t["term"] for t in lexicon if t.get("kind", "core") not in TERM_KINDS]
            if odd:
                raise SessionError(
                    f"unknown term kind for {', '.join(odd)}; one of {', '.join(TERM_KINDS)}"
                )
            plan["lexicon"] = lexicon
        known = {sec["id"] for sec in plan["outline"]}
        unknown = sorted({t["section"] for t in plan["lexicon"]} - known)
        if unknown:
            raise SessionError(f"lexicon entries point to no section: {', '.join(unknown)}")
        _write_json(self.plan_path, plan)
        return plan

    def set_pr(self, url: str) -> dict[str, Any]:
        """Record the session's PR (its link), once the agent opened it."""
        if not url.startswith(("https://", "http://")):
            raise SessionError(f"not a link: {url!r}")
        plan = self.read_plan()
        plan["pr"] = {"url": url, "at": now_iso()}
        _write_json(self.plan_path, plan)
        return plan["pr"]

    def read_variant(self) -> dict[str, Any]:
        """The setup the session runs with: {name, models}, `models` mapping a role to the
        model its agent runs on. A session that names none runs variant "none"."""
        variant = self.read_plan().get("variant") or {}
        return {"name": variant.get("name") or "none", "models": dict(variant.get("models", {}))}

    def set_variant(self, name: str, models: dict[str, str]) -> dict[str, Any]:
        """Name the setup the session runs with and the model of each role it sets, in one
        write, so the label matches what ran. A role left out keeps the coordinator's
        model; a helper takes its role agent's."""
        name = name.strip()
        if not name:
            raise SessionError("a variant needs a name")
        odd = sorted(set(models) - set(AGENT_ROLES))
        if odd:
            raise SessionError(f"unknown role {', '.join(odd)}; one of {', '.join(AGENT_ROLES)}")
        if any(not m.strip() for m in models.values()):
            raise SessionError("a model per role needs a model name")
        plan = self.read_plan()
        plan["variant"] = {"name": name, "models": models}
        _write_json(self.plan_path, plan)
        return plan["variant"]

    def section_files(self) -> dict[str, Path]:
        """Each written section's file, by id in id order: <id>.html for an HTML section,
        else <id>.md. When both exist, the .html file."""
        if not self.sections_dir.is_dir():
            return {}
        files = {p.stem: p for p in self.sections_dir.glob("*.md") if p.is_file()}
        files.update({p.stem: p for p in self.sections_dir.glob("*.html") if p.is_file()})
        return dict(sorted(files.items()))

    def read_sections(self) -> dict[str, str]:
        """Each written section's text: the Markdown of a Markdown section, the HTML
        document of an HTML section."""
        return {sid: p.read_text(encoding="utf-8") for sid, p in self.section_files().items()}

    def read_prose(self) -> dict[str, str]:
        """Each written section's words, as the precedence check reads them: a Markdown
        section without its code, diagrams and maths; an HTML section's visible text."""
        html = self.html_sections()
        return {
            sid: frame.visible_text(text) if sid in html else _strip_unmarked(text)
            for sid, text in self.read_sections().items()
        }

    def html_sections(self) -> set[str]:
        """The ids of the HTML sections."""
        return {sid for sid, p in self.section_files().items() if p.suffix == ".html"}

    def two_file_sections(self) -> list[str]:
        """The ids of the sections with both an <id>.md and an <id>.html file: the .md file
        is ignored."""
        return sorted(
            sid for sid in self.html_sections() if (self.sections_dir / f"{sid}.md").is_file()
        )

    def read_audit(self) -> list[dict[str, Any]]:
        return _read_json(self.audit_path, [])

    def check_precedence(self, write: bool = True) -> list[dict[str, Any]]:
        """The precedence check: every forward reference and early use of the lexicon.

        A term's home section is the outline section its lexicon entry names; an entry
        whose section is not in the outline is skipped. A forward reference is an
        entry's definition or tip using another term whose home section comes later;
        an early use is a term found in the prose of a section before its home
        section, other than an overview section (`"overview": true`). Returns one
        problem per finding: {issue, term, section (the id the audit entry points at),
        home (1-based position of the term's home section), at (position of the later
        home section, or of the early section), field, other}. With `write`, replaces
        the forward and early entries of audit.json and keeps every other entry, so a
        rerun is idempotent."""
        plan = self.read_plan()
        pos = {sec["id"]: i + 1 for i, sec in enumerate(plan["outline"])}
        order = [sec["id"] for sec in plan["outline"]]
        overviews = {sec["id"] for sec in plan["outline"] if sec.get("overview") is True}
        entries = [
            e for e in plan["lexicon"] if e.get("term", "").strip() and e.get("section") in pos
        ]
        prose = self.read_prose()
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
                if sid not in overviews and _uses(prose.get(sid, ""), e["term"]):
                    problems.append({
                        "issue": "early", "term": e["term"], "section": sid,
                        "home": home, "at": pos[sid], "field": "", "other": "",
                    })  # fmt: skip
        if write:
            kept = [a for a in self.read_audit() if a.get("issue") not in ("forward", "early")]
            _write_json(self.audit_path, kept + [precedence_audit_entry(p) for p in problems])
        return problems

    def check_sections(self) -> list[dict[str, Any]]:
        """The section problems of the check: how a section is written, not a term. Never
        written to audit.json, whose entries the page draws as an underline on their term:
        these name no word, so `check` only prints them, for the agent.

        - html-block: an HTML block in a Markdown section, raw HTML that starts its own
          paragraph (a line beginning with a tag, up to the next blank line), as Markdown
          reads it: inline HTML, and tags in a code block or a Mermaid diagram, are not.
        - two-files: a section with both <id>.md and <id>.html; the .md file is ignored.
        - too-large: an HTML section file over HTML_SECTION_LIMIT, its media folder apart.
        - stale-anchor: a waiting question (a deferred question, or an open one with an
          anchor section) anchored to a section the outline no longer has: it would never
          be asked again. The agent re-anchors it with `anchor`.

        Returns {issue, section, at (its position in the outline, "·" outside it), note},
        in outline order."""
        pos = {sec["id"]: i + 1 for i, sec in enumerate(self.read_plan()["outline"])}
        files = self.section_files()
        problems: list[dict[str, Any]] = []

        def add(issue: str, sid: str, note: str) -> None:
            problems.append({"issue": issue, "section": sid, "at": pos.get(sid, "·"), "note": note})

        for sid, path in files.items():
            if path.suffix == ".html":
                size = path.stat().st_size
                if size > HTML_SECTION_LIMIT:
                    add("too-large", sid, f"{path.name} is {size / 2**20:.1f} MB, over "
                        f"{HTML_SECTION_LIMIT // 2**20} MB: move its media to the media folder "
                        f"sections/{sid}/ or the web")  # fmt: skip
                continue
            for token in md.parse(path.read_text(encoding="utf-8")):
                head = token.content.strip().splitlines()[0] if token.content.strip() else ""
                if token.type != "html_block" or not head or head.startswith("<!--"):
                    continue
                line = token.map[0] + 1 if token.map else 0
                head = head if len(head) <= 60 else head[:57] + "..."
                add("html-block", sid, f"{path.name}:{line} {head}  move this HTML block "
                    "into an HTML section")  # fmt: skip
        for sid in self.two_file_sections():
            add("two-files", sid, f"{sid}.md and {sid}.html both present: the page shows "
                f"{sid}.html, {sid}.md is ignored")  # fmt: skip
        for q in self.read_questions():
            waiting = q["status"] == "deferred" or q["status"] == "open" and q.get("section")
            if waiting and q.get("section") and q["section"] not in pos:
                add("stale-anchor", q["section"], f"{q['id']} ({q['status']}) waits on it, a "
                    "section the outline no longer has: re-anchor it with view-concept "
                    "anchor")  # fmt: skip
        # In outline order; a section outside the outline last.
        return sorted(problems, key=lambda p: p["at"] if isinstance(p["at"], int) else len(pos) + 1)

    def read_comments(self) -> dict[str, Any]:
        return _read_json(self.comments_path, {"batches": []})

    def read_changes(self) -> list[dict[str, Any]]:
        """The change history, oldest first."""
        if self.change_history_path.exists() or not self.legacy_changes_path.exists():
            return _read_json(self.change_history_path, [])
        return _read_json(self.legacy_changes_path, [])

    def add_change(
        self, change: str, by: str = "", cause: list[str] | None = None
    ) -> dict[str, Any]:
        """Append one change of the model to the change history: a few words, who made it
        and what caused it."""
        if not change.strip():
            raise SessionError("empty change")
        changes = self.read_changes()
        d = {
            "id": f"m{len(changes) + 1}",
            "at": now_iso(),
            "by": by.strip(),
            "change": change.strip(),
            "cause": [c.strip() for c in cause or [] if c.strip()] or ["own judgment"],
        }
        changes.append(d)
        _write_json(self.change_history_path, changes)
        return d

    def read_implemented(self) -> list[dict[str, Any]]:
        """Each implementer run's trace, oldest first: `through`, the last change of the model
        it took into account, and `at`."""
        return _read_json(self.implemented_path, [])

    def mark_implemented(self, change_id: str) -> dict[str, Any]:
        """Record that the code now carries the model up to this change. Later changes of the
        model are not implemented yet (see `unimplemented_changes`)."""
        ids = [d["id"] for d in self.read_changes()]
        if change_id not in ids:
            raise SessionError(f"no change {change_id!r} in the change history")
        runs = self.read_implemented()
        if (
            runs
            and runs[-1]["through"] in ids
            and ids.index(change_id) < ids.index(runs[-1]["through"])
        ):
            raise SessionError(
                f"{change_id} comes before {runs[-1]['through']}, already implemented"
            )
        d = {"through": change_id, "at": now_iso()}
        runs.append(d)
        _write_json(self.implemented_path, runs)
        return d

    def implemented_through(self) -> str:
        """The last change of the model the code carries, "" when no implementer has run."""
        runs = self.read_implemented()
        return runs[-1]["through"] if runs else ""

    def model_approved(self) -> bool:
        """Whether the user approved the model (a branch review's « Approve model »), or an
        implementer already ran."""
        if self.read_implemented():
            return True
        return any(b.get("action") == "approve-model" for b in self.read_comments()["batches"])

    def unimplemented_changes(self) -> list[dict[str, Any]]:
        """The changes of the model the code does not carry yet: every change logged after
        the last one an implementer took into account. None before the model is approved:
        until then there is no code to keep up with the model."""
        if not self.coordinated or not self.model_approved():
            return []
        changes = self.read_changes()
        ids = [d["id"] for d in changes]
        through = self.implemented_through()
        start = ids.index(through) + 1 if through in ids else 0
        return changes[start:]

    def read_terminal_messages(self) -> list[dict[str, Any]]:
        return _read_json(self.terminal_messages_path, [])

    def read_code_map(self) -> str:
        """The code map: which modules carry the feature and where each concept lives, as
        the planner wrote it and the implementer keeps it. Empty when none is written."""
        try:
            return self.code_map_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def read_request(self) -> str:
        """The request transcript: the whole conversation that led to the review. Empty
        when none is written (the review started from a single message)."""
        try:
            return self.request_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def write_request(self, text: str) -> None:
        """Write the request transcript, replacing any previous one."""
        if not text.strip():
            raise SessionError("empty request transcript")
        self.request_path.write_text(text.strip() + "\n", encoding="utf-8")

    def add_terminal_message(self, text: str) -> dict[str, Any]:
        """Record a terminal message of the user about the feature, so the subagents,
        which never see the terminal, read it."""
        if not text.strip():
            raise SessionError("empty message")
        messages = self.read_terminal_messages()
        d = {
            "id": f"tm{len(messages) + 1}",
            "at": now_iso(),
            "phase": self.read_status().get("phase", ""),
            "text": text.strip(),
        }
        messages.append(d)
        _write_json(self.terminal_messages_path, messages)
        return d

    def read_questions(self) -> list[dict[str, Any]]:
        return _read_json(self.questions_path, [])

    def add_question(
        self,
        text: str,
        options: list[str] | None = None,
        multi: bool = False,
        recommended: str = "",
        background: str = "",
        section: str = "",
    ) -> dict[str, Any]:
        """Put an agent question to the user, and wait for the answer: the phase becomes
        "awaiting-answer". During scoping nothing waits: the phase stays "scoping".
        `recommended` is the answer the agent suggests, `background` what the user needs to
        know to answer, `section` the anchor section the page shows it after."""
        if not text.strip():
            raise SessionError("empty question")
        if section:
            self._check_section(section)
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
        if background.strip():
            q["background"] = background.strip()
        if section:
            q["section"] = section
        questions.append(q)
        _write_json(self.questions_path, questions)
        if self.read_status().get("phase") != "scoping":
            self.write_status("awaiting-answer")
        return q

    def _question(self, questions: list[dict[str, Any]], qid: str) -> dict[str, Any]:
        """The agent question `qid` of `questions`."""
        q = next((q for q in questions if q["id"] == qid), None)
        if q is None:
            raise SessionError(f"no question {qid!r}")
        return q

    def _open_question(self, questions: list[dict[str, Any]], qid: str) -> dict[str, Any]:
        """The open agent question `qid` of `questions`."""
        q = self._question(questions, qid)
        if q["status"] != "open":
            raise SessionError(f"{qid} is already {q['status']}")
        return q

    def _check_section(self, section: str) -> None:
        if section not in {s["id"] for s in self.read_plan().get("outline", [])}:
            raise SessionError(f"no section {section!r} in the outline")

    def _answer(self, qid: str, **entry: Any) -> dict[str, Any]:
        """The entry of an answer batch for `qid`, with `threads`, the side threads the user
        opened on the question, when there are any: the user discussed it there first."""
        tids = [t["id"] for t in self.read_threads() if t.get("question") == qid]
        return {"question": qid, **entry, **({"threads": tids} if tids else {})}

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
            [], action="answer", answers=[self._answer(qid, choices=choices, text=text)]
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
        batch = self.add_batch([], action="answer", answers=[self._answer(qid, skipped=True)])
        q["status"] = "skipped"
        q["skipped"] = batch["sent"]
        _write_json(self.questions_path, questions)
        return batch

    def unclear_question(self, qid: str, note: str = "") -> dict[str, Any]:
        """The user cannot answer an open agent question yet (« I don't understand »): the
        model has to explain what it needs first. Sent at once, as an answer batch whose
        entry is `{question, unclear: true, note}`; the question becomes "deferred" until
        the agent asks it again (`reask`). Returns the batch."""
        questions = self.read_questions()
        q = self._open_question(questions, qid)
        note = note.strip()
        batch = self.add_batch(
            [], action="answer", answers=[self._answer(qid, unclear=True, note=note)]
        )
        q["status"] = "deferred"
        q.setdefault("unclear", []).append({"note": note, "at": batch["sent"]})
        _write_json(self.questions_path, questions)
        return batch

    def anchor_question(self, qid: str, section: str) -> dict[str, Any]:
        """Set the anchor section of an open or deferred agent question: the section after
        which it is asked. Returns the question."""
        questions = self.read_questions()
        q = self._question(questions, qid)
        if q["status"] not in ("open", "deferred"):
            raise SessionError(f"{qid} is already {q['status']}")
        self._check_section(section)
        q["section"] = section
        _write_json(self.questions_path, questions)
        return q

    def reask_question(self, qid: str, text: str = "", recommended: str = "") -> dict[str, Any]:
        """Ask a deferred agent question again, under the same id, once the model explains
        what it needs: it is open again, with a new text or recommended answer when given.
        Its background is removed: the background serves the user in scoping only, and
        the question is now asked at the end of the section that explains it. The phase
        becomes "awaiting-answer", as when a question is asked. Returns the question."""
        questions = self.read_questions()
        q = self._question(questions, qid)
        if q["status"] != "deferred":
            raise SessionError(f"{qid} is {q['status']}, not deferred")
        q["status"] = "open"
        if text.strip():
            q["text"] = text.strip()
        q.pop("background", None)
        if recommended.strip():
            q["recommended"] = recommended.strip()
        q["reasked"] = now_iso()
        _write_json(self.questions_path, questions)
        if self.read_status().get("phase") != "scoping":
            self.write_status("awaiting-answer")
        return q

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

    # ---- the doc set ----
    def read_doc_set(self) -> dict[str, Any]:
        """The doc set: {docs: [{path, reason}], removed: [paths]}, empty without a file."""
        data = _read_json(self.doc_set_path, {})
        return {"docs": list(data.get("docs", [])), "removed": list(data.get("removed", []))}

    def add_doc(self, path: str, reason: str, user: bool = False) -> dict[str, Any]:
        """Add a doc to the doc set, or change its reason. A doc the user removed is
        refused unless `user` (the user asked for it in a comment), which takes it out of
        `removed`. The doc need not exist yet: the branch may create it."""
        path = doc_path(path)
        if not reason.strip():
            raise SessionError("a doc of the doc set needs a reason")
        data = self.read_doc_set()
        if path in data["removed"]:
            if not user:
                raise SessionError(
                    f"{path} was removed by the user: add it back only when the user asks (--user)"
                )
            data["removed"].remove(path)
        entry = {"path": path, "reason": " ".join(reason.split())}
        at = next((i for i, d in enumerate(data["docs"]) if d.get("path") == path), None)
        if at is None:
            data["docs"].append(entry)
        else:
            data["docs"][at] = entry
        _write_json(self.doc_set_path, data)
        return entry

    def remove_doc(self, path: str, user: bool = False) -> None:
        """Remove a doc from the doc set; `user` (the user asked in a comment) records it
        in `removed`, so an agent's refresh never adds it back."""
        path = doc_path(path)
        data = self.read_doc_set()
        listed = any(d.get("path") == path for d in data["docs"])
        if not listed and not user:
            raise SessionError(f"{path} is not in the doc set")
        data["docs"] = [d for d in data["docs"] if d.get("path") != path]
        if user and path not in data["removed"]:
            data["removed"].append(path)
        _write_json(self.doc_set_path, data)

    def repo_dir(self) -> Path | None:
        """The worktree a code session works in (plan.json `repo`), None without one."""
        repo = self.read_plan().get("repo")
        return Path(repo) if repo else None

    def doc_file(self, path: str) -> Path | None:
        """Where doc `path` lives in the worktree, None when the session has no repo or the
        path leads out of it (a symbolic link included). The file may not exist."""
        repo = self.repo_dir()
        if repo is None:
            return None
        root = repo.resolve()
        try:
            file = (root / doc_path(path)).resolve()
        except SessionError:  # a path written into doc-set.json by hand
            return None
        return file if file.is_relative_to(root) else None

    def read_docs(self) -> dict[str, str | None]:
        """The text of each doc of the doc set, read from the worktree on every call (no
        copy in the session), in the doc set's order: None for a doc missing there."""
        out: dict[str, str | None] = {}
        for d in self.read_doc_set()["docs"]:
            file = self.doc_file(d["path"])
            out[d["path"]] = (
                file.read_text(encoding="utf-8", errors="replace")
                if file is not None and file.is_file()
                else None
            )
        return out

    def doc_texts(self) -> dict[str, str]:
        """The docs that exist, keyed as their highlight baseline is: `doc:<path>`."""
        return {DOC_KEY + p: t for p, t in self.read_docs().items() if t is not None}

    # ---- stale passages ----
    def read_stale(self) -> list[dict[str, Any]]:
        """Every stale passage flagged, shown or not: [{id, doc, quote, section, note, at}]."""
        return _read_json(self.stale_path, [])

    def shown_stale(self, docs: dict[str, str | None] | None = None) -> list[dict[str, Any]]:
        """The stale passages the page shows: those whose quote is still found in their
        doc's current text (`docs`, the doc set's texts, read when not given). A flag whose
        passage changed, or whose doc left the doc set, is not shown, and stays in the
        file."""
        docs = self.read_docs() if docs is None else docs
        return [
            f
            for f in self.read_stale()
            if (text := docs.get(f.get("doc", ""))) is not None and _found(f.get("quote", ""), text)
        ]

    def add_stale(self, doc: str, quote: str, note: str, section: str = "") -> dict[str, Any]:
        """Flag a stale passage of a doc of the doc set: `quote` is the passage's exact
        text in the file, `section` the model section it contradicts (or a reference
        model's), `note` one line saying why."""
        doc = doc_path(doc)
        text = self.read_docs().get(doc, None)
        if doc not in {d["path"] for d in self.read_doc_set()["docs"]}:
            raise SessionError(f"{doc} is not in the doc set")
        if not quote.strip() or not note.strip():
            raise SessionError("a stale passage needs its quote and a note")
        if text is None or not _found(quote, text):
            raise SessionError(f"the quote is not in {doc}: copy the passage as the file has it")
        flags = self.read_stale()
        n = max((int(f["id"][1:]) for f in flags if str(f.get("id", ""))[1:].isdigit()), default=0)
        flag = {
            "id": f"s{n + 1}",
            "doc": doc,
            "quote": quote.strip(),
            "section": section.strip(),
            "note": " ".join(note.split()),
            "at": now_iso(),
        }
        _write_json(self.stale_path, [*flags, flag])
        return flag

    def drop_stale(self, ids: list[str]) -> None:
        """Remove stale passages, fixed or dismissed."""
        flags = self.read_stale()
        unknown = sorted(set(ids) - {f.get("id") for f in flags})
        if unknown:
            raise SessionError(f"no stale passage {', '.join(unknown)}")
        _write_json(self.stale_path, [f for f in flags if f.get("id") not in ids])

    def merge_base(self) -> str:
        """The commit where the branch left its base branch (plan.json `base`, else main):
        `git merge-base <base> HEAD` in the worktree. "" when git cannot tell (no repo,
        not a git repository, no such base): the docs then carry no base mark."""
        repo = self.repo_dir()
        if repo is None:
            return ""
        base = str(self.read_plan().get("base") or "main")
        return (_git(repo, "merge-base", base, "HEAD") or "").strip()

    def base_text(self, path: str, commit: str) -> str | None:
        """Doc `path` as it was at `commit` (the merge base), None when it did not exist
        there: a doc the branch created."""
        repo = self.repo_dir()
        if repo is None or not commit:
            return None
        return _git(repo, "show", f"{commit}:{doc_path(path)}")

    def doc_files(self) -> list[Path]:
        """The worktree file of each doc of the doc set, for `signature`."""
        files = (self.doc_file(d["path"]) for d in self.read_doc_set()["docs"])
        return [f for f in files if f is not None]

    # ---- the drafts file ----
    def read_drafts(self) -> dict[str, Any]:
        """The drafts file: {drafts: [{id, section, quote, prefix, text, thread?}], note,
        deleted: [ids]}. The page writes it, every page open on the session reads it."""
        data = _read_json(self.drafts_path, {})
        return {
            "drafts": list(data.get("drafts", [])),
            "note": str(data.get("note", "")),
            "deleted": list(data.get("deleted", [])),
        }

    def save_draft(self, draft: dict[str, Any]) -> bool:
        """Add or replace draft `draft["id"]`: the last edit wins, whichever page made it.
        An edit to a deleted draft is dropped: returns False."""
        did = str(draft.get("id", ""))
        if not DRAFT_ID_RE.match(did):
            raise SessionError(f"invalid draft id {did!r}")
        with _DRAFTS_LOCK:
            data = self.read_drafts()
            if did in data["deleted"]:
                return False
            entry = {k: str(draft.get(k) or "") for k in DRAFT_FIELDS}
            entry["id"] = did
            if not entry["thread"]:
                del entry["thread"]
            at = next((i for i, d in enumerate(data["drafts"]) if d.get("id") == did), None)
            if at is None:
                data["drafts"].append(entry)
            else:
                data["drafts"][at] = entry
            _write_json(self.drafts_path, data)
            return True

    def delete_drafts(self, ids: list[str]) -> None:
        """Delete drafts `ids` on every page: an edit to one arriving later is dropped."""
        with _DRAFTS_LOCK:
            data = self.read_drafts()
            data["drafts"] = [d for d in data["drafts"] if d.get("id") not in ids]
            data["deleted"] = [*data["deleted"], *(i for i in ids if i not in data["deleted"])]
            _write_json(self.drafts_path, data)

    def save_note(self, note: str) -> None:
        with _DRAFTS_LOCK:
            data = self.read_drafts()
            data["note"] = note
            _write_json(self.drafts_path, data)

    def import_drafts(self, drafts: list[dict[str, Any]], note: str) -> None:
        """Move a browser's drafts and note kept before the drafts file: they go after those
        already there; a draft already in the file (same id) or deleted is skipped."""
        with _DRAFTS_LOCK:
            data = self.read_drafts()
            known = {d.get("id") for d in data["drafts"]} | set(data["deleted"])
            for d in drafts:
                did = str(d.get("id", ""))
                if not DRAFT_ID_RE.match(did) or did in known:
                    continue
                entry = {k: str(d.get(k) or "") for k in DRAFT_FIELDS}
                entry["id"] = did
                if not entry["thread"]:
                    del entry["thread"]
                data["drafts"].append(entry)
                known.add(did)
            if note.strip():
                data["note"] = "\n\n".join(n for n in (data["note"].strip(), note.strip()) if n)
            _write_json(self.drafts_path, data)

    def clear_sent_drafts(self, ids: list[str]) -> None:
        """After a batch: the drafts it carried and the note are gone from every page. A sent
        draft counts as deleted, so an edit to it arriving later is dropped."""
        with _DRAFTS_LOCK:
            data = self.read_drafts()
            data["drafts"] = [d for d in data["drafts"] if d.get("id") not in ids]
            data["deleted"] = [*data["deleted"], *(i for i in ids if i not in data["deleted"])]
            data["note"] = ""
            _write_json(self.drafts_path, data)

    def drafts_signature(self) -> tuple:
        """Changes whenever the drafts file changes; kept apart from `signature` so a draft
        typed on another page redraws the review, not the explanation."""
        return _stat_signature([self.drafts_path])

    def read_status(self) -> dict[str, Any]:
        return _read_json(self.status_path, {"phase": "idle"})

    def write_status(
        self,
        phase: str,
        section: str | list[str] = "",
        message: str = "",
        done: bool = False,
    ) -> dict[str, Any]:
        """Declare the phase the agent is in.

        `since` is the time of this call (seconds, compared with batch times) and `at` the
        same time as an epoch float, compared with file modification times; `files` lists
        the sections that have a file now, so a section file that appears later is a trace
        of writing (see `shown_status`).

        A writing run starts on the call that enters "writing": `run` = {start, set}, the
        run set being the sections named, or, when none is named, every section of the
        outline with no file yet, or the whole outline when every section has one. A
        writing call during a writing run keeps the run's start and adds the sections it
        names to the set. Any other phase ends the run. `done` (phase "scoping" only) is
        the scoping done mark: the agent has nothing more to ask. A phase other than the
        previous one is appended to the phase history (`read_phase_history`)."""
        if phase not in PHASES:
            raise SessionError(f"unknown phase {phase!r}; one of {', '.join(PHASES)}")
        if done and phase != "scoping":
            raise SessionError("the scoping done mark goes with the phase 'scoping' only")
        sections = [section] if isinstance(section, str) else list(section)
        sections = list(dict.fromkeys(s for s in sections if s))
        previous = self.read_status()
        files = list(self.section_files())
        at = time.time()
        status: dict[str, Any] = {
            "phase": phase,
            "section": sections[0] if sections else "",
            "message": message,
            "since": now_iso(),
            "at": at,
            "files": files,
        }
        if phase == "writing":
            run = previous.get("run") if previous.get("phase") == "writing" else None
            if run:
                run = {**run, "set": run["set"] + [s for s in sections if s not in run["set"]]}
            else:
                run = {"start": at, "set": sections or self._unwritten(set(files))}
            status["run"] = run
        if done:
            status["done"] = True
        _write_json(self.status_path, status)
        if phase != previous.get("phase"):
            _append_jsonl(self.phase_history_path, {"phase": phase, "at": now_iso_ms()})
        return status

    def read_phase_history(self) -> list[dict[str, Any]]:
        """Each change of the declared phase, {phase, at}, oldest first: when the page
        started waiting for the user and when it stopped (the run metrics' waiting split).
        status.json keeps the current phase only."""
        return _read_jsonl(self.phase_history_path)

    def _unwritten(self, had: set[str]) -> list[str]:
        """The run set of a run that names none: the outline's sections with no file in
        `had`, or the whole outline when every one has a file."""
        outline = [s["id"] for s in self.read_plan().get("outline", [])]
        return [sid for sid in outline if sid not in had] or outline

    def section_times(self) -> dict[str, float]:
        """Each section file's modification time, by id."""
        return {sid: p.stat().st_mtime for sid, p in self.section_files().items()}

    def shown_status(self) -> dict[str, Any]:
        """The status as the page shows it: `status.json` plus
        - `shown`: the phase the banner shows, the derived phase when a trace in the
          session files is later than the last status call, else the declared `phase`;
        - `derived`: whether `shown` comes from a trace;
        - `run`: while `shown` is "writing", {start, set, written}: the run set in outline
          order and its sections written in this run (file modified since the run's
          start); None otherwise;
        - `scoping_done`: the scoping done mark, unless a question was asked or a batch
          sent after it.

        A trace is a change only one kind of step makes: a section file that appears where
        there was none (writing; the run starts at the first such file, its set the
        sections that had no file before it), a plan change while no section has a file
        (planning, outside scoping), an audit file change except during a writing run with
        sections of its set left (audit). The latest trace wins."""
        status = self.read_status()
        phase = status.get("phase", "idle")
        since = status.get("at")
        times = self.section_times()
        outline = [s["id"] for s in self.read_plan().get("outline", [])]
        traces: list[tuple[float, str]] = []
        run: dict[str, Any] | None = None
        if phase == "writing":
            run = status.get("run") or {
                "start": since or 0.0,
                "set": [status["section"]] if status.get("section") else outline,
            }
        # A status written before `files` existed cannot tell a new file from a rewritten
        # one, so it derives nothing; nor does a session with no status call.
        if since is not None and "files" in status:
            had = set(status["files"])
            new = {sid: t for sid, t in times.items() if sid not in had and t > since}
            if new and phase != "writing":
                run = {"start": min(new.values()), "set": self._unwritten(had)}
                traces.append((max(new.values()), "writing"))
            plan_t = _mtime(self.plan_path)
            if plan_t and plan_t > since and not times and phase not in ("scoping", "planning"):
                traces.append((plan_t, "planning"))
            audit_t = _mtime(self.audit_path)
            left = run and any(times.get(sid, -1.0) < run["start"] for sid in run["set"])
            if audit_t and audit_t > since and phase != "audit" and not left:
                traces.append((audit_t, "audit"))
        shown = max(traces)[1] if traces else phase
        out = {**status, "shown": shown, "derived": shown != phase, "run": None}
        if shown == "writing" and run:
            order = {sid: i for i, sid in enumerate(outline)}
            ids = sorted(run["set"], key=lambda sid: order.get(sid, len(order)))
            written = [sid for sid in ids if times.get(sid, -1.0) >= run["start"]]
            out["run"] = {"start": iso_time(run["start"]), "set": ids, "written": written}
        out["scoping_done"] = bool(phase == "scoping" and status.get("done")) and not any(
            t > status.get("since", "")
            for t in [*self._asked_times(), *(b["sent"] for b in self.read_comments()["batches"])]
        )
        return out

    def _asked_times(self) -> list[str]:
        """When each agent question was asked or asked again."""
        return [t for q in self.read_questions() for t in (q.get("asked"), q.get("reasked")) if t]

    def last_activity(self) -> str:
        """When the agent last wrote a session file, "" when never. Only what the agent
        writes counts: the page's own writes (a batch, an answer, seen.json, drafts.json) and the
        watch's heartbeat do not; questions count by when they were asked, comments by
        when they were resolved."""
        paths = [
            self.plan_path,
            self.audit_path,
            self.status_path,
            self.change_history_path,
            self.legacy_changes_path,
            self.implemented_path,
            self.terminal_messages_path,
            self.code_map_path,
            self.request_path,
            self.doc_set_path,
            self.stale_path,
            *self.section_files().values(),
        ]
        times = [iso_time(t) for p in paths if (t := _mtime(p))]
        times += self._asked_times()
        for b in self.read_comments()["batches"]:
            times += [t for x in [b, *b["comments"]] if (t := x.get("resolved_at"))]
        return max(times, default="")

    def batch_progress(self) -> dict[str, Any] | None:
        """Where the last batch sent from the page stands: {id, sent, action, comments,
        answers, stage}, `stage` being "sent" while it waits in the inbox, "received" once
        the delivery mark (the watch's cursor) passed it, "acted" once the agent wrote a
        session file after receiving it. None when no batch was sent."""
        batches = self.read_comments()["batches"]
        if not batches:
            return None
        b = batches[-1]
        out = {
            "id": b["id"],
            "sent": b["sent"],
            "action": b.get("action", ""),
            "comments": len(b["comments"]),
            "answers": len(b.get("answers", [])),
            "stage": "sent",
        }
        try:
            cursor = int(self.cursor_path.read_text())
        except (FileNotFoundError, ValueError):
            cursor = 0
        size = _mtime(self.inbox_path) and self.inbox_path.stat().st_size
        delivered = _mtime(self.cursor_path)
        if size and cursor >= size and delivered:
            out["stage"] = "acted" if self.last_activity() > iso_time(delivered) else "received"
        return out

    def record_delivery(self, batch_id: str) -> None:
        """Record that the watch or a wait handed batch `batch_id` to the agent now."""
        _append_jsonl(self.deliveries_path, {"batch": batch_id, "at": now_iso_ms()})

    def read_deliveries(self) -> dict[str, str]:
        """When each batch was handed to the agent, by batch id (the first delivery when
        a batch was delivered twice). Pickup time runs from a batch's `sent` to it."""
        out: dict[str, str] = {}
        for d in _read_jsonl(self.deliveries_path):
            out.setdefault(str(d.get("batch", "")), str(d.get("at", "")))
        return out

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
            self.change_history_path,
            self.legacy_changes_path,
            self.implemented_path,
            self.questions_path,
            self.published_path,
        ]
        if self.sections_dir.is_dir():
            paths += sorted([*self.sections_dir.glob("*.md"), *self.sections_dir.glob("*.html")])
        # The docs of the doc set are files of the worktree: an edit there re-renders too.
        paths += [self.doc_set_path, self.stale_path]
        with contextlib.suppress(SessionError):
            paths += self.doc_files()
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
        record = _read_json(self.agent_path, {})
        return {key: str(value) for key, value in record.items() if key != "conversations"}

    def conversations(self) -> list[str]:
        """Every agent conversation the session ran in, oldest first, the current one
        (`parent`) last. A session opened from a new conversation (after /clear, the next
        day) adds it; the earlier ones stay, so the runs they hold can still be found. A
        session recorded before the list existed has its `parent` only."""
        listed = _read_json(self.agent_path, {}).get("conversations")
        if isinstance(listed, list):
            return [str(c) for c in listed if c]
        parent = self.read_parent()
        return [parent] if parent else []

    def read_parent(self) -> str:
        """Id of the agent conversation that drives this one, "" when unknown."""
        return self.read_agent().get("parent", "")

    def has_written(self) -> bool:
        """Whether what « Write plan » or « Write model » asks for exists already, so the
        button asks for a rewrite: the plan, or in a coordinated session the sections (its
        planner drafts an outline before scoping ends)."""
        return bool(self.read_sections() if self.coordinated else self.read_plan()["outline"])

    @property
    def coordinated(self) -> bool:
        """Whether the main session only coordinates subagents (the view-branch workflow)."""
        return self.read_plan().get("workflow") == "view-branch"

    def fork_parent(self) -> str:
        """The conversation a side thread forks from, "" when it starts from the folder: a
        coordinated session's main conversation holds coordination, not content."""
        return "" if self.coordinated else self.read_parent()

    def bind_agent(self, agent: str, parent: str = "", name: str = "") -> bool:
        """Record the agent driving the session. Returns True when it changed (a resumed
        session runs in a new agent conversation, so threads fork from the new one). The
        conversation joins the session's list of conversations (`conversations`)."""
        if not agent:
            return False
        current = self.read_agent()
        record = {"agent": agent, "parent": parent, "name": name or current.get("name", "")}
        if all(current.get(key) == value for key, value in record.items()):
            return False
        conversations = self.conversations()
        if parent and parent not in conversations:
            conversations.append(parent)
        _write_json(self.agent_path, {**record, "since": now_iso(), "conversations": conversations})
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

    def new_thread(
        self, section: str = "", quote: str = "", prefix: str = "", question: str = ""
    ) -> dict[str, Any]:
        """Create an empty thread, anchored to a passage like a comment, to an open agent
        question (`question`, its id: the user discusses it before answering), or to
        nothing."""
        if question:
            self._open_question(self.read_questions(), question)
        n = max((int(t["id"][1:]) for t in self.read_threads()), default=0) + 1
        thread = {
            "id": f"t{n}",
            "created": now_iso(),
            "section": section,
            "quote": quote,
            "prefix": prefix,
            "question": question,
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
        """Delete a thread that led to nothing. One a sent comment or a sent answer points
        to is kept: the session reads it to act on that comment or answer."""
        path = self.thread_path(tid)
        if not path.exists():
            raise SessionError(f"no thread {tid!r}")
        batches = self.read_comments()["batches"]
        commented = {c.get("thread") for b in batches for c in b["comments"]}
        answered = {t for b in batches for a in b.get("answers", []) for t in a.get("threads", [])}
        if tid in commented | answered:
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
        corrections, "answer" that they answered, skipped or did not understand agent
        questions (`answers`, see `answer_question`, `skip_question` and
        `unclear_question`), "plan" that they ended scoping (every open question is then
        marked skipped, but a section question whose section is not written yet), "grill"
        that they started a grill, "stop-grill" that they stopped it, and "go-on" that they
        asked the writer of a branch review to go on past a pause, leaving its questions
        open."""
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
        if action == "plan":
            batch["rewrite"] = self.has_written()
        batches.append(batch)
        _write_json(self.comments_path, data)
        with self.inbox_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(batch, ensure_ascii=False) + "\n")
        # Highlights show what changed since the last batch: every baseline moves here,
        # the docs' included.
        self.mark_seen({**self.read_sections(), **self.doc_texts()})
        if action == "plan":
            self._skip_open_questions(batch["sent"])
        return batch

    def _skip_open_questions(self, at: str) -> None:
        """Mark the open agent questions skipped: scoping ended without their answers. A
        section question whose anchor section is not written yet stays open, to be asked at
        the end of that section once it is; a deferred question stays deferred: it is asked
        again after its anchor section."""
        questions = self.read_questions()
        written = self.section_files()
        open_ = [
            q
            for q in questions
            if q["status"] == "open" and (not q.get("section") or q["section"] in written)
        ]
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
                    c["resolved_at"] = now_iso()
                    if reply:
                        c["reply"] = reply
                    touched.append(c["id"])
            if b["id"] in wanted and not b["comments"]:
                b["resolved_at"] = now_iso()
                if reply:
                    b["reply"] = reply
        unknown = wanted - set(touched) - {b["id"] for b in data["batches"]}
        if unknown:
            raise SessionError(f"unknown id(s): {', '.join(sorted(unknown))}")
        _write_json(self.comments_path, data)
        return touched

    # ---- the publish record ----
    def published_sections(self, plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """What a published page shows of the prose: every explanation section (no
        `"part": 2`) that is written, in outline order, as {id, number (its position in
        the outline, as the page numbers it), title, markdown (the file's text: the HTML
        document of an HTML section), html (whether it is an HTML section)}."""
        plan = plan or self.read_plan()
        sections = self.read_sections()
        html = self.html_sections()
        return [
            {"id": s["id"], "number": i + 1, "title": s.get("title", s["id"]),
             "markdown": sections[s["id"]], "html": s["id"] in html}
            for i, s in enumerate(plan["outline"])
            if s.get("part") != 2 and s["id"] in sections
        ]  # fmt: skip

    def fingerprint(self) -> str:
        """A hash of what a published page shows: the title, the published sections and
        the lexicon. The publish date, comments and highlights are left out."""
        plan = self.read_plan()
        content = {
            "title": str(plan["title"]).strip() or self.slug,
            "sections": [
                [s["id"], s["title"], s["markdown"]] for s in self.published_sections(plan)
            ],
            "lexicon": [
                [str(t.get(k) or "") for k in ("term", "section", "definition", "tip")]
                for t in plan["lexicon"]
            ],
        }
        canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def read_published(self) -> dict[str, Any]:
        """The publish record: {url, at, fingerprint}, {} when the session is not published."""
        return _read_json(self.published_path, {})

    def write_published(self, url: str, fingerprint: str) -> dict[str, Any]:
        record = {"url": url, "at": now_iso(), "fingerprint": fingerprint}
        _write_json(self.published_path, record)
        return record

    def delete_published(self) -> None:
        self.published_path.unlink(missing_ok=True)

    def is_out_of_date(self) -> bool:
        """Whether the session changed since its last publish: its fingerprint differs from
        the recorded one. A session never published is not out of date."""
        record = self.read_published()
        return bool(record) and record.get("fingerprint") != self.fingerprint()

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
        html = self.html_sections()
        sections = {
            sid: _export_html_section(self, sid, text, vault_dir)
            if sid in html
            else _externalize(text, vault_dir, self.slug)
            for sid, text in self.read_sections().items()
        }
        path.write_text(self.render_markdown(plan, sections), encoding="utf-8")
        return path

    def render_markdown(
        self, plan: dict[str, Any] | None = None, sections: dict[str, str] | None = None
    ) -> str:
        plan = plan or self.read_plan()
        sections = self.read_sections() if sections is None else sections
        title = str(plan["title"]).strip() or self.slug
        # Sessions created before the rename call it `question`.
        request = plan.get("initial_request", plan.get("question", ""))
        request = str(request).replace('"', "'")
        lines = [
            "---",
            "type: explanation",
            f'initial_request: "{request}"',
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
            lines += ["## Change history", "", format_changes(changes), ""]
        return "\n".join(lines)


# ---- export: media out of the note ----
# Markdown sections embed their visuals as base64 data URIs, and their widgets (step
# players, sliders) as raw HTML whose behaviour sits in inline on* attributes. Obsidian
# slows down on a note of several MB and does not run inline handlers, so the export moves
# both out of the note: each data URI becomes a file in <slug>/assets/, each widget a file
# in <slug>/widgets/ rendered by a dataviewjs block (Dataview plugin, JavaScript queries
# enabled) through <slug>/widget.js, which turns the on* attributes back into event
# listeners.

DATA_URI = re.compile(r"data:([a-z0-9.+/-]+);base64,([A-Za-z0-9+/=]+)")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(" + DATA_URI.pattern + r"\)")
ON_ATTR = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)
MEDIA_EXT = {
    "image/png": "png",
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
}

WIDGET_JS = """\
// Dataview view written by `view-concept export`: renders one widget of the note.
// The widget HTML keeps its behaviour in inline on* attributes, which Obsidian does not
// run, so each one is turned back into an event listener. src="assets/..." resolve
// against `root`, the vault path of this folder.
const { file, root } = input;
const resolve = p => app.vault.adapter.getResourcePath(`${root}/${p}`);
const html = (await app.vault.adapter.read(file))
  .replace(/src="(assets\\/[^"]+)"/g, (_, p) => `src="${resolve(p)}"`);
const box = dv.container.createDiv();
box.innerHTML = html;
for (const el of box.querySelectorAll("*")) {
  for (const a of [...el.attributes]) {
    if (!a.name.startsWith("on")) continue;
    const fn = new Function("event", a.value);
    el.removeAttribute(a.name);
    el.addEventListener(a.name.slice(2), function (event) { return fn.call(this, event); });
  }
}
"""


# An HTML section needs no guessing: its file is copied into <slug>/ with the frame's
# head written in (VAULT_FRAME_HEAD), with its media folder, and the note holds, under
# the section's title, a link to the file (it opens the section in the browser, as a page
# of its own, in the page's default theme) and a dataviewjs block that draws the section
# in a section frame inside the note, as the page does (frame.py), through
# <slug>/section.js, a copy of static/vault-section.js. The note does not hold the
# section's prose, so Obsidian's search does not find it.

# The head an exported HTML section gets: the theme tokens and frame.js, written next to
# it in <slug>/. section.js replaces these two links by the files' text (see there).
VAULT_FRAME_HEAD = '<link rel="stylesheet" href="frame.css"><script src="frame.js"></script>'


def _export_html_section(s: Session, sid: str, text: str, vault_dir: Path) -> str:
    """Copy an HTML section's file, with the frame's head, and its media folder into
    vault_dir/<slug>/, and return what the note holds in its place: a link to the file
    and the dataviewjs block that draws it."""
    media = vault_dir / s.slug
    rel = media.resolve().relative_to(_vault_root(vault_dir.resolve())).as_posix()
    media.mkdir(parents=True, exist_ok=True)
    (media / f"{sid}.html").write_text(frame.inject(text, VAULT_FRAME_HEAD), encoding="utf-8")
    if s.media_folder(sid).is_dir():
        shutil.copytree(s.media_folder(sid), media / sid, dirs_exist_ok=True)
    (media / "frame.css").write_text(frame.tokens_css(), encoding="utf-8")
    (media / "frame.js").write_text(frame.frame_js(), encoding="utf-8")
    view = (frame.STATIC / "vault-section.js").read_text(encoding="utf-8")
    view = view.replace("{SANDBOX}", frame.SANDBOX).replace("{HEAD}", json.dumps(VAULT_FRAME_HEAD))
    (media / "section.js").write_text(view, "utf-8")
    args = json.dumps({"file": f"{rel}/{sid}.html", "root": rel}, ensure_ascii=False)
    return (
        f"[Open this section in the browser]({s.slug}/{sid}.html)\n\n"
        f'```dataviewjs\nawait dv.view("{rel}/section", {args})\n```'
    )


def _vault_root(path: Path) -> Path:
    """The Obsidian vault holding `path`: the nearest ancestor with a .obsidian folder."""
    for p in [path, *path.parents]:
        if (p / ".obsidian").is_dir():
            return p
    return path


def _externalize(text: str, vault_dir: Path, slug: str) -> str:
    """Rewrite one section for the vault note, writing its media under vault_dir/<slug>/."""
    media = vault_dir / slug
    rel = media.resolve().relative_to(_vault_root(vault_dir.resolve())).as_posix()

    def save(mime: str, b64: str) -> str | None:
        ext = MEDIA_EXT.get(mime)
        if not ext:
            return None
        data = base64.b64decode(b64)
        name = f"{hashlib.sha1(data).hexdigest()[:12]}.{ext}"
        (media / "assets").mkdir(parents=True, exist_ok=True)
        if not (media / "assets" / name).exists():
            (media / "assets" / name).write_bytes(data)
        return name

    def asset_src(m: re.Match[str]) -> str:
        name = save(m.group(1), m.group(2))
        return f"assets/{name}" if name else m.group(0)

    def widget(block: str) -> str:
        html = DATA_URI.sub(asset_src, block)
        name = f"{hashlib.sha1(html.encode()).hexdigest()[:12]}.html"
        (media / "widgets").mkdir(parents=True, exist_ok=True)
        (media / "widgets" / name).write_text(html, encoding="utf-8")
        (media / "widget.js").write_text(WIDGET_JS, encoding="utf-8")
        args = json.dumps({"file": f"{rel}/widgets/{name}", "root": rel}, ensure_ascii=False)
        return f'```dataviewjs\nawait dv.view("{rel}/widget", {args})\n```'

    def image(m: re.Match[str]) -> str:
        name = save(m.group(2), m.group(3))
        return f"![{m.group(1)}]({slug}/assets/{name})" if name else m.group(0)

    parts = re.split(r"(\n\s*\n)", text)
    for i, part in enumerate(parts):
        if part.lstrip().startswith("<") and (DATA_URI.search(part) or ON_ATTR.search(part)):
            parts[i] = widget(part.strip())
        else:
            parts[i] = MD_IMAGE.sub(image, part)
    return "".join(parts)


def doc_path(path: str) -> str:
    """A doc's path as the doc set keeps it: relative to the repo root, in POSIX form,
    never leaving the repo."""
    raw = path.strip().replace("\\", "/")
    p = PurePosixPath(raw)
    if not raw or p.is_absolute() or ".." in p.parts or str(p) in ("", "."):
        raise SessionError(f"not a path inside the repo: {path!r}")
    return str(p)


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
        # When the session folder was made: a pending launch gives way to the first
        # session created in its project after it (launch.py).
        st = d.stat()
        born = getattr(st, "st_birthtime", st.st_ctime)
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
                "workflow": plan.get("workflow", ""),
                "repo": plan.get("repo", ""),
                "project": project_of(plan.get("repo", "")),
                "listening": s.is_listening(),
                "created_at": datetime.fromtimestamp(born, UTC).isoformat(timespec="milliseconds"),
            }
        )
    return sorted(out, key=lambda r: r["updated"], reverse=True)


# Where Claude Code puts the worktrees it creates (`claude -w`), under the main checkout.
WORKTREES_DIR = "/.claude/worktrees/"


@cache
def project_of(repo: str) -> str:
    """The project a session's repo belongs to: the main checkout of its git repository,
    so the sessions of every worktree of a repository group together. "" for a session
    with no repo (an explanation). A repo that no longer exists (a removed worktree) is
    cut at its worktrees folder, else kept as is."""
    if not repo:
        return ""
    try:
        common = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        common = ""
    if common.endswith("/.git"):
        return common.removesuffix("/.git")
    return repo.split(WORKTREES_DIR, 1)[0]


def _found(quote: str, text: str) -> bool:
    """Whether a quoted passage is in a text, spaces and line breaks aside."""
    quote = " ".join(quote.split())
    return bool(quote) and quote in " ".join(text.split())


def _git(repo: Path, *args: str) -> str | None:
    """The output of a read-only git command in `repo`, None when it fails."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, timeout=5, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def _mtime(path: Path) -> float | None:
    """A file's modification time, None when it does not exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def iso_time(ts: float) -> str:
    """An epoch time as the ISO time the session files use."""
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


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
    if batch.get("action") == "plan" and batch.get("rewrite", bool(outline)):
        # What the button writes exists already: the answers given since may change it.
        lines.append(
            "action: plan (the user asked to rewrite the plan from the page: open questions "
            "are marked skipped, but a section question whose section is not written yet; "
            "revise the plan with the answers, or the model in a branch review)"
        )
    elif batch.get("action") == "plan":
        lines.append(
            "action: plan (the user ended scoping from the page: open questions are marked "
            "skipped, but a section question whose section is not written yet; write the "
            "plan, or the model in a branch review)"
        )
    if batch.get("action") == "grill":
        lines.append(
            "action: grill (the user started a grill: ask every open design decision as a "
            "question with a recommended answer, until none is left)"
        )
    if batch.get("action") == "stop-grill":
        lines.append("action: stop-grill (the user stopped the grill)")
    if batch.get("action") == "go-on":
        lines.append(
            "action: go-on (the user asked to go on past the pause: write the next sections; "
            "the pause's questions stay open)"
        )
    if batch.get("action") == "answer":
        asked = {q["id"]: q["text"] for q in questions or []}
        answers = batch.get("answers", [])
        ids = ", ".join(a["question"] for a in answers)
        verb = (
            "skipped"
            if all(a.get("skipped") for a in answers)
            else "did not understand"
            if all(a.get("unclear") for a in answers)
            else "answered"
        )
        lines.append(f"action: answer (the user {verb} agent question {ids} from the page)")
        for a in answers:
            text = " ".join(asked.get(a["question"], "").split())
            quoted = f" « {text} »" if text else ""
            if a.get("skipped"):
                lines.append(f"{a['question']} skipped{quoted} (no answer: use your default)")
            elif a.get("unclear"):
                note = f": {a['note']}" if a.get("note") else ""
                lines.append(
                    f"{a['question']} unclear{quoted} (the user doesn't understand it yet: "
                    f"explain what it needs, then ask it again){note}"
                )
            else:
                parts = [", ".join(a.get("choices", [])), a.get("text", "")]
                answer = " — ".join(p for p in parts if p)
                lines.append(f"answer to {a['question']}{quoted}: {answer}")
            lines += [f"    (from side thread {t}: threads/{t}.json)" for t in a.get("threads", [])]
    if batch.get("note"):
        lines.append(f"note: {batch['note']}")
    lines += [format_comment(c, number) for c in batch["comments"]]
    return "\n".join(lines)


def format_comment(c: dict[str, Any], number: dict[str, int]) -> str:
    """One comment of a batch: where it is anchored (a section, a doc of the Doc tab by its
    path, the doc set list), its text, the thread it comes from."""
    sec = c["section"]
    if sec.startswith(DOC_KEY):
        where = f"(doc {sec.removeprefix(DOC_KEY)})"
    elif sec == DOC_SET_ANCHOR:
        where = "(doc set)"
    else:
        where = f"§{number[sec]} ({sec})" if sec in number else f"({sec or 'no section'})"
    quote = " ".join(c["quote"].split())
    lines = [f"[{c['id']}] {where} « {quote} »" if quote else f"[{c['id']}] {where}"]
    lines += [f"    {line}" for line in c["text"].splitlines()]
    if c.get("thread"):
        lines.append(f"    (from side thread {c['thread']}: threads/{c['thread']}.json)")
    return "\n".join(lines)


def format_changes(changes: list[dict[str, Any]]) -> str:
    """Markdown bullets, in the shape of a PR description's Decisions section."""
    out = []
    for d in changes:
        line = f"- {d['change']}"
        # `instead`, `why` and `files`: entries of a session written before the change history.
        if d.get("instead"):
            line += f", rather than {d['instead']}"
        if d.get("why"):
            line += f". {d['why']}"
        if d.get("files"):
            line += f" ({', '.join(f'`{f}`' for f in d['files'])})"
        out.append(line)
    return "\n".join(out)
