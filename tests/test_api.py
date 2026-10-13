import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from view_concept import frame, server
from view_concept.store import Session, SessionError


@pytest.fixture
def client(session, monkeypatch):
    """A client whose server reads sessions from the test session's directory."""
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, session.dir.parent))
    return TestClient(server.app)


def test_api(client):
    r = client.get("/api/s/kv-cache")
    assert r.status_code == 200
    assert r.json()["sections"]["s1"]["html"] == "<p>L'attention.</p>\n"
    r = client.post("/api/s/kv-cache/batch", json={"comments": [{"section": "s1", "text": "hi"}]})
    assert r.json()["id"] == "b1"
    assert client.get("/api/s/missing").status_code == 404


def test_api_says_whether_claude_is_listening(client, session):
    assert client.get("/api/s/kv-cache").json()["listening"] is False
    session.write_heartbeat()
    assert client.get("/api/s/kv-cache").json()["listening"] is True


def test_api_sends_the_claude_questions(client, session):
    assert client.get("/api/s/kv-cache").json()["questions"] == []
    session.add_question("PR or merge?", ["PR", "merge"])
    state = client.get("/api/s/kv-cache").json()
    assert [q["id"] for q in state["questions"]] == ["q1"]
    assert state["status"]["phase"] == "awaiting-answer"


def test_api_answers_a_claude_question(client, session):
    session.add_question("PR or merge?", ["PR", "merge"])
    url = "/api/s/kv-cache/questions/q1/answer"
    assert client.post(url, json={"choices": [], "text": " "}).status_code == 400
    r = client.post(url, json={"choices": ["PR"], "text": ""})
    assert r.status_code == 200 and r.json()["action"] == "answer"
    state = client.get("/api/s/kv-cache").json()
    assert state["questions"][0]["status"] == "answered"
    assert state["comments"]["batches"][-1]["answers"][0]["choices"] == ["PR"]
    assert client.post(url, json={"text": "again"}).status_code == 400


def test_api_skips_a_claude_question(client, session):
    session.add_question("PR or merge?", ["PR", "merge"], recommended="PR")
    assert client.get("/api/s/kv-cache").json()["questions"][0]["recommended"] == "PR"
    url = "/api/s/kv-cache/questions/q1/skip"
    r = client.post(url)
    assert r.status_code == 200 and r.json()["answers"] == [{"question": "q1", "skipped": True}]
    q = client.get("/api/s/kv-cache").json()["questions"][0]
    assert q["status"] == "skipped" and q["skipped"] == r.json()["sent"]
    assert client.post(url).status_code == 400
    assert client.post("/api/s/kv-cache/questions/q9/skip").status_code == 400


def test_api_defers_an_unclear_question(client, session):
    session.add_question("PR or merge?", ["PR", "merge"], recommended="PR")
    url = "/api/s/kv-cache/questions/q1/unclear"
    r = client.post(url, json={"note": "what is a merge?"})
    assert r.status_code == 200
    assert r.json()["answers"] == [{"question": "q1", "unclear": True, "note": "what is a merge?"}]
    assert client.get("/api/s/kv-cache").json()["questions"][0]["status"] == "deferred"
    assert client.post(url, json={}).status_code == 400


def test_api_says_whether_a_grill_runs(client, session):
    assert client.get("/api/s/kv-cache").json()["grilling"] is False
    assert client.post("/api/s/kv-cache/batch", json={"action": "grill"}).status_code == 200
    assert client.get("/api/s/kv-cache").json()["grilling"] is True
    client.post("/api/s/kv-cache/batch", json={"action": "stop-grill"})
    assert client.get("/api/s/kv-cache").json()["grilling"] is False


def test_api_plan_skips_the_open_questions(client, session):
    session.add_question("Level?")
    assert client.post("/api/s/kv-cache/batch", json={"action": "plan"}).status_code == 200
    assert client.get("/api/s/kv-cache").json()["questions"][0]["status"] == "skipped"


