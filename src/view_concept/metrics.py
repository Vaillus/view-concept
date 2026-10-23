"""Run metrics of a feature: where the time of a review goes, read from Claude Code's
transcripts and the session's own files. The Metrics tab draws what `session_metrics`
returns (`GET /api/s/{slug}/metrics`).

A **run** is one agent doing one job: a role agent's run (`kind: "role"`), a helper's part
of it (`"helper"`), or one **coordinator pass** (`"pass"`). Its identity: role, trigger,
parent run, model, variant.

- A role agent's or a helper's transcript is
  `<projects>/<repo dir>/<conversation id>/subagents/agent-<id>.jsonl`, beside its meta
  file `agent-<id>.meta.json`. A run is kept when its first prompt names `view-concept
  context <slug>` (the arguments, read as shell words, give `--role`, `--trigger` and
  `--section`), or when its parent is a kept run. A conversation can serve two sessions.
- A helper is a run whose meta file names a `parentAgentId`: its parent is that run, and
  it has its role agent's role. A role agent's parent is the coordinator pass whose Agent
  tool call carries the meta file's `toolUseId`.
- A coordinator pass is the coordinator's work on one event (a batch delivered to it, or
  the start of a role agent with no batch before it), until it waits for the next one with
  every agent it started ended. Batches delivered while a pass runs join it.

The projects folder is `~/.claude/projects`, or `$VIEW_CONCEPT_CLAUDE_PROJECTS`. The
session's conversations are `agent.json`'s `conversations`, else its `parent`. Only a
session whose agent is `claude` has runs; any other keeps its waiting split and quality
signals, which come from the session's files.

A run's time splits into **stretches**: each runs from one tool result to the next and
takes the activity of the tool call that ends it; a wait for a message with no tool
running (the agent waits on its helpers) is a stretch of its own, and the last stretch is
the report. A role agent's or a helper's stretch over STALL seconds is **stalled**:
counted apart, and left out of every sum (wall time, activities, model and tool time). A
coordinator pass's stretches never stall: its long stretches are its wait on the agents it
started, which stays agent time.
"""

from __future__ import annotations

import bisect
import json
import os
import re
import shlex
import statistics
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .store import Session, list_sessions, project_of

PROJECTS_ENV = "VIEW_CONCEPT_CLAUDE_PROJECTS"
STALL = 600.0  # seconds: a run stretch longer than this is stalled
CHAIN = 2.0  # seconds: a turn started this soon after a pass's end continues it
BREAK = 60.0  # seconds: user time longer than this is drawn as a break
SLOW = 3.0  # a run whose wall time passes this many times its role's median is slow
ROLES = ("planner", "writer", "implementer", "reviewer")
ACTIVITIES = (
    "loading context",
    "exploring code",
    "writing",
    "view-concept commands",
    "waiting on helpers",
    "report",
    "other",
)
# The phases in which the page waits for the user; every other phase means the agent works.
WAITING_PHASES = {
    "idle",
    "awaiting-answer",
    "awaiting-model",
    "awaiting-docs",
    "awaiting-pr",
    "awaiting-approval",
    "scoping",
}
QUALITY = (
    "comments",
    "rewrites",
    "unclear",
    "changes_after_approval",
    "findings",
    "reviewer_reruns",
)


# ---- time ----


def _dt(value: Any) -> datetime | None:
    """An ISO time (`Z` or offset) as an aware datetime, None when absent or invalid."""
    if not value or not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _iso(d: datetime | None) -> str | None:
    return d.astimezone(UTC).isoformat(timespec="milliseconds") if d else None


def _secs(a: datetime | None, b: datetime | None) -> float:
    """Seconds from a to b, never negative."""
    return max(0.0, (b - a).total_seconds()) if a and b else 0.0


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def _median(values: list[float]) -> float | None:
    return _r(statistics.median(values)) if values else None


# ---- session records (tolerant: a missing or broken file is no record) ----


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _phase_history(s: Session) -> list[tuple[datetime, str]]:
    out = [
        (at, str(h.get("phase", ""))) for h in s.read_phase_history() if (at := _dt(h.get("at")))
    ]
    return sorted(out)


def _deliveries(s: Session) -> dict[str, datetime]:
    return {bid: at for bid, raw in s.read_deliveries().items() if bid and (at := _dt(raw))}


def _batches(s: Session) -> list[dict[str, Any]]:
    data = _json(s.comments_path, {})
    return data.get("batches", []) if isinstance(data, dict) else []


# ---- transcripts ----


@dataclass
class Tool:
    id: str
    name: str
    input: dict[str, Any]
    at: datetime
    result_at: datetime | None = None
    result_chars: int = 0


