import json
from datetime import datetime, timedelta

import pytest

from view_concept.store import (
    LISTENING_FOR,
    Session,
    SessionError,
    format_batch,
    format_changes,
    list_sessions,
)


def test_create_is_idempotent(session):
    assert session.create("other") is False
    assert session.read_plan()["title"] == "Le KV cache"


def test_invalid_slug():
    with pytest.raises(SessionError):
        Session("../etc")


def test_batch_ids_and_inbox(session):
    b1 = session.add_batch([{"section": "s1", "quote": "q", "text": "a"}, {"text": "  "}])
    b2 = session.add_batch([{"section": "s2", "text": "b"}], note="n")
    assert [c["id"] for c in b1["comments"]] == ["c1"]  # blank comment dropped
    assert b2["id"] == "b2" and b2["comments"][0]["id"] == "c2"
    lines = session.inbox_path.read_text().splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["b1", "b2"]


def test_empty_batch_rejected(session):
    with pytest.raises(SessionError):
        session.add_batch([{"text": ""}], note=" ")


def test_resolve(session):
    session.add_batch([{"text": "a"}, {"text": "b"}])
    session.add_batch([{"text": "c"}])
    assert session.resolve(["b1"], "done") == ["c1", "c2"]
    comments = [c for b in session.read_comments()["batches"] for c in b["comments"]]
    assert [c["status"] for c in comments] == ["resolved", "resolved", "sent"]
    assert comments[0]["reply"] == "done"
    with pytest.raises(SessionError):
        session.resolve(["c9"])


def test_format_batch_numbers_sections(session):
    b = session.add_batch([{"section": "s2", "quote": "le\n cache", "text": "x\ny"}], note="n")
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "[c1] §2 (s2) « le cache »" in out
    assert "    y" in out and "note: n" in out


def test_export_orders_sections_and_overwrites(session, tmp_path):
    vault = tmp_path / "vault"
    p1 = session.export(vault)
    text = p1.read_text()
    assert text.index("## Attention") < text.index("## Cache")
    assert "view-concept: kv-cache" in text
    assert "clé \\| key" in text  # pipe escaped in the lexicon table
    assert session.export(vault) == p1


def test_export_does_not_clobber_foreign_note(session, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Le KV cache.md").write_text("my own note")
    p = session.export(vault)
    assert p.name == "Le KV cache (kv-cache).md"
    assert (vault / "Le KV cache.md").read_text() == "my own note"


def test_list_sessions(session, tmp_path):
    session.add_batch([{"text": "a"}])
    rows = list_sessions(tmp_path)
    assert rows[0]["slug"] == "kv-cache" and rows[0]["pending"] == 1


def test_status(session):
    assert session.read_status()["phase"] == "idle"
    st = session.write_status("writing", "s2")
    assert session.read_status() == st
    with pytest.raises(SessionError):
        session.write_status("dreaming")


def test_approve_plan_batch(session):
    b = session.add_batch([], action="approve-plan")  # an approval alone is not empty
    assert b["action"] == "approve-plan"
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "action: approve-plan" in out
    with pytest.raises(SessionError):
        session.add_batch([], action="delete-everything")


def test_approve_model_batch(session):
    session.write_status("awaiting-model")
    b = session.add_batch([{"text": "rename it"}], action="approve-model")
    assert b["action"] == "approve-model"
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert (
        "action: approve-model (the user approved the model from the page: "
        "start the implementation)"
    ) in out


def test_review_code_batch(session):
    session.write_status("awaiting-review")
    b = session.add_batch([{"text": "check the tests too"}], action="review-code")
    assert b["action"] == "review-code"
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "action: review-code (the user asked to start the code review from the page)" in out


def test_code_session_needs_repo(tmp_path):
    with pytest.raises(SessionError):
        Session("x", tmp_path).create("X", kind="code")
    s = Session("y", tmp_path)
    s.create("Y", kind="code", repo=str(tmp_path))
    assert s.read_plan()["repo"] == str(tmp_path.resolve())


def test_changes(session, tmp_path):
    d = session.add_change("Keep one inbox", why="Simpler", instead="a socket", files=["a.py"])
    assert d["id"] == "m1" and session.changes_path.name == "changes.json"
    assert format_changes(session.read_changes()) == (
        "- Keep one inbox, rather than a socket. Simpler (`a.py`)"
    )
    assert "## Model changes" in session.render_markdown()
    with pytest.raises(SessionError):
        session.add_change(" ")


def test_workflow_is_stored_and_defaults_by_kind(tmp_path):
    s = Session("x", tmp_path)
    s.create("X")
    assert s.read_plan()["workflow"] == "view-concept"
    s = Session("y", tmp_path)
    s.create("Y", kind="code", repo=str(tmp_path))
    assert s.read_plan()["workflow"] == "view-branch"
    s = Session("z", tmp_path)
    s.create("Z", kind="code", repo=str(tmp_path), workflow="view-refactor")
    assert s.read_plan()["workflow"] == "view-refactor"


def test_workflow_is_validated(tmp_path):
    with pytest.raises(SessionError, match="unknown workflow"):
        Session("x", tmp_path).create("X", kind="code", repo=str(tmp_path), workflow="view-pr")
    with pytest.raises(SessionError, match="code session"):
        Session("y", tmp_path).create("Y", workflow="view-refactor")
    assert not Session("x", tmp_path).exists()


def test_listening_follows_the_heartbeat(session):
    assert session.is_listening() is False  # no watch has run
    before = session.signature()
    session.write_heartbeat()
    assert session.is_listening()
    assert session.signature() == before  # a heartbeat does not re-render the page
    at = datetime.fromisoformat(json.loads(session.watch_path.read_text())["at"])
    assert session.is_listening(at + timedelta(seconds=LISTENING_FOR - 1))
    assert not session.is_listening(at + timedelta(seconds=LISTENING_FOR + 1))
    session.watch_path.write_text("{}")
    assert session.is_listening() is False


def test_claude_question(session):
    before = session.signature()
    q1 = session.add_question(" Which one? ", ["a PR", " ", "a merge"])
    assert q1["id"] == "q1" and q1["text"] == "Which one?" and q1["status"] == "open"
    assert q1["options"] == ["a PR", "a merge"] and q1["multi"] is False
    assert session.read_status()["phase"] == "awaiting-answer"
    assert session.signature() != before  # the page shows the card
    q2 = session.add_question("Anything else?", multi=True)
    assert q2["id"] == "q2" and q2["options"] == []
    assert [q["id"] for q in session.read_questions()] == ["q1", "q2"]
    with pytest.raises(SessionError):
        session.add_question(" ")
