import json

import pytest
from fastapi.testclient import TestClient

from explain_view import server
from explain_view.store import Session


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
