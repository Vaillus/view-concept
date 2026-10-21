"""The agent harnesses a session can run on, and how a side thread talks to each.

The skills drive a session from whichever agent the user works in; only the side threads
need the harness itself, because each one is a headless conversation the server starts.
A backend knows how to start one turn (`args`), what the harness prints (`feed`), and how
the harness names the conversation it ran (`TurnState.session`).

Three backends:

- `claude`: `claude -p`, forking the main conversation on a thread's first turn.
- `codex`: `codex exec`, forking the main conversation the same way.

A coordinated session (view-branch) never forks: its main conversation only coordinates
subagents, so a thread starts from the session folder instead (`Session.fork_parent`).
- `command`: any program that reads a prompt on stdin and prints its answer on stdout
  (`VIEW_CONCEPT_AGENT_COMMAND`, or the `jazz run` preset). It has no conversation to
  fork, so every turn carries the explanation's location and the thread so far.

A backend also starts a workbench's runs (bench.py): `run_args`, `run_feed` and
`run_close`. A run is a blank conversation (no resume, no fork) that may write in its
cwd, the run's throwaway checkout, and nowhere else, with the project's settings only (on
Claude, `--setting-sources project`: the checkout's CLAUDE.md files, none of the user's).
Claude and Codex enforce the write limit: Claude has no shell and its Edit and Write are
allowed under the cwd only; Codex's workspace-write sandbox has `/tmp` and `$TMPDIR`
taken out, where the other checkouts of the same « Run all » sit. The command backend
enforces nothing: the program writes wherever it likes. Jazz starts no run
(`run_refusal`): its preset is read-only, so the run could not write its README.
Its final text is the run report: Claude's `result` event, Codex's last agent message, a
command's stdout.
"""

from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass, field
from typing import Any

from .store import Session

AGENT_ENV = "VIEW_CONCEPT_AGENT"
COMMAND_ENV = "VIEW_CONCEPT_AGENT_COMMAND"
CLAUDE_ENV = "VIEW_CONCEPT_CLAUDE"
CODEX_ENV = "VIEW_CONCEPT_CODEX"
JAZZ_ENV = "VIEW_CONCEPT_JAZZ"

AGENTS = ("claude", "codex", "jazz", "command")
THREAD_TOOLS = ["Read", "Grep", "Glob", "WebSearch", "WebFetch", "Bash"]
# What a Claude thread may run: reads anywhere, the web, and shell commands that only
# read (git history, the view-concept commands that print). `dontAsk` refuses the rest.
THREAD_ALLOWED = [
    "Read",
    "Grep",
    "Glob",
    "WebSearch",
    "WebFetch",
    *(f"Bash(git {c}:*)" for c in ("log", "show", "diff", "blame", "status", "ls-files")),
    *(f"Bash(view-concept {c}:*)" for c in ("context", "changes", "pending", "list")),
]

# What a run's Claude may do: read anywhere, and write inside its cwd (the throwaway
# checkout) only. No shell: a prefix rule such as `find:*` or `cat:*` also matches
# `find -delete` or `cat > path`, and Read, Grep and Glob already list and read files.
RUN_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write"]
RUN_ALLOWED = ["Read", "Grep", "Glob", "Edit(./**)", "Write(./**)"]
# Codex's workspace-write sandbox also opens `/tmp` and `$TMPDIR`, where every checkout
# sits (`tempfile.mkdtemp`): a run closes both, so only its cwd stays writable.
CODEX_RUN_SANDBOX = [
    'sandbox_mode="workspace-write"',
    "sandbox_workspace_write.exclude_tmpdir_env_var=true",
    "sandbox_workspace_write.exclude_slash_tmp=true",
    'approval_policy="never"',
]


@dataclass
class TurnState:
    """What one turn has reported so far."""

    session: str = ""
    finished: bool = False
    failed: bool = False
    error: str = ""
    final_text: str = ""
    structured: Any = None  # the object a turn run with a JSON schema returned
    noise: list[str] = field(default_factory=list)