@dataclass
class Call:
    """One API call: the assistant lines that share a message id."""

    id: str
    start: datetime
    end: datetime
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None
    output: int | None = None
    tools: list[Tool] = field(default_factory=list)

    @property
    def prompt_tokens(self) -> int:
        """What the call read: new input, input written to the cache, input read from it."""
        u = self.usage
        return sum(
            int(u.get(k) or 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )


@dataclass
class Transcript:
    path: Path
    start: datetime | None = None
    end: datetime | None = None
    prompt: str = ""  # the first user message
    calls: list[Call] = field(default_factory=list)
    inputs: list[datetime] = field(default_factory=list)  # every user line, in time order
    texts: list[tuple[datetime, str]] = field(default_factory=list)  # user lines' text
    prompts: list[datetime] = field(default_factory=list)  # user lines that are no result
    turn_ends: list[datetime] = field(default_factory=list)
    tools: dict[str, Tool] = field(default_factory=dict)


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(str(b.get("text", "")))
                elif b.get("type") == "tool_result":
                    parts.append(_text_of(b.get("content")))
        return "\n".join(parts)
    return ""


def _parse(path: Path) -> Transcript:
    t = Transcript(path)
    calls: dict[str, Call] = {}
    for rec in _jsonl(path):
        at = _dt(rec.get("timestamp"))
        if at is None:
            continue
        kind = rec.get("type")
        if kind == "system" and rec.get("subtype") == "turn_duration":
            t.turn_ends.append(at)
            continue
        if kind not in ("user", "assistant"):
            continue
        t.start = min(t.start or at, at)
        t.end = max(t.end or at, at)
        msg = rec.get("message") or {}
        content = msg.get("content")
        if kind == "user":
            if not t.prompt and not t.calls:
                t.prompt = _text_of(content)
            t.inputs.append(at)
            t.texts.append((at, _text_of(content)))
            results = [
                b for b in content or [] if isinstance(b, dict) and b.get("type") == "tool_result"
            ]
            if not results and not rec.get("isMeta"):
                t.prompts.append(at)
            for b in results:
                tool = t.tools.get(str(b.get("tool_use_id", "")))
                if tool and tool.result_at is None:
                    tool.result_at = at
                    tool.result_chars = len(_text_of(b.get("content")))
            continue
        model = str(msg.get("model", ""))
        mid = str(msg.get("id") or rec.get("uuid") or len(calls))
        call = calls.get(mid)
        if call is None:
            call = calls[mid] = Call(mid, at, at)
            t.calls.append(call)
        call.end = max(call.end, at)
        if model and model != "<synthetic>":
            call.model = model
        if msg.get("usage"):
            call.usage = msg["usage"]
        if msg.get("stop_reason"):
            call.stop_reason = msg["stop_reason"]
            call.output = int((msg.get("usage") or {}).get("output_tokens") or 0)
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                tool = Tool(str(b.get("id", "")), str(b.get("name", "")), b.get("input") or {}, at)
                call.tools.append(tool)
                t.tools[tool.id] = tool
    t.inputs.sort()
    t.turn_ends.sort()
    return t


_CACHE: dict[Path, tuple[int, int, Transcript]] = {}
_LOCK = threading.Lock()


def load_transcript(path: Path) -> Transcript:
    """A parsed transcript, cached in-process by (path, mtime, size)."""
    st = path.stat()
    with _LOCK:
        hit = _CACHE.get(path)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
    t = _parse(path)
    with _LOCK:
        _CACHE[path] = (st.st_mtime_ns, st.st_size, t)
    return t


def projects_dir() -> Path:
    return Path(os.environ.get(PROJECTS_ENV) or Path.home() / ".claude" / "projects")


def _coordinator_paths(conv: str) -> list[Path]:
    root = projects_dir()
    return sorted(root.glob(f"*/{conv}.jsonl")) if root.is_dir() else []


def _subagent_paths(conv: str) -> list[Path]:
    root = projects_dir()
    return sorted(root.glob(f"*/{conv}/subagents/agent-*.jsonl")) if root.is_dir() else []


# ---- activities ----

_CD = re.compile(r"""^\s*cd\s+("[^"]*"|'[^']*'|[^\s;&]+)\s*(?:&&|;)\s*""")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_QUOTED = re.compile(r""""(?:\\.|[^"\\])*"|'[^']*'""")
_REDIRECT = re.compile(r"(?<![0-9&<>])>{1,2}\s*(?!&|/dev/null)[^\s|&;)]")
_WRITES_IN_CODE = re.compile(r"\.write_text\(|\.write\(|json\.dump\(|open\([^)]*['\"][wa]")
_WRITE_COMMANDS = {"tee", "cp", "mv", "mkdir", "touch", "rm", "patch", "ln", "install"}
_GIT_WRITES = {
    "add",
    "commit",
    "apply",
    "mv",
    "rm",
    "stash",
    "checkout",
    "switch",
    "merge",
    "rebase",
    "cherry-pick",
    "worktree",
    "reset",
    "restore",
}
_WAIT_COMMANDS = {"until", "sleep", "while", "wait"}
_CHECK_COMMANDS = {"pytest", "ruff", "ty", "uv", "npm", "npx", "node", "make", "mypy"}
_CONTEXT_COMMAND = re.compile(r"view-concept\s+context\b")
_ROLE_FILE = re.compile(r"roles/[\w-]+\.md")
_READ_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead", "WebFetch", "WebSearch"}
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_AGENT_TOOLS = {"Agent", "Task", "TaskOutput"}
_SHELL_TOOLS = {"Bash", "Shell", "exec_command"}


def _segments(command: str) -> list[list[str]]:
    """The words of each simple command of a shell line (split on && ; | and newlines)."""
    out = []
    for part in re.split(r"&&|\|\||[;|\n]", _QUOTED.sub("''", command)):
        words = part.split()
        while words and _ENV.match(words[0]):
            words.pop(0)
        if words:
            out.append(words)
    return out


def _writes(command: str) -> bool:
    """Whether a shell command writes a file: a redirection to a file, a command that
    creates, moves or edits files, a git command that changes the tree, or code that
    opens a file for writing."""
    first_line, _, body = command.partition("\n")
    if _REDIRECT.search(_QUOTED.sub("''", first_line)) or _WRITES_IN_CODE.search(body):
        return True
    for words in _segments(first_line):
        if words[0] in _WRITE_COMMANDS:
            return True
        if words[0] == "sed" and any(w.startswith("-i") for w in words[1:]):
            return True
        if words[0] == "git" and len(words) > 1 and words[1] in _GIT_WRITES:
            return True
    return False


def shell_activity(command: str) -> str:
    """The activity of a shell command, from its first word after any leading `cd … &&`:
    `view-concept context` reads, so it explores code, any other view-concept command is a
    view-concept command; a command that writes a file is writing; a wait loop is waiting
    on helpers; tests and lint are other; any other command explores code. Loading context
    is not a command's own activity: it is the run's opening (`_opening`)."""
    rest = command
    while m := _CD.match(rest):
        rest = rest[m.end() :]
    if _CONTEXT_COMMAND.search(rest):
        return "exploring code"
    segments = _segments(rest)
    words = segments[0] if segments else []
    first = words[0] if words else ""
    if first == "uv" and words[1:3] == ["run", "view-concept"]:
        first = "view-concept"
    if first == "view-concept":
        return "view-concept commands"
    if _writes(rest):
        return "writing"
    if first in _WAIT_COMMANDS:
        return "waiting on helpers"
    if first in _CHECK_COMMANDS:
        return "other"
    return "exploring code"


def tool_activity(tool: Tool) -> str:
    """The activity of one tool call, from its name (and a shell command's words), outside
    the run's opening."""
    name, inp = tool.name, tool.input
    if name in _SHELL_TOOLS:
        return shell_activity(str(inp.get("command") or inp.get("cmd") or ""))
    if name in _WRITE_TOOLS:
        return "writing"
    if name in _AGENT_TOOLS:
        return "waiting on helpers"
    if name == "SubagentHandback":
        return "report"
    if name in _READ_TOOLS:
        return "exploring code"
    return "other"


def _opens(tool: Tool, named: set[str]) -> bool:
    """Whether a tool call belongs in a run's opening on its own: it runs `view-concept
    context`, or reads a role file (`roles/<name>.md`) the run's first prompt names."""
    if tool.name in _SHELL_TOOLS:
        command = str(tool.input.get("command") or tool.input.get("cmd") or "")
        if _CONTEXT_COMMAND.search(command):
            return True
        text = command
    elif tool.name in _READ_TOOLS:
        text = str(tool.input.get("file_path") or tool.input.get("path") or "")
    else:
        return False
    return tool_activity(tool) == "exploring code" and bool(named & set(_ROLE_FILE.findall(text)))


def _opening(calls: list[Call], prompt: str | None) -> int:
    """How many of a run's first calls are its opening, the calls that load its context:
    from the first call, each that runs the context command or reads a role file the first
    prompt names, with every other file it reads. The first call that does neither ends
    it. A coordinator pass (prompt None) has no opening."""
    if prompt is None:
        return 0
    named = set(_ROLE_FILE.findall(prompt))
    for i, call in enumerate(calls):
        tools = call.tools
        if not (
            any(_opens(t, named) for t in tools)
            and all(tool_activity(t) == "exploring code" for t in tools)
        ):
            return i
    return len(calls)


# The activity a call takes when its tools differ: the first in this order.
_PRIORITY = (
    "writing",
    "waiting on helpers",
    "view-concept commands",
    "loading context",
    "exploring code",
    "report",
    "other",
)


def _tool_label(tool: Tool) -> str:
    inp = tool.input
    for key in ("command", "cmd", "file_path", "path", "pattern", "description", "query"):
        if inp.get(key):
            return str(inp[key])[:200]
    return ""


# ---- run measures ----


@dataclass
class Stretch:
    start: datetime
    end: datetime
    activity: str
    tool: str = ""
    command: str = ""
    tool_seconds: float = 0.0
    tools: list[Tool] = field(default_factory=list)
    can_stall: bool = True  # False for a coordinator pass's stretches

    @property
    def seconds(self) -> float:
        return _secs(self.start, self.end)

    @property
    def stalled(self) -> bool:
        return self.can_stall and self.seconds > STALL


def stretches(
    calls: list[Call],
    inputs: list[datetime],
    start: datetime,
    end: datetime,
    can_stall: bool = True,
    prompt: str | None = None,
) -> list[Stretch]:
    """Split a run into stretches. A call with tools ends its stretch at its last tool
    result, and the stretch takes the call's activity; its tool time runs from the first
    tool call to that result. A call with no tool, before the last, ends with the agent
    waiting for a message (its helpers' reports): that stretch runs to the next message and
    waits on helpers, the wait counted as tool time. The last stretch is the report. The
    calls of the run's opening (`_opening`, from its first prompt) are loading context.
    With can_stall False (a coordinator pass), no stretch is stalled."""
    out: list[Stretch] = []
    cursor = start
    opening = _opening(calls, prompt)
    for i, call in enumerate(calls):
        if call.tools:
            results = [t.result_at for t in call.tools if t.result_at]
            stop = max([call.end, *results])
            if i < opening:
                activity, main = "loading context", call.tools[0]
            else:
                acts = {tool_activity(t): t for t in call.tools}
                activity = next(a for a in _PRIORITY if a in acts)
                main = acts[activity]
            tool_secs = _secs(min(t.at for t in call.tools), stop) if results else 0.0
            out.append(
                Stretch(cursor, stop, activity, main.name, _tool_label(main), tool_secs, call.tools)
            )
        elif i == len(calls) - 1:
            stop = max(end, call.end)
            out.append(Stretch(cursor, stop, "report"))
        else:
            k = bisect.bisect_right(inputs, call.end)
            stop = inputs[k] if k < len(inputs) else end
            stop = max(stop, call.end)
            out.append(Stretch(cursor, stop, "waiting on helpers", "", "", _secs(call.end, stop)))
        cursor = stop
    if out:
        out[-1].activity = "report"
        if out[-1].end < end:
            out[-1].end = end
    elif end > start:
        out.append(Stretch(start, end, "report"))
    for p in out:
        p.can_stall = can_stall
    return out


def measure(
    calls: list[Call],
    inputs: list[datetime],
    start: datetime,
    end: datetime,
    can_stall: bool = True,
    prompt: str | None = None,
) -> dict[str, Any]:
    """Every measure of one run.

    - wall: first line to last, stalled stretches left out; stalled: their seconds.
    - tool_time / model_time: the time a tool ran (or the run waited for a message), and
      the rest, the model's own time.
    - startup: until the first write (the start of the first writing stretch; the whole
      run when it writes nothing): its seconds, the API calls made before it, and their
      prompt tokens.
    - tokens: prompt tokens (input + cache writes + cache reads) of the first call, the
      last, and in all; the share read from the cache; output tokens summed over the calls
      that record a stop reason only, with no estimate (None when none does).
    - context: the first call's prompt tokens, the characters the opening's calls read
      (loading context), and the characters `view-concept context` printed in it.
    - activities: seconds by activity, stalled stretches left out.
    """
    parts = stretches(calls, inputs, start, end, can_stall, prompt)
    live = [p for p in parts if not p.stalled]
    stalled = sum(p.seconds for p in parts if p.stalled)
    activities = dict.fromkeys(ACTIVITIES, 0.0)
    for p in live:
        activities[p.activity] += p.seconds
    tool_time = sum(min(p.tool_seconds, p.seconds) for p in live)
    wall = sum(p.seconds for p in live)
    first_write = next((p.start for p in parts if p.activity == "writing"), None)
    until = first_write or end
    before = [c for c in calls if c.start < until]
    startup_parts = [p for p in live if p.end <= until] if first_write else live
    prompts = [c.prompt_tokens for c in calls]
    total = sum(prompts)
    cache_read = sum(int(c.usage.get("cache_read_input_tokens") or 0) for c in calls)
    recorded = [c.output for c in calls if c.stop_reason and c.output is not None]
    read_chars = context_chars = 0
    for p in parts:
        if p.activity != "loading context":
            continue
        for t in p.tools:
            read_chars += t.result_chars
            if _CONTEXT_COMMAND.search(str(t.input.get("command", ""))):
                context_chars += t.result_chars
    return {
        "wall": _r(wall),
        "stalled": _r(stalled),
        "model_time": _r(wall - tool_time),
        "tool_time": _r(tool_time),
        "api_calls": len(calls),
        "tool_calls": sum(len(c.tools) for c in calls),
        "startup": {
            "seconds": _r(sum(p.seconds for p in startup_parts)),
            "api_calls": len(before),
            "prompt_tokens": sum(c.prompt_tokens for c in before),
        },
        "tokens": {
            "first": prompts[0] if prompts else 0,
            "last": prompts[-1] if prompts else 0,
            "total": total,
            "cache_read_share": round(cache_read / total, 2) if total else 0.0,
            "output": sum(recorded) if recorded else None,
            "output_calls": len(recorded),
        },
        "context": {
            "prompt_tokens": prompts[0] if prompts else 0,
            "read_chars": read_chars,
            "context_chars": context_chars,
        },
        "activities": {k: _r(v) for k, v in activities.items()},
        "stretches": [
            {
                "start": _r(_secs(start, p.start)),
                "end": _r(_secs(start, p.end)),
                "activity": p.activity,
                "tool": p.tool,
                "command": p.command,
                "tool_seconds": _r(p.tool_seconds),
                "stalled": p.stalled,
            }
            for p in parts
        ],
        "first_write": _r(_secs(start, first_write)) if first_write else None,
    }


def _model(calls: list[Call]) -> str:
    models = Counter(c.model for c in calls if c.model)
    return models.most_common(1)[0][0] if models else ""


# ---- runs ----


def _context_args(prompt: str, slug: str) -> dict[str, Any] | None:
    """The arguments of the `view-concept context <slug>` command a prompt names, read as
    shell words: role, trigger words, section. None when the prompt names no such command
    for this session."""
    m = re.search(r"view-concept\s+context\s+" + re.escape(slug) + r"(?=[\s`'\"]|$)", prompt)
    if not m:
        return None
    line = prompt[m.end() :].split("\n", 1)[0].split("`", 1)[0]
    try:
        words = shlex.split(line)
    except ValueError:
        words = line.split()
    args: dict[str, Any] = {"role": "", "trigger": [], "section": ""}
    i = 0
    while i < len(words):
        w = words[i]
        if w in ("--role", "--section") and i + 1 < len(words):
            args[w[2:]] = words[i + 1]
            i += 2
        elif w == "--trigger":
            i += 1
            while i < len(words) and not words[i].startswith("--"):
                args["trigger"].append(words[i])
                i += 1
        else:
            i += 1
    return args


@dataclass
class Run:
    id: str
    kind: str  # role, helper or pass
    role: str
    trigger_words: list[str]
    section: str
    parent: str
    description: str
    start: datetime
    end: datetime
    calls: list[Call]
    inputs: list[datetime]
    tool_use_id: str = ""  # the parent's Agent call that started it
    transcript: Transcript | None = None
    measures: dict[str, Any] = field(default_factory=dict)
    helpers: list[str] = field(default_factory=list)
    wave: int | None = None
    series: str | None = None
    slow: bool = False

    @property
    def model(self) -> str:
        return _model(self.calls)

    @property
    def trigger(self) -> str:
        return " ".join(self.trigger_words)


def _subagent_runs(slug: str, convs: list[str]) -> list[Run]:
    """The role agents and helpers of a session, from the subagent transcripts of its
    conversations: a run whose first prompt names `view-concept context <slug>`, and every
    run whose parent is a kept run. A helper has its role agent's role."""
    found: dict[str, tuple[Transcript, dict[str, Any]]] = {}
    for conv in convs:
        for path in _subagent_paths(conv):
            run_id = path.stem.removeprefix("agent-")
            if run_id in found:
                continue
            try:
                t = load_transcript(path)
            except OSError:
                continue
            if t.start is None or t.end is None:
                continue
            meta = _json(path.with_name(f"{path.stem}.meta.json"), {})
            found[run_id] = (t, meta if isinstance(meta, dict) else {})
    args = {rid: _context_args(t.prompt, slug) for rid, (t, _) in found.items()}
    kept = {rid for rid, a in args.items() if a is not None}
    changed = True
    while changed:
        changed = False
        for rid, (_, meta) in found.items():
            if rid not in kept and str(meta.get("parentAgentId", "")) in kept:
                kept.add(rid)
                changed = True
    runs: dict[str, Run] = {}
    for rid in sorted(kept, key=lambda r: found[r][0].start or datetime.min.replace(tzinfo=UTC)):
        t, meta = found[rid]
        a = args[rid] or {"role": "", "trigger": [], "section": ""}
        parent = str(meta.get("parentAgentId", ""))
        is_helper = bool(parent) and parent in kept
        assert t.start and t.end
        runs[rid] = Run(
            id=rid,
            kind="helper" if is_helper else "role",
            role=a["role"],
            trigger_words=list(a["trigger"]),
            section=a["section"],
            parent=parent if is_helper else "",
            description=str(meta.get("description", "")),
            start=t.start,
            end=t.end,
            calls=t.calls,
            inputs=t.inputs,
            tool_use_id=str(meta.get("toolUseId", "")),
            transcript=t,
        )
    for run in runs.values():
        root = run
        seen = set()
        while root.kind == "helper" and root.parent in runs and root.id not in seen:
            seen.add(root.id)
            root = runs[root.parent]
        if run.kind == "helper":
            run.role = root.role or run.role
            run.trigger_words = run.trigger_words or list(root.trigger_words)
            runs[run.parent].helpers.append(run.id)
    for run in runs.values():
        run.measures = measure(run.calls, run.inputs, run.start, run.end, prompt=_prompt(run))
    return list(runs.values())


# ---- coordinator passes ----


@dataclass
class Pass:
    start: datetime
    end: datetime
    transcript: Transcript
    batches: list[str] = field(default_factory=list)
    runs: list[str] = field(default_factory=list)  # role runs started in it
    waited: datetime | None = None

    @property
    def id(self) -> str:
        return "pass:" + (self.batches[0] if self.batches else self.runs[0] if self.runs else "")


def _turn_end_after(t: Transcript, at: datetime) -> datetime:
    """The end of the coordinator's turn running at `at`: its next `turn_duration` line,
    else (an older transcript) its next call that ended the turn, else its last line."""
    k = bisect.bisect_left(t.turn_ends, at)
    if k < len(t.turn_ends):
        return t.turn_ends[k]
    ends = [c.end for c in t.calls if c.end >= at and c.stop_reason == "end_turn"]
    return min(ends) if ends else max(t.end or at, at)


def _batch_deliveries(t: Transcript, slug: str) -> dict[str, datetime]:
    """When each batch of the session reached the coordinator: the first message (a watch
    event or a `wait` result) that carries its header."""
    pattern = re.compile(r"view-concept · " + re.escape(slug) + r" · batch (b\d+)\b")
    out: dict[str, datetime] = {}
    for at, text in t.texts:
        for m in pattern.finditer(text):
            out.setdefault(m.group(1), at)
    return out


def _passes(
    transcripts: list[Transcript],
    deliveries: dict[str, datetime],
    runs: list[Run],
) -> list[Pass]:
    """Group the coordinator's work into passes. Events in time order: each batch
    delivered to a conversation, and each role agent it started. An event after the
    current pass's end opens a new pass, which ends at the end of the coordinator's turn;
    a role agent started in a pass extends it to the end of the coordinator's turn that
    follows the agent's end. A role agent started in a turn whose message arrived within
    CHAIN seconds of the pass's end (the second notice of an agent's end, queued behind
    the first) belongs to the pass: the coordinator did not wait for a new event."""
    role_runs = {r.tool_use_id: r for r in runs if r.kind == "role" and r.tool_use_id}
    out: list[Pass] = []
    for t in transcripts:
        if t.start is None or t.end is None:
            continue
        events: list[tuple[datetime, str, str]] = []
        for bid, at in deliveries.items():
            if t.start <= at <= t.end:
                events.append((at, "batch", bid))
        for tool_id, run in role_runs.items():
            tool = t.tools.get(tool_id)
            if tool:
                events.append((tool.at, "run", run.id))
        events.sort()
        by_id = {r.id: r for r in runs}
        current: Pass | None = None
        for at, kind, ref in events:
            if current is not None and kind == "run" and at > current.end:
                k = bisect.bisect_right(t.prompts, at) - 1
                if k >= 0 and t.prompts[k] <= current.end + timedelta(seconds=CHAIN):
                    current.end = _turn_end_after(t, at)
            if current is None or at > current.end:
                current = Pass(at, _turn_end_after(t, at), t)
                out.append(current)
            if kind == "batch":
                current.batches.append(ref)
            else:
                current.runs.append(ref)
                run_end = by_id[ref].end
                current.end = max(current.end, _turn_end_after(t, run_end))
    return sorted(out, key=lambda p: p.start)


def _pass_run(p: Pass, labels: dict[str, str]) -> Run:
    t = p.transcript
    calls = [c for c in t.calls if p.start <= c.start <= p.end]
    inputs = [i for i in t.inputs if p.start <= i <= p.end]
    run = Run(
        id=p.id,
        kind="pass",
        role="coordinator",
        trigger_words=list(p.batches),
        section="",
        parent="",
        description=", ".join(labels.get(b, b) for b in p.batches),
        start=p.start,
        end=p.end,
        calls=calls,
        inputs=inputs,
        transcript=t,
    )
    run.measures = measure(calls, inputs, p.start, p.end, can_stall=False)
    return run


# ---- waiting ----


def batch_label(b: dict[str, Any]) -> str:
    """What a batch carried, in the page's words: its button, its answers, its comments."""
    action = b.get("action", "")
    buttons = {
        "approve-plan": "« Approve plan »",
        "approve-model": "« Approve model »",
        "write-docs": "« Write docs and create PR »" if b.get("then_pr") else "« Write docs »",
        "create-pr": "« Create PR »",
        "grill": "« Grill »",
        "stop-grill": "« Stop grill »",
        "go-on": "« Go on »",
        "rewrite-readme": f"« rewrite {b.get('path', 'README.md')} with write-readme »",
        "write-lexicon": "« write repo lexicon »",
    }
    parts = []
    if action == "plan":
        parts.append("« Rewrite model »" if b.get("rewrite") else "« Write model »")
    elif action == "answer":
        n = len(b.get("answers") or [])
        parts.append("an answer" if n == 1 else f"{n} answers")
    elif action in buttons:
        parts.append(buttons[action])
    n = len(b.get("comments") or [])
    if n:
        parts.append("1 comment" if n == 1 else f"{n} comments")
    if not parts and b.get("note"):
        parts.append("a note")
    return " · ".join(parts)


def _first_after(times: list[datetime], at: datetime) -> datetime | None:
    k = bisect.bisect_left(times, at)
    return times[k] if k < len(times) else None


def _phase_after(
    history: list[tuple[datetime, str]], at: datetime, waiting: bool, before: datetime | None
) -> datetime | None:
    for when, phase in history:
        if (
            when >= at
            and (before is None or when < before)
            and (phase in WAITING_PHASES) == waiting
        ):
            return when
    return None


def _waiting(
    batches: list[dict[str, Any]],
    passes: list[Pass],
    deliveries: dict[str, datetime],
    history: list[tuple[datetime, str]],
    runs_by_id: dict[str, Run],
) -> list[dict[str, Any]]:
    """Waiting per batch. Pickup runs from the batch's sending to the coordinator's first
    call after its delivery; agent time from there to the page waiting again: the first
    waiting phase after the pass's last role agent ended, else the pass's end. A batch
    delivered during a pass it did not open is busy: no pickup, its whole wait is agent
    time. User time runs from the page waiting to the next batch that opens a pass.
    Agent time leaves out the stalled stretches of the pass's runs (merged where runs
    overlap), and `stalled` holds those seconds. With no coordinator transcript (another
    agent), the phase history alone gives the times."""
    pass_of = {bid: p for p in passes for bid in p.batches}
    for i, p in enumerate(passes):
        nxt = passes[i + 1].start if i + 1 < len(passes) else None
        last_end = max([runs_by_id[r].end for r in p.runs if r in runs_by_id], default=p.start)
        p.waited = _phase_after(history, last_end, True, nxt) or p.end
    out: list[dict[str, Any]] = []
    waits: list[datetime | None] = []
    prev_waited: datetime | None = None
    for b in batches:
        bid = str(b.get("id", ""))
        sent = _dt(b.get("sent"))
        delivered = deliveries.get(bid)
        p = pass_of.get(bid)
        acted = waited = None
        if p is not None:
            busy = p.batches[0] != bid
            starts = [c.start for c in p.transcript.calls]
            acted = _first_after(starts, delivered or p.start) if not busy else None
            waited = p.waited
        else:
            busy = bool(sent and prev_waited and sent < prev_waited)
            if delivered and not busy:
                acted = _phase_after(history, delivered, False, None)
            waited = _phase_after(history, acted or delivered, True, None) if delivered else None
        runs = _descendants(p.runs, runs_by_id) if p else []
        begin = sent if busy else acted
        stalled = (
            _overlap(_stall_spans([runs_by_id[r] for r in runs]), begin, waited)
            if begin and waited
            else 0.0
        )
        out.append(
            {
                "id": bid,
                "label": batch_label(b),
                "sent": _iso(sent),
                "delivered": _iso(delivered),
                "acted": _iso(acted),
                "waited": _iso(waited),
                "pickup": _r(_secs(sent, acted)) if acted and not busy else None,
                "agent": _r(_secs(begin, waited) - stalled) if waited else None,
                "user": None,
                "busy": busy,
                "stalled": _r(stalled),
                "runs": runs,
            }
        )
        waits.append(waited)
        if waited:
            prev_waited = max(prev_waited or waited, waited)
    # User time belongs to the last batch the page's wait answers, up to the next batch
    # that is not busy.
    for i, rec in enumerate(out):
        waited = waits[i]
        if waited is None or waited in waits[i + 1 :]:
            continue
        nxt = next((_dt(r["sent"]) for r in out[i + 1 :] if not r["busy"] and r["sent"]), None)
        if nxt:
            rec["user"] = _r(_secs(waited, nxt))
    return out


def _prompt(r: Run) -> str | None:
    """A run's first prompt, which names the role files of its opening; None for a
    coordinator pass, which has no opening."""
    if r.kind == "pass":
        return None
    return r.transcript.prompt if r.transcript else ""


def _stretches_of(r: Run) -> list[Stretch]:
    return stretches(r.calls, r.inputs, r.start, r.end, r.kind != "pass", _prompt(r))


def _stall_spans(runs: list[Run]) -> list[tuple[datetime, datetime]]:
    """The stalled stretches of these runs, merged where they overlap."""
    spans = sorted((p.start, p.end) for r in runs for p in _stretches_of(r) if p.stalled)
    out: list[tuple[datetime, datetime]] = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _overlap(spans: list[tuple[datetime, datetime]], a: datetime, b: datetime) -> float:
    """Seconds of these disjoint spans that fall between a and b."""
    return sum(_secs(max(a, x), min(b, y)) for x, y in spans)


def _descendants(ids: list[str], runs_by_id: dict[str, Run]) -> list[str]:
    out: list[str] = []
    todo = list(ids)
    while todo:
        rid = todo.pop(0)
        if rid in runs_by_id and rid not in out:
            out.append(rid)
            todo.extend(runs_by_id[rid].helpers)
    return out


def _clock(
    batches: list[dict[str, Any]], passes: list[Pass], runs_by_id: dict[str, Run]
) -> list[dict[str, Any]]:
    """The review's clock: consecutive spans, no gap. Each batch that is not busy brings
    the user time before it, its pickup and its agent time; a pass that no batch opened
    (the first run, a terminal message) is agent time of its own. A user span over BREAK
    seconds is a break; an agent span whose runs hold a stalled stretch is a stalled
    break."""
    events: list[tuple[datetime, datetime | None, datetime, str, bool]] = []
    for b in batches:
        sent, acted, waited = _dt(b["sent"]), _dt(b["acted"]), _dt(b["waited"])
        if not b["busy"] and sent and waited:
            events.append((sent, acted, waited, b["id"], bool(b["stalled"])))
    opened = {b["id"] for b in batches}
    for p in passes:
        if not (set(p.batches) & opened) and p.waited:
            stalled = any(
                (runs_by_id[r].measures.get("stalled") or 0) > 0
                for r in _descendants(p.runs, runs_by_id)
            )
            events.append((p.start, None, p.waited, "", stalled))
    events.sort(key=lambda e: e[0])
    spans: list[dict[str, Any]] = []

    def add(kind: str, start: datetime, end: datetime, batch: str, stalled: bool = False):
        if spans:
            start = max(start, _dt(spans[-1]["end"]) or start)
        if end <= start:
            return
        seconds = _secs(start, end)
        brk = (kind == "user" and seconds > BREAK) or (kind == "agent" and stalled)
        spans.append(
            {
                "kind": kind,
                "start": _iso(start),
                "end": _iso(end),
                "seconds": _r(seconds),
                "batch": batch,
                "break": brk,
                "stalled": kind == "agent" and stalled,
            }
        )

    for start, acted, waited, bid, stalled in events:
        if spans:
            add("user", _dt(spans[-1]["end"]) or start, start, bid)
        if acted:
            add("pickup", start, acted, bid)
        add("agent", acted or start, waited, bid, stalled)
    return spans


# ---- waves and series ----


def _waves(runs: list[Run]) -> list[dict[str, Any]]:
    """The helpers a run started together: those whose Agent calls are in one API call of
    their parent. Launch time runs from the parent's last action before that call (the
    message before it) to the last helper's start; the wave saves its helpers' summed wall
    time minus its slowest helper and its launch time. Loading is each helper's loading
    context time, as min and max."""
    by_id = {r.id: r for r in runs}
    waves: list[dict[str, Any]] = []
    for parent in runs:
        if not parent.helpers or parent.transcript is None:
            continue
        groups: dict[str, list[Run]] = {}
        call_of = {t.id: c for c in parent.calls for t in c.tools}
        for hid in parent.helpers:
            helper = by_id[hid]
            call = call_of.get(helper.tool_use_id)
            if call is not None:
                groups.setdefault(call.id, []).append(helper)
        for call_id, helpers in groups.items():
            call = next(c for c in parent.calls if c.id == call_id)
            k = bisect.bisect_left(parent.inputs, call.start)
            before = parent.inputs[k - 1] if k > 0 else parent.start
            started = max(h.start for h in helpers)
            walls = [h.measures["wall"] or 0.0 for h in helpers]
            slowest = max(helpers, key=lambda h: h.measures["wall"] or 0.0)
            launch = _secs(before, started)
            loading = [h.measures["activities"]["loading context"] or 0.0 for h in helpers]
            waves.append(
                {
                    "run": parent.id,
                    "role": parent.role,
                    "trigger": parent.trigger,
                    "helpers": [h.id for h in sorted(helpers, key=lambda h: h.start)],
                    "start": _iso(started),
                    "launch": _r(launch),
                    "slowest": _r(max(walls)),
                    "slowest_helper": slowest.id,
                    "sum": _r(sum(walls)),
                    "saved": _r(sum(walls) - max(walls) - launch),
                    "loading": [_r(min(loading)), _r(max(loading))],
                }
            )
    waves.sort(key=lambda w: w["start"])
    for i, w in enumerate(waves):
        for hid in w["helpers"]:
            by_id[hid].wave = i
    return waves


def _one_event(words: list[str]) -> bool:
    """Whether a trigger holds one event: one batch (a button label beside it is the same
    event), or with no batch, one word."""
    batches = [w for w in words if re.fullmatch(r"b\d+", w)]
    return len(batches) == 1 if batches else len(words) == 1


def _series(runs: list[Run]) -> list[dict[str, Any]]:
    """Runs of one role in a row (no role agent of another role between them), each on
    one event: what continuing one agent across those events would save is their summed
    startup cost."""
    role_runs = sorted((r for r in runs if r.kind == "role"), key=lambda r: r.start)
    groups: list[list[Run]] = []
    current: list[Run] = []
    for r in role_runs:
        if current and r.role == current[-1].role and _one_event(r.trigger_words):
            current.append(r)
            continue
        if len(current) > 1:
            groups.append(current)
        current = [r] if _one_event(r.trigger_words) else []
    if len(current) > 1:
        groups.append(current)
    out = []
    for i, group in enumerate(groups, 1):
        sid = f"s{i}"
        for r in group:
            r.series = sid
        out.append(
            {
                "id": sid,
                "role": group[0].role,
                "runs": [r.id for r in group],
                "startup": _r(sum(r.measures["startup"]["seconds"] or 0.0 for r in group)),
            }
        )
    return out


# ---- threads ----


def _turns(t: Transcript) -> list[tuple[datetime, datetime, list[Call]]]:
    """A thread transcript's turns: from each user prompt to the next."""
    out = []
    for i, start in enumerate(t.prompts):
        stop = t.prompts[i + 1] if i + 1 < len(t.prompts) else None
        calls = [c for c in t.calls if c.start >= start and (stop is None or c.start < stop)]
        end = max((c.end for c in calls), default=start)
        out.append((start, end, calls))
    return out


def _threads(s: Session) -> list[dict[str, Any]]:
    """Each side-thread turn: its start (the reply's `at`), its first-text and end times
    from the reply's record (`first_text`, `ended`), else the end from the turn's own
    transcript (named by `agent_session`); prompt tokens and tool calls from that
    transcript when found."""
    out = []
    paths = sorted(s.threads_dir.glob("t*.json")) if s.threads_dir.is_dir() else []
    for path in sorted(paths, key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0):
        th = _json(path, {})
        if not isinstance(th, dict):
            continue
        turns: list[tuple[datetime, datetime, list[Call]]] = []
        session_id = str(th.get("agent_session", ""))
        found = _coordinator_paths(session_id) if session_id else []
        if found:
            try:
                turns = _turns(load_transcript(found[0]))
            except OSError:
                turns = []
        n = 0
        for msg in th.get("messages", []):
            if msg.get("role") != "assistant":
                continue
            n += 1
            start = _dt(msg.get("at"))
            first = _dt(msg.get("first_text"))
            ended = _dt(msg.get("ended"))
            turn = turns[n - 1] if n - 1 < len(turns) else None
            if ended is None and turn:
                ended = turn[1]
            calls = turn[2] if turn else None
            out.append(
                {
                    "thread": str(th.get("id", path.stem)),
                    "turn": n,
                    "section": str(th.get("section", "")),
                    "start": _iso(start),
                    "first_text": _r(_secs(start, first)) if first and start else None,
                    "end": _r(_secs(start, ended)) if ended and start else None,
                    "prompt_tokens": calls[0].prompt_tokens if calls else None,
                    "tool_calls": sum(len(c.tools) for c in calls) if calls is not None else None,
                }
            )
    return sorted(out, key=lambda x: x["start"] or "")


# ---- quality ----


def quality(s: Session, runs: list[Run]) -> dict[str, int]:
    """The quality signals: comments sent; rewrites (« Rewrite model »: a plan batch with
    `rewrite`); unclear answers; changes of the model logged after the first « Approve
    model » batch; findings (items left judged `diverges`, and findings across items);
    reviewer runs after the first."""
    batches = _batches(s)
    approved = next(
        (_dt(b.get("sent")) for b in batches if b.get("action") == "approve-model"), None
    )
    changes = _json(s.change_history_path, None)
    if not isinstance(changes, list):
        changes = _json(s.legacy_changes_path, [])
    after = 0
    if approved and isinstance(changes, list):
        after = sum(1 for c in changes if (_dt(c.get("at")) or approved) > approved)
    plan = _json(s.plan_path, {})
    outline = plan.get("outline", []) if isinstance(plan, dict) else []
    findings = sum(
        1
        for o in outline
        if isinstance(o, dict)
        and ((o.get("item") or {}).get("verdict") == "diverges" or o.get("kind") == "finding")
    )
    reviewers = sum(1 for r in runs if r.kind == "role" and r.role == "reviewer")
    return {
        "comments": sum(len(b.get("comments") or []) for b in batches),
        "rewrites": sum(1 for b in batches if b.get("action") == "plan" and b.get("rewrite")),
        "unclear": sum(
            1
            for b in batches
            for a in b.get("answers") or []
            if isinstance(a, dict) and a.get("unclear")
        ),
        "changes_after_approval": after,
        "findings": findings,
        "reviewer_reruns": max(0, reviewers - 1),
    }


# ---- one review, and every review of its repository ----


def _review_runs(s: Session) -> list[Run]:
    """A session's role agents and helpers: none unless its agent is Claude Code."""
    if (s.read_agent().get("agent") or "claude") != "claude":
        return []
    return _subagent_runs(s.slug, s.conversations())


def _role_walls(runs: list[Run]) -> dict[str, list[float]]:
    """Wall times of the role agents, by role (helpers left out: a helper does one part
    of a run, so it is not compared with whole runs)."""
    out: dict[str, list[float]] = {}
    for r in runs:
        if r.kind == "role" and r.role in ROLES:
            out.setdefault(r.role, []).append(r.measures["wall"] or 0.0)
    return out


def _repo_reviews(s: Session, plan: dict[str, Any]) -> list[Session]:
    """Every feature of the session's repository (its main checkout), itself
    included."""
    project = project_of(str(plan.get("repo", "")))
    out = []
    for row in list_sessions(s.dir.parent):
        if row["workflow"] != "build-feature" or row["slug"] == s.slug:
            continue
        if project and row["project"] == project:
            out.append(Session(row["slug"], s.dir.parent))
    return [s, *sorted(out, key=lambda x: x.slug)]


def _compare(
    s: Session, reviews: list[tuple[Session, list[Run]]]
) -> tuple[dict[str, float | None], dict[str, Any]]:
    """The medians of run wall time per role over the repository's reviews, and the
    comparison by variant: per review, its median wall time per role and its quality
    signals; per variant, the median of its reviews' values."""
    walls: dict[str, list[float]] = {}
    variants: dict[str, list[dict[str, Any]]] = {}
    for review, runs in reviews:
        per_role = _role_walls(runs)
        for role, values in per_role.items():
            walls.setdefault(role, []).extend(values)
        name = review.read_variant()["name"]
        variants.setdefault(name, []).append(
            {
                "slug": review.slug,
                "current": review.slug == s.slug,
                "roles": {role: _median(v) for role, v in per_role.items()},
                "quality": quality(review, runs),
            }
        )
    medians = {role: _median(walls[role]) for role in ROLES if role in walls}
    out = []
    for name, rows in variants.items():
        roles = {
            role: _median([r["roles"][role] for r in rows if r["roles"].get(role) is not None])
            for role in ROLES
            if any(r["roles"].get(role) is not None for r in rows)
        }
        qual = {k: _median([float(r["quality"][k]) for r in rows]) for k in QUALITY}
        out.append({"name": name, "reviews": rows, "median": {"roles": roles, "quality": qual}})
    out.sort(key=lambda v: (v["name"] != "none", v["name"]))
    return medians, {"variants": out}


def _run_view(r: Run, variant: str) -> dict[str, Any]:
    m = r.measures
    return {
        "id": r.id,
        "kind": r.kind,
        "role": r.role,
        "trigger": r.trigger,
        "section": r.section,
        "parent": r.parent,
        "model": r.model,
        "variant": variant,
        "description": r.description,
        "start": _iso(r.start),
        "end": _iso(r.end),
        **{k: m[k] for k in ("wall", "stalled", "model_time", "tool_time")},
        **{k: m[k] for k in ("api_calls", "tool_calls", "startup", "tokens", "context")},
        "activities": m["activities"],
        "stretches": m["stretches"],
        "first_write": m["first_write"],
        "helpers": list(r.helpers),
        "wave": r.wave,
        "flags": {"slow": r.slow, "series": r.series},
    }


def _by_role(runs: list[Run]) -> list[dict[str, Any]]:
    """Agent time by role: the time at least one of its runs was going, stalls left out,
    so helpers running side by side count once. That time is split by activity: a moment
    two stretches share goes half to each, and a role agent waiting on helpers takes no
    share of a moment one of its role's runs spends on any other activity."""
    stretches_by: dict[str, list[Stretch]] = {}
    counts: Counter[str] = Counter()
    for r in runs:
        counts[r.role] += 1
        live = [p for p in _stretches_of(r) if not p.stalled]
        stretches_by.setdefault(r.role, []).extend(live)
    rows: list[dict[str, Any]] = []
    for role, parts in stretches_by.items():
        events = sorted(
            [(p.start, 1, p.activity) for p in parts] + [(p.end, -1, p.activity) for p in parts],
            key=lambda e: (e[0], e[1]),
        )
        activities = dict.fromkeys(ACTIVITIES, 0.0)
        active: Counter[str] = Counter()
        seconds = 0.0
        prev: datetime | None = None
        for when, step, activity in events:
            if prev is not None and when > prev and +active:
                span = _secs(prev, when)
                seconds += span
                work = {a: n for a, n in active.items() if n > 0 and a != "waiting on helpers"}
                share = work or {a: n for a, n in active.items() if n > 0}
                total = sum(share.values())
                for a, n in share.items():
                    activities[a] += span * n / total
            active[activity] += step
            prev = when
        rows.append(
            {
                "role": role,
                "seconds": _r(seconds),
                "runs": counts[role],
                "activities": {k: _r(v) for k, v in activities.items()},
            }
        )
    order = [*ROLES, "coordinator"]
    return sorted(rows, key=lambda x: order.index(x["role"]) if x["role"] in order else 99)


def session_metrics(s: Session) -> dict[str, Any]:
    """The metrics report of one feature, as the Metrics tab reads it."""
    plan = _json(s.plan_path, {})
    variant = s.read_variant()
    agent = s.read_agent().get("agent") or "claude"
    runs = _review_runs(s)
    convs = s.conversations() if agent == "claude" else []
    transcripts: list[Transcript] = []
    for conv in convs:
        for path in _coordinator_paths(conv):
            try:
                transcripts.append(load_transcript(path))
            except OSError:
                continue
    raw_batches = _batches(s)
    deliveries = {}
    for t in transcripts:
        for bid, at in _batch_deliveries(t, s.slug).items():
            deliveries.setdefault(bid, at)
    deliveries.update(_deliveries(s))
    passes = _passes(transcripts, deliveries, runs)
    labels = {str(b.get("id", "")): batch_label(b) for b in raw_batches}
    pass_runs = {}
    by_id = {r.id: r for r in runs}
    for p in passes:
        pr = _pass_run(p, labels)
        pass_runs[p.id] = pr
        for rid in p.runs:
            by_id[rid].parent = p.id
    history = _phase_history(s)
    batches = _waiting(raw_batches, passes, deliveries, history, by_id)
    clock = _clock(batches, passes, by_id)
    waves = _waves(runs)
    series = _series(runs)
    reviews = [(s, runs)] + [(r, _review_runs(r)) for r in _repo_reviews(s, plan)[1:]]
    medians, compare = _compare(s, reviews)
    for r in runs:
        median = medians.get(r.role)
        r.slow = (
            r.kind == "role"
            and bool(median)
            and (r.measures["wall"] or 0.0) > SLOW * (median or 0.0)
        )
    all_runs = sorted([*runs, *pass_runs.values()], key=lambda r: r.start)
    return {
        "slug": s.slug,
        "variant": variant,
        "agent": agent,
        "model": _model([c for r in all_runs for c in r.calls]),
        "clock": clock,
        "by_role": _by_role(all_runs),
        "batches": batches,
        "runs": [_run_view(r, variant["name"]) for r in all_runs],
        "waves": waves,
        "series": series,
        "threads": _threads(s),
        "quality": quality(s, runs),
        "medians": medians,
        "compare": compare,
    }
