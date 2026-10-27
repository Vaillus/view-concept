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
    # A fact goes on a doc's anchor only.
    bad = {"section": "s1", "quote": "x", "fact": "f1", "text": "why?"}
    assert client.post("/api/s/kv-cache/threads", json=bad).status_code == 400
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
    assert set(VERDICT_FILE) == {"build-feature", "triage-code", "review-docs"}
    for verdicts in VERDICT_FILE.values():
        assert all(v["meaning"] and v["tone"] in TONES for v in verdicts)
        assert len({v["key"] for v in verdicts}) == len(verdicts)


@pytest.mark.parametrize("workflow", ["build-feature", "triage-code"])
def test_api_sends_the_verdicts_of_the_session_workflow(client, session, workflow):
    set_workflow(session, workflow)
    verdicts = client.get("/api/s/kv-cache").json()["verdicts"]
    assert [v["key"] for v in verdicts] == [v["key"] for v in VERDICT_FILE[workflow]]
    assert verdicts[-1]["key"] == {"build-feature": "conforms", "triage-code": "keep"}[workflow]


def test_api_branch_verdicts_keep_their_tones_and_destinations(client, session):
    set_workflow(session, "build-feature")
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
    assert state["verdicts"] == VERDICT_FILE["build-feature"]


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
    s.create("The gate", kind="code", repo=str(session.dir), workflow="build-feature")
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
    assert "-webkit-font-smoothing" not in tokens  # the tokens, without the skin's styles
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
    assert r.json()["command"] == (
        "claude --permission-mode auto -w session-sidebar '/build-feature add a sidebar'"
    )
    assert opened == [(str(tmp_path), r.json()["command"])]
    r = client.post("/api/launch", json={**body, "skill": "explain"})
    assert r.status_code == 400 and len(opened) == 1


def test_a_pending_launch_shows_until_its_session_exists(client, tmp_path, monkeypatch):
    monkeypatch.setattr(server.launch, "open_terminal", lambda *a: None)
    rows: list[dict] = []
    monkeypatch.setattr(server, "list_sessions", lambda: rows)
    project = tmp_path / "proj"
    project.mkdir()
    r = client.post("/api/launch", json={"project": str(project), "request": "explain the gate"})
    lid = r.json()["launch"]["id"]
    got = client.get("/api/launches").json()
    assert [x["request"] for x in got["launches"]] == ["explain the gate"]
    assert got["pending_for"] == 300
    at = got["launches"][0]["at"]
    # A session of another project, or one created before the launch, leaves it pending.
    rows.append({"slug": "other", "project": "/elsewhere", "created_at": "9999"})
    rows.append({"slug": "old", "project": str(project.resolve()), "created_at": "2000"})
    assert [x["id"] for x in client.get("/api/launches").json()["launches"]] == [lid]
    # The first session created in its project after it takes its place.
    rows.append({"slug": "new", "project": str(project.resolve()), "created_at": at + "1"})
    assert client.get("/api/launches").json()["launches"] == []
    # × removes one.
    r = client.post("/api/launch", json={"project": str(project), "request": "again"})
    assert client.delete(f"/api/launches/{r.json()['launch']['id']}").status_code == 200
    assert client.get("/api/launches").json()["launches"] == []


def test_state_carries_what_the_banner_is_computed_from(client, session):
    st = session.write_status("writing", ["s1"])
    state = client.get("/api/s/kv-cache").json()
    assert state["status"]["shown"] == "writing" and state["status"]["run"]["set"] == ["s1"]
    assert state["activity"] >= st["since"]
    assert state["batch"] is None
    client.post("/api/s/kv-cache/batch", json={"comments": [{"section": "s1", "text": "hi"}]})
    batch = client.get("/api/s/kv-cache").json()["batch"]
    assert batch["id"] == "b1" and batch["stage"] == "sent" and batch["comments"] == 1