class Backend:
    name = ""
    forks = False  # a thread can start from the main conversation
    structured = False  # a turn can be held to a JSON schema (`schema_args`)

    def args(self, s: Session, thread: dict[str, Any]) -> list[str]:
        raise NotImplementedError

    def schema_args(self, schema: dict[str, Any]) -> list[str]:
        """The arguments that hold the turn's answer to `schema`, on a structured backend;
        the answer then lands in `TurnState.structured`."""
        return []

    def prompt(self, thread: dict[str, Any], briefing: str, text: str) -> str:
        """What goes on stdin: the briefing on a thread's first turn, then the message."""
        return text if thread["agent_session"] else f"{briefing}\n\n{text}"

    def feed(
        self, line: str, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState
    ) -> bool:
        """Fold one output line into the thread and the turn. True when the thread changed."""
        raise NotImplementedError

    def close(
        self, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState, code: int
    ) -> None:
        """Settle the turn once the process has exited."""
        if code and not turn.failed:
            turn.failed = True
            turn.error = "\n".join(turn.noise[-5:]) or f"exit code {code}"
        elif not turn.finished and not turn.failed:
            turn.failed = True
            turn.error = "\n".join(turn.noise[-5:]) or "the agent ended without an answer"

    # ---- a workbench's run (bench.py) ----
    def run_args(self) -> list[str]:
        """The command of a run: a blank conversation that may write in its cwd only."""
        raise NotImplementedError

    def run_feed(self, line: str, turn: TurnState) -> None:
        """Fold one output line of a run into its turn; `final_text` is its run report."""
        raise NotImplementedError

    def run_close(self, turn: TurnState, code: int) -> None:
        """Settle a run once its process has exited."""
        if code and not turn.failed:
            turn.failed = True
            turn.error = "\n".join(turn.noise[-5:]) or f"exit code {code}"
        elif not turn.finished and not turn.failed:
            turn.failed = True
            turn.error = "\n".join(turn.noise[-5:]) or "the agent ended without a run report"


class ClaudeBackend(Backend):
    name = "claude"
    forks = True
    structured = True

    def args(self, s: Session, thread: dict[str, Any]) -> list[str]:
        args = [os.environ.get(CLAUDE_ENV, "claude"), "-p", "--output-format", "stream-json"]
        args += ["--verbose", "--include-partial-messages", "--strict-mcp-config"]
        args += ["--permission-mode", "dontAsk"]
        args += ["--tools", *THREAD_TOOLS, "--allowedTools", *THREAD_ALLOWED]
        args += ["--add-dir", str(s.dir)]
        if thread["agent_session"]:
            args += ["--resume", thread["agent_session"]]
        elif s.fork_parent():
            args += ["--resume", s.fork_parent(), "--fork-session"]
        return args

    def schema_args(self, schema: dict[str, Any]) -> list[str]:
        return ["--json-schema", json.dumps(schema)]

    def run_args(self) -> list[str]:
        args = [os.environ.get(CLAUDE_ENV, "claude"), "-p", "--output-format", "stream-json"]
        args += ["--verbose", "--strict-mcp-config", "--setting-sources", "project"]
        args += ["--permission-mode", "dontAsk"]
        return args + ["--tools", *RUN_TOOLS, "--allowedTools", *RUN_ALLOWED]

    def run_feed(self, line: str, turn: TurnState) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            turn.noise.append(line.rstrip())
            return
        if event.get("type") == "system" and event.get("subtype") == "init":
            turn.session = event.get("session_id", turn.session)
        elif event.get("type") == "result":
            turn.finished = True
            turn.final_text = str(event.get("result", ""))
            if event.get("is_error"):
                turn.failed = True
                turn.error = turn.final_text.strip()

    def feed(
        self, line: str, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState
    ) -> bool:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            turn.noise.append(line.rstrip())
            return False
        kind = event.get("type")
        if kind == "result":
            turn.finished = True
            turn.final_text = str(event.get("result", ""))
            turn.structured = event.get("structured_output")
            if event.get("is_error"):
                turn.failed = True
                turn.error = turn.final_text.strip()
            return False
        if kind == "system" and event.get("subtype") == "init":
            turn.session = event.get("session_id", turn.session)
            thread["agent_session"] = turn.session or thread["agent_session"]
            thread["activity"] = "thinking"
            return True
        if kind != "stream_event":
            return False
        inner = event.get("event", {})
        inner_type = inner.get("type")
        if inner_type == "message_start":
            _separate_messages(reply)
        elif inner_type == "content_block_start":
            block = inner.get("content_block", {})
            if block.get("type") == "tool_use":
                thread["activity"] = f"using {block.get('name', 'a tool')}"
                return True
            if block.get("type") == "thinking":
                thread["activity"] = "thinking"
                return True
        elif inner_type == "content_block_delta":
            delta = inner.get("delta", {})
            if delta.get("type") == "text_delta":
                reply["text"] += delta.get("text", "")
                thread["activity"] = "writing"
                return True
        return False