def test_api_sends_the_session_workflow(client, session):
    assert client.get("/api/s/kv-cache").json()["workflow"] == "view-concept"


def test_api_renders_tips(client, session):
    plan = session.read_plan()
    plan["lexicon"] = [
        {"term": "clé", "section": "s1", "definition": "vecteur", "tip": "un *vecteur* $k$"},
        {"term": "valeur", "section": "s1", "definition": "l'autre vecteur"},
    ]
    session.plan_path.write_text(json.dumps(plan))
    lex = client.get("/api/s/kv-cache").json()["plan"]["lexicon"]
    assert "<em>vecteur</em>" in lex[0]["tip_html"] and "math inline" in lex[0]["tip_html"]
    assert lex[1]["tip_html"] == "l'autre vecteur"  # falls back to the definition


def test_api_threads(client, session):
    r = client.get("/api/s/kv-cache/threads")
    assert r.json() == {"forkable": False, "threads": []}
    assert client.post("/api/s/kv-cache/threads", json={"text": " "}).status_code == 400
    session.new_thread("s1", "L'attention")
    session.bind_agent("claude", "main-1")
    r = client.get("/api/s/kv-cache/threads").json()
    assert r["forkable"] and r["threads"][0]["id"] == "t1"
    assert client.post("/api/s/kv-cache/threads/x1", json={"text": "hi"}).status_code == 400
    assert client.delete("/api/s/kv-cache/threads/t1").status_code == 200
    assert client.delete("/api/s/kv-cache/threads/t1").status_code == 400


def test_api_keeps_the_part_of_an_outline_item(client, session):
    plan = session.read_plan()
    plan["outline"].append({"id": "s9", "title": "Cards", "part": "refactoring"})
    session.plan_path.write_text(json.dumps(plan))
    outline = client.get("/api/s/kv-cache").json()["plan"]["outline"]
    assert outline[-1]["part"] == "refactoring"


VERDICT_FILE = yaml.safe_load((Path(server.__file__).parent / "verdicts.yaml").read_text())
TONES = {"ok", "danger", "warn", "alt", "flag", "info"}


def set_workflow(session, workflow):
    plan = session.read_plan()
    plan["workflow"] = workflow
    session.plan_path.write_text(json.dumps(plan))


def test_every_verdict_has_a_meaning_and_a_tone():
    assert set(VERDICT_FILE) == {"view-branch", "view-refactor"}
    for verdicts in VERDICT_FILE.values():
        assert all(v["meaning"] and v["tone"] in TONES for v in verdicts)
        assert len({v["key"] for v in verdicts}) == len(verdicts)


@pytest.mark.parametrize("workflow", ["view-branch", "view-refactor"])
def test_api_sends_the_verdicts_of_the_session_workflow(client, session, workflow):
    set_workflow(session, workflow)
    verdicts = client.get("/api/s/kv-cache").json()["verdicts"]
    assert [v["key"] for v in verdicts] == [v["key"] for v in VERDICT_FILE[workflow]]
    assert verdicts[-1]["key"] == {"view-branch": "conforms", "view-refactor": "keep"}[workflow]


def test_api_branch_verdicts_keep_their_tones_and_destinations(client, session):
    set_workflow(session, "view-branch")
    verdicts = client.get("/api/s/kv-cache").json()["verdicts"]
    assert {v["key"]: v["tone"] for v in verdicts} == {
        "diverges": "danger",
        "move": "warn",
        "split": "alt",
        "throw": "flag",
        "out-of-pr": "info",
        "conforms": "ok",
    }
    assert {v["key"] for v in verdicts if v.get("sends_to")} == {"diverges", "move"}


def test_api_falls_back_to_branch_verdicts_without_a_workflow(client, session):
    plan = session.read_plan()
    del plan["workflow"]
    session.plan_path.write_text(json.dumps(plan))
    state = client.get("/api/s/kv-cache").json()
    assert state["workflow"] == ""
    assert state["verdicts"] == VERDICT_FILE["view-branch"]


