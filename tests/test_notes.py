import os
import subprocess
import sys

from view_concept.notes import add_links, write_note


def view_concept(home, notes, *args):
    """Run the command line against a session store in `home`, session notes in `notes`
    (off when None)."""
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(home)}
    env.pop("VIEW_CONCEPT_SESSION_NOTES", None)
    if notes is not None:
        env["VIEW_CONCEPT_SESSION_NOTES"] = str(notes)
    for name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "JAZZ_AGENT_PROCESS"):
        env.pop(name, None)
    cmd = [sys.executable, "-m", "view_concept.cli", *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_a_note_names_its_session_and_links(tmp_path):
    path, created = write_note(
        tmp_path, "kw-eval", 'Eval "setup"', "view-concept", "http://h/s/kw-eval", ["a", "a"]
    )
    assert created
    assert path.read_text() == (
        "---\ntype: view-concept-session\naliases:\n"
        '  - "Eval \\"setup\\""\nworkflow: view-concept\nurl: http://h/s/kw-eval\n---\n'
        "Liens : [[a]]\n"
    )


def test_adding_links_keeps_what_the_user_wrote(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("---\ntype: x\n---\nLiens : [[a]]\n\nMes notes, voir [[b|B]].\n")
    assert add_links(path, ["a", "b", "c"]) == ["c"]
    expected = "---\ntype: x\n---\nLiens : [[a]] [[c]]\n\nMes notes, voir [[b|B]].\n"
    assert path.read_text() == expected


def test_a_note_without_its_links_line_gets_one(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("---\ntype: x\n---\nRien.\n")
    add_links(path, ["a"])
    assert path.read_text() == "---\ntype: x\n---\nRien.\n\nLiens : [[a]]\n"


def test_an_existing_note_is_not_rewritten(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("mine\n")
    _, created = write_note(tmp_path, "s", "T", "view-concept", "u", [])
    assert not created and path.read_text() == "mine\n"


def test_new_writes_no_note_when_notes_are_off(tmp_path):
    r = view_concept(tmp_path, None, "new", "Tree", "--link", "nowhere")
    assert r.returncode == 0, r.stderr
    assert '"note"' not in r.stdout


def test_new_writes_the_note_with_its_links(tmp_path):
    notes = tmp_path / "vault" / "sessions"
    assert view_concept(tmp_path, notes, "new", "Tree", "--slug", "tree").returncode == 0
    r = view_concept(tmp_path, notes, "new", "Eval", "--slug", "eval", "--link", "tree")
    assert r.returncode == 0, r.stderr
    text = (notes / "eval.md").read_text()
    assert "url: http://127.0.0.1:" in text and "/s/eval\n" in text
    assert text.endswith("Liens : [[tree]]\n")


def test_new_refuses_a_link_to_an_unknown_session(tmp_path):
    r = view_concept(tmp_path, tmp_path / "notes", "new", "Eval", "--link", "nowhere")
    assert r.returncode != 0 and "nowhere" in r.stderr
    assert not (tmp_path / "sessions" / "eval").exists()


def test_note_designates_an_existing_session_then_adds_links(tmp_path):
    view_concept(tmp_path, None, "new", "Tree", "--slug", "tree")
    view_concept(tmp_path, None, "new", "Eval", "--slug", "eval")
    notes = tmp_path / "notes"
    assert view_concept(tmp_path, notes, "note", "eval").returncode == 0
    assert (notes / "eval.md").read_text().endswith("Liens :\n")
    assert view_concept(tmp_path, notes, "note", "eval", "--link", "tree").returncode == 0
    assert (notes / "eval.md").read_text().endswith("Liens : [[tree]]\n")


def test_note_refuses_when_notes_are_off(tmp_path):
    view_concept(tmp_path, None, "new", "Tree", "--slug", "tree")
    r = view_concept(tmp_path, None, "note", "tree")
    assert r.returncode != 0 and "VIEW_CONCEPT_SESSION_NOTES" in r.stderr
