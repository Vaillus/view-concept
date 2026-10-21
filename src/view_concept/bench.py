"""The runs of a workbench: write-readme run on each case of the case set, by the server.

A run is one execution of write-readme on one case, by a fresh agent the server starts: a
blank conversation (no resume, no fork) on the session's agent (`agents.resolve`), given
one prompt that names the skill version's path and the case's folder, and nothing else.
« Run » on a case starts one run of it, « Run all » one run per case not running already;
no batch is written, so the session's agent learns of a run only when a comment names it.

Each run follows these steps:

1. The skill file (store.SKILL_FILE in the session's repo) is copied to its skill version,
   skill-versions/v<k>.md: a text equal to the newest version's takes its number, any
   other text the next one. « Run all » copies it once, so all its runs read one version,
   and the run reads that copy, which an edit of the skill file during the run never
   reaches.
2. The throwaway checkout: the pinned commit of the cases' repo exported (`git archive`)
   into a fresh temp folder, with no git history, so a draft case cannot read back the
   README removed from it (its comparison README). The file hashes there are noted.
3. The run's agent works in the checkout (its cwd), with write access there only.
4. When it ends, the run keeps, in runs/<case id>/<n>/: the README it wrote (README.md),
   its run report, the agent's last message (report.md), a copy of every other file it
   wrote under files/<path>, and run.json; its `other_files` lists every file it wrote,
   changed or deleted besides its README, the flag the page shows on the case. The
   checkout is deleted.

A run that fails (its agent could not start, exited non-zero or ended with no final text)
leaves no run folder: its error goes to runs/<case id>/error.json, which the case's next
run deletes. While a run runs, the server keeps its process here (`_running`); a run.json
still "running" with no process here was cut off by a server restart, and reads as the
error « interrupted ».
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import IO, Any

from .agents import Backend, TurnState, resolve
from .store import (
    Session,
    SessionError,
    _read_json,
    _write_json,
    case_readme,
    now_iso,
)

# (session dir, case id) -> the running process, None while its checkout is being made.
_running: dict[tuple[str, str], subprocess.Popen | None] = {}
_lock = threading.Lock()

GIT_ARCHIVE_TIMEOUT = 300  # seconds
# The fields of run.json the page reads.
RUN_FIELDS = ("n", "skill_version", "state", "started", "ended", "agent", "other_files")


class RunFailed(Exception):
    pass


def is_running(s: Session, cid: str) -> bool:
    return (str(s.dir), cid) in _running


def prompt(version: Path, folder: str) -> str:
    """The one message a run's agent gets: the skill version's path and the case's folder."""
    return (
        f"Read the skill file {version} and follow it to write the README of the folder"
        f" {folder} (the repository root when empty) in this repository, the current folder."
        " No one answers questions during this run: where the skill asks the user, take its"
        " default. Write only that README. End with the run report the skill prints, as your"
        " last message."
    )


# ---- skill versions ----
def versions(s: Session) -> dict[int, Path]:
    """Every skill version so far, by number."""
    folder = s.skill_versions_dir
    if not folder.is_dir():
        return {}
    out = {}
    for f in folder.glob("v*.md"):
        with contextlib.suppress(ValueError):
            out[int(f.stem[1:])] = f
    return dict(sorted(out.items()))


def current_version(s: Session) -> int | None:
    """The number of the newest skill version when the skill file's text equals it, else
    None (the file changed since, or no run copied it yet)."""
    file = s.skill_file()
    known = versions(s)
    if file is None or not file.is_file() or not known:
        return None
    k = max(known)
    return k if known[k].read_text(encoding="utf-8") == file.read_text(encoding="utf-8") else None


def copy_skill(s: Session) -> tuple[int, Path]:
    """Copy the skill file to its skill version: the newest version's number when the text
    equals it, else a new version k+1. Returns the number and the copy's path."""
    file = s.skill_file()
    if file is None or not file.is_file():
        raise SessionError(f"no skill file at {file}")
    text = file.read_text(encoding="utf-8")
    known = versions(s)
    if known and known[max(known)].read_text(encoding="utf-8") == text:
        return max(known), known[max(known)]
    k = max(known, default=0) + 1
    path = s.skill_versions_dir / f"v{k}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return k, path


