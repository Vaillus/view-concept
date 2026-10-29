"""Command line: what the view-concept, build-feature, triage-code and review-docs skills call
from the agent."""

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
    FACT_PARTS,
    FACT_PROPOSALS,
    HEARTBEAT_EVERY,
    HOME,
    KINDS,
    MOVE_FATES,
    PHASES,
    WORKFLOWS,
    Session,
    SessionError,
    format_batch,
    format_changes,
    format_doc,
    format_fact,
    format_move,
    format_precedence,
    format_section_problem,
    format_triage,
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
    if not a.no_browser and not focus_page(a.slug):
        webbrowser.open(url)
    print(url)


def focus_page(slug: str) -> bool:
    """Show the session in a page already open in the browser, instead of a new tab.
    False when no page is open."""
    req = urllib.request.Request(f"{_base_url()}/api/focus/{slug}", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read()).get("pages", 0) > 0
    except OSError:
        return False


def cmd_serve(a: argparse.Namespace) -> None:
    from .server import run

    run(HOST, _port())


def cmd_stop(a: argparse.Namespace) -> None:
    print("stopped" if stop_server() else "no server pid on record")


def _batches(s: Session, slug: str):
    """Yield each new batch of the inbox as `(text, cursor after it, batch id)`, and None
    while the inbox is quiet; writes the heartbeat meanwhile.

    The cursor persists across runs, so a later run neither loses a batch sent in between
    nor repeats one already delivered. The caller stores the cursor and records the
    delivery (`deliver`) once it has printed the text."""
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
                        batch = json.loads(raw)
                        text = format_batch(slug, batch, outline, questions, s.move_readmes())
                        yield text, cursor, str(batch.get("id", ""))
                    else:
                        s.cursor_path.write_text(str(cursor))
                continue
        yield None
        time.sleep(0.5)


def deliver(s: Session, delivery: tuple[str, int, str]) -> None:
    """Hand one batch to the agent: print it, move the cursor past it, and record when."""
    text, cursor, batch_id = delivery
    print(text, flush=True)
    s.cursor_path.write_text(str(cursor))
    if batch_id:
        s.record_delivery(batch_id)


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
            deliver(s, delivery)


def cmd_wait(a: argparse.Namespace) -> None:
    """Block until the next batch, print it and exit; for an agent without a background
    monitor. Exit code 3 and no output when none arrives within `--timeout` seconds."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    deadline = time.monotonic() + a.timeout
    for delivery in _batches(s, a.slug):
        if delivery is not None:
            deliver(s, delivery)
            return
        if time.monotonic() >= deadline:
            sys.exit(WAIT_TIMEOUT_CODE)


def cmd_status(a: argparse.Namespace) -> None:
    st = Session(a.slug).write_status(a.phase, a.section, a.message or "", a.done)
    print(" ".join([st["phase"], *st.get("run", {}).get("set", [])]))


def cmd_question(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    q = s.add_question(
        a.text,
        a.option,
        a.multi,
        a.recommended or "",
        a.background or "",
        a.section or "",
        a.element or "",
        a.supposition,
    )
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


def cmd_anchor(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    q = s.anchor_question(a.qid, a.section)
    print(f"{q['id']} anchored to {q['section']}")


def cmd_reask(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    q = s.reask_question(a.qid, a.text or "", a.recommended or "")
    print(f"{q['id']} open")
    if not s.is_listening():
        print(
            f"view-concept: no watch or wait is running for {a.slug}; the answer will wait in the "
            "inbox until one starts. Start listening now.",
            file=sys.stderr,
        )


def cmd_change(a: argparse.Namespace) -> None:
    d = Session(a.slug).add_change(a.change, a.by or "", a.cause)
    print(f"{d['id']} recorded")


def cmd_implemented(a: argparse.Namespace) -> None:
    """Record the last change of the model an implementer run took into account, or, with
    no change id, print how far the code carries the model."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    if a.change_id:
        print(f"implemented through {s.mark_implemented(a.change_id)['through']}")
        return
    through = s.implemented_through()
    print(f"implemented through {through}" if through else "no implementer run yet")
    pending = [d["id"] for d in s.unimplemented_changes()]
    print(f"not implemented yet: {', '.join(pending)}" if pending else "nothing left to implement")


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


