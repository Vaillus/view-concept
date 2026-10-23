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
        "--workflow", "triage-code",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    plan = json.loads((tmp_path / "sessions" / "triage" / "plan.json").read_text())
    assert plan["workflow"] == "triage-code"


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


def test_check_prints_section_problems_only(tmp_path):
    assert view_concept(tmp_path, "new", "Coraux").returncode == 0
    d = tmp_path / "sessions" / "coraux"
    plan = json.loads((d / "plan.json").read_text())
    plan["outline"] = [{"id": "s1", "title": "Gènes"}, {"id": "adn", "title": "ADN"}]
    (d / "plan.json").write_text(json.dumps(plan))
    (d / "sections" / "s1.md").write_text(
        "Le <b>seuil</b> est bas.\n\n"
        '<div class="cf"><svg></svg>\n</div>\n\n'
        "<!-- a note -->\n\n"
        '```mermaid\nflowchart LR\n  A["a<br/>b"]\n```\n\n'
        "```html\n<div>code</div>\n```\n"
    )
    (d / "sections" / "adn.md").write_text("Old.")
    (d / "sections" / "adn.html").write_text("<p>" + "x" * (2 * 2**20) + "</p>")
    r = view_concept(tmp_path, "check", "coraux")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [
        "0 problems written to audit.json",
        'html-block §1 (s1)  s1.md:3 <div class="cf"><svg></svg>  move this HTML block into an'
        " HTML section",
        "too-large  §2 (adn)  adn.html is 2.0 MB, over 2 MB: move its media to the media"
        " folder sections/adn/ or the web",
        "two-files  §2 (adn)  adn.md and adn.html both present: the page shows adn.html, adn.md"
        " is ignored",
        "3 section problems, printed only (not in audit.json)",
    ]
    assert json.loads((d / "audit.json").read_text()) == []


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
    delivered = Session("pair", tmp_path / "sessions").read_deliveries()
    assert list(delivered) == ["b1", "b2"] and delivered["b1"] <= delivered["b2"]


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


def test_implemented_records_and_reports_what_the_code_carries(tmp_path):
    r = view_concept(
        tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path),
        "--workflow", "build-feature",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    for change in ("gate split", "threshold renamed"):
        view_concept(tmp_path, "change", "gate", change)
    assert view_concept(tmp_path, "implemented", "gate", "m1").stdout.strip() == (
        "implemented through m1"
    )
    assert view_concept(tmp_path, "implemented", "gate").stdout.splitlines() == [
        "implemented through m1",
        "not implemented yet: m2",
    ]
    r = view_concept(tmp_path, "implemented", "gate", "m9")
    assert r.returncode != 0 and "no change 'm9'" in r.stderr


def test_pr_records_the_link_in_the_plan(tmp_path):
    r = view_concept(
        tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path),
        "--workflow", "build-feature",
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    url = "https://github.com/o/r/pull/42"
    assert view_concept(tmp_path, "pr", "gate", url).stdout.strip() == f"PR recorded: {url}"
    plan = Session("gate", tmp_path / "sessions").read_plan()
    assert plan["pr"]["url"] == url and plan["pr"]["at"] and plan["title"] == "Gate"
    r = view_concept(tmp_path, "pr", "gate", "42")
    assert r.returncode != 0 and "not a link" in r.stderr


