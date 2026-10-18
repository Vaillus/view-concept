import pytest

from view_concept import launch
from view_concept.store import SessionError


def test_command_quotes_the_request_for_the_shell():
    line = launch.command("view-refactor", "triage `src/` ; it's messy")
    assert line == (
        "claude --permission-mode auto '/view-refactor triage `src/` ; it'\"'\"'s messy'"
    )


def test_command_needs_a_known_skill_and_a_request():
    with pytest.raises(SessionError):
        launch.command("explain", "x")
    with pytest.raises(SessionError):
        launch.command("view-branch", "  ")


def test_open_terminal_needs_a_folder(tmp_path):
    with pytest.raises(SessionError):
        launch.open_terminal(str(tmp_path / "missing"), "claude")