def test_api_sends_no_verdicts_to_an_explanation(client):
    assert client.get("/api/s/kv-cache").json()["verdicts"] == []


def test_api_updated_sections(client, session):
    s1 = client.get("/api/s/kv-cache").json()["sections"]["s1"]
    assert s1["updated"] is False and "seen_html" not in s1  # a first write is read
    (session.sections_dir / "s1.md").write_text("L'attention, réécrite.\n")
    s1 = client.get("/api/s/kv-cache").json()["sections"]["s1"]
    assert s1["updated"] and s1["seen_html"] == "<p>L'attention.</p>\n"
    # Marking read records the text the page showed, not a later rewrite.
    client.post("/api/s/kv-cache/seen", json={"sections": {"s1": "L'attention, réécrite.\n"}})
    assert client.get("/api/s/kv-cache").json()["sections"]["s1"]["updated"] is False
    (session.sections_dir / "s3.md").write_text("Nouvelle.\n")
    assert client.get("/api/s/kv-cache").json()["sections"]["s3"]["updated"] is False


def test_api_sends_the_publish_record(client, session):
    assert client.get("/api/s/kv-cache").json()["published"] is None
    record = session.write_published("https://example.org/kv-cache/", session.fingerprint())
    published = client.get("/api/s/kv-cache").json()["published"]
    assert published == {"url": record["url"], "at": record["at"], "out_of_date": False}
    (session.sections_dir / "s1.md").write_text("L'attention, réécrite.")
    assert client.get("/api/s/kv-cache").json()["published"]["out_of_date"] is True


def test_api_publishes(client, session, monkeypatch):
    def fake_publish(s):
        assert s.slug == "kv-cache"
        return "https://example.org/kv-cache/"

    monkeypatch.setattr(server.publish, "publish", fake_publish)
    r = client.post("/api/s/kv-cache/publish")
    assert r.status_code == 200 and r.json() == {"url": "https://example.org/kv-cache/"}


def test_api_unpublishes(client, session, monkeypatch):
    called = []
    monkeypatch.setattr(server.publish, "unpublish", lambda s: called.append(s.slug))
    r = client.post("/api/s/kv-cache/unpublish")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert called == ["kv-cache"]


@pytest.mark.parametrize("action", ["publish", "unpublish"])
def test_api_publish_errors_are_bad_requests(client, monkeypatch, action):
    def refuse(s):
        raise SessionError("kv-cache is a code session")

    monkeypatch.setattr(server.publish, action, refuse)
    r = client.post(f"/api/s/kv-cache/{action}")
    assert r.status_code == 400 and r.json()["detail"] == "kv-cache is a code session"
    assert client.post(f"/api/s/missing/{action}").status_code == 404


def test_a_branch_review_needs_no_fork_for_its_threads(client, session):
    # Its threads start from the session folder, so the page does not warn about a fork.
    s = Session("gate", session.dir.parent)
    s.create("The gate", kind="code", repo=str(session.dir))
    assert client.get("/api/s/gate/threads").json()["forkable"] is True


def test_api_shows_the_change_history(client, session):
    session.add_change("gate split in two", by="writer", cause=["c7"])
    (d,) = client.get("/api/s/kv-cache").json()["changes"]
    assert d["change"] == "gate split in two" and d["cause"] == ["c7"]


def test_api_shows_the_changes_not_implemented_yet(client, session):
    s = Session("gate", session.dir.parent)
    s.create("The gate", kind="code", repo=str(session.dir), workflow="view-branch")
    s.add_change("gate split")
    s.add_change("threshold renamed")
    s.add_batch([], action="approve-model")
    s.mark_implemented("m1")
    state = client.get("/api/s/gate").json()
    assert state["implemented"] == "m1" and state["unimplemented"] == ["m2"]


