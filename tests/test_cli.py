import json
import os
import subprocess
import sys
import time

from view_concept.store import Session


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


def test_question_prints_its_id(tmp_path):
    assert view_concept(tmp_path, "new", "Ask").returncode == 0
    r = view_concept(
        tmp_path, "question", "ask", "PR or merge?", "--option", "PR", "--option", "merge"
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "q1"
    assert "no watch is running" in r.stderr
    d = tmp_path / "sessions" / "ask"
    (q,) = json.loads((d / "questions.json").read_text())
    assert q["options"] == ["PR", "merge"] and q["multi"] is False
    assert json.loads((d / "status.json").read_text())["phase"] == "awaiting-answer"
    Session("ask", root=tmp_path / "sessions").write_heartbeat()
    r = view_concept(tmp_path, "question", "ask", "Which files?", "--multi")
    assert r.stdout.strip() == "q2"
    assert r.stderr == ""
    assert view_concept(tmp_path, "question", "nope", "Hm?").returncode != 0
    assert not (tmp_path / "sessions" / "nope").exists()


def test_check_prints_and_writes_problems(tmp_path):
    assert view_concept(tmp_path, "new", "KKT").returncode == 0
    d = tmp_path / "sessions" / "kkt"
    plan = json.loads((d / "plan.json").read_text())
    plan["outline"] = [{"id": "s1", "title": "Intro"}, {"id": "s2", "title": "Convexity"}]
    plan["lexicon"] = [
        {"term": "KKT conditions", "section": "s1", "definition": "d",
         "tip": "Holds for a convex problem."},
        {"term": "convex problem", "section": "s2", "definition": "d"},
    ]  # fmt: skip
    (d / "plan.json").write_text(json.dumps(plan))
    (d / "sections" / "s1.md").write_text("Take a convex problem.")
    r = view_concept(tmp_path, "check", "kkt")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [
        "forward  KKT conditions (1)  tip uses «convex problem» (2)",
        "early    convex problem (2)  used in section 1",
        "2 problems written to audit.json",
    ]
    assert [a["issue"] for a in json.loads((d / "audit.json").read_text())] == ["forward", "early"]
    assert view_concept(tmp_path, "check", "nope").returncode != 0
