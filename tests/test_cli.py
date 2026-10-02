import json
import os
import subprocess
import sys


def view_concept(home, *args):
    """Run the command line against a session store in `home`."""
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(home)}
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    cmd = [sys.executable, "-m", "view_concept.cli", *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_new_stores_the_workflow(tmp_path):
    r = view_concept(
        tmp_path, "new", "Triage", "--kind", "code", "--repo", str(tmp_path),
        "--workflow", "view-refactor",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    plan = json.loads((tmp_path / "sessions" / "triage" / "plan.json").read_text())
    assert plan["workflow"] == "view-refactor"


def test_new_rejects_an_unknown_workflow(tmp_path):
    r = view_concept(tmp_path, "new", "Triage", "--workflow", "view-pr")
    assert r.returncode != 0 and "invalid choice" in r.stderr
    assert not (tmp_path / "sessions" / "triage").exists()
