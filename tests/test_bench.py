import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

from view_concept import bench, server
from view_concept.store import Session, SessionError

# Stands in for a run's agent (the command backend): reads the prompt, writes the README of
# the folder it names, prints a run report. The environment makes it misbehave.
FAKE_RUN = """\
import os, re, sys, time
prompt = sys.stdin.read()
skill = re.search(r"Read the skill file (\\S+) and", prompt).group(1)
folder = re.search(r"the folder (.*?) \\(the repository root", prompt).group(1)
if os.environ.get("BENCH_FAIL"):
    print("it broke")
    sys.exit(2)
if os.environ.get("BENCH_SILENT"):
    sys.exit(0)
if os.environ.get("BENCH_SLOW"):
    while not os.path.exists(os.environ["BENCH_SLOW"]):
        time.sleep(0.05)
readme = os.path.join(folder, "README.md") if folder else "README.md"
had = os.path.exists(readme)
with open(readme, "w") as f:
    f.write(f"# rewritten\\n\\nfrom {skill}, had a README: {had}\\n")
if os.environ.get("BENCH_STRAY"):
    open("notes.txt", "w").write("stray\\n")
    os.remove("core/audio.py")
print("write-readme · report")
print(f"cwd has .git: {os.path.exists('.git')}")
"""


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    script = tmp_path / "fake-run"
    script.write_text(f"#!{sys.executable}\n{FAKE_RUN}")
    script.chmod(0o755)
    for name in ("BENCH_FAIL", "BENCH_SILENT", "BENCH_SLOW", "BENCH_STRAY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    return script


@pytest.fixture
def client(workbench, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, workbench.dir.parent))
    return TestClient(server.app)


def wait_done(s, *cases):
    for _ in range(200):
        if not any(bench.is_running(s, c) for c in cases):
            return
        time.sleep(0.05)
    raise AssertionError("still running")


def skill(s):
    return s.skill_file()


def test_a_skill_version_is_numbered_by_its_text(workbench):
    s = workbench
    assert bench.current_version(s) is None
    k, path = bench.copy_skill(s)
    assert (k, path.name) == (1, "v1.md") and path.read_text() == "# write-readme\n\nRule 1.\n"
    assert bench.copy_skill(s)[0] == 1 and bench.current_version(s) == 1
    skill(s).write_text("# write-readme\n\nRule 2.\n")
    assert bench.current_version(s) is None
    assert bench.copy_skill(s)[0] == 2
    skill(s).write_text("# write-readme\n\nRule 1.\n")  # back to v1's text: still a new one
    assert bench.copy_skill(s)[0] == 3
    assert list(bench.versions(s)) == [1, 2, 3]


def test_the_throwaway_checkout_has_no_history_and_no_draft_readme(workbench, cases_repo):
    repo, sha = cases_repo
    edit = bench.make_checkout(repo, sha, {"folder": "core", "kind": "edit"})
    draft = bench.make_checkout(repo, sha, {"folder": "core", "kind": "draft"})
    try:
        assert (edit / "core" / "README.md").is_file() and not (edit / ".git").exists()
        assert not (draft / "core" / "README.md").exists()
        assert (draft / "core" / "audio.py").is_file() and (draft / "README.md").is_file()
        assert edit.name.startswith("vc-run-")
    finally:
        for d in (edit, draft):
            import shutil

            shutil.rmtree(d)


def test_other_files_leave_the_readme_out():
    before = {"README.md": "a", "core/README.md": "b", "core/x.py": "c"}
    after = {"README.md": "a", "core/README.md": "B", "notes.txt": "d"}
    assert bench.other_files(before, after, "core/README.md") == ["core/x.py", "notes.txt"]


def test_the_prompt_names_the_skill_version_and_the_folder(tmp_path):
    text = bench.prompt(tmp_path / "v2.md", "core/transcript")
    assert f"Read the skill file {tmp_path / 'v2.md'} and follow it" in text
    assert "the README of the folder core/transcript (the repository root when empty)" in text