def test_metrics_serve_branch_reviews_only(client, session, tmp_path, monkeypatch):
    monkeypatch.setenv("VIEW_CONCEPT_CLAUDE_PROJECTS", str(tmp_path / "projects"))
    assert client.get("/api/s/kv-cache/metrics").status_code == 404
    review = Session("review", session.dir.parent)
    review.create("A review", kind="code", repo=str(tmp_path / "repo"))
    review.add_batch([{"section": "s1", "text": "why?"}])
    r = client.get("/api/s/review/metrics")
    assert r.status_code == 200
    m = r.json()
    assert m["slug"] == "review" and m["variant"] == {"name": "none", "models": {}}
    assert m["runs"] == [] and m["quality"]["comments"] == 1
    assert [b["id"] for b in m["batches"]] == ["b1"]
    assert m["compare"]["variants"][0]["reviews"][0]["current"] is True


def test_drafts_are_shared_through_the_session_folder(client, session):
    url = "/api/s/kv-cache/drafts"
    assert client.get(url).json() == {"drafts": [], "note": ""}
    a = {"section": "s1", "quote": "L'attention", "prefix": "", "text": "Also on the Mac?"}
    assert client.put(f"{url}/a1", json=a).json() == {"saved": True}
    assert client.put(f"{url}/b2", json={**a, "text": "B", "thread": "t1"}).json()["saved"]
    # The last edit wins, whichever page made it; the order stays.
    client.put(f"{url}/a1", json={**a, "text": "Fine for me."})
    client.put(f"{url}/a1", json={**a, "text": "Fine, but show it."})
    client.put("/api/s/kv-cache/note", json={"note": "general"})
    got = client.get(url).json()
    assert [(d["id"], d["text"]) for d in got["drafts"]] == [
        ("a1", "Fine, but show it."),
        ("b2", "B"),
    ]
    assert got["drafts"][1]["thread"] == "t1" and "thread" not in got["drafts"][0]
    assert got["note"] == "general"
    # A draft deleted on one page is gone on both; an edit to it arriving later is dropped.
    assert client.delete(f"{url}/b2").status_code == 200
    assert client.put(f"{url}/b2", json={**a, "text": "late"}).json() == {"saved": False}
    assert [d["id"] for d in client.get(url).json()["drafts"]] == ["a1"]
    assert client.put(f"{url}/bad%20id", json=a).status_code == 400


def test_a_batch_clears_the_drafts_it_carried(client, session):
    url = "/api/s/kv-cache/drafts"
    client.put(f"{url}/a1", json={"section": "s1", "text": "one"})
    client.put(f"{url}/a2", json={"section": "s1", "text": "two"})
    client.put("/api/s/kv-cache/note", json={"note": "n"})
    body = {"comments": [{"section": "s1", "text": "one"}], "note": "n", "drafts": ["a1"]}
    assert client.post("/api/s/kv-cache/batch", json=body).status_code == 200
    assert client.get(url).json() == {
        "drafts": [{"id": "a2", "section": "s1", "quote": "", "prefix": "", "text": "two"}],
        "note": "",
    }
    # A sent draft is gone like a deleted one: a late edit to it does not bring it back.
    late = client.put(f"{url}/a1", json={"section": "s1", "text": "one, edited"})
    assert late.json() == {"saved": False}
    assert [d["id"] for d in client.get(url).json()["drafts"]] == ["a2"]


def test_a_browsers_old_drafts_move_after_those_there(client, session):
    url = "/api/s/kv-cache/drafts"
    client.put(f"{url}/a1", json={"section": "s1", "text": "here"})
    client.put("/api/s/kv-cache/note", json={"note": "first"})
    old = [{"id": "a1", "text": "dup"}, {"id": "o1", "section": "s2", "text": "old", "x": 1}]
    r = client.post(f"{url}/import", json={"drafts": old, "note": "second"})
    assert r.status_code == 200
    got = client.get(url).json()
    assert [(d["id"], d["text"]) for d in got["drafts"]] == [("a1", "here"), ("o1", "old")]
    assert got["note"] == "first\n\nsecond"


def test_drafts_are_not_the_agents_activity(client, session):
    before = session.last_activity()
    sig = session.signature()
    client.put("/api/s/kv-cache/drafts/a1", json={"section": "s1", "text": "x"})
    assert session.last_activity() == before and session.signature() == sig
    assert session.drafts_signature() != ()


