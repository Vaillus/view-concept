import pytest

from view_concept import launch
from view_concept.store import SessionError


def test_command_quotes_the_request_for_the_shell():
    line = launch.command("triage-code", "triage `src/` ; it's messy")
    assert line == ("claude --permission-mode auto '/triage-code triage `src/` ; it'\"'\"'s messy'")


def test_command_needs_a_known_skill_and_a_request():
    with pytest.raises(SessionError):
        launch.command("explain", "x")
    with pytest.raises(SessionError):
        launch.command("build-feature", "  ")


def test_command_refuses_a_worktree_for_a_skill_that_makes_its_own():
    assert " -w review " in launch.command("build-feature", "x", worktree="review")
    with pytest.raises(SessionError):
        launch.command("review-docs", "x", worktree="docs")
    assert " -w " not in launch.command("review-docs", "x")


def test_open_terminal_needs_a_folder(tmp_path):
    with pytest.raises(SessionError):
        launch.open_terminal(str(tmp_path / "missing"), "claude")


def test_a_view_concept_launch_gives_way_to_a_session_with_no_project(tmp_path):
    path = tmp_path / "launches.json"
    launch.add_pending(str(tmp_path), "explain the gate", "view-concept", path)
    review = launch.add_pending(str(tmp_path), "review", "build-feature", path)
    rows = [{"slug": "loose", "project": None, "created_at": "9999"}]
    # The session with no project takes the view-concept launch's place, not the review's.
    assert [x["id"] for x in launch.pending(rows, path)] == [review["id"]]


def test_a_docs_review_can_be_launched():
    assert "review-docs" in launch.SKILLS and launch.SKILLS[0] == "build-feature"
    assert launch.command("review-docs", "the install docs").endswith(
        "'/review-docs the install docs'"
    )
