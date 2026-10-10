import pytest

from view_concept.context import CONTEXT_RECENT, build
from view_concept.store import Session, SessionError


@pytest.fixture
def review(tmp_path):
    s = Session("gate", tmp_path)
    s.create("The gate", "rework the gate", kind="code", repo=str(tmp_path), base="main")
    return s


def test_planner_context_holds_the_folder_and_no_sections(session):
    session.add_question("Level?")
    text = build(session, "planner")
    assert "## Initial request\nexplique le KV cache" in text
    assert "## Trigger\nnone: the first run of this role" in text
    assert "1. Attention (s1)" in text and "- clé | key (section 1): vecteur" in text
    assert "Open:\n- q1 [open] Level?" in text
    assert "## Sections" not in text and "L'attention." not in text


def test_writer_gets_every_section_and_thread_only_its_own(session):
    writer = build(session, "writer")
    assert "### 1. Attention (s1)\nL'attention." in writer and "Le cache." in writer
    thread = build(session, "thread", section="s2")
    assert "Le cache." in thread and "L'attention." not in thread


def test_review_context_names_the_repo_and_base(review, tmp_path):
    assert f"Repository: {tmp_path} · base branch: main." in build(review, "planner")


def test_trigger_events_are_given_in_full(session):
    session.add_question("PR or merge?", ["PR", "merge"])
    session.answer_question("q1", ["PR"], "squash it")
    b = session.add_batch([{"section": "s2", "quote": "Le cache", "text": "split this"}])
    session.add_terminal_message("keep it short")
    text = build(session, "writer", ["q1", b["comments"][0]["id"], "tm1", "« Write model »"])
    trigger = text.split("## Trigger\n")[1].split("\n\n")[0]
    assert "- q1 [answered] PR or merge? → PR — squash it" in trigger
    assert "[c1] §2 (s2) « Le cache »\n    split this" in trigger
    assert "- tm1 (awaiting-answer): keep it short" in trigger
    assert trigger.endswith("« Write model »")
    with pytest.raises(SessionError, match="no 'q9'"):
        build(session, "writer", ["q9"])
    with pytest.raises(SessionError, match="unknown role"):
        build(session, "coder")


def test_logs_are_capped_but_open_questions_are_not(session):
    n = CONTEXT_RECENT + 3
    for i in range(n):
        session.add_question(f"closed {i}?")
        session.answer_question(f"q{i + 1}", [], f"answer {i}")
    session.add_question("still open?")
    for i in range(n):
        session.add_change(f"change {i}")
        session.add_terminal_message(f"message {i}")
    text = build(session, "planner")
    # An older closed question stays as one line, without its answer.
    assert "Older, answer not loaded:\n- q1 [answered] closed 0?\n" in text
    assert "answer 0" not in text and "answer 3" in text
    assert f"- q{n + 1} [open] still open?" in text
    assert f"## Change history ({CONTEXT_RECENT} most recent of {n})" in text
    assert "change 2 " not in text and "change 3 (" in text
    assert f"## Terminal messages ({CONTEXT_RECENT} most recent of {n})" in text
    assert "message 2\n" not in text and "message 3\n" in text
