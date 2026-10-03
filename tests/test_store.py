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


def test_create_pr_batch(session):
    session.write_status("awaiting-pr")
    b = session.add_batch([{"text": "squash the fixups"}], action="create-pr")
    assert b["action"] == "create-pr"
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "action: create-pr (the user asked to open the PR from the page)" in out


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


def test_answer_is_sent_as_a_batch(session):
    session.add_question("PR or merge?", ["a PR", "a merge"])
    with pytest.raises(SessionError, match="empty answer"):
        session.answer_question("q1", [], " ")
    with pytest.raises(SessionError, match="not an option"):
        session.answer_question("q1", ["a rebase"])
    with pytest.raises(SessionError, match="one choice"):
        session.answer_question("q1", ["a PR", "a merge"])
    b = session.answer_question("q1", ["a PR"], " squash it ")
    assert b["action"] == "answer" and b["comments"] == []
    assert b["answers"] == [{"question": "q1", "choices": ["a PR"], "text": "squash it"}]
    assert json.loads(session.inbox_path.read_text().splitlines()[-1])["id"] == b["id"]
    assert session.read_comments()["batches"][-1]["answers"] == b["answers"]
    (q,) = session.read_questions()
    assert q["status"] == "answered"
    assert q["answer"] == {"choices": ["a PR"], "text": "squash it", "at": b["sent"]}
    with pytest.raises(SessionError, match="already answered"):
        session.answer_question("q1", [], "again")
    with pytest.raises(SessionError, match="no question"):
        session.answer_question("q9", [], "hm")


def test_a_question_keeps_the_scoping_phase(session):
    session.write_status("scoping")
    session.add_question("How familiar are you with KKT?")
    session.add_question("What is it for?")
    assert session.read_status()["phase"] == "scoping"


def test_question_with_a_recommended_answer(session):
    assert "recommended" not in session.add_question("PR or merge?", ["a PR", "a merge"])
    q = session.add_question("Which?", ["a PR", "a merge"], recommended=" a PR ")
    assert q["recommended"] == "a PR"
    assert session.read_questions()[1]["recommended"] == "a PR"


def test_skip_is_sent_as_a_batch(session):
    session.add_question("PR or merge?", ["a PR", "a merge"])
    b = session.skip_question("q1")
    assert b["action"] == "answer" and b["comments"] == []
    assert b["answers"] == [{"question": "q1", "skipped": True}]
    assert json.loads(session.inbox_path.read_text().splitlines()[-1])["id"] == b["id"]
    (q,) = session.read_questions()
    assert q["status"] == "skipped" and q["skipped"] == b["sent"] and "answer" not in q
    with pytest.raises(SessionError, match="already skipped"):
        session.skip_question("q1")
    with pytest.raises(SessionError, match="already skipped"):
        session.answer_question("q1", [], "after all")
    with pytest.raises(SessionError, match="no question"):
        session.skip_question("q9")
    session.add_question("Why?")
    session.answer_question("q2", [], "because")
    with pytest.raises(SessionError, match="already answered"):
        session.skip_question("q2")


def test_format_skip_batch(session):
    session.add_question("Which  files?", ["a.py", "b.py"])
    b = session.skip_question("q1")
    out = format_batch("kv-cache", b, session.read_plan()["outline"], session.read_questions())
    assert "action: answer (the user skipped agent question q1 from the page)" in out
    assert "q1 skipped « Which files? » (no answer: use your default)" in out


def test_answer_batch_needs_answers(session):
    with pytest.raises(SessionError):
        session.add_batch([], action="answer")
    with pytest.raises(SessionError):
        session.add_batch([{"text": "a"}], answers=[{"question": "q1", "choices": [], "text": "x"}])


def test_format_answer_batch(session):
    session.add_question("Which  files?", ["a.py", "b.py"], multi=True)
    session.add_question("Why?")
    b1 = session.answer_question("q1", ["a.py", "b.py"], "and the tests")
    b2 = session.answer_question("q2", [], "because")
    outline, questions = session.read_plan()["outline"], session.read_questions()
    out = format_batch("kv-cache", b1, outline, questions)
    assert "action: answer (the user answered agent question q1 from the page)" in out
    assert "answer to q1 « Which files? »: a.py, b.py — and the tests" in out
    assert "answer to q2 « Why? »: because" in format_batch("kv-cache", b2, outline, questions)