def cmd_request(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    s.write_request(sys.stdin.read() if a.file == "-" else Path(a.file).read_text("utf-8"))
    print(f"request transcript written: {s.request_path}")


def cmd_pr(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    print(f"PR recorded: {s.set_pr(a.url)['url']}")


def _existing(slug: str) -> Session:
    s = Session(slug)
    if not s.exists():
        raise SessionError(f"no session {slug!r}")
    return s


def _int_arg(value: str, what: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise SessionError(f"{what} is a whole number, not {value!r}") from None


def cmd_doc_set(a: argparse.Namespace) -> None:
    """Change the doc set (add or remove a doc, class one minor or not, record a README's
    failure indicator, put the docs in the write order), or, with no operation, print it."""
    s = _existing(a.slug)
    args = a.args
    if a.op != "minor" and (a.added is not None or a.removed is not None):
        raise SessionError("--added and --removed go with minor only")
    if a.op != "failing" and a.structure:
        raise SessionError("--structure goes with failing only")
    if a.op not in ("failing", "moved") and a.clear:
        raise SessionError("--clear goes with failing or moved only")
    if a.user and a.op not in ("add", "remove"):
        raise SessionError("--user goes with add or remove only")
    if a.op == "add":
        if len(args) != 2:
            raise SessionError('doc-set add takes a path and a reason: add <path> "<reason>"')
        print(f"added {s.add_doc(args[0], args[1], a.user)['path']}")
        return
    if a.op == "remove":
        if len(args) != 1:
            raise SessionError("doc-set remove takes one path")
        s.remove_doc(args[0], a.user)
        print(f"removed {args[0]}" + (" (by the user: not added back)" if a.user else ""))
        return
    if a.op == "minor":
        if len(args) != 2 or a.added is None or a.removed is None:
            raise SessionError(
                "doc-set minor takes a path, a reason and the diff size: "
                'minor <path> "<reason>" --added N --removed N'
            )
        print(format_doc(s.set_minor(args[0], args[1], a.added, a.removed)))
        return
    if a.op == "major":
        if len(args) != 1:
            raise SessionError("doc-set major takes one path")
        print(format_doc(s.set_major(args[0])))
        return
    if a.op == "failing":
        if a.clear:
            if len(args) != 1 or a.structure:
                raise SessionError("doc-set failing <path> --clear takes the path alone")
            print(format_doc(s.set_failing(args[0], None)))
            return
        if len(args) != 3:
            raise SessionError("doc-set failing takes a README, then <fail> <total> [--structure]")
        fail, total = _int_arg(args[1], "fail"), _int_arg(args[2], "total")
        print(format_doc(s.set_failing(args[0], fail, total, a.structure)))
        return
    if a.op == "moved":
        if a.clear:
            if len(args) != 1:
                raise SessionError("doc-set moved <path> --clear takes the path alone")
            print(format_doc(s.set_moved(args[0], None)))
            return
        if len(args) != 2:
            raise SessionError("doc-set moved takes the doc's path and its old path")
        print(format_doc(s.set_moved(args[0], args[1])))
        return
    if a.op == "order":
        if not args:
            raise SessionError("doc-set order takes every doc of the doc set, in the write order")
        s.order_docs(args)
    elif args:
        raise SessionError("give an operation: add, remove, minor, major, failing, moved or order")
    data = s.read_doc_set()
    for d in data["docs"]:
        print(format_doc(d))
    if not data["docs"]:
        print("(no doc set yet)")
    if data["removed"]:
        print(f"removed by the user: {', '.join(data['removed'])}")


def cmd_stale(a: argparse.Namespace) -> None:
    """Flag a stale passage, drop flags, or, with no argument, print the flags shown."""
    s = _existing(a.slug)
    if a.drop:
        if a.doc:
            raise SessionError("--drop takes stale passage ids only")
        s.drop_stale(a.drop)
        print(f"dropped {', '.join(a.drop)}")
        return
    if a.doc:
        if not a.quote or not a.note:
            raise SessionError('stale takes a doc, a quote and a note: <doc> "<quote>" "<note>"')
        print(s.add_stale(a.doc, a.quote, a.note, a.section or "")["id"])
        return
    flags = s.shown_stale()
    for f in flags:
        quote = " ".join(f["quote"].split())
        section = f" (section {f['section']})" if f.get("section") else ""
        print(f"{f['id']} {f['doc']} « {quote} »{section}: {f['note']}")
    if not flags:
        print("(no stale passage shown)")


def cmd_facts(a: argparse.Namespace) -> None:
    """Record a missing fact of a README (what its old text said and no README written
    says any more, after a full rewrite, a restructuring or a rewritten folder model),
    mark the user's decision on one, drop a README's list, or, with no operation, print
    them by README."""
    s = _existing(a.slug)
    args = a.args
    if a.op != "add" and (a.propose or a.reason or a.passage is not None):
        raise SessionError("--propose, --reason and --passage go with add only")
    if a.op not in ("add", "clear") and a.part:
        raise SessionError("--part goes with add and clear only")
    if a.op == "add":
        if len(args) != 2 or not a.propose or not a.reason or not a.part:
            raise SessionError(
                "facts add takes a README, the fact, its part, proposal and reason: add <path> "
                '"<fact>" --part readme|model --propose keep|leave --reason "<one line>" '
                "[--passage N]"
            )
        f = s.add_missing_fact(args[0], args[1], a.propose, a.reason, a.passage, a.part)
        print(f["id"])
        return
    if a.op == "mark":
        if len(args) != 2:
            raise SessionError("facts mark takes a fact id and a state: <id> kept|left|pending")
        f = s.mark_missing_fact(args[0], args[1])
        print(f"{f['id']} {f['state']}")
        return
    if a.op == "clear":
        if len(args) != 1 or not a.part:
            raise SessionError(
                "facts clear takes one README path and the part whose facts it drops: "
                "clear <path> --part readme|model"
            )
        n = s.clear_missing_facts(args[0], a.part)
        print(f"cleared {n} missing facts of {args[0]} from part {a.part}")
        return
    if args:
        raise SessionError("give an operation: add, mark or clear")
    data = s.read_missing_facts()
    for path, facts in data.items():
        print(f"{path} · {len(facts)} missing facts")
        for f in facts:
            print(f"  {format_fact(f)}")
    if not data:
        print("(no missing fact)")


def cmd_triage(a: argparse.Namespace) -> None:
    """Set a concept's row of the concept triage, remove one, or, with no operation,
    print the triage."""
    s = _existing(a.slug)
    args = a.args
    if a.op == "set":
        if len(args) != 3 or args[1] not in ("enters", "out"):
            raise SessionError(
                "triage set takes a concept, enters or out, and the reason: "
                'set "<concept>" enters|out "<reason>"'
            )
        print(format_triage(s.set_triage(args[0], args[1] == "enters", args[2])))
        return
    if a.op == "remove":
        if len(args) != 1:
            raise SessionError("triage remove takes one row id")
        s.remove_triage(args[0])
        print(f"removed {args[0]}")
        return
    if args:
        raise SessionError("give an operation: set or remove")
    rows = s.read_triage()
    for r in rows:
        print(format_triage(r))
    if not rows:
        print("(no concept triage yet)")


def cmd_moves(a: argparse.Namespace) -> None:
    """Add a row to a README's move plan, clear a plan, or, with no operation, print the
    plans by README."""
    s = _existing(a.slug)
    args = a.args
    if a.op != "add" and (a.becomes or a.to or a.note):
        raise SessionError("--becomes, --to and --note go with add only")
    if a.op == "add":
        if len(args) != 2 or not a.becomes:
            raise SessionError(
                'moves add takes a README and the passage: add <readme> "<passage>" '
                "--becomes as-is|rewritten|nowhere [--to <readme>] "
                '[--note "<one line>"]'
            )
        row = s.add_move(args[0], args[1], a.becomes, a.to or "", a.note or "")
        print(format_move(row))
        return
    if a.op == "clear":
        if len(args) != 1:
            raise SessionError("moves clear takes one README path")
        print(f"cleared {s.clear_moves(args[0])} rows of the move plan of {args[0]}")
        return
    if args:
        raise SessionError("give an operation: add or clear")
    data = s.read_moves()
    for path, rows in data.items():
        print(f"{path} · {len(rows)} passages")
        for r in rows:
            print(f"  {format_move(r)}")
    if not data:
        print("(no move plan)")


def cmd_reference(a: argparse.Namespace) -> None:
    """Set or clear the reference model, list its candidates, or, with none of these,
    print it."""
    s = _existing(a.slug)
    if sum(map(bool, (a.other, a.clear, a.candidates))) > 1:
        raise SessionError("give a session, --clear or --candidates, one at a time")
    if a.candidates:
        rows = s.reference_candidates()
        for c in rows:
            print(f"{c['slug']} · {c['title']} · updated {c['updated']}")
            print(f"  sections: {' / '.join(c['sections']) or '(none)'}")
            print(f"  terms: {', '.join(c['terms']) or '(none)'}")
        if not rows:
            print("(no feature of this repo)")
        return
    if a.clear or a.other:
        ref = s.set_reference("" if a.clear else a.other, a.reason or "")
        print(f"reference model: {ref['slug']} — {ref['reason']}" if ref else "no reference model")
        return
    model = s.reference_model()
    if not model:
        print("no reference model")
        return
    reason = f" — {model['reason']}" if model["reason"] else ""
    print(f"reference model: {model['slug']} ({model['title']}){reason}")


def cmd_variant(a: argparse.Namespace) -> None:
    """Name the setup a session runs with and the model of each role, or, with no name,
    print it: the coordinator passes a role's model when it starts that role's agent."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    if a.name:
        models: dict[str, str] = {}
        for pair in a.model:
            role, sep, model = pair.partition("=")
            if not sep:
                raise SessionError(f"--model takes role=model, got {pair!r}")
            models[role.strip()] = model.strip()
        s.set_variant(a.name, models)
    elif a.model:
        raise SessionError("--model goes with a variant name")
    v = s.read_variant()
    pairs = ", ".join(f"{role}={model}" for role, model in v["models"].items())
    print(f"variant: {v['name']}" + (f" · models: {pairs}" if pairs else " · no model per role"))


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
    audit.json (replacing the previous ones, keeping the agent's own entries). Then the
    section problems (an HTML block in a Markdown section, two files for one section, an
    HTML section file over the limit, a waiting question anchored to a section the outline
    no longer has), printed only: they name no word to underline."""
    s = Session(a.slug)
    if not s.exists():
        raise SessionError(f"no session {a.slug!r}")
    problems = s.check_precedence()
    for p in problems:
        print(format_precedence(p))
    print(f"{len(problems)} problem{'' if len(problems) == 1 else 's'} written to audit.json")
    sections = s.check_sections()
    for p in sections:
        print(format_section_problem(p))
    if sections:
        n = len(sections)
        print(f"{n} section problem{'' if n == 1 else 's'}, printed only (not in audit.json)")


def cmd_pending(a: argparse.Namespace) -> None:
    s = Session(a.slug)
    outline, moves = s.read_plan()["outline"], s.move_readmes()
    for b in s.read_comments()["batches"]:
        open_ = [c for c in b["comments"] if c["status"] == "sent"]
        if open_:
            print(format_batch(a.slug, {**b, "comments": open_}, outline, moves=moves))
            print()


def cmd_resolve(a: argparse.Namespace) -> None:
    touched = Session(a.slug).resolve(a.ids, a.reply or "")
    print(f"resolved {', '.join(touched) or 'nothing'}")


def cmd_export(a: argparse.Namespace) -> None:
    print(Session(a.slug).export())


def cmd_publish(a: argparse.Namespace) -> None:
    from .publish import publish

    print(publish(Session(a.slug)))


def cmd_unpublish(a: argparse.Namespace) -> None:
    from .publish import unpublish

    unpublish(Session(a.slug))
    print(f"unpublished {a.slug}")


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
    q.add_argument("--base", help="the branch a feature compares with")
    q.add_argument(
        "--workflow",
        choices=WORKFLOWS,
        help="the skill driving the session; picks its verdict set "
        "(default: view-concept, or build-feature for a code session)",
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
    q.add_argument(
        "--section",
        action="append",
        default=[],
        help="a section the writing run writes (repeatable), on the call that starts the run: "
        "its run set; none means every section with no file yet",
    )
    q.add_argument(
        "--done",
        action="store_true",
        help="with phase 'scoping': the agent has nothing more to ask (scoping done)",
    )
    q.add_argument("--message", help="short free text shown next to the phase")
    q.set_defaults(fn=cmd_status)

    q = sub.add_parser("question", help="put an agent question to the user in the page")
    q.add_argument("slug")
    q.add_argument("text", help="the question")
    q.add_argument("--option", action="append", default=[], help="one choice (repeatable)")
    q.add_argument("--multi", action="store_true", help="the user may pick several choices")
    q.add_argument("--recommended", help="the answer you suggest: an option, or a text")
    q.add_argument(
        "--background",
        help="what the user needs to know to answer: the mechanism today, each option's trade-offs",
    )
    q.add_argument("--section", help="the anchor section: the page shows the question after it")
    q.add_argument(
        "--element",
        help="on a scoping section: the id of the element of the drawing the hole bears on",
    )
    q.add_argument(
        "--supposition",
        action="store_true",
        help="a hole you already answered (the text): the user approves or corrects it",
    )
    q.set_defaults(fn=cmd_question)

    q = sub.add_parser(
        "anchor", help="set the section after which an open or deferred question is asked"
    )
    q.add_argument("slug")
    q.add_argument("qid", help="the question id, e.g. q1")
    q.add_argument("section", help="the outline id of its anchor section")
    q.set_defaults(fn=cmd_anchor)

    q = sub.add_parser(
        "reask", help="ask a deferred question again, under the same id (deferred -> open)"
    )
    q.add_argument("slug")
    q.add_argument("qid", help="the question id, e.g. q1")
    q.add_argument("--text", help="a new wording of the question")
    q.add_argument("--recommended", help="a new recommended answer")
    q.set_defaults(fn=cmd_reask)

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
    q.add_argument("--by", help="who made it: scoper, planner or writer")
    q.add_argument(
        "--cause",
        nargs="*",
        default=[],
        help="the question, comment or terminal message ids that led to it (default: own judgment)",
    )
    q.set_defaults(fn=cmd_change)

    q = sub.add_parser(
        "implemented",
        help="record the last model change the code now carries, or print what is left",
    )
    q.add_argument("slug")
    q.add_argument("change_id", nargs="?", help="the last change taken into account, e.g. m8")
    q.set_defaults(fn=cmd_implemented)

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

    q = sub.add_parser(
        "request", help="write the request transcript (request.md), replacing any previous one"
    )
    q.add_argument("slug")
    q.add_argument(
        "file", help="a Markdown file, one `## User` or `## Agent` heading per message, or -"
    )
    q.set_defaults(fn=cmd_request)

    q = sub.add_parser("pr", help="record the session's PR link, for the page to show")
    q.add_argument("slug")
    q.add_argument("url", help="the PR's link, as gh pr create prints it")
    q.set_defaults(fn=cmd_pr)

    q = sub.add_parser(
        "variant",
        help="name the setup the session runs with and a model per role, or print it",
    )
    q.add_argument("slug")
    q.add_argument("name", nargs="?", help="the setup's name, e.g. « writer on sonnet »")
    q.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="ROLE=MODEL",
        help="the model a role's agent runs on, e.g. writer=sonnet (repeatable); "
        "a role left out keeps the coordinator's model",
    )
    q.set_defaults(fn=cmd_variant)

    q = sub.add_parser(
        "doc-set",
        help="print the doc set, or change it: add or remove a doc, class one minor or "
        "major, record a README's failure indicator or the old path of a moved doc, put the "
        "docs in the write order",
    )
    q.add_argument("slug")
    q.add_argument(
        "op", nargs="?", choices=("add", "remove", "minor", "major", "failing", "moved", "order")
    )
    q.add_argument(
        "args",
        nargs="*",
        help="add <path> <reason> · remove <path> · minor <path> <reason> · major <path> · "
        "failing <path> <fail> <total> · moved <path> <old path> (the code moved the doc "
        "from its old path) · order <path> <path>… (every doc, in the write order); a path "
        "is relative to the repo root",
    )
    q.add_argument("--added", type=int, help="with minor: the lines the doc's diff adds")
    q.add_argument("--removed", type=int, help="with minor: the lines the doc's diff removes")
    q.add_argument(
        "--structure", action="store_true", help="with failing: the README's structure fails"
    )
    q.add_argument(
        "--clear",
        action="store_true",
        help="with failing: remove the indicator; with moved: remove the old path",
    )
    q.add_argument(
        "--user",
        action="store_true",
        help="the user asked for it in a comment: remove records the doc as removed by the "
        "user (a refresh never adds it back); add takes it back in",
    )
    q.set_defaults(fn=cmd_doc_set)

    q = sub.add_parser(
        "stale", help="flag a doc passage the model contradicts, drop flags, or print them"
    )
    q.add_argument("slug")
    q.add_argument("doc", nargs="?", help="the doc's path, a doc of the doc set")
    q.add_argument("quote", nargs="?", help="the passage, exactly as the file has it")
    q.add_argument("note", nargs="?", help="one line: why the model contradicts it")
    q.add_argument("--section", help="the model section it contradicts")
    q.add_argument("--drop", nargs="+", metavar="ID", help="remove flags (fixed or dismissed)")
    q.set_defaults(fn=cmd_stale)

    q = sub.add_parser(
        "facts",
        help="record the missing facts of a README (what its old text said and no README "
        "written says any more, after a full rewrite, a restructuring or a rewritten "
        "folder model), mark the user's decision on one, or print them",
    )
    q.add_argument("slug")
    q.add_argument("op", nargs="?", choices=("add", "mark", "clear"))
    q.add_argument(
        "args",
        nargs="*",
        help="add <path> <fact> · mark <id> kept|left|pending · clear <path> (a new rewrite "
        "by one skill replaces the README's facts of that skill's part)",
    )
    q.add_argument(
        "--part",
        choices=FACT_PARTS,
        help="with add and clear: the part of the old README the fact came from, readme "
        "(the README's skeleton, write-readme's) or model (the folder model, document-feature's)",
    )
    q.add_argument("--propose", choices=FACT_PROPOSALS, help="with add: keep or leave the fact")
    q.add_argument("--reason", help="with add: one line, why that proposal")
    q.add_argument("--passage", type=int, help="with add: the number of the old README's passage")
    q.set_defaults(fn=cmd_facts)

    q = sub.add_parser(
        "triage",
        help="print the concept triage (whether each concept of the model enters the docs), "
        "or set or remove a row",
    )
    q.add_argument("slug")
    q.add_argument("op", nargs="?", choices=("set", "remove"))
    q.add_argument(
        "args",
        nargs="*",
        help="set <concept> enters|out <reason> (a concept already listed keeps its row and "
        "id) · remove <id>",
    )
    q.set_defaults(fn=cmd_triage)

    q = sub.add_parser(
        "moves",
        help="print the move plans of the restructured READMEs, add a row to one, or clear one",
    )
    q.add_argument("slug")
    q.add_argument("op", nargs="?", choices=("add", "clear"))
    q.add_argument(
        "args",
        nargs="*",
        help="add <readme> <passage> (a README of the doc set; a passage of its folder model "
        "in one line) · "
        "clear <readme>",
    )
    q.add_argument("--becomes", choices=MOVE_FATES, help="with add: what it becomes")
    q.add_argument("--to", help="with add: the README it goes to (none with --becomes nowhere)")
    q.add_argument("--note", help="with add: one optional line")
    q.set_defaults(fn=cmd_moves)

    q = sub.add_parser(
        "reference",
        help="take a feature's model as the reference model of a docs review, or clear it",
    )
    q.add_argument("slug")
    q.add_argument("other", nargs="?", help="the slug of a feature of the same repo")
    q.add_argument("--reason", help="one line: why this model is the reference (with a session)")
    q.add_argument("--clear", action="store_true", help="remove the reference model")
    q.add_argument(
        "--candidates",
        action="store_true",
        help="list the repo's features, with their sections and terms",
    )
    q.set_defaults(fn=cmd_reference)

    q = sub.add_parser("context", help="print the context a subagent or a side thread starts from")
    q.add_argument("slug")
    q.add_argument("--role", choices=ROLES, required=True)
    q.add_argument(
        "--trigger",
        nargs="*",
        default=[],
        help="the events that started this run: question, comment, batch, terminal "
        "message, change or section ids, or a word such as « Write model »",
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
        help="list forward references and early uses of the lexicon, write them to audit.json;"
        " list section problems (HTML blocks, two files, an HTML section over 2 MB)",
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

    q = sub.add_parser(
        "publish", help="publish the explanation as a page in the pages repo, print its link"
    )
    q.add_argument("slug")
    q.set_defaults(fn=cmd_publish)

    q = sub.add_parser("unpublish", help="delete the published page from the pages repo")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_unpublish)

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
