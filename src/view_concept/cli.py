"""Command line: what the view-concept and view-pr skills call from Claude Code."""

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

from .store import (
    HOME,
    KINDS,
    PHASES,
    Session,
    SessionError,
    format_batch,
    format_changes,
    list_sessions,
    slugify,
)

PID_FILE = HOME / "server.pid"
LOG_FILE = HOME / "server.log"
HOST = "127.0.0.1"


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


def bind_parent(s: Session) -> None:
    """Record the Claude Code session running this command: side threads fork from it.
    Claude Code sets CLAUDE_CODE_SESSION_ID in its shell; run elsewhere, the recorded
    session is left as it was."""
    s.bind_parent(os.environ.get("CLAUDE_CODE_SESSION_ID", ""))


def cmd_new(a: argparse.Namespace) -> None:
    slug = a.slug or slugify(a.title)
    s = Session(slug)
    created = s.create(a.title, a.question or "", a.kind, a.repo or "")
    bind_parent(s)
    print(json.dumps({"slug": slug, "dir": str(s.dir), "created": created}))


def cmd_open(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}; create it with `view-concept new`")
    bind_parent(s)
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


def cmd_watch(a: argparse.Namespace) -> None:
    """Print each new batch of the inbox as it arrives. Meant to run under Monitor.

    The cursor persists across restarts, so re-arming after a Monitor timeout neither
    loses a batch sent in between nor repeats one already delivered."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    try:
        cursor = int(s.cursor_path.read_text())
    except (FileNotFoundError, ValueError):
        cursor = 0
    print(f"watching {a.slug} (inbox offset {cursor})", flush=True)
    while True:
        try:
            size = s.inbox_path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size > cursor:
            with s.inbox_path.open("rb") as f:
                f.seek(cursor)
                chunk = f.read(size - cursor)
            end = chunk.rfind(b"\n") + 1  # only complete lines
            if end:
                outline = s.read_plan()["outline"]
                for line in chunk[:end].decode("utf-8").splitlines():
                    if line.strip():
                        print(format_batch(a.slug, json.loads(line), outline), flush=True)
                cursor += end
                s.cursor_path.write_text(str(cursor))
        time.sleep(0.5)


def cmd_status(a: argparse.Namespace) -> None:
    st = Session(a.slug).write_status(a.phase, a.section or "", a.message or "")
    print(f"{st['phase']} {st['section']}".strip())


def cmd_change(a: argparse.Namespace) -> None:
    d = Session(a.slug).add_change(a.change, a.why or "", a.instead or "", a.files)
    print(f"{d['id']} recorded")


def cmd_changes(a: argparse.Namespace) -> None:
    """Model changes of one session, or of every code session on a repository."""
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


def main() -> None:
    p = argparse.ArgumentParser(prog="view-concept")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("new", help="create a session (no-op if it exists)")
    q.add_argument("title")
    q.add_argument("--slug")
    q.add_argument("--question")
    q.add_argument("--kind", choices=KINDS, default="explanation")
    q.add_argument("--repo", help="repository a code session is about (citations link into it)")
    q.set_defaults(fn=cmd_new)

    q = sub.add_parser("open", help="start the server if needed and open the page")
    q.add_argument("slug")
    q.add_argument("--no-browser", action="store_true")
    q.set_defaults(fn=cmd_open)

    sub.add_parser("serve", help="run the server in the foreground").set_defaults(fn=cmd_serve)
    sub.add_parser("stop", help="stop the background server").set_defaults(fn=cmd_stop)

    q = sub.add_parser("watch", help="stream comment batches (run under Monitor)")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_watch)

    q = sub.add_parser("status", help="tell the page what Claude is doing now")
    q.add_argument("slug")
    q.add_argument("phase", choices=PHASES)
    q.add_argument("--section", help="outline id being written, for phase 'writing'")
    q.add_argument("--message", help="short free text shown next to the phase")
    q.set_defaults(fn=cmd_status)

    q = sub.add_parser("change", help="record a model change accepted in a PR review")
    q.add_argument("slug")
    q.add_argument("change", help="the model change, one sentence")
    q.add_argument("--why", help="the reason, one sentence")
    q.add_argument("--instead", help="what the PR does now")
    q.add_argument("--files", nargs="*", default=[], help="files the model change touches")
    q.set_defaults(fn=cmd_change)

    q = sub.add_parser(
        "changes",
        help="print model changes as Markdown bullets (for a PR description's Decisions section)",
    )
    q.add_argument("slug", nargs="?")
    q.add_argument("--repo", help="all code sessions on this repo (default: current dir)")
    q.set_defaults(fn=cmd_changes)

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
