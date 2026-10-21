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
    assert "1. Attention (s1)" in text and "- clé | key (section 1, core): vecteur" in text
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


@pytest.fixture
def branch(tmp_path):
    s = Session("gate", tmp_path)
    s.create("The gate", "rework the gate", kind="code", repo=str(tmp_path), workflow="view-branch")
    s.write_plan(
        outline=[
            {"id": "s1", "title": "Today"},
            {"id": "s2", "title": "The gate", "earns": "what it refuses", "brief": "no flag"},
            {"id": "i1", "title": "cli", "part": "refactoring", "item": {"verdict": "diverges"}},
            {"id": "i2", "title": "store", "part": "refactoring", "item": {"verdict": "conforms"}},
        ]
    )
    for sid, text in [("s1", "Today."), ("s2", "The gate."), ("i1", "Cli."), ("i2", "Store.")]:
        (s.sections_dir / f"{sid}.md").write_text(text)
    return s


def test_the_implementer_gets_the_modeling_part_and_the_items_it_must_act_on(branch):
    text = build(branch, "implementer", ["i1"])
    assert "- section 3. cli (i1), below" in text
    assert "The gate." in text and "Cli." in text and "Store." not in text
    assert "Store." in build(branch, "reviewer")


def test_the_implementer_gets_the_to_do_list_without_naming_it(branch):
    plan = branch.read_plan()
    todo = {"id": "todo", "title": "To-do", "part": "refactoring"}
    branch.write_plan(outline=[*plan["outline"], todo])
    (branch.sections_dir / "todo.md").write_text("- update the README")
    text = build(branch, "implementer")
    assert "- update the README" in text and "Cli." not in text


def test_changes_not_implemented_yet_are_shown_once_the_model_is_approved(branch):
    for i in range(CONTEXT_RECENT + 2):
        branch.add_change(f"change {i}")
    assert "Not implemented yet" not in build(branch, "writer")
    branch.add_batch([], action="approve-model")
    assert "No implementer has run." in build(branch, "writer")
    branch.mark_implemented("m1")
    text = build(branch, "implementer", ["m2", "m3"])
    assert "- m2: change 1 (cause: own judgment)" in text.split("## Trigger\n")[1]
    assert "The code carries the model up to m1." in text
    # m2 is older than the recent window but not implemented yet, so it is loaded anyway.
    assert "Not implemented yet: m2, m3," in text and text.count("- m2: change 1") == 2
    branch.mark_implemented(f"m{CONTEXT_RECENT + 2}")
    assert "Every change of the model is implemented." in build(branch, "reviewer")


def test_the_lexicon_gives_each_term_its_kind(branch):
    branch.write_plan(
        lexicon=[
            {"term": "gate", "section": "s2", "definition": "drops a segment"},
            {"term": "FSRS", "section": "s1", "definition": "a scheduler", "kind": "peripheral"},
        ]
    )
    text = build(branch, "writer")
    assert "- gate (section 2, core): drops a segment" in text
    assert "- FSRS (section 1, peripheral): a scheduler" in text


def test_the_outline_leaves_out_a_brief_left_in_an_older_plan(branch):
    # An older session's outline entry may still hold a brief: it stays in plan.json,
    # and the context no longer prints it.
    assert branch.read_plan()["outline"][1]["brief"] == "no flag"
    text = build(branch, "writer")
    assert "2. The gate (s2): what it refuses\n3. cli (i1)" in text
    assert "Brief" not in text and "no flag" not in text


def test_an_html_section_is_given_by_its_visible_text(branch):
    (branch.sections_dir / "s2.html").write_text("<style>p{}</style><p>The  gate,\n drawn.</p>")
    text = build(branch, "writer")
    assert "### 2. The gate (s2) · HTML section, its visible text (sections/s2.html)" in text
    assert "The gate, drawn." in text and "<p>" not in text


def test_deferred_questions_are_listed_with_their_note_and_anchor(session):
    session.add_question("PR or merge?", ["PR", "merge"], recommended="PR")
    session.unclear_question("q1", "what is a merge?")
    session.anchor_question("q1", "s2")
    text = build(session, "writer")
    assert "Open: none" in text
    assert (
        "- q1 [deferred] PR or merge? (options: PR / merge) (recommended: PR) "
        "(anchor section: s2) → unclear: what is a merge?"
    ) in text


