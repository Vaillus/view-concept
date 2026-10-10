"""Command line: what the view-concept, view-branch and view-refactor skills call from the agent."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from .agents import AGENTS, detect
from .context import ROLES, build
from .store import (
    HEARTBEAT_EVERY,
    HOME,
    KINDS,
    PHASES,
    WORKFLOWS,
    Session,
    SessionError,
    format_batch,
    format_changes,
    format_precedence,
    list_sessions,
    slugify,
)

PID_FILE = HOME / "server.pid"
LOG_FILE = HOME / "server.log"
HOST = "127.0.0.1"
WAIT_TIMEOUT_CODE = 3
DEFAULT_WAIT_SECONDS = 540


def _port() -> int:
    return int(os.environ.get("VIEW_CONCEPT_PORT", "5080"))


def _base_url() -> str:
    return f"http://{HOST}:{_port()}"


def server_up() -> bool:
    try:
        with urllib.request.urlopen(f"{_base_url()}/api/health", timeout=0.5) as r:
            return r.status == 200
    except OSError:
        return False


def ensure_server() -> None:
    if server_up():
        return
    HOME.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("ab") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "view_concept.cli", "serve"],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid))
    for _ in range(50):
        if server_up():
            return
        time.sleep(0.1)
    raise SessionError(f"server did not start, see {LOG_FILE}")


def stop_server() -> bool:
    try:
        pid = int(PID_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return False
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    PID_FILE.unlink(missing_ok=True)
    return True


def bind_agent(s: Session, a: argparse.Namespace) -> None:
    """Record the agent running this command: side threads run on it and, when it can
    fork its conversation, fork from it. Claude Code and Codex announce themselves in the
    environment; any other agent passes `--agent`. Run from a plain shell, the recorded
    agent is left as it was."""
    detected, parent = detect()
    s.bind_agent(
        a.agent or detected,
        parent if not a.agent or a.agent == detected else "",
        a.agent_name or "",
    )


def cmd_new(a: argparse.Namespace) -> None:
    slug = a.slug or slugify(a.title)
    s = Session(slug)
    created = s.create(
        a.title, a.initial_request or "", a.kind, a.repo or "", a.workflow or "", a.base or ""
    )
    bind_agent(s, a)
    print(json.dumps({"slug": slug, "dir": str(s.dir), "created": created}))


def cmd_open(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}; create it with `view-concept new`")
    bind_agent(s, a)
    ensure_server()
    url = f"{_base_url()}/s/{a.slug}"
    if not a.no_browser:
        webbrowser.open(url)
    print(url)


def cmd_serve(a: argparse.Namespace) -> None:
    from .server import run

    run(HOST, _port())


def cmd_stop(a: argparse.Namespace) -> None:
    print("stopped" if stop_server() else "no server pid on record")


def _batches(s: Session, slug: str):
    """Yield each new batch of the inbox as `(text, cursor after it)`, and None while the
    inbox is quiet; writes the heartbeat meanwhile.

    The cursor persists across runs, so a later run neither loses a batch sent in between
    nor repeats one already delivered. The caller stores the cursor once it has delivered
    the text."""
    try:
        cursor = int(s.cursor_path.read_text())
    except (FileNotFoundError, ValueError):
        cursor = 0
    beat = 0.0
    while True:
        if time.monotonic() - beat >= HEARTBEAT_EVERY:
            s.write_heartbeat()
            beat = time.monotonic()
        try:
            size = s.inbox_path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size > cursor:
            with s.inbox_path.open("rb") as f:
                f.seek(cursor)
                chunk = f.read(size - cursor)
            complete = chunk[: chunk.rfind(b"\n") + 1]  # only complete lines
            if complete:
                outline, questions = s.read_plan()["outline"], s.read_questions()
                for raw in complete.splitlines(keepends=True):
                    cursor += len(raw)
                    if raw.strip():
                        yield format_batch(slug, json.loads(raw), outline, questions), cursor
                    else:
                        s.cursor_path.write_text(str(cursor))
                continue
        yield None
        time.sleep(0.5)


def cmd_watch(a: argparse.Namespace) -> None:
    """Print each new batch of the inbox as it arrives; for an agent with a background
    monitor tool (Claude Code's `Monitor`). Starting prints nothing: every line is an event,
    and a re-arm is not news. While it runs, the watch writes its heartbeat (watch.json),
    which tells the page the agent is listening."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    for delivery in _batches(s, a.slug):
        if delivery is not None:
            text, cursor = delivery
            print(text, flush=True)
            s.cursor_path.write_text(str(cursor))


def cmd_wait(a: argparse.Namespace) -> None:
    """Block until the next batch, print it and exit; for an agent without a background
    monitor. Exit code 3 and no output when none arrives within `--timeout` seconds."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    deadline = time.monotonic() + a.timeout
    for delivery in _batches(s, a.slug):
        if delivery is not None:
            text, cursor = delivery
            print(text, flush=True)
            s.cursor_path.write_text(str(cursor))
            return
        if time.monotonic() >= deadline:
            sys.exit(WAIT_TIMEOUT_CODE)


def cmd_status(a: argparse.Namespace) -> None:
    st = Session(a.slug).write_status(a.phase, a.section or "", a.message or "")
    print(f"{st['phase']} {st['section']}".strip())


def cmd_question(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    q = s.add_question(a.text, a.option, a.multi, a.recommended or "")
    print(q["id"])
    # The answer only reaches the agent through a watch or a wait: say so while none runs.
    if not s.is_listening():
        print(
            f"view-concept: no watch or wait is running for {a.slug}; the answer will wait in the "
            "inbox until one starts. Start listening now.",
            file=sys.stderr,
        )


def cmd_answered(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    q = s.answered_in_terminal(a.qid, a.text or "")
    print(f"{q['id']} answered")


def cmd_change(a: argparse.Namespace) -> None:
    d = Session(a.slug).add_change(a.change, a.by or "", a.cause)
    print(f"{d['id']} recorded")


def cmd_plan(a: argparse.Namespace) -> None:
    raw = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SessionError(f"{a.file} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not {"outline", "lexicon"} & data.keys():
        raise SessionError('expected {"outline": [...], "lexicon": [...]} (either or both)')
    plan = Session(a.slug).write_plan(data.get("outline"), data.get("lexicon"))
    print(f"{len(plan['outline'])} sections, {len(plan['lexicon'])} terms")


def cmd_message(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    print(f"{s.add_terminal_message(a.text)['id']} recorded")


def cmd_context(a: argparse.Namespace) -> None:
    print(build(Session(a.slug), a.role, a.trigger, a.section or ""), end="")


def cmd_changes(a: argparse.Namespace) -> None:
    """The change history of one session, or of every code session on a repository."""
    if a.slug:
        slugs = [a.slug]
    else:
        repo = str(Path(a.repo or ".").expanduser().resolve())
        slugs = [r["slug"] for r in list_sessions() if r["repo"] == repo]
    for slug in slugs:
        changes = Session(slug).read_changes()
        if changes:
            if len(slugs) > 1:
                print(f"<!-- {slug} -->")
            print(format_changes(changes))


def cmd_check(a: argparse.Namespace) -> None:
    """The precedence check: list forward references and early uses, write them to
    audit.json (replacing the previous ones, keeping the agent's own entries)."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    problems = s.check_precedence()
    for p in problems:
        print(format_precedence(p))
    print(f"{len(problems)} problem{'' if len(problems) == 1 else 's'} written to audit.json")


def cmd_pending(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    outline = s.read_plan()["outline"]
    for b in s.read_comments()["batches"]:
        open_ = [c for c in b["comments"] if c["status"] == "sent"]
        if open_:
            print(format_batch(a.slug, {**b, "comments": open_}, outline))
            print()


def cmd_resolve(a: argparse.Namespace) -> None:
    touched = Session(a.slug).resolve(a.ids, a.reply or "")
    print(f"resolved {', '.join(touched) or 'nothing'}")


def cmd_export(a: argparse.Namespace) -> None:
    print(Session(a.slug).export())


def cmd_list(a: argparse.Namespace) -> None:
    for r in list_sessions():
        pending = f"  ({r['pending']} open comments)" if r["pending"] else ""
        print(f"{r['slug']:40} {r['updated']}  {r['title']}{pending}")


def _add_agent_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--agent",
        choices=AGENTS,
        help="the agent running this command, for side threads; Claude Code and Codex are "
        "detected, any other agent passes it",
    )
    parser.add_argument("--agent-name", help="the agent's own name (Jazz: its agent id)")


def main() -> None:
    p = argparse.ArgumentParser(prog="view-concept")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("new", help="create a session (no-op if it exists)")
    q.add_argument("title")
    q.add_argument("--slug")
    q.add_argument("--initial-request", help="the user's first message, verbatim")
    q.add_argument("--kind", choices=KINDS, default="explanation")
    q.add_argument("--repo", help="repository a code session is about (citations link into it)")
    q.add_argument("--base", help="the branch a branch review compares with")
    q.add_argument(
        "--workflow",
        choices=WORKFLOWS,
        help="the skill driving the session; picks its verdict set "
        "(default: view-concept, or view-branch for a code session)",
    )
    _add_agent_flags(q)
    q.set_defaults(fn=cmd_new)

    q = sub.add_parser("open", help="start the server if needed and open the page")
    q.add_argument("slug")
    q.add_argument("--no-browser", action="store_true")
    _add_agent_flags(q)
    q.set_defaults(fn=cmd_open)

    sub.add_parser("serve", help="run the server in the foreground").set_defaults(fn=cmd_serve)
    sub.add_parser("stop", help="stop the background server").set_defaults(fn=cmd_stop)

    q = sub.add_parser("watch", help="stream comment batches (run under a background monitor)")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_watch)

    q = sub.add_parser(
        "wait", help="block until the next comment batch, print it and exit (3 on timeout)"
    )
    q.add_argument("slug")
    q.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_WAIT_SECONDS,
        help="seconds to wait for a batch (default: %(default)s)",
    )
    q.set_defaults(fn=cmd_wait)

    q = sub.add_parser("status", help="tell the page what the agent is doing now")
    q.add_argument("slug")
    q.add_argument("phase", choices=PHASES)
    q.add_argument("--section", help="outline id being written, for phase 'writing'")
    q.add_argument("--message", help="short free text shown next to the phase")
    q.set_defaults(fn=cmd_status)

    q = sub.add_parser("question", help="put an agent question to the user in the page")
    q.add_argument("slug")
    q.add_argument("text", help="the question")
    q.add_argument("--option", action="append", default=[], help="one choice (repeatable)")
    q.add_argument("--multi", action="store_true", help="the user may pick several choices")
    q.add_argument("--recommended", help="the answer you suggest: an option, or a text")
    q.set_defaults(fn=cmd_question)

    q = sub.add_parser(
        "answered", help="mark an open agent question answered in the terminal (sends no batch)"
    )
    q.add_argument("slug")
    q.add_argument("qid", help="the question id, e.g. q1")
    q.add_argument("--text", help="the answer as the user gave it")
    q.set_defaults(fn=cmd_answered)

    q = sub.add_parser("change", help="append a change of the model to the change history")
    q.add_argument("slug")
    q.add_argument("change", help="what changed in the model, in a few words")
    q.add_argument("--by", help="who made it: planner or writer")
    q.add_argument(
        "--cause",
        nargs="*",
        default=[],
        help="the question, comment or terminal message ids that led to it (default: own judgment)",
    )
    q.set_defaults(fn=cmd_change)

    q = sub.add_parser("plan", help="replace the outline and/or the lexicon, nothing else")
    q.add_argument("slug")
    q.add_argument(
        "file", help='a JSON file {"outline": [...], "lexicon": [...]} (either or both), or -'
    )
    q.set_defaults(fn=cmd_plan)

    q = sub.add_parser("message", help="record a terminal message of the user about the feature")
    q.add_argument("slug")
    q.add_argument("text", help="the message, as the user wrote it")
    q.set_defaults(fn=cmd_message)

    q = sub.add_parser("context", help="print the context a subagent or a side thread starts from")
    q.add_argument("slug")
    q.add_argument("--role", choices=ROLES, required=True)
    q.add_argument(
        "--trigger",
        nargs="*",
        default=[],
        help="the events that started this run: question, comment, batch or terminal "
        "message ids, or a word such as « Write model »",
    )
    q.add_argument("--section", help="for a side thread: the section of its passage")
    q.set_defaults(fn=cmd_context)

    q = sub.add_parser(
        "changes",
        help="print the change history as Markdown bullets (for a PR's Decisions section)",
    )
    q.add_argument("slug", nargs="?")
    q.add_argument("--repo", help="all code sessions on this repo (default: current dir)")
    q.set_defaults(fn=cmd_changes)

    q = sub.add_parser(
        "check",
        help="list forward references and early uses of the lexicon, write them to audit.json",
    )
    q.add_argument("slug")
    q.set_defaults(fn=cmd_check)

    q = sub.add_parser("pending", help="print comments not yet resolved")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_pending)

    q = sub.add_parser("resolve", help="mark comments (c3) or batches (b2) resolved")
    q.add_argument("slug")
    q.add_argument("ids", nargs="+")
    q.add_argument("--reply", help="short note shown under the comment on the page")
    q.set_defaults(fn=cmd_resolve)

    q = sub.add_parser("export", help="write the explanation to the Obsidian vault")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_export)

    sub.add_parser("list", help="list sessions").set_defaults(fn=cmd_list)

    a = p.parse_args()
    try:
        a.fn(a)
    except SessionError as e:
        print(f"view-concept: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
