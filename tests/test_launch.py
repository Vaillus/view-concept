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


def test_a_view_concept_launch_gives_way_to_a_session_with_no_project(tmp_path):
    path = tmp_path / "launches.json"
    launch.add_pending(str(tmp_path), "explain the gate", "view-concept", path)
    review = launch.add_pending(str(tmp_path), "review", "view-branch", path)
    rows = [{"slug": "loose", "project": None, "created_at": "9999"}]
    # The session with no project takes the view-concept launch's place, not the review's.
    assert [x["id"] for x in launch.pending(rows, path)] == [review["id"]]


def test_a_docs_review_can_be_launched():
    assert "view-docs" in launch.SKILLS and launch.SKILLS[0] == "view-branch"
    assert launch.command("view-docs", "the install docs").endswith("'/view-docs the install docs'")