@pytest.fixture
def doc_review(session):
    """A feature next to the test session, on a repo with one doc in its doc set."""
    repo = session.dir.parent / "repo"
    (repo / "docs" / "img").mkdir(parents=True)
    (repo / "docs" / "reference.md").write_text("# Reference\n\nThe keys 1 to 4.\n")
    (repo / "docs" / "img" / "tabs.png").write_bytes(b"png")
    s = Session("doc-tab", session.dir.parent)
    s.create("Doc tab", kind="code", repo=str(repo), base="main")
    s.add_doc("docs/reference.md", "the tabs and keys")
    s.add_doc("docs/missing.md", "created later")
    return s


def test_state_carries_the_doc_set_and_each_doc(client, doc_review):
    docs = client.get("/api/s/doc-tab").json()["docs"]
    assert docs["set"][0]["path"] == "docs/reference.md"
    assert docs["set"][0]["reason"] == "the tabs and keys"
    assert docs["removed"] == []
    view = docs["views"]["docs/reference.md"]
    assert view["exists"] is True and view["updated"] is False
    assert view["html"] == "<h1>Reference</h1>\n<p>The keys 1 to 4.</p>\n"
    assert docs["views"]["docs/missing.md"] == {"exists": False}
    assert client.get("/api/s/kv-cache").json()["docs"]["set"] == []


def test_a_rewritten_doc_is_updated_until_marked_read(client, doc_review):
    doc = doc_review.repo_dir() / "docs" / "reference.md"
    client.get("/api/s/doc-tab")  # the first text is the first baseline
    doc.write_text("# Reference\n\nThe keys 1 to 5.\n")
    view = client.get("/api/s/doc-tab").json()["docs"]["views"]["docs/reference.md"]
    assert view["updated"] is True and "1 to 4" in view["seen_html"]
    md = "# Reference\n\nThe keys 1 to 5.\n"
    r = client.post("/api/s/doc-tab/seen", json={"sections": {"doc:docs/reference.md": md}})
    assert r.status_code == 200
    view = client.get("/api/s/doc-tab").json()["docs"]["views"]["docs/reference.md"]
    assert view["updated"] is False


def edit_doc(client, md, base, path="docs/reference.md"):
    return client.post("/api/s/doc-tab/doc", json={"path": path, "md": md, "base": base})


def test_a_doc_edited_in_the_page_is_written_with_no_green_highlight(client, doc_review):
    doc = doc_review.repo_dir() / "docs" / "reference.md"
    old = doc.read_text()
    client.get("/api/s/doc-tab")  # the first text is the first baseline
    new = "# Reference\n\nThe keys 1 to 5.\n"
    r = edit_doc(client, new, old)
    assert r.status_code == 200
    assert doc.read_text() == new
    view = client.get("/api/s/doc-tab").json()["docs"]["views"]["docs/reference.md"]
    assert view["updated"] is False


def test_an_edit_keeps_the_green_highlight_of_an_unread_rewrite(client, doc_review):
    doc = doc_review.repo_dir() / "docs" / "reference.md"
    client.get("/api/s/doc-tab")
    rewrite = "# Reference\n\nThe keys 1 to 5.\n"
    doc.write_text(rewrite)
    edit = "# Reference\n\nThe keys 1 to 5, and 0.\n"
    r = edit_doc(client, edit, rewrite)
    assert r.status_code == 200
    view = client.get("/api/s/doc-tab").json()["docs"]["views"]["docs/reference.md"]
    assert view["updated"] is True and "1 to 4" in view["seen_html"]


def test_an_edit_of_a_doc_changed_meanwhile_is_refused(client, doc_review):
    doc = doc_review.repo_dir() / "docs" / "reference.md"
    old = doc.read_text()
    doc.write_text("# Reference\n\nRewritten by the agent.\n")
    r = edit_doc(client, "mine", old)
    assert r.status_code == 409
    assert "Rewritten by the agent" in doc.read_text()


def test_only_a_doc_of_the_doc_set_in_the_worktree_is_edited(client, doc_review):
    for path in ("README.md", "docs/missing.md", "../outside.md"):
        r = edit_doc(client, "x", "", path)
        assert r.status_code == 400, path
    assert not (doc_review.repo_dir() / "docs" / "missing.md").exists()


