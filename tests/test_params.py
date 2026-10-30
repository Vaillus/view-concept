import json

import pytest
from fastapi.testclient import TestClient

from view_concept import server
from view_concept.context import build
from view_concept.store import Session, SessionError

ROW = {"concepts": [{"name": "vector", "gloss": "An ordered list of numbers."}]}


@pytest.fixture
def drawing(session):
    plan = session.read_plan()
    plan["outline"].insert(0, {"id": "scoping", "title": "Scoping", "part": "scoping"})
    session.plan_path.write_text(json.dumps(plan))
    (session.sections_dir / "scoping.html").write_text('<p id="e1">self-attention</p>')
    return session


def test_the_parameters_file_keeps_what_a_section_saved_and_received(drawing):
    assert drawing.read_params() == {}
    assert drawing.section_params("scoping") == {"saved": {}, "received": {}}
    drawing.save_params("scoping", {"answers": {"dot product": "yes"}})
    drawing.set_received("scoping", "dot product", ROW)
    drawing.save_params("scoping", {"answers": {"dot product": "quickly"}})
    saved = {"answers": {"dot product": "quickly"}}
    assert drawing.read_params() == {"scoping": {"saved": saved, "received": {"dot product": ROW}}}
    with pytest.raises(SessionError, match="no HTML section 's1'"):
        drawing.save_params("s1", {})
    with pytest.raises(SessionError, match="saves an object"):
        drawing.save_params("scoping", [1])


def test_the_scoper_planner_and_writer_read_the_parameters(drawing):
    assert "## Parameters" not in build(drawing, "writer")
    drawing.save_params("scoping", {"answers": {"softmax": "no"}})
    for role in ("scoper", "planner", "writer"):
        assert '"softmax": "no"' in build(drawing, role).split("## Parameters\n")[1]
    assert "## Parameters" not in build(drawing, "thread", section="s1")


def test_the_page_reads_and_writes_a_section_s_parameters(drawing, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, drawing.dir.parent))
    client = TestClient(server.app)
    url = "/api/s/kv-cache/params/scoping"
    assert client.get(url).json() == {"saved": {}, "received": {}}
    assert client.put(url, json={"saved": {"focus": ["dot product"]}}).json() == {"ok": True}
    assert client.get(url).json()["saved"] == {"focus": ["dot product"]}
    assert client.get("/api/s/kv-cache/params/s1").status_code == 400
    assert client.put(url, json={"saved": []}).status_code == 422


def test_an_answer_received_after_publishing_marks_the_page_out_of_date(drawing, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, drawing.dir.parent))
    client = TestClient(server.app)
    assert client.get("/api/s/kv-cache/published").json() == {"published": None}
    # A report section that uses the channel: the drawing itself is not published.
    (drawing.sections_dir / "s1.md").unlink()
    (drawing.sections_dir / "s1.html").write_text("<p>a tree of self-attention</p>")
    drawing.write_published("https://example.org/kv-cache/", drawing.fingerprint())
    page, params = drawing.signature(), drawing.params_signature()
    drawing.set_received("s1", "dot product", ROW)
    # The page is not re-rendered, but the stream's params event has the publish record
    # reloaded, and it now asks for a republish.
    assert drawing.signature() == page and drawing.params_signature() != params
    assert client.get("/api/s/kv-cache/published").json()["published"]["out_of_date"] is True
