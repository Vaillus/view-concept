import json
import os
import subprocess
import sys
import time

from view_concept.store import Session


def view_concept(home, *args):
    """Run the command line against a session store in `home`."""
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(home)}
    for name in (
        "CLAUDE_CODE_SESSION_ID",
        "CODEX_THREAD_ID",
        "JAZZ_AGENT_PROCESS",
        "VIEW_CONCEPT_AGENT",
    ):
        env.pop(name, None)
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
    assert "no watch or wait is running" in r.stderr
    d = tmp_path / "sessions" / "ask"
    (q,) = json.loads((d / "questions.json").read_text())
    assert q["options"] == ["PR", "merge"] and q["multi"] is False
    assert json.loads((d / "status.json").read_text())["phase"] == "awaiting-answer"
    Session("ask", root=tmp_path / "sessions").write_heartbeat()
    r = view_concept(tmp_path, "question", "ask", "Which files?", "--multi")
    assert r.stdout.strip() == "q2"
    assert r.stderr == ""
    r = view_concept(tmp_path, "question", "ask", "Squash?", "--recommended", "yes")
    assert r.stdout.strip() == "q3"
    assert json.loads((d / "questions.json").read_text())[2]["recommended"] == "yes"
    assert view_concept(tmp_path, "question", "nope", "Hm?").returncode != 0
    assert not (tmp_path / "sessions" / "nope").exists()


def test_answered_marks_a_question_answered_in_the_terminal(tmp_path):
    assert view_concept(tmp_path, "new", "Ask").returncode == 0
    assert view_concept(tmp_path, "question", "ask", "PR or merge?").returncode == 0
    r = view_concept(tmp_path, "answered", "ask", "q1", "--text", "a PR")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "q1 answered"
    d = tmp_path / "sessions" / "ask"
    (q,) = json.loads((d / "questions.json").read_text())
    assert q["status"] == "answered"
    assert q["answer"]["text"] == "a PR" and q["answer"]["from"] == "terminal"
    assert not (d / "inbox.jsonl").exists()
    r = view_concept(tmp_path, "answered", "ask", "q1")
    assert r.returncode != 0 and "already answered" in r.stderr
    assert view_concept(tmp_path, "answered", "ask", "q2").returncode != 0
    assert view_concept(tmp_path, "answered", "nope", "q1").returncode != 0


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


def start_wait(home, slug, *flags):
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(home)}
    cmd = [sys.executable, "-m", "view_concept.cli", "wait", slug, *flags]
    return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_wait_times_out_with_code_3_and_no_output(tmp_path):
    assert view_concept(tmp_path, "new", "Idle").returncode == 0
    r = view_concept(tmp_path, "wait", "idle", "--timeout", "1")
    assert r.returncode == 3 and r.stdout == ""


def test_wait_delivers_one_batch_per_call(tmp_path):
    assert view_concept(tmp_path, "new", "Pair").returncode == 0
    inbox = tmp_path / "sessions" / "pair" / "inbox.jsonl"
    for number, text in enumerate(["first", "second"], start=1):
        batch = {
            "id": f"b{number}",
            "at": "now",
            "comments": [{"id": f"c{number}", "section": "s1", "quote": "", "text": text}],
        }
        with inbox.open("a") as handle:
            handle.write(json.dumps(batch) + "\n")
    first = view_concept(tmp_path, "wait", "pair", "--timeout", "5")
    assert first.returncode == 0 and "first" in first.stdout and "second" not in first.stdout
    second = view_concept(tmp_path, "wait", "pair", "--timeout", "5")
    assert second.returncode == 0 and "second" in second.stdout and "first" not in second.stdout
    assert view_concept(tmp_path, "wait", "pair", "--timeout", "1").returncode == 3


def test_wait_writes_its_heartbeat(tmp_path):
    assert view_concept(tmp_path, "new", "Beat wait").returncode == 0
    proc = start_wait(tmp_path, "beat-wait", "--timeout", "3")
    try:
        heartbeat = tmp_path / "sessions" / "beat-wait" / "watch.json"
        for _ in range(50):
            if heartbeat.exists():
                break
            time.sleep(0.1)
        assert json.loads(heartbeat.read_text())["pid"] == proc.pid
    finally:
        proc.terminate()
        proc.communicate(timeout=5)


def test_new_records_the_agent_passed_by_flag(tmp_path):
    r = view_concept(tmp_path, "new", "Flagged", "--agent", "jazz", "--agent-name", "writer")
    assert r.returncode == 0, r.stderr
    record = json.loads((tmp_path / "sessions" / "flagged" / "agent.json").read_text())
    assert (record["agent"], record["name"], record["parent"]) == ("jazz", "writer", "")


def test_new_detects_codex_and_its_thread(tmp_path):
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(tmp_path), "CODEX_THREAD_ID": "thr-1"}
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    cmd = [sys.executable, "-m", "view_concept.cli", "new", "Detected"]
    assert subprocess.run(cmd, env=env, capture_output=True, text=True).returncode == 0
    record = json.loads((tmp_path / "sessions" / "detected" / "agent.json").read_text())
    assert (record["agent"], record["parent"]) == ("codex", "thr-1")


def test_a_branch_review_logs_and_prints_its_context(tmp_path):
    repo = str(tmp_path)
    r = view_concept(
        tmp_path,
        "new",
        "Gate",
        "--kind",
        "code",
        "--repo",
        repo,
        "--base",
        "main",
        "--initial-request",
        "rework the gate",
    )
    assert r.returncode == 0, r.stderr
    assert view_concept(tmp_path, "message", "gate", "keep the CLI").stdout.strip() == (
        "tm1 recorded"
    )
    r = view_concept(tmp_path, "change", "gate", "gate split", "--by", "planner", "--cause", "tm1")
    assert r.stdout.strip() == "m1 recorded"
    r = view_concept(tmp_path, "context", "gate", "--role", "planner", "--trigger", "tm1")
    assert r.returncode == 0, r.stderr
    assert "## Initial request\nrework the gate" in r.stdout
    assert "## Trigger\n- tm1 (idle): keep the CLI" in r.stdout
    assert "- m1 by planner: gate split (cause: tm1)" in r.stdout
    assert view_concept(tmp_path, "changes", "gate").stdout.strip() == "- gate split"
    plan = tmp_path / "p.json"
    plan.write_text(json.dumps({"outline": [{"id": "s1", "title": "Today"}]}))
    assert view_concept(tmp_path, "plan", "gate", str(plan)).stdout.strip() == "1 sections, 0 terms"
    saved = json.loads((tmp_path / "sessions" / "gate" / "plan.json").read_text())
    assert saved["initial_request"] == "rework the gate" and saved["base"] == "main"
