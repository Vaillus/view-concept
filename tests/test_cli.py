import json
import os
import subprocess
import sys
import time


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


def start_watch(home, slug):
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(home)}
    cmd = [sys.executable, "-m", "view_concept.cli", "watch", slug]
    return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_watch_prints_nothing_when_it_starts(tmp_path):
    assert view_concept(tmp_path, "new", "Quiet").returncode == 0
    proc = start_watch(tmp_path, "quiet")
    time.sleep(1.5)
    proc.terminate()
    out, _ = proc.communicate(timeout=5)
    assert out == ""


def test_watch_writes_its_heartbeat(tmp_path):
    assert view_concept(tmp_path, "new", "Beat").returncode == 0
    proc = start_watch(tmp_path, "beat")
    try:
        heartbeat = tmp_path / "sessions" / "beat" / "watch.json"
        for _ in range(50):
            if heartbeat.exists():
                break
            time.sleep(0.1)
        assert json.loads(heartbeat.read_text())["pid"] == proc.pid
    finally:
        proc.terminate()
        proc.communicate(timeout=5)