def test_a_batch_resets_the_highlight_baseline(session):
    session.read_seen(session.read_sections())  # the page loads the first texts
    (session.sections_dir / "s1.md").write_text("L'attention, réécrite.")
    (session.sections_dir / "s2.md").write_text("Le cache, réécrit.")
    session.mark_seen({"s2": "Le cache, réécrit."})  # « mark read » on one section
    seen = session.read_seen(session.read_sections())
    assert seen["s1"] == "L'attention." and seen["s2"] == "Le cache, réécrit."
    session.add_question("Why?")
    session.answer_question("q1", [], "because")  # an answer is a batch too
    assert session.read_seen(session.read_sections()) == session.read_sections()


@pytest.fixture
def ordered(tmp_path):
    """A session whose lexicon breaks the precedence rule in every way the check finds."""
    s = Session("kkt", tmp_path)
    s.create("KKT")
    plan = s.read_plan()
    plan["outline"] = [{"id": "a", "title": "Rules"}, {"id": "b", "title": "KKT"},
                       {"id": "c", "title": "Convexity"}]  # fmt: skip
    plan["lexicon"] = [
        {"term": "rule", "section": "a", "definition": "a constraint on a convex problem"},
        {"term": "KKT conditions", "section": "b", "definition": "optimality test",
         "tip": "Holds at the optimum of a Convex Problem."},
        {"term": "convex problem", "section": "c", "definition": "bowl-shaped"},
        {"term": "ghost", "section": "zz", "definition": "uses convex problem"},
    ]  # fmt: skip
    s.plan_path.write_text(json.dumps(plan))
    (s.sections_dir / "a.md").write_text(
        "Rules and a ruler. The kkt conditions come later. `convex problem` in code.\n"
    )
    (s.sections_dir / "b.md").write_text("A rule; the KKT conditions.")
    (s.sections_dir / "c.md").write_text("A convex problem.")
    return s


def test_check_finds_forward_references_and_early_uses(ordered):
    problems = ordered.check_precedence(write=False)
    found = {(p["issue"], p["term"], p["section"], p["field"], p["other"]) for p in problems}
    assert found == {
        ("forward", "rule", "a", "definition", "convex problem"),
        ("forward", "KKT conditions", "b", "tip", "convex problem"),
        ("early", "KKT conditions", "a", "", ""),
    }
    assert not ordered.audit_path.exists()


def test_check_matches_whole_words_only(ordered):
    # With « rule » introduced in section 3, section 2's « A rule; » is an early use,
    # section 1's « Rules » and « ruler » are not, nor is a term inside inline code.
    plan = ordered.read_plan()
    plan["lexicon"][0]["section"] = "c"
    ordered.plan_path.write_text(json.dumps(plan))
    early = {(p["term"], p["section"]) for p in ordered.check_precedence(write=False)
             if p["issue"] == "early"}  # fmt: skip
    assert early == {("rule", "b"), ("KKT conditions", "a")}


def test_check_skips_entries_outside_the_outline(ordered):
    assert all(p["term"] != "ghost" for p in ordered.check_precedence(write=False))


def test_check_writes_audit_and_reruns_idempotently(ordered):
    mine = {"term": "bowl-shaped", "section": "c", "issue": "metaphor", "note": "n"}
    stale = {"term": "old", "section": "a", "issue": "early", "note": "introduced in section 9"}
    ordered.audit_path.write_text(json.dumps([mine, stale]))
    ordered.check_precedence()
    first = ordered.read_audit()
    ordered.check_precedence()
    assert ordered.read_audit() == first
    assert first[0] == mine and stale not in first
    assert {"term": "KKT conditions", "section": "b", "issue": "forward",
            "note": "tip uses «convex problem» (section 3)"} in first  # fmt: skip
    assert {"term": "KKT conditions", "section": "a", "issue": "early",
            "note": "introduced in section 2"} in first  # fmt: skip
    assert len(first) == 4