def test_every_role_of_a_code_session_gets_the_code_map(review, session):
    assert "## Code map\n(none written yet)" in build(review, "writer")
    review.code_map_path.write_text("- the gate: `src/gate.py`\n")
    for role in ("planner", "writer", "implementer", "reviewer", "thread"):
        assert "## Code map\n- the gate: `src/gate.py`\n" in build(review, role)
    # An explanation has no code, so no code map.
    assert "## Code map" not in build(session, "writer")


TRANSCRIPT = "## User\nrework the gate, as we said\n\n## Agent\nA flag, or a rule?"


def test_without_a_transcript_every_role_gets_the_initial_request(branch):
    for role in ("planner", "writer", "implementer", "reviewer", "thread"):
        text = build(branch, role)
        assert "## Initial request\nrework the gate\n" in text
        assert "Request transcript" not in text and "request.md" not in text


def test_the_planner_and_the_writer_read_the_transcript_whole(branch):
    branch.write_request(TRANSCRIPT)
    for role in ("planner", "writer"):
        text = build(branch, role)
        assert "## Request transcript\n" in text and TRANSCRIPT in text
        assert "## Initial request" not in text


def test_the_other_roles_get_the_initial_request_and_the_transcript_path(branch):
    branch.write_request(TRANSCRIPT)
    for role in ("implementer", "reviewer", "thread"):
        text = build(branch, role)
        assert "## Initial request\nrework the gate\n" in text
        assert f"{branch.request_path}: open it when a comment needs" in text
        assert "A flag, or a rule?" not in text


def test_the_doc_set_goes_to_the_roles_that_work_on_the_docs(review, tmp_path):
    (tmp_path / "README.md").write_text("The keys 1 to 4.\n")
    review.add_doc("README.md", "the keys")
    review.add_doc("docs/old.md", "out of date")
    review.remove_doc("docs/old.md", user=True)
    review.add_stale("README.md", "keys 1 to 4", "five keys now", section="sheet")
    for role in ("writer", "implementer", "reviewer"):
        text = build(review, role)
        assert "## Doc set\n" in text and "- README.md: the keys" in text
        assert "Removed by the user (never add them back unless the user asks): docs/old.md" in text
        assert "- s1 README.md « keys 1 to 4 » (contradicts sheet): five keys now" in text
    assert "## Doc set" not in build(review, "planner")
    assert "## Doc set" not in build(review, "thread")


def test_a_review_with_no_doc_set_says_so(review):
    assert "## Doc set\nThe repo docs" in build(review, "writer")
    assert "(none written yet)\n\n## Stale passages" in build(review, "writer")


def _done_run(s, cid, n, k):
    import json

    folder = s.run_dir(cid, n)
    folder.mkdir(parents=True)
    record = {"case": cid, "n": n, "skill_version": k, "state": "done", "other_files": []}
    (folder / "run.json").write_text(json.dumps(record))
    (folder / "README.md").write_text("# core\n\nThe run's README.\n")


def test_a_workbench_context_prints_the_case_set_not_an_outline(workbench, cases_repo):
    s, (repo, sha) = workbench, cases_repo
    s.add_case("core", "edit")
    _done_run(s, "core", 1, 1)
    text = build(s, "thread", section="run:core:1:readme")
    assert "## Outline" not in text and "## Lexicon" not in text
    assert f"Skill file: {s.skill_file()}" in text
    assert f"Cases' repo: {repo.resolve()} at the pinned commit {sha}." in text
    assert "- core: core/ · edit · runs: 1 (skill v1, done)" in text
    assert "## Text of the passage (run core/ 1 · README, skill v1: runs/core/1/README.md)" in text
    assert "The run's README." in text
    pinned = build(s, "thread", section="pinned:core")
    assert "# core\n\nThe library." in pinned
    assert "# write-readme\n\nRule 1." in build(s, "thread", section="skill:")


def test_a_workbench_thread_is_briefed_with_the_case_set(workbench):
    from view_concept import threads
    from view_concept.agents import ClaudeBackend

    s = workbench
    s.add_case("core", "edit")
    _done_run(s, "core", 2, 1)
    thread = {"id": "t1", "section": "run:core:2:readme", "quote": "The run's", "question": ""}
    text = threads._briefing(s, thread, ClaudeBackend())
    assert "Passage: run core/ 2 · README, skill v1: runs/core/2/README.md: « The run's »" in text
    assert "## Case set" in text and "- core: core/ · edit · runs: 2 (skill v1, done)" in text
    assert "The run's README." in text and "a section of the workbench" in text
