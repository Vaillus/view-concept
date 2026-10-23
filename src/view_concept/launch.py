"""Start a new agent session from the page: open a terminal window in a project and type
the command that starts Claude Code on a skill there.

The skill drives the session from that terminal, as when the user starts it by hand: it
creates the session and runs `view-concept open`, which brings the page to it. The agent
runs in auto mode (`--permission-mode auto`): an action the user's settings do not allow
in advance is approved or refused at once by Claude Code's automatic check, and nobody is
asked, so a session started from the phone never waits on a permission prompt in a
terminal window the phone cannot see. A session started by hand keeps its own mode.

From the tap on Start until its agent opens the session, the launch is a pending launch:
every page's sidebar shows it under its project, « starting », then « not started » once
PENDING_FOR seconds went by (the page reads `at`). It gives way to the first session
created in that project after it; × removes it. The pending launches live in
<home>/launches.json, for every page of the server."""

from __future__ import annotations

import shlex
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .store import HOME, SessionError, _read_json, _write_json, project_of, slugify

# The skills a session can start on, in the order the page offers them.
SKILLS = ("build-feature", "triage-code", "review-docs", "view-concept")
# The skills that create their own branch and worktree: a launch takes no worktree for them,
# or the session would run in one and write in the other.
OWN_WORKTREE = ("review-docs",)
# The permission mode every launch starts the agent in (see the module's docstring).
PERMISSION_MODE = "auto"
# After this many seconds with no session, a pending launch reads « not started ».
PENDING_FOR = 300
LAUNCHES = HOME / "launches.json"
_LOCK = threading.Lock()

# A new Ghostty window opened in a folder, with a line typed into its shell. The shell is
# the user's login shell, so `claude` is found as in any terminal they open; the window
# stays at a prompt when the agent exits. Folder and line come as arguments, never
# spliced into the script.
GHOSTTY_SCRIPT = """
on run argv
  tell application "Ghostty"
    set cfg to new surface configuration
    set initial working directory of cfg to item 1 of argv
    set initial input of cfg to item 2 of argv
    new window with configuration cfg
    activate
  end tell
end run
"""


def command(skill: str, request: str, worktree: str = "") -> str:
    """The shell line that starts Claude Code on `skill` with the user's request. With
    `worktree`, Claude Code first creates that git worktree and runs in it; a skill of
    OWN_WORKTREE refuses one."""
    if skill not in SKILLS:
        raise SessionError(f"unknown skill {skill!r}; one of {', '.join(SKILLS)}")
    if not request.strip():
        raise SessionError("describe the feature")
    if worktree and skill in OWN_WORKTREE:
        raise SessionError(f"{skill} creates its own worktree; start it with none")
    args = ["claude", "--permission-mode", PERMISSION_MODE]
    if worktree:
        args += ["-w", slugify(worktree)]
    args.append(f"/{skill} {request.strip()}")
    return shlex.join(args)


def open_terminal(folder: str, line: str) -> None:
    """Open a Ghostty window in `folder` and type `line` into its shell."""
    if not Path(folder).is_dir():
        raise SessionError(f"no folder {folder!r}")
    try:
        done = subprocess.run(
            ["osascript", "-", folder, line + "\n"],
            input=GHOSTTY_SCRIPT,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise SessionError(f"could not open Ghostty: {e}") from e
    if done.returncode:
        raise SessionError(f"could not open Ghostty: {done.stderr.strip()}")


# ---- pending launches ----


def _now() -> datetime:
    return datetime.now(UTC)


def add_pending(folder: str, request: str, skill: str, path: Path | None = None) -> dict[str, Any]:
    """Record a launch just started in `folder`: {id, project, request, skill, at}."""
    path = path or LAUNCHES
    entry = {
        "id": uuid.uuid4().hex[:12],
        "project": project_of(str(Path(folder).expanduser().resolve())),
        "request": request.strip(),
        "skill": skill,
        "at": _now().isoformat(timespec="milliseconds"),
    }
    with _LOCK:
        launches = _read_json(path, [])
        launches.append(entry)
        _write_json(path, launches)
    return entry


def remove_pending(lid: str, path: Path | None = None) -> None:
    path = path or LAUNCHES
    with _LOCK:
        launches = _read_json(path, [])
        _write_json(path, [x for x in launches if x.get("id") != lid])


def _gives_way(launch: dict[str, Any], session: dict[str, Any]) -> bool:
    """Whether `session` is the one `launch` started: created after it, in its project. A
    view-concept launch may make an explanation with no repository, hence no project."""
    if str(session.get("created_at", "")) <= str(launch.get("at", "")):
        return False
    if session.get("project") == launch.get("project"):
        return True
    return launch.get("skill") == "view-concept" and not session.get("project")


def pending(sessions: list[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    """The pending launches no session took the place of yet, oldest first. A launch gives
    way to the first session created in its project after it (each session to one launch,
    the oldest); those that gave way leave the file."""
    path = path or LAUNCHES
    with _LOCK:
        launches = sorted(_read_json(path, []), key=lambda x: str(x.get("at", "")))
        taken: set[str] = set()
        left = []
        for launch in launches:
            hit = next(
                (
                    s
                    for s in sorted(sessions, key=lambda s: str(s.get("created_at", "")))
                    if s["slug"] not in taken and _gives_way(launch, s)
                ),
                None,
            )
            if hit:
                taken.add(hit["slug"])
            else:
                left.append(launch)
        if len(left) != len(launches):
            _write_json(path, left)
    return left
