"""Start a new agent session from the page: open a terminal window in a project and type
the command that starts Claude Code on a skill there.

The skill drives the session from that terminal, as when the user starts it by hand: it
creates the session and runs `view-concept open`, which brings the page to it."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .store import SessionError, slugify

# The skills a session can start on, in the order the page offers them.
SKILLS = ("view-branch", "view-refactor", "view-concept")

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
    `worktree`, Claude Code first creates that git worktree and runs in it."""
    if skill not in SKILLS:
        raise SessionError(f"unknown skill {skill!r}; one of {', '.join(SKILLS)}")
    if not request.strip():
        raise SessionError("describe the feature")
    args = ["claude"]
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