# ---- the throwaway checkout ----
def make_checkout(repo: Path, commit: str, case: dict[str, Any]) -> Path:
    """The pinned commit's files exported into a fresh temp folder, with no git history;
    a draft case's README removed there."""
    dest = Path(tempfile.mkdtemp(prefix="vc-run-"))
    try:
        archive = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", commit],
            capture_output=True,
            timeout=GIT_ARCHIVE_TIMEOUT,
        )
        if archive.returncode:
            detail = archive.stderr.decode("utf-8", errors="replace").strip()
            raise RunFailed(f"git archive {commit[:7]} failed: {detail}")
        untar = subprocess.run(
            ["tar", "-x", "-C", str(dest)],
            input=archive.stdout,
            capture_output=True,
            timeout=GIT_ARCHIVE_TIMEOUT,
        )
        if untar.returncode:
            raise RunFailed(f"tar failed: {untar.stderr.decode('utf-8', errors='replace')}")
        if case.get("kind") == "draft":
            (dest / case_readme(case)).unlink(missing_ok=True)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def snapshot(root: Path) -> dict[str, str]:
    """A hash of every file under `root`, by its path relative to it."""
    out = {}
    for f in root.rglob("*"):
        if f.is_file() and not f.is_symlink():
            out[f.relative_to(root).as_posix()] = hashlib.sha1(f.read_bytes()).hexdigest()
    return out


def other_files(before: dict[str, str], after: dict[str, str], readme: str) -> list[str]:
    """The files a run wrote, changed or deleted besides its README."""
    touched = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    return sorted(touched - {readme})


# ---- starting runs ----
def start(s: Session, case: str = "") -> list[dict[str, Any]]:
    """Start one run of `case`, or with "" one run of every case not running already.
    Returns [{case, n}] for each run started. Refused with no case set, for an unknown
    case and for a case running already."""
    with _lock:
        data = s.read_cases()
        if not data["repo"] or not data["commit"] or not data["cases"]:
            raise SessionError("this session has no case set yet")
        if case:
            cases = [c for c in data["cases"] if c.get("id") == case]
            if not cases:
                raise SessionError(f"no case {case!r}")
            if is_running(s, case):
                raise SessionError(f"{case} is running already")
        else:
            cases = [c for c in data["cases"] if not is_running(s, c["id"])]
        if not cases:
            return []
        try:
            backend = resolve(s)
        except ValueError as e:
            raise SessionError(str(e)) from e
        k, version = copy_skill(s)
        started = []
        for c in cases:
            n = _new_run(s, c, k, data["commit"], backend.name)
            _running[(str(s.dir), c["id"])] = None
            args = (s, c, n, version, Path(data["repo"]), data["commit"], backend)
            threading.Thread(target=_run, args=args, daemon=True).start()
            started.append({"case": c["id"], "n": n})
    return started


def _new_run(s: Session, case: dict[str, Any], k: int, commit: str, agent: str) -> int:
    """Make the folder of the case's next run, with its run.json "running". A new run
    deletes the case's last error, and the runs a server restart cut off."""
    folder = s.case_runs_dir(case["id"])
    (folder / "error.json").unlink(missing_ok=True)
    for run in s.read_runs(case["id"]):
        if run.get("state") == "running":
            shutil.rmtree(s.run_dir(case["id"], int(run["n"])), ignore_errors=True)
    taken = [int(d.name) for d in folder.glob("*") if d.name.isdigit()] if folder.is_dir() else []
    n = max(taken, default=0) + 1
    record = {
        "case": case["id"],
        "n": n,
        "skill_version": k,
        "commit": commit,
        "started": now_iso(),
        "ended": None,
        "agent": agent,
        "state": "running",
        "other_files": [],
    }
    _write_json(s.run_dir(case["id"], n) / "run.json", record)
    return n