def test_a_run_keeps_its_readme_report_and_skill_version(client, workbench, fake_run):
    s = workbench
    s.add_case("core", "edit")
    s.add_case("core", "draft")
    r = client.post("/api/s/bench/runs", json={"case": "core"})
    assert r.status_code == 200 and r.json() == {"started": [{"case": "core", "n": 1}]}
    wait_done(s, "core")
    state = client.get("/api/s/bench").json()["bench"]
    core = state["cases"][0]
    assert (core["id"], core["name"], core["running"], core["error"]) == ("core", "core/", False,
                                                                          None)  # fmt: skip
    assert core["pinned"]["md"] == "# core\n\nThe library.\n"
    run = core["runs"][0]
    assert (run["n"], run["skill_version"], run["state"], run["other_files"]) == (1, 1, "done", [])
    assert run["agent"] == "command" and run["started"] and run["ended"]
    assert str(s.skill_versions_dir / "v1.md") in run["readme"]["md"]
    assert "had a README: True" in run["readme"]["md"]
    assert run["report"]["md"] == "write-readme · report\ncwd has .git: False\n"
    assert state["versions"] == 1 and state["skill"]["version"] == 1
    assert state["skill"]["path"] == "skills/write-readme/SKILL.md" and state["skill"]["exists"]
    assert state["short"] == state["commit"][:7]
    # « Run all »: one run per case, the draft's README removed from its checkout.
    r = client.post("/api/s/bench/runs", json={"case": ""})
    assert sorted(x["case"] for x in r.json()["started"]) == ["core", "core-draft"]
    wait_done(s, "core", "core-draft")
    cases = client.get("/api/s/bench").json()["bench"]["cases"]
    assert [x["n"] for x in cases[0]["runs"]] == [1, 2]
    assert "had a README: False" in cases[1]["runs"][0]["readme"]["md"]
    assert cases[1]["name"] == "core/ (draft)"


def test_a_run_writing_another_file_is_flagged(client, workbench, fake_run, monkeypatch):
    s = workbench
    s.add_case("core", "edit")
    monkeypatch.setenv("BENCH_STRAY", "1")
    client.post("/api/s/bench/runs", json={"case": "core"})
    wait_done(s, "core")
    run = client.get("/api/s/bench").json()["bench"]["cases"][0]["runs"][0]
    assert run["other_files"] == ["core/audio.py", "notes.txt"]
    assert (s.run_dir("core", 1) / "files" / "notes.txt").read_text() == "stray\n"
    assert not (s.run_dir("core", 1) / "files" / "core" / "audio.py").exists()


def test_a_failed_run_leaves_its_error_and_no_run(client, workbench, fake_run, monkeypatch):
    s = workbench
    s.add_case("core", "edit")
    monkeypatch.setenv("BENCH_FAIL", "1")
    client.post("/api/s/bench/runs", json={"case": "core"})
    wait_done(s, "core")
    core = client.get("/api/s/bench").json()["bench"]["cases"][0]
    assert core["runs"] == [] and core["error"] == "it broke"
    assert not s.run_dir("core", 1).exists()
    monkeypatch.delenv("BENCH_FAIL")
    monkeypatch.setenv("BENCH_SILENT", "1")
    client.post("/api/s/bench/runs", json={"case": "core"})
    wait_done(s, "core")
    assert "without a run report" in client.get("/api/s/bench").json()["bench"]["cases"][0]["error"]
    monkeypatch.delenv("BENCH_SILENT")
    client.post("/api/s/bench/runs", json={"case": "core"})
    wait_done(s, "core")
    core = client.get("/api/s/bench").json()["bench"]["cases"][0]
    assert core["error"] is None and [r["n"] for r in core["runs"]] == [1]


def test_a_run_on_jazz_is_refused_with_an_error_on_the_case(client, workbench, monkeypatch):
    s = workbench
    s.add_case("core", "edit")
    s.add_case("core/transcript", "draft")
    monkeypatch.delenv("VIEW_CONCEPT_AGENT_COMMAND", raising=False)
    monkeypatch.delenv("VIEW_CONCEPT_AGENT", raising=False)
    s.bind_agent("jazz", name="writer")
    r = client.post("/api/s/bench/runs", json={"case": ""})
    assert r.status_code == 200 and r.json()["started"] == []
    cases = client.get("/api/s/bench").json()["bench"]["cases"]
    assert all(c["runs"] == [] and "do not start on Jazz" in c["error"] for c in cases)
    assert bench.current_version(s) is None  # no skill version copied for no run