def test_the_page_serves_a_repo_file_a_doc_points_to(client, doc_review):
    assert client.get("/s/doc-tab/repo/docs/img/tabs.png").content == b"png"
    assert client.get("/s/doc-tab/repo/docs/img/none.png").status_code == 404
    assert client.get("/s/doc-tab/repo/.git/config").status_code == 404
    (doc_review.repo_dir() / ".git").mkdir()
    (doc_review.repo_dir() / ".git" / "config").write_text("[core]")
    assert client.get("/s/doc-tab/repo/.git/config").status_code == 404
    assert client.get("/s/doc-tab/repo/.GIT/config").status_code == 404
    assert client.get("/s/doc-tab/repo/..%2Fsessions%2Fdoc-tab%2Fplan.json").status_code == 404
    assert client.get("/s/kv-cache/repo/README.md").status_code == 404


def _git(repo, *args):
    import subprocess

    cmd = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args]
    subprocess.run(cmd, check=True, capture_output=True)


def test_the_base_mark_compares_a_doc_with_the_merge_base(client, doc_review):
    repo = doc_review.repo_dir()
    doc = repo / "docs" / "reference.md"
    _git(repo, "init", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    _git(repo, "switch", "-c", "feat")
    doc.write_text("# Reference\n\nThe keys 1 to 5.\n")  # uncommitted: still compared
    (repo / "docs" / "missing.md").write_text("Created on the branch.\n")
    views = client.get("/api/s/doc-tab").json()["docs"]["views"]
    ref = views["docs/reference.md"]
    assert ref["base_html"] == "<h1>Reference</h1>\n<p>The keys 1 to 4.</p>\n"
    assert ref["new"] is False and "1 to 5" in ref["html"]
    assert views["docs/missing.md"]["base_html"] is None
    assert views["docs/missing.md"]["new"] is True


def test_the_base_mark_reads_a_worktree_below_the_git_root(client, doc_review):
    repo = doc_review.repo_dir()
    (repo / "docs" / "missing.md").write_text("At the base.\n")
    _git(repo.parent, "init", "-b", "main")
    _git(repo.parent, "add", repo.name)
    _git(repo.parent, "commit", "-m", "base")
    views = client.get("/api/s/doc-tab").json()["docs"]["views"]
    assert views["docs/missing.md"]["base_html"] == "<p>At the base.</p>\n"
    assert views["docs/missing.md"]["new"] is False


def test_a_git_failure_is_no_base_mark(doc_review):
    _git(doc_review.repo_dir(), "init", "-b", "main")
    assert doc_review.base_text("docs/reference.md", "0" * 40) is None


def test_no_base_mark_when_git_cannot_tell(client, doc_review):
    view = client.get("/api/s/doc-tab").json()["docs"]["views"]["docs/reference.md"]
    assert view["base_html"] is None and view["new"] is False


def test_state_counts_the_stale_passages_shown(client, doc_review):
    doc_review.add_stale("docs/reference.md", "The keys 1 to 4.", "five keys", "sheet")
    docs = client.get("/api/s/doc-tab").json()["docs"]
    assert docs["set"][0]["stale"] == 1 and docs["set"][1]["stale"] == 0
    assert docs["stale"] == [{"id": "s1", "doc": "docs/reference.md",
                              "quote": "The keys 1 to 4.", "section": "sheet",
                              "note": "five keys"}]  # fmt: skip


def test_state_carries_minor_docs_and_failure_indicators(client, doc_review):
    doc_review.add_doc("README.md", "the install")
    doc_review.set_minor("docs/reference.md", "a name in a list", 1, 1)
    doc_review.set_failing("README.md", 3, 6, structure=True)
    doc_review.order_docs(["README.md", "docs/missing.md", "docs/reference.md"])
    docs = client.get("/api/s/doc-tab").json()["docs"]
    assert [d["path"] for d in docs["set"]] == ["README.md", "docs/missing.md", "docs/reference.md"]
    assert docs["set"][0]["failing"] == {"fail": 3, "total": 6, "structure": True}
    assert docs["set"][2]["minor"] == "a name in a list"
    assert docs["set"][2]["diff"] == {"added": 1, "removed": 1}
    assert "minor" not in docs["set"][0] and "failing" not in docs["set"][2]


def test_state_carries_the_missing_facts_highlighted_until_read(client, doc_review):
    doc_review.add_doc("README.md", "the install")
    doc_review.add_missing_fact("README.md", "Run serve.", "leave", "the code says open", 4)
    docs = client.get("/api/s/doc-tab").json()["docs"]  # the first list is the baseline
    facts = docs["facts"]["README.md"]
    assert docs["set"][2]["facts"] == 1 and docs["set"][0]["facts"] == 0
    assert facts["list"] == [{"id": "f1", "fact": "Run serve.", "passage": 4,
                              "proposal": "leave", "reason": "the code says open",
                              "state": "pending", "updated": False}]  # fmt: skip
    doc_review.add_missing_fact("README.md", "Offline, TeX.", "keep", "a link")
    doc_review.mark_missing_fact("f1", "left")
    facts = client.get("/api/s/doc-tab").json()["docs"]["facts"]["README.md"]
    assert [f["updated"] for f in facts["list"]] == [True, True]
    r = client.post("/api/s/doc-tab/seen", json={"sections": {"facts:README.md": facts["text"]}})
    assert r.status_code == 200
    facts = client.get("/api/s/doc-tab").json()["docs"]["facts"]["README.md"]
    assert [f["updated"] for f in facts["list"]] == [False, False]
    # A batch moves the baseline too.
    doc_review.mark_missing_fact("f2", "kept")
    body = {"comments": [{"section": "doc:README.md", "quote": "Offline, TeX.", "text": "ok",
                          "fact": "f2"}]}  # fmt: skip
    b = client.post("/api/s/doc-tab/batch", json=body).json()
    assert b["comments"][0]["fact"] == "f2"
    facts = client.get("/api/s/doc-tab").json()["docs"]["facts"]["README.md"]
    assert [f["updated"] for f in facts["list"]] == [False, False]


def test_a_pending_missing_fact_is_counted_on_its_doc(client, doc_review):
    # The page puts a minor README back in the review list while one of its facts waits.
    doc_review.add_doc("README.md", "the install")
    doc_review.add_missing_fact("README.md", "Run serve.", "leave", "the code says open")
    doc_review.add_missing_fact("README.md", "Offline, TeX.", "keep", "a link")
    docs = client.get("/api/s/doc-tab").json()["docs"]
    assert docs["set"][2]["pending"] == 2 and docs["set"][0]["pending"] == 0
    doc_review.mark_missing_fact("f1", "left")
    doc_review.mark_missing_fact("f2", "kept")
    assert client.get("/api/s/doc-tab").json()["docs"]["set"][2]["pending"] == 0


def test_a_batch_asks_for_the_doc_pass_and_the_pr(client):
    body = {"action": "write-docs", "then_pr": True}
    r = client.post("/api/s/kv-cache/batch", json=body)
    assert r.status_code == 200 and r.json()["then_pr"] is True
    r = client.post("/api/s/kv-cache/batch", json={"action": "create-pr", "then_pr": True})
    assert r.status_code == 400


def test_a_batch_asks_to_rewrite_a_readme(client, doc_review):
    doc_review.add_doc("README.md", "the install")
    body = {"action": "rewrite-readme", "path": "README.md"}
    r = client.post("/api/s/doc-tab/batch", json=body)
    assert r.status_code == 200 and r.json()["path"] == "README.md"
    body = {"action": "rewrite-readme", "path": "docs/reference.md"}
    assert client.post("/api/s/doc-tab/batch", json=body).status_code == 400
    body = {"action": "write-docs", "path": "README.md"}
    assert client.post("/api/s/doc-tab/batch", json=body).status_code == 400


def test_a_docs_review_shows_its_doc_set_with_no_plan_nor_sections(client, session):
    repo = session.dir.parent / "docs-repo"
    repo.mkdir()
    (repo / "README.md").write_text("## Install\n\nYou need uv.\n")
    s = Session("install-docs", session.dir.parent)
    s.create("Install docs", kind="code", repo=str(repo), workflow="review-docs")
    s.add_doc("README.md", "the install part")
    state = client.get("/api/s/install-docs").json()
    assert state["workflow"] == "review-docs" and state["verdicts"] == []
    assert state["plan"]["outline"] == [] and state["sections"] == {}
    assert state["docs"]["set"][0]["path"] == "README.md"
    assert state["docs"]["views"]["README.md"]["exists"] is True


def test_the_reference_model_is_read_from_another_session(client, doc_review):
    docs = Session("install-docs", doc_review.dir.parent)
    docs.create("Install", kind="code", repo=doc_review.read_plan()["repo"], workflow="review-docs")
    assert client.get("/api/s/install-docs").json()["docs"]["reference"] is None
    plan = doc_review.read_plan()
    plan["outline"] = [{"id": "sheet", "title": "Sheet"}]
    plan["lexicon"] = [{"term": "doc set", "section": "sheet", "definition": "the *list*"}]
    doc_review.plan_path.write_text(json.dumps(plan))
    docs.set_reference("doc-tab", "adds review-docs")
    ref = client.get("/api/s/install-docs").json()["docs"]["reference"]
    assert ref["slug"] == "doc-tab" and ref["title"] == "Doc tab" and ref["url"] == "/s/doc-tab"
    assert ref["reason"] == "adds review-docs"
    assert ref["lexicon"][0]["tip_html"] == "the <em>list</em>"
    plan["lexicon"][0]["definition"] = "the docs"
    doc_review.plan_path.write_text(json.dumps(plan))  # re-read as it is now
    ref = client.get("/api/s/install-docs").json()["docs"]["reference"]
    assert ref["lexicon"][0]["tip_html"] == "the docs"


def test_state_carries_the_concept_triage_highlighted_until_read(client, doc_review):
    doc_review.set_triage("pooled WER", True, "a wrong WER")
    triage = client.get("/api/s/doc-tab").json()["docs"]["triage"]  # the baseline
    assert triage["list"] == [{"id": "k1", "concept": "pooled WER", "enters": True,
                               "reason": "a wrong WER", "updated": False}]  # fmt: skip
    doc_review.set_triage("pooled WER", False, "nobody reads it")
    triage = client.get("/api/s/doc-tab").json()["docs"]["triage"]
    assert triage["list"][0]["updated"] is True
    r = client.post("/api/s/doc-tab/seen", json={"sections": {"triage:": triage["text"]}})
    assert r.status_code == 200
    assert client.get("/api/s/doc-tab").json()["docs"]["triage"]["list"][0]["updated"] is False
    body = {"comments": [{"section": "triage:k1", "quote": "pooled WER", "text": "it enters"}]}
    assert client.post("/api/s/doc-tab/batch", json=body).status_code == 200
    body = {"comments": [{"section": "triage:", "text": "x"}]}
    assert client.post("/api/s/doc-tab/batch", json=body).status_code == 400


def test_state_carries_the_move_plans_highlighted_until_read(client, doc_review):
    doc_review.add_doc("README.md", "the install")
    doc_review.add_move("README.md", "the WER rules", "model", "rewritten", to="core/README.md")
    moves = client.get("/api/s/doc-tab").json()["docs"]["moves"]  # the baseline
    assert moves["README.md"]["list"] == [{"id": "p1", "passage": "the WER rules",
                                           "part": "model", "to": "core/README.md",
                                           "becomes": "rewritten", "note": "",
                                           "updated": False}]  # fmt: skip
    doc_review.add_move("README.md", "old results", "model", "nowhere")
    plan = client.get("/api/s/doc-tab").json()["docs"]["moves"]["README.md"]
    assert [r["updated"] for r in plan["list"]] == [False, True]
    seen = {"sections": {"moves:README.md": plan["text"]}}
    assert client.post("/api/s/doc-tab/seen", json=seen).status_code == 200
    plan = client.get("/api/s/doc-tab").json()["docs"]["moves"]["README.md"]
    assert [r["updated"] for r in plan["list"]] == [False, False]
    body = {
        "action": "write-readmes",
        "comments": [{"section": "moves:p2", "quote": "old results", "text": "keep"}],
    }
    b = client.post("/api/s/doc-tab/batch", json=body).json()
    assert b["action"] == "write-readmes" and b["comments"][0]["section"] == "moves:p2"