def test_request_writes_the_transcript_from_a_file_or_stdin(tmp_path):
    assert view_concept(tmp_path, "new", "Gate").returncode == 0
    source = tmp_path / "transcript.md"
    source.write_text("## User\nrework the gate\n")
    r = view_concept(tmp_path, "request", "gate", str(source))
    assert r.returncode == 0, r.stderr
    request = tmp_path / "sessions" / "gate" / "request.md"
    assert request.read_text() == "## User\nrework the gate\n"
    env = {**os.environ, "VIEW_CONCEPT_HOME": str(tmp_path)}
    cmd = [sys.executable, "-m", "view_concept.cli", "request", "gate", "-"]
    r = subprocess.run(cmd, env=env, input="## Agent\nreplaced\n", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert request.read_text() == "## Agent\nreplaced\n"
    assert view_concept(tmp_path, "request", "nope", str(source)).returncode != 0


def test_status_takes_a_run_set_and_a_scoping_done_mark(tmp_path):
    s = Session("demo", tmp_path / "sessions")
    s.create("Demo", "explain")
    s.write_plan([{"id": "a", "title": "A"}, {"id": "b", "title": "B"}], [])
    r = view_concept(tmp_path, "status", "demo", "writing", "--section", "b", "--section", "a")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["writing", "b", "a"]
    start = s.read_status()["run"]["start"]
    view_concept(tmp_path, "status", "demo", "writing", "--section", "c")
    assert s.read_status()["run"] == {"start": start, "set": ["b", "a", "c"]}
    assert view_concept(tmp_path, "status", "demo", "scoping", "--done").returncode == 0
    assert s.read_status()["done"] is True
    assert view_concept(tmp_path, "status", "demo", "writing", "--done").returncode != 0


def test_variant_names_the_setup_and_a_model_per_role(tmp_path):
    assert view_concept(tmp_path, "new", "Speed").returncode == 0
    r = view_concept(tmp_path, "variant", "speed")
    assert r.returncode == 0 and r.stdout.strip() == "variant: none · no model per role"
    r = view_concept(tmp_path, "variant", "speed", "writer on sonnet", "--model", "writer=sonnet")
    assert r.returncode == 0 and "writer=sonnet" in r.stdout
    plan = json.loads((tmp_path / "sessions" / "speed" / "plan.json").read_text())
    assert plan["variant"] == {"name": "writer on sonnet", "models": {"writer": "sonnet"}}
    r = view_concept(tmp_path, "variant", "speed", "odd", "--model", "helper=haiku")
    assert r.returncode == 1 and "unknown role helper" in r.stderr
    r = view_concept(tmp_path, "variant", "speed", "odd", "--model", "writer")
    assert r.returncode == 1 and "role=model" in r.stderr


def test_doc_set_adds_removes_and_prints_the_docs(tmp_path):
    r = view_concept(tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path))
    assert r.returncode == 0, r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "add", "docs/reference.md", "the tabs")
    assert r.returncode == 0 and r.stdout.strip() == "added docs/reference.md", r.stderr
    assert view_concept(tmp_path, "doc-set", "gate", "add", "README.md", "install").returncode == 0
    r = view_concept(tmp_path, "doc-set", "gate", "remove", "README.md", "--user")
    assert r.returncode == 0, r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "add", "README.md", "install")
    assert r.returncode == 1 and "removed by the user" in r.stderr
    r = view_concept(tmp_path, "doc-set", "gate")
    assert r.stdout.splitlines() == [
        "docs/reference.md — the tabs",
        "removed by the user: README.md",
    ]
    r = view_concept(tmp_path, "doc-set", "gate", "add", "../x.md", "out")
    assert r.returncode == 1 and "inside the repo" in r.stderr


def test_doc_set_classes_minor_docs_records_indicators_and_orders(tmp_path):
    r = view_concept(tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path))
    assert r.returncode == 0, r.stderr
    for path in ("README.md", "docs/reference.md"):
        assert view_concept(tmp_path, "doc-set", "gate", "add", path, "why").returncode == 0
    minor = ("minor", "docs/reference.md", "a name in a list", "--added", "1", "--removed", "1")
    r = view_concept(tmp_path, "doc-set", "gate", *minor)
    assert r.returncode == 0, r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "failing", "README.md", "3", "6", "--structure")
    assert r.returncode == 0, r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "order", "docs/reference.md", "README.md")
    assert r.stdout.splitlines() == [
        "docs/reference.md — why · minor: a name in a list (+1 −1)",
        "README.md — why · 3/6 failing, structure fails",
    ]
    assert view_concept(tmp_path, "doc-set", "gate", "major", "docs/reference.md").returncode == 0
    r = view_concept(tmp_path, "doc-set", "gate", "failing", "README.md", "--clear")
    assert r.returncode == 0, r.stderr
    r = view_concept(tmp_path, "doc-set", "gate")
    assert r.stdout.splitlines() == ["docs/reference.md — why", "README.md — why"]
    r = view_concept(tmp_path, "doc-set", "gate", "minor", "README.md", "why")
    assert r.returncode == 1 and "--added N --removed N" in r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "order", "README.md")
    assert r.returncode == 1 and "missing: docs/reference.md" in r.stderr
    r = view_concept(tmp_path, "doc-set", "gate", "failing", "README.md", "x", "6")
    assert r.returncode == 1 and "whole number" in r.stderr