class CodexBackend(Backend):
    name = "codex"
    forks = True

    def args(self, s: Session, thread: dict[str, Any]) -> list[str]:
        args = [os.environ.get(CODEX_ENV, "codex"), "exec"]
        if thread["agent_session"]:
            args += ["resume", thread["agent_session"]]
        elif s.fork_parent():
            args += ["fork", s.fork_parent()]
        args += ["--json", "--skip-git-repo-check"]
        args += ["-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"']
        args += ["-"]
        return args

    def run_args(self) -> list[str]:
        args = [os.environ.get(CODEX_ENV, "codex"), "exec", "--json", "--skip-git-repo-check"]
        for setting in CODEX_RUN_SANDBOX:
            args += ["-c", setting]
        return [*args, "-"]

    def run_feed(self, line: str, turn: TurnState) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            turn.noise.append(line.rstrip())
            return
        kind = event.get("type")
        item = event.get("item", {})
        if kind == "thread.started":
            turn.session = event.get("thread_id", turn.session)
        elif kind in ("turn.failed", "error"):
            turn.failed = True
            detail = event.get("message") or (event.get("error") or {}).get("message") or ""
            turn.error = str(detail).strip() or turn.error
        elif kind == "turn.completed":
            turn.finished = True
        elif kind == "item.completed" and item.get("type") == "agent_message":
            # The last message is the run report.
            turn.final_text = str(item.get("text", ""))

    def feed(
        self, line: str, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState
    ) -> bool:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            turn.noise.append(line.rstrip())
            return False
        kind = event.get("type")
        if kind == "thread.started":
            turn.session = event.get("thread_id", turn.session)
            thread["agent_session"] = turn.session or thread["agent_session"]
            thread["activity"] = "thinking"
            return True
        if kind == "turn.started":
            thread["activity"] = "thinking"
            return True
        if kind in ("turn.failed", "error"):
            turn.failed = True
            detail = event.get("message") or (event.get("error") or {}).get("message") or ""
            turn.error = str(detail).strip() or turn.error
            return False
        if kind == "turn.completed":
            turn.finished = True
            return False
        item = event.get("item", {})
        item_type = item.get("type")
        if kind == "item.started" and item_type == "command_execution":
            thread["activity"] = "using shell"
            return True
        if kind == "item.completed" and item_type == "agent_message":
            _separate_messages(reply)
            reply["text"] += str(item.get("text", ""))
            thread["activity"] = "writing"
            return True
        return False


class CommandBackend(Backend):
    """A program that answers a prompt read on stdin; its stdout is the reply."""

    name = "command"

    def __init__(self, argv: list[str]):
        self.argv = argv

    def args(self, s: Session, thread: dict[str, Any]) -> list[str]:
        return list(self.argv)

    def prompt(self, thread: dict[str, Any], briefing: str, text: str) -> str:
        """Without a conversation to resume, every turn replays the thread so far."""
        lines = [briefing, ""]
        earlier = [message for message in thread["messages"] if message["text"].strip()]
        if earlier:
            lines += ["The thread so far:"]
            for message in earlier:
                who = "User" if message["role"] == "user" else "You"
                lines.append(f"{who}: {message['text'].strip()}")
            lines.append("")
        lines.append(f"User: {text}" if earlier else text)
        return "\n".join(lines)

    def feed(
        self, line: str, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState
    ) -> bool:
        reply["text"] += line
        thread["agent_session"] = thread["agent_session"] or "command"
        thread["activity"] = "writing"
        return True

    def close(
        self, thread: dict[str, Any], reply: dict[str, Any], turn: TurnState, code: int
    ) -> None:
        if code:
            turn.failed = True
            turn.error = reply["text"].strip()[-400:] or f"exit code {code}"
        else:
            turn.finished = True
            reply["text"] = reply["text"].strip()

    def run_args(self) -> list[str]:
        return list(self.argv)

    def run_feed(self, line: str, turn: TurnState) -> None:
        turn.final_text += line

    def run_close(self, turn: TurnState, code: int) -> None:
        if code:
            turn.failed = True
            out = turn.final_text.strip()[-400:] or "\n".join(turn.noise[-5:])
            turn.error = out or f"exit code {code}"
        else:
            turn.finished = True


def _separate_messages(reply: dict[str, Any]) -> None:
    """One reply can span several messages around tool calls: keep them apart."""
    if reply["text"] and not reply["text"].endswith("\n\n"):
        reply["text"] += "\n\n"


def jazz_command(name: str) -> list[str]:
    """`jazz run` answers one prompt read from stdin; tools above `read-only` are declined."""
    jazz = os.environ.get(JAZZ_ENV, "jazz")
    return [jazz, "--no-tui", "run", "--agent", name, "--approval-policy", "read-only"]


def chosen(s: Session) -> str:
    """The agent a session's side threads and runs use: `command` when a program is set,
    else the environment, then what `new` / `open` recorded, then Claude Code."""
    if os.environ.get(COMMAND_ENV):
        return "command"
    return os.environ.get(AGENT_ENV) or s.read_agent().get("agent") or "claude"


def run_refusal(s: Session) -> str:
    """Why the session's agent cannot start a workbench's runs, or "" when it can. Jazz is
    refused: its `jazz run` preset is read-only, so a run could not write its README."""
    if chosen(s) != "jazz":
        return ""
    return (
        "runs do not start on Jazz: `jazz run` is started read-only, so a run could not "
        "write its README. Open the session from Claude Code or Codex (`view-concept open "
        f"{s.slug} --agent claude`), or set {COMMAND_ENV} to a program that may write"
    )


def resolve(s: Session) -> Backend:
    """The backend a session's side threads use: the environment, then what `new` / `open`
    recorded from the agent running them, then Claude Code."""
    recorded = s.read_agent()
    agent = chosen(s)
    custom = os.environ.get(COMMAND_ENV)
    if custom:
        return CommandBackend(shlex.split(custom))
    if agent == "claude":
        return ClaudeBackend()
    if agent == "codex":
        return CodexBackend()
    if agent == "jazz":
        name = os.environ.get("VIEW_CONCEPT_JAZZ_AGENT") or recorded.get("name", "")
        if not name:
            raise ValueError(
                "side threads on Jazz need the agent's name: pass --agent-name to `view-concept "
                "open`, or set VIEW_CONCEPT_JAZZ_AGENT"
            )
        return CommandBackend(jazz_command(name))
    if agent == "command":
        raise ValueError(f"set {COMMAND_ENV} to the program side threads run")
    raise ValueError(f"unknown agent {agent!r}, expected one of {', '.join(AGENTS)}")


def detect(environ: dict[str, str] | None = None) -> tuple[str, str]:
    """The agent running this process and its conversation id ("" when it has none to fork)."""
    env = os.environ if environ is None else environ
    if env.get("CLAUDE_CODE_SESSION_ID"):
        return "claude", env["CLAUDE_CODE_SESSION_ID"]
    if env.get("CODEX_THREAD_ID"):
        return "codex", env["CODEX_THREAD_ID"]
    if env.get("JAZZ_AGENT_PROCESS") == "1":
        return "jazz", ""
    return "", ""
