import json

import pytest

from view_concept.store import Session


@pytest.fixture
def session(tmp_path):
    s = Session("kv-cache", tmp_path)
    s.create("Le KV cache", "explique le KV cache")
    plan = s.read_plan()
    plan["outline"] = [{"id": "s1", "title": "Attention"}, {"id": "s2", "title": "Cache"}]
    plan["lexicon"] = [{"term": "clé | key", "section": "s1", "definition": "vecteur"}]
    s.plan_path.write_text(json.dumps(plan))
    (s.sections_dir / "s2.md").write_text("Le cache.")
    (s.sections_dir / "s1.md").write_text("L'attention.")
    return s


@pytest.fixture(autouse=True)
def _launches_file(tmp_path, monkeypatch):
    """Pending launches go to a file of the test, never to the user's home."""
    from view_concept import launch

    monkeypatch.setattr(launch, "LAUNCHES", tmp_path / "launches.json")