def test_facts_records_marks_prints_and_clears_missing_facts(tmp_path):
    r = view_concept(tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert view_concept(tmp_path, "doc-set", "gate", "add", "README.md", "why").returncode == 0
    assert view_concept(tmp_path, "facts", "gate").stdout.strip() == "(no missing fact)"
    add = ("add", "README.md", "Run serve.", "--propose", "leave", "--reason", "the code")
    r = view_concept(tmp_path, "facts", "gate", *add, "--passage", "4")
    assert r.returncode == 0 and r.stdout.strip() == "f1", r.stderr
    r = view_concept(tmp_path, "facts", "gate", "mark", "f1", "left")
    assert r.returncode == 0 and r.stdout.strip() == "f1 left", r.stderr
    assert view_concept(tmp_path, "facts", "gate").stdout.splitlines() == [
        "README.md · 1 missing facts",
        "  f1 [left] « Run serve. » (passage 4) · propose leave: the code",
    ]
    r = view_concept(tmp_path, "facts", "gate", "add", "README.md", "x", "--propose", "keep")
    assert r.returncode == 1 and "--propose keep|leave" in r.stderr
    r = view_concept(tmp_path, "facts", "gate", "clear", "README.md")
    assert r.stdout.strip() == "cleared 1 missing facts of README.md"


def test_stale_flags_prints_and_drops_passages(tmp_path):
    (tmp_path / "README.md").write_text("The keys 1 to 4.\n")
    r = view_concept(tmp_path, "new", "Gate", "--kind", "code", "--repo", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert view_concept(tmp_path, "doc-set", "gate", "add", "README.md", "keys").returncode == 0
    flag = ("README.md", "keys 1 to 4", "five", "--section", "s")
    r = view_concept(tmp_path, "stale", "gate", *flag)
    assert r.returncode == 0 and r.stdout.strip() == "s1", r.stderr
    r = view_concept(tmp_path, "stale", "gate")
    assert r.stdout.strip() == "s1 README.md « keys 1 to 4 » (section s): five"
    assert view_concept(tmp_path, "stale", "gate", "--drop", "s1").returncode == 0
    assert view_concept(tmp_path, "stale", "gate").stdout.strip() == "(no stale passage shown)"
    r = view_concept(tmp_path, "stale", "gate", "README.md", "absent", "five")
    assert r.returncode == 1 and "quote is not in" in r.stderr


def test_reference_sets_prints_and_clears_the_reference_model(tmp_path):
    for title, workflow in (("Gate", "build-feature"), ("Docs", "review-docs")):
        args = ("new", title, "--kind", "code", "--repo", str(tmp_path), "--workflow", workflow)
        assert view_concept(tmp_path, *args).returncode == 0
    r = view_concept(tmp_path, "reference", "docs", "--candidates")
    assert r.returncode == 0 and r.stdout.splitlines()[0].startswith("gate · Gate · updated ")
    r = view_concept(tmp_path, "reference", "docs", "gate")
    assert r.returncode == 1 and "needs its reason" in r.stderr
    r = view_concept(tmp_path, "reference", "docs", "gate", "--reason", "adds a skill")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "reference model: gate — adds a skill"
    r = view_concept(tmp_path, "reference", "docs")
    assert r.stdout.strip() == "reference model: gate (Gate) — adds a skill"
    assert view_concept(tmp_path, "reference", "docs", "--clear").returncode == 0
    assert view_concept(tmp_path, "reference", "docs").stdout.strip() == "no reference model"
    r = view_concept(tmp_path, "reference", "docs", "nope", "--reason", "x")
    assert r.returncode == 1 and "no other session" in r.stderr
    r = view_concept(tmp_path, "reference", "docs", "gate", "--clear")
    assert r.returncode == 1 and "one at a time" in r.stderr