def _run(
    s: Session,
    case: dict[str, Any],
    n: int,
    version: Path,
    repo: Path,
    commit: str,
    backend: Backend,
) -> None:
    """Make the checkout, run the agent there, keep what it produced; or record the error."""
    key = (str(s.dir), case["id"])
    checkout: Path | None = None
    try:
        checkout = make_checkout(repo, commit, case)
        before = snapshot(checkout)
        turn = _agent(key, backend, checkout, prompt(version, case["folder"]))
        _keep(s, case, n, checkout, before, turn.final_text.strip())
    except (RunFailed, OSError, SessionError, subprocess.SubprocessError) as e:
        _fail(s, case["id"], n, str(e) or type(e).__name__)
    finally:
        if checkout is not None:
            shutil.rmtree(checkout, ignore_errors=True)
        with _lock:
            # Only once the final state is on disk, as for a side thread.
            _running.pop(key, None)


def _agent(key: tuple[str, str], backend: Backend, cwd: Path, text: str) -> TurnState:
    """Run the agent on the prompt in `cwd` until it ends. Raises RunFailed when it could
    not start, exited non-zero or ended with no final text."""
    args = backend.run_args()
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as err:
        try:
            proc = subprocess.Popen(
                args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True
            )
        except OSError as e:
            raise RunFailed(f"could not start {args[0]}: {e}") from e
        with _lock:
            _running[key] = proc
        turn = TurnState()
        assert proc.stdin and proc.stdout
        try:
            proc.stdin.write(text)
            proc.stdin.close()
        except BrokenPipeError:
            turn.noise.append("the agent closed its input before reading the prompt")
        for line in proc.stdout:
            backend.run_feed(line, turn)
        code = proc.wait()
        turn.noise += _tail(err)
        backend.run_close(turn, code)
    if turn.failed:
        raise RunFailed(turn.error or f"exit code {code}")
    if not turn.final_text.strip():
        raise RunFailed("the agent ended without a run report")
    return turn


def _tail(f: IO[str], lines: int = 5) -> list[str]:
    f.seek(0)
    return [line.rstrip() for line in f.read().splitlines()[-lines:] if line.strip()]


def _keep(
    s: Session, case: dict[str, Any], n: int, checkout: Path, before: dict[str, str], report: str
) -> None:
    """Keep what the run produced in its folder, and mark it done."""
    folder = s.run_dir(case["id"], n)
    readme = case_readme(case)
    if (checkout / readme).is_file():
        shutil.copyfile(checkout / readme, folder / "README.md")
    (folder / "report.md").write_text(report + "\n", encoding="utf-8")
    others = other_files(before, snapshot(checkout), readme)
    for path in others:
        if (checkout / path).is_file():
            (folder / "files" / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checkout / path, folder / "files" / path)
    record = _read_json(folder / "run.json", {})
    record.update(state="done", ended=now_iso(), other_files=others)
    _write_json(folder / "run.json", record)


def _fail(s: Session, cid: str, n: int, error: str) -> None:
    """A failed run leaves no run folder, only its error."""
    shutil.rmtree(s.run_dir(cid, n), ignore_errors=True)
    _write_json(s.case_runs_dir(cid) / "error.json", {"at": now_iso(), "error": error.strip()})


# ---- what the page reads ----
def case_runs(s: Session, cid: str) -> tuple[list[dict[str, Any]], str | None]:
    """The runs of a case the page lists (oldest first, a running one included) and its
    error: the last failed attempt, or « interrupted » for a run a server restart cut off;
    None when there is none."""
    running = is_running(s, cid)
    runs, interrupted = [], False
    for run in s.read_runs(cid):
        if run.get("state") == "running" and not running:
            interrupted = True
            continue
        runs.append(run)
    error = s.read_run_error(cid)
    if error:
        return runs, str(error.get("error", "")) or "the run failed"
    return runs, "interrupted" if interrupted else None


def run_text(s: Session, run: dict[str, Any], name: str) -> str | None:
    """A file a done run kept (README.md, report.md), None while it runs or when absent."""
    if run.get("state") != "done":
        return None
    file = s.run_dir(str(run["case"]), int(run["n"])) / name
    return file.read_text(encoding="utf-8", errors="replace") if file.is_file() else None