def test_a_running_case_is_not_started_again(client, workbench, fake_run, monkeypatch, tmp_path):
    s = workbench
    s.add_case("core", "edit")
    s.add_case("", "edit")
    go = tmp_path / "go"
    monkeypatch.setenv("BENCH_SLOW", str(go))
    assert client.post("/api/s/bench/runs", json={"case": "core"}).status_code == 200
    try:
        core = client.get("/api/s/bench").json()["bench"]["cases"][0]
        assert core["running"] and core["runs"][0]["state"] == "running"
        assert core["runs"][0]["readme"] is None and core["runs"][0]["report"] is None
        r = client.post("/api/s/bench/runs", json={"case": "core"})
        assert r.status_code == 400 and "running already" in r.json()["detail"]
        r = client.post("/api/s/bench/runs", json={"case": ""})
        assert r.json()["started"] == [{"case": "root", "n": 1}]
    finally:
        go.write_text("")
        wait_done(s, "core", "root")


def test_a_run_cut_off_by_a_restart_reads_as_interrupted(client, workbench):
    s = workbench
    s.add_case("core", "edit")
    folder = s.run_dir("core", 1)
    folder.mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"case": "core", "n": 1, "state": "running"}))
    core = client.get("/api/s/bench").json()["bench"]["cases"][0]
    assert core["runs"] == [] and core["error"] == "interrupted"


def test_runs_need_a_case_set(client, workbench):
    r = client.post("/api/s/bench/runs", json={"case": ""})
    assert r.status_code == 400 and "no case set" in r.json()["detail"]
    workbench.add_case("core", "edit")
    assert client.post("/api/s/bench/runs", json={"case": "deploy"}).status_code == 400


def test_bench_is_null_outside_a_workbench(session, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, session.dir.parent))
    assert TestClient(server.app).get("/api/s/kv-cache").json()["bench"] is None


def test_a_run_changes_the_signature(workbench, cases_repo):
    s = workbench
    before = s.signature()
    s.add_case("core", "edit")
    after = s.signature()
    assert after != before
    s.run_dir("core", 1).mkdir(parents=True)
    (s.run_dir("core", 1) / "run.json").write_text("{}")
    assert s.signature() != after
    with pytest.raises(SessionError):
        s.case_runs_dir("../x")
    assert os.path.basename(str(s.skill_file())) == "SKILL.md"


def test_a_run_is_a_blank_conversation_that_writes_in_its_checkout_only(monkeypatch):
    from view_concept.agents import ClaudeBackend, CodexBackend, TurnState

    monkeypatch.delenv("VIEW_CONCEPT_CLAUDE", raising=False)
    monkeypatch.delenv("VIEW_CONCEPT_CODEX", raising=False)
    args = ClaudeBackend().run_args()
    assert args[:2] == ["claude", "-p"] and "--resume" not in args and "--add-dir" not in args
    assert args[args.index("--setting-sources") + 1] == "project"
    assert "Write(./**)" in args and "Edit(./**)" in args and "Write" in args
    # No shell: a prefix rule like `find:*` would also let `find -delete` through.
    assert "Bash" not in args and not any(a.startswith("Bash(") for a in args)
    turn = TurnState()
    ClaudeBackend().run_feed(json.dumps({"type": "result", "result": "the report"}), turn)
    assert turn.finished and turn.final_text == "the report"
    args = CodexBackend().run_args()
    assert args[:2] == ["codex", "exec"] and "fork" not in args and "resume" not in args
    assert 'sandbox_mode="workspace-write"' in args and args[-1] == "-"
    # /tmp and $TMPDIR hold the other checkouts: a Codex run may not write there.
    assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in args
    assert "sandbox_workspace_write.exclude_slash_tmp=true" in args
    turn = TurnState()
    for event in (
        {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "last"}},
        {"type": "turn.completed"},
    ):
        CodexBackend().run_feed(json.dumps(event), turn)
    CodexBackend().run_close(turn, 0)
    assert not turn.failed and turn.final_text == "last"
