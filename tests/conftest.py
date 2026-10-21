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


@pytest.fixture(autouse=True)
def _push_file(tmp_path, monkeypatch):
    """Notices read the test's push file and sessions folder, never the user's home."""
    from view_concept import push

    monkeypatch.setattr(push, "PUSH", tmp_path / "push.json")
    monkeypatch.setattr(push, "SESSIONS", tmp_path / "sessions")


def _git(repo, *args):
    import subprocess

    cmd = ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@t", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def cases_repo(tmp_path):
    """A tiny repo for a workbench's cases: a root README, core/ with a README, core/transcript/
    with none, and one commit; returns (repo, sha)."""
    repo = tmp_path / "audio"
    (repo / "core" / "transcript").mkdir(parents=True)
    (repo / "README.md").write_text("# audio\n\nThe repo.\n")
    (repo / "core" / "README.md").write_text("# core\n\nThe library.\n")
    (repo / "core" / "audio.py").write_text("x = 1\n")
    (repo / "core" / "transcript" / "wer.py").write_text("def wer(): ...\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    return repo, _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def workbench(tmp_path, cases_repo):
    """A tune-readme session whose repo holds the skill file, its cases' repo set."""
    checkout = tmp_path / "view-concept"
    (checkout / "skills" / "write-readme").mkdir(parents=True)
    (checkout / "skills" / "write-readme" / "SKILL.md").write_text("# write-readme\n\nRule 1.\n")
    s = Session("bench", tmp_path / "sessions")
    s.create("Bench", kind="code", repo=str(checkout), workflow="tune-readme")
    s.set_cases(str(cases_repo[0]), "HEAD")
    return s