def test_an_html_section_is_drawn_in_a_frame(client, session):
    (session.sections_dir / "s3.html").write_text("<html><head><title>x</title></head><p>Fig</p>")
    view = client.get("/api/s/kv-cache").json()["sections"]["s3"]
    assert view["kind"] == "html" and view["version"] and "html" not in view
    r = client.get("/s/kv-cache/sections/s3.html")
    assert r.status_code == 200
    assert r.text.startswith(f"<html><head>{server.FRAME_HEAD}<title>")
    # Opened on its own (a new tab, its address), it keeps an origin of its own.
    assert r.headers["content-security-policy"] == f"sandbox {frame.SANDBOX}"
    tokens = client.get("/frame/tokens.css").text
    assert '[data-theme="catppuccin-latte"]' in tokens and "--ink: var(--om-foreground)" in tokens
    assert "font-family" not in tokens  # the tokens, without the skin's styles
    assert client.get("/s/kv-cache/sections/s1.html").status_code == 404


def test_an_updated_html_section_carries_its_baseline_file(client, session):
    (session.sections_dir / "s3.html").write_text("<p>Fig</p>")
    view = client.get("/api/s/kv-cache").json()["sections"]["s3"]
    assert view["updated"] is False and "seen" not in view  # a first write is read
    (session.sections_dir / "s3.html").write_text("<p>Fig, reef</p>")
    view = client.get("/api/s/kv-cache").json()["sections"]["s3"]
    # The page compares the visible text of both files for the changes frame message.
    assert view["updated"] and view["seen"] == "<p>Fig</p>"


@pytest.mark.parametrize(
    ("document", "framed"),
    [
        ("<p>x</p>", "H<p>x</p>"),
        ("<!doctype html><p>x</p>", "<!doctype html>H<p>x</p>"),
        ("<!DOCTYPE html><html lang=en><body>", "<!DOCTYPE html><html lang=en>H<body>"),
        ("<html><HEAD id=h><style></style>", "<html><HEAD id=h>H<style></style>"),
    ],
)
def test_the_frame_head_comes_first_in_the_head(document, framed):
    assert frame.inject(document, "H") == framed


def test_the_page_serves_an_html_sections_media_folder(client, session):
    (session.sections_dir / "s3.html").write_text('<video src="s3/step-1.mp4"></video>')
    (session.sections_dir / "s3").mkdir()
    (session.sections_dir / "s3" / "step-1.mp4").write_bytes(b"mp4")
    media = client.get("/s/kv-cache/sections/s3/step-1.mp4")
    assert media.content == b"mp4"
    assert media.headers["content-security-policy"] == f"sandbox {frame.SANDBOX}"
    assert client.get("/s/kv-cache/sections/s3/missing.mp4").status_code == 404
    assert client.get("/s/kv-cache/sections/s3/..%2F..%2Fplan.json").status_code == 404
    (session.sections_dir / "s1").mkdir()
    (session.sections_dir / "s1" / "a.png").write_bytes(b"png")
    assert client.get("/s/kv-cache/sections/s1/a.png").status_code == 404  # not an HTML section


def test_focus_counts_the_open_pages(client):
    assert client.post("/api/focus/kv-cache").json() == {"pages": 0}
    assert client.post("/api/focus/missing").status_code == 404


def test_launch_opens_a_terminal_in_the_project(client, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(server.launch, "open_terminal", lambda *a: opened.append(a))
    body = {"project": str(tmp_path), "request": "add a sidebar", "worktree": "Session sidebar"}
    r = client.post("/api/launch", json=body)
    assert r.json()["command"] == "claude -w session-sidebar '/view-branch add a sidebar'"
    assert opened == [(str(tmp_path), r.json()["command"])]
    r = client.post("/api/launch", json={**body, "skill": "explain"})
    assert r.status_code == 400 and len(opened) == 1
