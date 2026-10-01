import json

import pytest
from fastapi.testclient import TestClient

from view_concept import server
from view_concept.store import Session


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
    session.bind_parent("main-1")
    r = client.get("/api/s/kv-cache/threads").json()
    assert r["forkable"] and r["threads"][0]["id"] == "t1"
    assert client.post("/api/s/kv-cache/threads/x1", json={"text": "hi"}).status_code == 400
    assert client.delete("/api/s/kv-cache/threads/t1").status_code == 200
    assert client.delete("/api/s/kv-cache/threads/t1").status_code == 400


def test_api_keeps_the_part_of_an_outline_item(client, session):
    plan = session.read_plan()
    plan["outline"].append({"id": "s9", "title": "Cards", "part": 2})
    session.plan_path.write_text(json.dumps(plan))
    outline = client.get("/api/s/kv-cache").json()["plan"]["outline"]
    assert outline[-1]["part"] == 2


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
