import json
import os
from datetime import datetime, timedelta

import pytest

from view_concept.store import (
    EARNS_MAX,
    LISTENING_FOR,
    Session,
    SessionError,
    format_batch,
    format_changes,
    list_sessions,
    project_of,
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


def test_export_moves_media_out_of_the_note(session, tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    gif = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
    widget = '<div onclick="this.x=1"><video src="data:video/mp4;base64,AAAA"></video></div>'
    (session.sections_dir / "s1.md").write_text(f"Avant.\n\n![schéma]({gif})\n\n{widget}\n\nAprès.")
    note = session.export(vault / "explanations").read_text()
    assert "base64" not in note
    media = vault / "explanations" / "kv-cache"
    [img] = list((media / "assets").glob("*.gif"))
    assert f"![schéma](kv-cache/assets/{img.name})" in note
    [html] = list((media / "widgets").glob("*.html"))
    assert 'src="assets/' in html.read_text() and "onclick" in html.read_text()
    assert 'dv.view("explanations/kv-cache/widget", ' in note
    assert f'"file": "explanations/kv-cache/widgets/{html.name}"' in note
    assert (media / "widget.js").exists()


def test_export_links_an_html_section_and_frames_it(session, tmp_path):
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    document = '<p>Une figure.</p><video src="s2/a.mp4"></video>'
    (session.sections_dir / "s2.html").write_text(document)
    (session.sections_dir / "s2").mkdir()
    (session.sections_dir / "s2" / "a.mp4").write_bytes(b"mp4")
    note = session.export(vault / "explanations").read_text()
    media = vault / "explanations" / "kv-cache"
    # copied with the frame's head, so the link shows the page's default theme
    exported = (media / "s2.html").read_text()
    assert exported.startswith(
        '<link rel="stylesheet" href="frame.css"><script src="frame.js"></script>'
    )
    assert exported.endswith(document)
    assert (media / "s2" / "a.mp4").read_bytes() == b"mp4"
    assert "## Cache\n\n[Open this section in the browser](kv-cache/s2.html)" in note
    assert 'dv.view("explanations/kv-cache/section", ' in note and "Une figure" not in note
    view = (media / "section.js").read_text()
    assert 'sandbox: "allow-scripts ' in view
    # the view drops the file's two links and writes the two files' text in their place
    assert 'html.split("<link rel=\\"stylesheet\\" href=\\"frame.css\\">' in view
    assert (media / "frame.css").exists() and (media / "frame.js").exists()


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


def test_phase_history(session):
    assert session.read_phase_history() == []
    session.write_status("writing", "s1")
    session.write_status("writing", "s2")  # same phase: no new entry
    session.write_status("awaiting-model")
    history = session.read_phase_history()
    assert [h["phase"] for h in history] == ["writing", "awaiting-model"]
    assert history[0]["at"] <= history[1]["at"] and "." in history[0]["at"]
    with session.phase_history_path.open("a") as f:
        f.write('{"phase": "idl')  # a line cut by a crash
    assert len(session.read_phase_history()) == 2


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


def test_plan_batch_skips_the_open_questions(session):
    session.write_status("scoping")
    session.add_question("Level?")
    session.add_question("Goal?")
    session.answer_question("q1", [], "heard the words")
    b = session.add_batch([{"text": "keep it short"}], action="plan")
    q1, q2 = session.read_questions()
    assert q1["status"] == "answered" and "skipped" not in q1
    assert q2["status"] == "skipped" and q2["skipped"] == b["sent"]
    # The session already has a plan: the button asked for a rewrite.
    assert b["rewrite"] is True
    assert (
        "action: plan (the user asked to rewrite the plan from the page: open questions "
        "are marked skipped, but a section question whose section is not written yet; "
        "revise the plan with the answers, or the model in a branch review)"
    ) in format_batch("kv-cache", b, [])
    assert (
        "action: plan (the user ended scoping from the page: open questions are marked "
        "skipped, but a section question whose section is not written yet; write the "
        "plan, or the model in a branch review)"
    ) in format_batch("kv-cache", {**b, "rewrite": False}, [])


def test_plan_batch_keeps_a_section_question_open_until_its_section_is_written(session):
    plan = session.read_plan()
    plan["outline"].append({"id": "s3", "title": "Eviction"})
    session.plan_path.write_text(json.dumps(plan))
    session.write_status("scoping")
    session.add_question("Evict what?", section="s3")
    session.add_question("Cache what?", section="s2")
    session.add_question("Level?")
    session.add_batch([], action="plan")
    q1, q2, q3 = session.read_questions()
    assert q1["status"] == "open"  # s3 is not written yet: asked at its end once it is
    assert q2["status"] == "skipped" and q3["status"] == "skipped"


def test_go_on_batch_leaves_the_questions_open(session):
    session.add_question("Evict what?", section="s2")
    b = session.add_batch([], action="go-on")
    assert session.read_questions()[0]["status"] == "open"
    assert (
        "action: go-on (the user asked to go on past the pause: write the next sections; "
        "the pause's questions stay open)"
    ) in format_batch("kv-cache", b, [])


def test_a_branch_review_rewrites_once_its_sections_exist(tmp_path):
    s = Session("x", tmp_path)
    s.create("X", kind="code", repo=str(tmp_path))
    plan = s.read_plan()
    plan["outline"] = [{"id": "s1", "title": "Today"}]  # the planner's draft
    s.plan_path.write_text(json.dumps(plan))
    assert s.add_batch([], action="plan")["rewrite"] is False
    (s.sections_dir / "s1.md").write_text("Today.")
    assert s.add_batch([], action="plan")["rewrite"] is True


def test_grill_batches(session):
    assert session.is_grilling() is False
    outline = session.read_plan()["outline"]
    b = session.add_batch([], action="grill")
    assert session.is_grilling() is True
    assert (
        "action: grill (the user started a grill: ask every open design decision as a "
        "question with a recommended answer, until none is left)"
    ) in format_batch("kv-cache", b, outline)
    session.add_batch([{"text": "unrelated"}])
    assert session.is_grilling() is True
    b = session.add_batch([], action="stop-grill")
    assert session.is_grilling() is False
    assert "action: stop-grill (the user stopped the grill)" in format_batch("kv-cache", b, outline)


def test_grill_ends(session):
    b = session.add_batch([], action="grill")
    session.resolve([b["id"]], reply="no decision left")
    assert session.is_grilling() is False
    session.add_batch([], action="grill")
    assert session.is_grilling() is True
    session.add_batch([], action="approve-model")
    assert session.is_grilling() is False
    session.add_batch([], action="grill")
    assert session.is_grilling() is True
    session.add_batch([], action="stop-grill")
    assert session.is_grilling() is False
    session.add_batch([], action="grill")
    assert session.is_grilling() is True


def test_code_session_needs_repo(tmp_path):
    with pytest.raises(SessionError):
        Session("x", tmp_path).create("X", kind="code")
    s = Session("y", tmp_path)
    s.create("Y", kind="code", repo=str(tmp_path))
    assert s.read_plan()["repo"] == str(tmp_path.resolve())


def test_change_history(session):
    d = session.add_change("gate split in two", by="writer", cause=["c7", "q3"])
    assert d["id"] == "m1" and d["by"] == "writer" and d["cause"] == ["c7", "q3"]
    assert session.change_history_path.name == "change-history.json"
    # A change no event led to is the agent's own.
    assert session.add_change("section 5 added")["cause"] == ["own judgment"]
    assert format_changes(session.read_changes()) == "- gate split in two\n- section 5 added"
    assert "## Change history" in session.render_markdown()
    with pytest.raises(SessionError):
        session.add_change(" ")


def test_a_session_written_before_the_change_history_keeps_its_changes(session):
    old = [
        {
            "id": "m1",
            "change": "Keep one inbox",
            "why": "Simpler",
            "instead": "a socket",
            "files": ["a.py"],
        }
    ]
    session.legacy_changes_path.write_text(json.dumps(old))
    assert format_changes(session.read_changes()) == (
        "- Keep one inbox, rather than a socket. Simpler (`a.py`)"
    )


def test_terminal_messages(session):
    session.write_status("scoping")
    m = session.add_terminal_message("  keep the CLI as it is  ")
    assert m["id"] == "tm1" and m["phase"] == "scoping" and m["text"] == "keep the CLI as it is"
    assert session.read_terminal_messages() == [m]
    with pytest.raises(SessionError):
        session.add_terminal_message(" ")


def test_the_request_transcript_is_written_and_replaced(session):
    assert session.read_request() == ""
    session.write_request("## User\nfirst\n")
    session.write_request("## User\nfirst\n\n## Agent\nsecond\n")
    assert session.read_request() == "## User\nfirst\n\n## Agent\nsecond"
    assert session.request_path.name == "request.md"
    with pytest.raises(SessionError):
        session.write_request("  \n")


def test_a_branch_review_records_its_base(tmp_path):
    s = Session("x", tmp_path)
    s.create("X", "rework the gate", kind="code", repo=str(tmp_path), base="main")
    plan = s.read_plan()
    assert plan["base"] == "main" and plan["initial_request"] == "rework the gate"
    assert s.coordinated and s.fork_parent() == ""


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


def test_answered_in_terminal_sends_no_batch(session):
    session.add_question("PR or merge?", ["a PR", "a merge"])
    session.add_question("Why?")
    assert session.read_status()["phase"] == "awaiting-answer"
    q = session.answered_in_terminal("q1", " a PR, squashed ")
    assert q["status"] == "answered"
    assert q["answer"]["choices"] == [] and q["answer"]["text"] == "a PR, squashed"
    assert q["answer"]["from"] == "terminal" and q["answer"]["at"]
    assert session.read_questions()[0] == q
    assert not session.inbox_path.exists() and session.read_comments().get("batches", []) == []
    assert session.answered_in_terminal("q2")["answer"]["text"] == ""
    assert session.read_status()["phase"] == "awaiting-answer"  # the agent sets the next one
    with pytest.raises(SessionError, match="already answered"):
        session.answered_in_terminal("q1", "again")
    with pytest.raises(SessionError, match="no question"):
        session.answered_in_terminal("q9")


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


def test_unclear_defers_a_question_until_it_is_asked_again(session):
    session.add_question(
        "PR or merge?", ["a PR", "a merge"], recommended="a PR", background="Today: …"
    )
    b = session.unclear_question("q1", " what is a merge here? ")
    assert b["action"] == "answer"
    assert b["answers"] == [{"question": "q1", "unclear": True, "note": "what is a merge here?"}]
    (q,) = session.read_questions()
    assert q["status"] == "deferred" and q["unclear"] == [
        {"note": "what is a merge here?", "at": b["sent"]}
    ]
    with pytest.raises(SessionError, match="already deferred"):
        session.answer_question("q1", ["a PR"])
    session.add_batch([], action="plan")  # « Write model » leaves a deferred question alone
    assert session.read_questions()[0]["status"] == "deferred"
    session.anchor_question("q1", "s2")
    with pytest.raises(SessionError, match="no section"):
        session.anchor_question("q1", "s9")
    session.write_status("writing", "s2")
    q = session.reask_question("q1")
    assert q["status"] == "open" and q["section"] == "s2" and "background" not in q
    assert q["text"] == "PR or merge?" and session.read_status()["phase"] == "awaiting-answer"
    with pytest.raises(SessionError, match="not deferred"):
        session.reask_question("q1")
    session.answer_question("q1", ["a merge"])
    assert session.read_questions()[0]["status"] == "answered"


def test_a_question_may_carry_a_background_and_an_anchor_section(session):
    q = session.add_question("Which?", background=" today: … ", section="s1")
    assert q["background"] == "today: …" and q["section"] == "s1"
    with pytest.raises(SessionError, match="no section"):
        session.add_question("Which?", section="s9")


def test_format_batch_says_an_unclear_answer(session):
    session.add_question("PR or merge?")
    b = session.unclear_question("q1", "what is a merge?")
    text = format_batch("kv-cache", b, session.read_plan()["outline"], session.read_questions())
    assert "action: answer (the user did not understand agent question q1 from the page)" in text
    assert (
        "q1 unclear « PR or merge? » (the user doesn't understand it yet: explain what it "
        "needs, then ask it again): what is a merge?"
    ) in text


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


def test_check_reports_no_early_use_in_an_overview_section(ordered):
    # Section 1 names « KKT conditions », whose home is section 2: an overview may.
    plan = ordered.read_plan()
    plan["outline"][0]["overview"] = True
    ordered.plan_path.write_text(json.dumps(plan))
    issues = {(p["issue"], p["term"]) for p in ordered.check_precedence(write=False)}
    assert ("early", "KKT conditions") not in issues
    assert ("forward", "rule") in issues


def test_plan_refuses_an_overview_that_is_not_a_boolean(session):
    with pytest.raises(SessionError, match="overview"):
        session.write_plan(outline=[{"id": "a", "title": "A", "overview": "yes"}])


def test_check_reports_a_waiting_question_whose_anchor_left_the_outline(session):
    session.add_question("Evict what?", section="s2")
    session.add_question("Cache what?", section="s2")
    session.add_question("Level?", section="s2")
    session.unclear_question("q2")
    session.answer_question("q3", [], "low")
    plan = session.read_plan()
    plan["outline"] = [s for s in plan["outline"] if s["id"] != "s2"]
    session.plan_path.write_text(json.dumps(plan))
    problems = [p for p in session.check_sections() if p["issue"] == "stale-anchor"]
    gone = "a section the outline no longer has: re-anchor it with view-concept anchor"
    assert [(p["section"], p["at"], p["note"]) for p in problems] == [
        ("s2", "·", f"q1 (open) waits on it, {gone}"),
        ("s2", "·", f"q2 (deferred) waits on it, {gone}"),
    ]


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


def test_fingerprint_follows_what_a_published_page_shows(session):
    before = session.fingerprint()
    assert session.fingerprint() == before  # stable
    session.add_batch([{"section": "s1", "text": "a comment"}])
    session.mark_seen({"s1": "older text"})
    assert session.fingerprint() == before  # comments and highlights do not count
    (session.sections_dir / "s2.md").write_text("Le cache, réécrit.")
    assert session.fingerprint() != before


def test_fingerprint_leaves_out_refactor_sections(session):
    before = session.fingerprint()
    plan = session.read_plan()
    plan["outline"].append({"id": "r1", "title": "Refactor", "part": 2})
    session.plan_path.write_text(json.dumps(plan))
    (session.sections_dir / "r1.md").write_text("Part 2.")
    assert session.fingerprint() == before


def test_fingerprint_follows_the_lexicon(session):
    before = session.fingerprint()
    plan = session.read_plan()
    plan["lexicon"][0]["tip"] = "un vecteur, développé"
    session.plan_path.write_text(json.dumps(plan))
    assert session.fingerprint() != before


def test_published_sections_in_outline_order(session):
    plan = session.read_plan()
    plan["outline"].insert(0, {"id": "s0", "title": "Unwritten"})
    session.plan_path.write_text(json.dumps(plan))
    rows = session.published_sections()
    assert [(r["id"], r["number"], r["title"]) for r in rows] == [
        ("s1", 2, "Attention"),
        ("s2", 3, "Cache"),
    ]


def test_out_of_date(session):
    assert session.read_published() == {} and not session.is_out_of_date()
    before = session.signature()
    record = session.write_published("https://x.github.io/e/kv-cache/", session.fingerprint())
    assert session.read_published() == record and set(record) == {"url", "at", "fingerprint"}
    assert session.signature() != before  # the page re-renders its buttons
    assert not session.is_out_of_date()
    (session.sections_dir / "s1.md").write_text("L'attention, réécrite.")
    assert session.is_out_of_date()
    session.delete_published()
    assert session.read_published() == {} and not session.is_out_of_date()


def test_write_plan_keeps_the_other_fields(tmp_path):
    s = Session("x", tmp_path)
    s.create("X", "rework the gate", kind="code", repo=str(tmp_path), base="main")
    s.write_plan(outline=[{"id": "s1", "title": "Today", "earns": "e"}])
    s.write_plan(lexicon=[{"term": "gate", "section": "s1", "definition": "d"}])
    plan = s.read_plan()
    assert plan["initial_request"] == "rework the gate" and plan["base"] == "main"
    assert plan["outline"][0]["id"] == "s1" and plan["lexicon"][0]["term"] == "gate"
    with pytest.raises(SessionError, match="no section: s9"):
        s.write_plan(lexicon=[{"term": "x", "section": "s9"}])
    with pytest.raises(SessionError, match="unique"):
        s.write_plan(outline=[{"id": "s1", "title": "A"}, {"id": "s1", "title": "B"}])
    with pytest.raises(SessionError, match="earns over"):
        s.write_plan(outline=[{"id": "s1", "title": "A", "earns": "x" * (EARNS_MAX + 1)}])
    with pytest.raises(SessionError, match="nothing to write"):
        s.write_plan()
    with pytest.raises(SessionError, match="unknown term kind for x"):
        s.write_plan(lexicon=[{"term": "x", "section": "s1", "kind": "borrowed"}])
    # a refused write changes nothing
    assert s.read_plan()["lexicon"] == [{"term": "gate", "section": "s1", "definition": "d"}]
    s.write_plan(lexicon=[{"term": "gate", "section": "s1", "kind": "peripheral"}])
    assert s.read_plan()["lexicon"][0]["kind"] == "peripheral"


def test_unimplemented_changes_follow_the_last_implementer_run(tmp_path):
    s = Session("gate", tmp_path)
    s.create("The gate", kind="code", repo=str(tmp_path), workflow="view-branch")
    s.add_change("gate split")
    s.add_change("threshold renamed")
    assert s.unimplemented_changes() == []  # the model is not approved yet
    s.add_batch([], action="approve-model")
    assert [d["id"] for d in s.unimplemented_changes()] == ["m1", "m2"]
    s.mark_implemented("m1")
    assert s.implemented_through() == "m1"
    assert [d["id"] for d in s.unimplemented_changes()] == ["m2"]
    s.mark_implemented("m2")
    assert s.unimplemented_changes() == []
    with pytest.raises(SessionError, match="comes before m2"):
        s.mark_implemented("m1")
    with pytest.raises(SessionError, match="no change 'm3'"):
        s.mark_implemented("m3")


def test_an_explanation_has_no_unimplemented_changes(session):
    session.add_change("renamed")
    session.add_batch([], action="approve-model")
    assert session.unimplemented_changes() == []


def test_an_html_section_is_read_from_its_html_file(session):
    (session.sections_dir / "s3.html").write_text("<p>Une figure.</p>")
    assert session.read_sections()["s3"] == "<p>Une figure.</p>"
    assert session.html_sections() == {"s3"}
    assert session.two_file_sections() == []


def test_the_html_file_wins_over_the_md_file(session):
    (session.sections_dir / "s1.html").write_text("<p>Réécrite en HTML.</p>")
    assert session.read_sections()["s1"] == "<p>Réécrite en HTML.</p>"
    assert session.two_file_sections() == ["s1"]


def test_an_html_section_changes_the_signature(session):
    before = session.signature()
    (session.sections_dir / "s3.html").write_text("<p>x</p>")
    assert session.signature() != before


def test_the_visible_text_of_an_html_section_counts_for_the_precedence_check(ordered):
    (ordered.sections_dir / "a.md").unlink()
    (ordered.sections_dir / "a.html").write_text(
        "<style>.convex-problem{}</style><svg><text>a convex problem</text></svg>"
        "<script>label('rule')</script>"
    )
    early = {(p["term"], p["section"]) for p in ordered.check_precedence(write=False)
             if p["issue"] == "early"}  # fmt: skip
    assert ("convex problem", "a") in early
    assert ordered.read_prose()["a"] == "a convex problem"


def test_project_of_groups_worktrees_under_their_main_checkout(tmp_path):
    import subprocess

    main = tmp_path / "repo"
    main.mkdir()
    git = ["git", "-C", str(main), "-c", "user.email=a@b", "-c", "user.name=a"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    tree = main / ".claude" / "worktrees" / "feat"
    subprocess.run([*git, "worktree", "add", "-q", str(tree)], check=True)
    assert project_of(str(main.resolve())) == str(main.resolve())
    assert project_of(str(tree.resolve())) == str(main.resolve())
    # a removed worktree is cut at its worktrees folder
    assert project_of("/gone/repo/.claude/worktrees/x") == "/gone/repo"
    assert project_of("") == ""


# ---- the banner computed from the files ----


def _touch(path, t):
    """Set a file's modification time."""
    os.utime(path, (t, t))


def _bare(session):
    """The fixture session with no section file yet."""
    for p in session.sections_dir.glob("*.md"):
        p.unlink()
    return session


def test_writing_run_keeps_its_start_and_grows_its_set(session):
    first = session.write_status("writing", ["s1"])
    again = session.write_status("writing", ["s2"])
    assert again["run"]["start"] == first["run"]["start"]
    assert again["run"]["set"] == ["s1", "s2"]
    session.write_status("audit")
    assert "run" not in session.read_status()
    assert session.write_status("writing")["run"]["start"] > first["run"]["start"]


def test_a_run_that_names_no_section_takes_those_with_no_file(session):
    (session.sections_dir / "s1.md").unlink()
    assert session.write_status("writing")["run"]["set"] == ["s1"]
    session.write_status("idle")
    (session.sections_dir / "s1.md").write_text("x")
    assert session.write_status("writing")["run"]["set"] == ["s1", "s2"]  # all have a file


def test_run_progress_counts_files_changed_since_its_start(session):
    st = session.write_status("writing", ["s2", "s1"])
    shown = session.shown_status()
    assert shown["shown"] == "writing" and not shown["derived"]
    assert shown["run"]["set"] == ["s1", "s2"] and shown["run"]["written"] == []
    _touch(session.sections_dir / "s2.md", st["at"] + 5)
    assert session.shown_status()["run"]["written"] == ["s2"]


def test_a_new_section_file_is_a_trace_of_writing(session):
    _bare(session)
    st = session.write_status("awaiting-answer")
    (session.sections_dir / "s2.md").write_text("x")
    _touch(session.sections_dir / "s2.md", st["at"] + 5)
    shown = session.shown_status()
    assert shown["phase"] == "awaiting-answer" and shown["shown"] == "writing"
    assert shown["derived"] and shown["run"]["set"] == ["s1", "s2"]
    assert shown["run"]["written"] == ["s2"]  # the file that revealed the run counts


def test_a_rewritten_section_is_no_trace(session):
    st = session.write_status("awaiting-answer")
    _touch(session.sections_dir / "s1.md", st["at"] + 5)
    assert session.shown_status()["shown"] == "awaiting-answer"


def test_a_plan_change_is_a_trace_of_planning_only_with_no_section(session):
    _bare(session)
    st = session.write_status("awaiting-approval")
    _touch(session.plan_path, st["at"] + 5)
    assert session.shown_status()["shown"] == "planning"
    session.write_status("scoping")  # scoping drafts the outline: no trace there
    _touch(session.plan_path, session.read_status()["at"] + 5)
    assert session.shown_status()["shown"] == "scoping"
    (session.sections_dir / "s1.md").write_text("x")
    st = session.write_status("awaiting-model")
    _touch(session.plan_path, st["at"] + 5)
    assert session.shown_status()["shown"] == "awaiting-model"


def test_an_audit_change_is_a_trace_of_the_audit_unless_sections_are_left(session):
    st = session.write_status("writing", ["s1", "s2"])
    session.audit_path.write_text("[]")
    _touch(session.audit_path, st["at"] + 5)
    assert session.shown_status()["shown"] == "writing"  # the writer's check, mid-run
    for sid in ("s1", "s2"):
        _touch(session.sections_dir / f"{sid}.md", st["at"] + 3)
    assert session.shown_status()["shown"] == "audit"


def test_a_status_without_files_derives_nothing(session):
    old = {"phase": "idle", "since": "2020-01-01T00:00:00+00:00"}
    session.status_path.write_text(json.dumps(old))
    assert session.shown_status()["shown"] == "idle"


def test_scoping_done_is_cleared_by_a_question_or_a_batch(session):
    with pytest.raises(SessionError):
        session.write_status("writing", done=True)
    session.write_status("scoping", done=True)
    assert session.read_status()["done"] and session.shown_status()["scoping_done"]
    st = session.read_status()
    st["since"] = "2020-01-01T00:00:00+00:00"
    session.status_path.write_text(json.dumps(st))
    session.add_question("Which one?")
    assert not session.shown_status()["scoping_done"]
    session.write_status("scoping", done=True)
    assert session.shown_status()["scoping_done"]
    st = session.read_status()
    st["since"] = "2020-01-01T00:00:00+00:00"
    session.status_path.write_text(json.dumps(st))
    session.questions_path.unlink()
    session.add_batch([{"text": "hi"}])
    assert not session.shown_status()["scoping_done"]


def test_last_activity_counts_only_what_the_agent_writes(session):
    for p in [*session.sections_dir.glob("*.md"), session.plan_path]:
        _touch(p, 1_000_000)
    assert session.last_activity() == "1970-01-12T13:46:40+00:00"
    session.add_batch([{"text": "hi"}])  # the page's write
    session.mark_seen({"s1": "x"})
    assert session.last_activity() == "1970-01-12T13:46:40+00:00"
    session.resolve(["c1"])
    assert session.last_activity() > "2000"


def test_batch_progress_follows_the_delivery_mark(session):
    assert session.batch_progress() is None
    for p in [*session.sections_dir.glob("*.md"), session.plan_path]:
        _touch(p, 1_000_000)
    b = session.add_batch([{"text": "hi"}])
    progress = session.batch_progress()
    assert progress and progress["id"] == b["id"] and progress["stage"] == "sent"
    session.cursor_path.write_text(str(session.inbox_path.stat().st_size))
    progress = session.batch_progress()
    assert progress and progress["stage"] == "received"
    _touch(session.cursor_path, 2_000_000)
    _touch(session.sections_dir / "s1.md", 3_000_000)
    progress = session.batch_progress()
    assert progress and progress["stage"] == "acted"


# ---- the Doc tab ----


@pytest.fixture
def docs_review(tmp_path):
    """A branch review on a repo (tmp_path/repo) with two docs."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Tool\n\nThe keys 1 to 4.\n")
    (repo / "docs" / "reference.md").write_text("# Reference\n\nTabs and keys.\n")
    s = Session("doc-tab", tmp_path / "sessions")
    s.create("Doc tab", kind="code", repo=str(repo), base="main")
    return s


def test_the_doc_set_keeps_a_reason_per_doc(docs_review):
    s = docs_review
    assert s.read_doc_set() == {"docs": [], "removed": []}
    s.add_doc("./docs/reference.md", "describes  the tabs")
    s.add_doc("README.md", "the install")
    s.add_doc("docs/reference.md", "describes the tabs and keys")
    assert s.read_doc_set()["docs"] == [
        {"path": "docs/reference.md", "reason": "describes the tabs and keys"},
        {"path": "README.md", "reason": "the install"},
    ]


@pytest.mark.parametrize("path", ["/etc/passwd", "../other/README.md", "docs/../../x.md", " "])
def test_a_doc_of_the_doc_set_stays_inside_the_repo(docs_review, path):
    with pytest.raises(SessionError):
        docs_review.add_doc(path, "why")


def test_a_doc_the_user_removed_comes_back_only_when_the_user_asks(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.remove_doc("README.md", user=True)
    assert s.read_doc_set() == {"docs": [], "removed": ["README.md"]}
    with pytest.raises(SessionError, match="removed by the user"):
        s.add_doc("README.md", "the install")
    s.add_doc("README.md", "the install", user=True)
    assert s.read_doc_set() == {"docs": [{"path": "README.md", "reason": "the install"}],
                                "removed": []}  # fmt: skip


def test_a_doc_back_in_the_doc_set_starts_with_no_highlight(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.read_seen(s.doc_texts())
    s.remove_doc("README.md", user=True)
    assert "doc:README.md" not in json.loads(s.seen_path.read_text())
    (s.repo_dir() / "README.md").write_text("rewritten while out")
    s.add_doc("README.md", "the install", user=True)
    assert s.read_seen(s.doc_texts())["doc:README.md"] == "rewritten while out"


def test_the_doc_set_anchor_names_no_section(docs_review):
    s = docs_review
    with pytest.raises(SessionError, match="may not start with 'doc:'"):
        s.write_plan(outline=[{"id": "doc:x", "title": "X"}])
    s.write_plan(outline=[{"id": "doc-set", "title": "Who keeps the doc list"}])
    b = s.add_batch([
        {"section": "doc-set", "quote": "", "text": "on the section"},
        {"section": "doc:", "quote": "", "text": "on the list"},
    ])  # fmt: skip
    text = format_batch("doc-tab", b, s.read_plan()["outline"])
    assert "[c1] §1 (doc-set)" in text and "[c2] (doc set)" in text


def test_an_agent_removes_a_doc_without_recording_it(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.remove_doc("README.md")
    assert s.read_doc_set() == {"docs": [], "removed": []}
    with pytest.raises(SessionError, match="not in the doc set"):
        s.remove_doc("README.md")


def test_a_doc_is_read_from_the_worktree_and_missing_reads_as_none(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.add_doc("docs/new.md", "created by the branch")
    assert s.read_docs() == {"README.md": "# Tool\n\nThe keys 1 to 4.\n", "docs/new.md": None}
    (s.repo_dir() / "README.md").write_text("edited in an editor")
    assert s.read_docs()["README.md"] == "edited in an editor"
    assert s.doc_texts() == {"doc:README.md": "edited in an editor"}


def test_a_doc_without_a_repo_reads_as_missing(session):
    session.add_doc("README.md", "the install")
    assert session.read_docs() == {"README.md": None}


def test_editing_a_doc_changes_the_signature(docs_review):
    s = docs_review
    before = s.signature()
    s.add_doc("README.md", "the install")
    listed = s.signature()
    assert listed != before
    readme = s.repo_dir() / "README.md"
    readme.write_text("a longer text than before")
    assert s.signature() != listed


def test_a_batch_moves_the_docs_baselines_keyed_by_path(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    assert s.read_seen(s.doc_texts()) == {"doc:README.md": "# Tool\n\nThe keys 1 to 4.\n"}
    (s.repo_dir() / "README.md").write_text("rewritten")
    s.add_batch([{"section": "doc:README.md", "quote": "keys", "text": "1 to 5"}])
    assert json.loads(s.seen_path.read_text())["doc:README.md"] == "rewritten"


def test_a_comment_on_a_doc_is_printed_with_its_path(docs_review):
    s = docs_review
    b = s.add_batch([
        {"section": "doc:docs/reference.md", "quote": "the keys 1, 2,\n3 and 4", "text": "5 keys"},
        {"section": "doc:", "quote": "README.md", "text": "remove it"},
    ])  # fmt: skip
    text = format_batch("doc-tab", b, [])
    assert "[c1] (doc docs/reference.md) « the keys 1, 2, 3 and 4 »\n    5 keys" in text
    assert "[c2] (doc set) « README.md »\n    remove it" in text


def test_a_stale_passage_shows_while_its_quote_is_in_the_doc(docs_review):
    s = docs_review
    with pytest.raises(SessionError, match="not in the doc set"):
        s.add_stale("README.md", "The keys", "five now")
    s.add_doc("README.md", "the install")
    with pytest.raises(SessionError, match="quote is not in"):
        s.add_stale("README.md", "The tabs", "five now")
    flag = s.add_stale("README.md", "The keys\n1 to 4", "five keys now", section="sheet")
    assert flag["id"] == "s1" and flag["section"] == "sheet"
    assert [f["id"] for f in s.shown_stale()] == ["s1"]
    (s.repo_dir() / "README.md").write_text("The keys 1 to 5.")
    assert s.shown_stale() == [] and len(s.read_stale()) == 1
    assert s.add_stale("README.md", "1 to 5", "fine")["id"] == "s2"
    s.drop_stale(["s1"])
    assert [f["id"] for f in s.read_stale()] == ["s2"]
    assert s.add_stale("README.md", "keys", "again")["id"] == "s3"
    with pytest.raises(SessionError, match="no stale passage s9"):
        s.drop_stale(["s9"])


def test_write_docs_carries_then_pr_only_when_true(session):
    b = session.add_batch([], action="write-docs")
    assert "then_pr" not in b
    assert (
        format_batch("kv-cache", b, [])
        .splitlines()[1]
        .startswith("action: write-docs (the user asked for the doc pass: refresh the doc set")
    )
    b = session.add_batch([], action="write-docs", then_pr=True)
    assert b["then_pr"] is True
    assert json.loads(session.inbox_path.read_text().splitlines()[-1])["then_pr"] is True
    assert (
        format_batch("kv-cache", b, [])
        .splitlines()[1]
        .startswith("action: write-docs then create-pr (the user asked for the doc pass and the PR")
    )
    with pytest.raises(SessionError, match="then_pr"):
        session.add_batch([], action="create-pr", then_pr=True)


def test_a_rewrite_request_keeps_its_readme_and_prints_it(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.add_doc("tools/README.md", "created by the branch")
    b = s.add_batch([], action="rewrite-readme", path="./README.md")
    assert b["path"] == "README.md"
    assert json.loads(s.inbox_path.read_text().splitlines()[-1])["path"] == "README.md"
    assert format_batch("doc-tab", b, []).splitlines()[1] == (
        "action: rewrite-readme README.md (the user asked to write this README again "
        "with write-readme)"
    )
    # A README of the doc set not in the worktree yet: the run drafts it.
    assert s.add_batch([], action="rewrite-readme", path="tools/README.md")["path"] == (
        "tools/README.md"
    )


def test_a_rewrite_request_names_a_readme_of_the_doc_set(docs_review):
    s = docs_review
    s.add_doc("README.md", "the install")
    s.add_doc("docs/reference.md", "the tabs")
    with pytest.raises(SessionError, match="names the README"):
        s.add_batch([], action="rewrite-readme")
    with pytest.raises(SessionError, match="not in the doc set"):
        s.add_batch([], action="rewrite-readme", path="other/README.md")
    with pytest.raises(SessionError, match="not a README.md"):
        s.add_batch([], action="rewrite-readme", path="docs/reference.md")
    with pytest.raises(SessionError, match="rewrite-readme only"):
        s.add_batch([], action="write-docs", path="README.md")
    with pytest.raises(SessionError, match="rewrite-readme only"):
        s.add_batch([{"text": "shorter"}], path="README.md")
    assert s.read_comments()["batches"] == []


def test_awaiting_docs_is_a_phase(session):
    assert session.write_status("awaiting-docs")["phase"] == "awaiting-docs"


def test_a_docs_review_is_a_code_session_not_coordinated(tmp_path):
    with pytest.raises(SessionError, match="code session"):
        Session("d", tmp_path).create("D", workflow="view-docs")
    s = Session("d", tmp_path)
    s.create("D", kind="code", repo=str(tmp_path), workflow="view-docs")
    assert s.read_plan()["workflow"] == "view-docs" and not s.coordinated


def test_the_reference_model_is_a_branch_review_of_the_same_repo(docs_review, tmp_path):
    root = docs_review.dir.parent
    repo = docs_review.read_plan()["repo"]
    docs = Session("install-docs", root)
    docs.create("Install", kind="code", repo=repo, workflow="view-docs")
    other = Session("elsewhere", root)
    other.create("Elsewhere", kind="code", repo=str(tmp_path), workflow="view-branch")
    triage = Session("triage", root)
    triage.create("Triage", kind="code", repo=repo, workflow="view-refactor")
    with pytest.raises(SessionError, match="no other session"):
        docs.set_reference("missing", "why")
    with pytest.raises(SessionError, match="no other session"):
        docs.set_reference("install-docs", "why")
    with pytest.raises(SessionError, match="not a session of this repo"):
        docs.set_reference("elsewhere", "why")
    with pytest.raises(SessionError, match="not a branch review"):
        docs.set_reference("triage", "why")
    with pytest.raises(SessionError, match="needs its reason"):
        docs.set_reference("doc-tab", "  ")
    ref = {"slug": "doc-tab", "reason": "adds view-docs"}
    assert docs.set_reference("doc-tab", " adds\n view-docs ") == ref
    assert docs.read_plan()["reference"] == ref
    assert docs.reference_model() == {
        "slug": "doc-tab",
        "title": "Doc tab",
        "reason": "adds view-docs",
        "lexicon": [],
    }
    docs.set_reference("")
    assert "reference" not in docs.read_plan() and docs.reference_model() is None


def test_a_bare_slug_reference_has_no_reason(docs_review):
    docs = Session("install-docs", docs_review.dir.parent)
    docs.create("Install", kind="code", repo=docs_review.read_plan()["repo"], workflow="view-docs")
    plan = docs.read_plan()
    plan["reference"] = "doc-tab"
    docs.plan_path.write_text(json.dumps(plan))
    model = docs.reference_model()
    assert model is not None and model["reason"] == ""


def test_the_reference_candidates_are_the_repos_branch_reviews(docs_review, tmp_path):
    root = docs_review.dir.parent
    repo = docs_review.read_plan()["repo"]
    plan = docs_review.read_plan()
    plan["outline"] = [
        {"id": "sheet", "title": "Sheet"},
        {"id": "i1", "title": "store", "part": "refactoring"},
    ]
    plan["lexicon"] = [{"term": "doc set", "section": "sheet", "definition": "the list"}]
    docs_review.plan_path.write_text(json.dumps(plan))
    docs = Session("install-docs", root)
    docs.create("Install", kind="code", repo=repo, workflow="view-docs")
    Session("triage", root).create("Triage", kind="code", repo=repo, workflow="view-refactor")
    Session("far", root).create("Far", kind="code", repo=str(tmp_path), workflow="view-branch")
    rows = docs.reference_candidates()
    assert [(r["slug"], r["sections"], r["terms"]) for r in rows] == [
        ("doc-tab", ["Sheet"], ["doc set"])
    ]


def test_docs_stay_out_of_the_publish_fingerprint_and_the_check(docs_review):
    s = docs_review
    before = s.fingerprint()
    s.add_doc("README.md", "the install")
    (s.repo_dir() / "README.md").write_text("Rewritten <div>\n\nblock</div>\n")
    assert s.fingerprint() == before
    assert s.published_sections() == [] and s.check_sections() == []
