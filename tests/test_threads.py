import json
import sys
import time

import pytest

from view_concept import threads
from view_concept.store import Session, SessionError, format_batch

# Stands in for `claude -p`: records its arguments and prompt, then streams a reply.
FAKE = """\
import json, sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "prompt": prompt}) + "\\n")
if "--json-schema" in sys.argv:
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "child-1"}))
    answer = {"choices": ["no", "maybe"], "text": "Drop it, the reads are cheap."}
    print(json.dumps({"type": "result", "is_error": False, "result": json.dumps(answer),
                      "structured_output": answer}))
    sys.exit(0)
if "FAIL" in prompt:
    print(json.dumps({"type": "result", "is_error": True, "result": "boom"}))
    sys.exit(1)
if "SLOW" in prompt:  # like claude, exit 143 on SIGTERM rather than die from it
    import signal, time
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    time.sleep(30)
def ev(e): print(json.dumps({"type": "stream_event", "event": e}), flush=True)
print(json.dumps({"type": "system", "subtype": "init", "session_id": "child-1"}))
ev({"type": "message_start"})
ev({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Short "}})
ev({"type": "content_block_start", "content_block": {"type": "tool_use", "name": "Read"}})
ev({"type": "message_start"})
ev({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "answer."}})
print(json.dumps({"type": "result", "is_error": False, "result": "answer."}))
"""


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    script = tmp_path / "claude"
    script.write_text(f"#!{sys.executable}\n{FAKE}")
    script.chmod(0o755)
    monkeypatch.setenv("VIEW_CONCEPT_CLAUDE", str(script))
    return script


def no_workflow(session):
    """The session as one written before workflows existed: an explanation that is not
    coordinated, whose threads fork the main conversation."""
    plan = session.read_plan()
    del plan["workflow"]
    session.plan_path.write_text(json.dumps(plan))
    return session


def calls(script):
    return [json.loads(line) for line in (script.parent / "claude.calls").read_text().splitlines()]


def wait_idle(session, tid):
    for _ in range(100):
        if not threads.is_running(session, tid):
            return session.read_thread(tid)
        time.sleep(0.05)
    raise AssertionError("thread still running")


def test_first_turn_forks_the_main_session(session, fake_claude):
    no_workflow(session)
    session.bind_agent("claude", "main-1")
    t = threads.create(session, "s2", "Le cache", "", "why a cache?")
    assert t["id"] == "t1" and t["state"] == "running"
    t = wait_idle(session, "t1")
    assert t["state"] == "idle" and t["agent_session"] == "child-1"
    assert t["forked_from"] == "main-1"
    assert [m["role"] for m in t["messages"]] == ["user", "assistant"]
    assert t["messages"][1]["text"] == "Short \n\nanswer."
    reply = t["messages"][1]
    assert reply["at"][:19] <= reply["first_text"][:19] and reply["first_text"] <= reply["ended"]
    (call,) = calls(fake_claude)
    assert call["args"][call["args"].index("--resume") + 1] == "main-1"
    assert "--fork-session" in call["args"]
    tools = call["args"][call["args"].index("--tools") + 1 :]
    assert tools[:6] == ["Read", "Grep", "Glob", "WebSearch", "WebFetch", "Bash"]
    allowed = call["args"][call["args"].index("--allowedTools") + 1 :]
    assert "Bash(git log:*)" in allowed and "Bash(view-concept context:*)" in allowed
    assert "Bash" not in allowed
    assert "§2 Cache (s2): « Le cache »" in call["prompt"]
    assert call["prompt"].endswith("why a cache?")


def test_later_turns_resume_the_thread(session, fake_claude):
    session.bind_agent("claude", "main-1")
    threads.create(session, "", "", "", "first")
    wait_idle(session, "t1")
    threads.send(session, "t1", "-- second")
    t = wait_idle(session, "t1")
    assert len(t["messages"]) == 4
    second = calls(fake_claude)[1]
    assert second["args"][second["args"].index("--resume") + 1] == "child-1"
    assert "--fork-session" not in second["args"]
    assert second["prompt"] == "-- second"  # sent on stdin, never parsed as a flag


def test_without_a_parent_the_thread_starts_fresh(session, fake_claude):
    no_workflow(session)
    threads.create(session, "", "", "", "hello")
    wait_idle(session, "t1")
    (call,) = calls(fake_claude)
    assert "--resume" not in call["args"]
    assert "read plan.json and sections/" in call["prompt"]


def test_error_and_busy(session, fake_claude):
    threads.create(session, "", "", "", "FAIL")
    t = wait_idle(session, "t1")
    assert t["state"] == "error" and t["error"] == "boom"
    threads.create(session, "", "", "", "SLOW")
    with pytest.raises(threads.ThreadBusy):
        threads.send(session, "t2", "again")
    threads.stop(session, "t2")
    t = wait_idle(session, "t2")
    assert t["state"] == "idle" and t["messages"][-1]["stopped"]


def test_interrupted_thread(session):
    t = session.new_thread()
    session.write_thread({**t, "state": "running"})  # left running by a dead server
    assert threads.view(session, session.read_thread("t1"))["error"] == "interrupted"


def test_bind_agent_and_thread_ids(session):
    assert session.read_parent() == ""
    assert session.bind_agent("claude", "a") and not session.bind_agent("claude", "a")
    assert session.bind_agent("claude", "b") and session.read_parent() == "b"
    assert session.conversations() == ["a", "b"]
    assert session.bind_agent("claude", "a") and session.conversations() == ["a", "b"]
    assert [session.new_thread()["id"] for _ in range(2)] == ["t1", "t2"]
    with pytest.raises(SessionError):
        session.read_thread("../plan")


def test_a_thread_from_before_agents_still_resumes(session, fake_claude):
    t = session.new_thread()
    del t["agent_session"]
    session.write_thread({**t, "claude_id": "old"})  # written before agent_session existed
    assert session.read_thread("t1")["agent_session"] == "old"
    threads.send(session, "t1", "again")
    wait_idle(session, "t1")
    args = calls(fake_claude)[-1]["args"]
    assert args[args.index("--resume") + 1] == "old" and "--fork-session" not in args


def test_a_session_from_before_agents_keeps_its_parent(session):
    session.legacy_claude_path.write_text(json.dumps({"parent": "p", "since": "x"}))
    assert session.read_agent() == {"agent": "claude", "parent": "p"}
    assert session.conversations() == ["p"]
    assert session.bind_agent("codex", "q") and session.read_parent() == "q"
    assert session.conversations() == ["p", "q"]


def test_comment_from_a_thread(session):
    b = session.add_batch([{"section": "s1", "text": "rewrite it", "thread": "t3"}])
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "(from side thread t3: threads/t3.json)" in out


def test_comment_from_a_thread_needs_no_text(session):
    b = session.add_batch([{"section": "s1", "thread": "t3"}, {"section": "s2", "text": " "}])
    assert [(c["text"], c["thread"]) for c in b["comments"]] == [("", "t3")]
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "(from side thread t3: threads/t3.json)" in out


def test_a_thread_on_a_missing_fact_keeps_the_fact_up_to_its_comment(session, fake_claude):
    t = threads.create(session, "doc:README.md", "Run serve.", "", "why leave it?", fact="f1")
    assert session.read_thread(t["id"])["fact"] == "f1"
    assert "fact" not in session.new_thread("s1", "Le cache")
    with pytest.raises(SessionError, match="anchored to its README"):
        session.new_thread("s1", "Le cache", fact="f1")
    with pytest.raises(SessionError, match="anchored to its README"):
        session.new_thread("doc:", "x", fact="f1")
    # The comment the thread becomes carries the fact.
    b = session.add_batch([{"section": "doc:README.md", "quote": "Run serve.", "text": "",
                            "thread": t["id"], "fact": "f1"}])  # fmt: skip
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "(doc README.md · fact f1) « Run serve. »" in out


def test_delete_thread(session, fake_claude):
    session.new_thread()
    session.new_thread()
    threads.delete(session, "t1")
    assert [t["id"] for t in session.read_threads()] == ["t2"]
    session.add_batch([{"thread": "t2"}])
    with pytest.raises(SessionError):  # a sent comment points to it
        threads.delete(session, "t2")
    with pytest.raises(SessionError):
        threads.delete(session, "t9")
    threads.create(session, "", "", "", "SLOW")
    with pytest.raises(threads.ThreadBusy):
        threads.delete(session, "t3")
    threads.stop(session, "t3")
    wait_idle(session, "t3")


CODEX_FAKE = """\
import json, sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "prompt": prompt}) + "\\n")
def emit(event): print(json.dumps(event), flush=True)
emit({"type": "thread.started", "thread_id": "codex-child"})
emit({"type": "turn.started"})
emit({"type": "item.started", "item": {"type": "command_execution", "command": "ls"}})
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "Codex answer."}})
emit({"type": "turn.completed", "usage": {}})
"""


@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    script = tmp_path / "codex"
    script.write_text(f"#!{sys.executable}\n{CODEX_FAKE}")
    script.chmod(0o755)
    monkeypatch.setenv("VIEW_CONCEPT_CODEX", str(script))
    return script


def codex_calls(script):
    return [json.loads(line) for line in (script.parent / "codex.calls").read_text().splitlines()]


def test_codex_first_turn_forks_then_resumes(session, fake_codex):
    no_workflow(session)
    session.bind_agent("codex", "codex-main")
    threads.create(session, "s2", "Le cache", "", "why a cache?")
    t = wait_idle(session, "t1")
    assert t["state"] == "idle" and t["agent_session"] == "codex-child"
    assert t["messages"][1]["text"] == "Codex answer."
    assert t["forked_from"] == "codex-main"
    threads.send(session, "t1", "and then?")
    wait_idle(session, "t1")
    first, second = codex_calls(fake_codex)
    assert first["args"][:3] == ["exec", "fork", "codex-main"]
    assert 'sandbox_mode="read-only"' in first["args"] and first["args"][-1] == "-"
    assert second["args"][:3] == ["exec", "resume", "codex-child"]
    assert second["prompt"] == "and then?"


COMMAND_FAKE = """\
import sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(prompt + "\\n=====\\n")
print("line one")
print("line two")
"""


@pytest.fixture
def fake_command(tmp_path, monkeypatch):
    script = tmp_path / "answer"
    script.write_text(f"#!{sys.executable}\n{COMMAND_FAKE}")
    script.chmod(0o755)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    return script


def test_command_backend_replays_the_thread_each_turn(session, fake_command):
    no_workflow(session)
    threads.create(session, "s2", "Le cache", "", "why a cache?")
    t = wait_idle(session, "t1")
    assert t["state"] == "idle" and t["messages"][1]["text"] == "line one\nline two"
    assert t["forked_from"] == ""
    threads.send(session, "t1", "and then?")
    wait_idle(session, "t1")
    first, second = (fake_command.parent / "answer.calls").read_text().split("=====\n")[:2]
    assert "§2 Cache (s2): « Le cache »" in first and first.strip().endswith("why a cache?")
    assert "read plan.json and sections/" in second
    assert "User: why a cache?" in second and "You: line one" in second
    assert second.strip().endswith("User: and then?")


def test_a_failing_command_reports_its_output(session, tmp_path, monkeypatch):
    script = tmp_path / "broken"
    script.write_text(f"#!{sys.executable}\nimport sys\nprint('no such agent')\nsys.exit(2)\n")
    script.chmod(0o755)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    threads.create(session, "", "", "", "hello")
    t = wait_idle(session, "t1")
    assert t["state"] == "error" and "no such agent" in t["error"]


def test_jazz_needs_an_agent_name(session, monkeypatch):
    monkeypatch.delenv("VIEW_CONCEPT_JAZZ_AGENT", raising=False)
    session.bind_agent("jazz")
    with pytest.raises(SessionError, match="agent's name"):
        threads.create(session, "", "", "", "hello")


def test_jazz_runs_read_only_under_the_recorded_agent(session, monkeypatch):
    from view_concept.agents import resolve

    monkeypatch.delenv("VIEW_CONCEPT_AGENT_COMMAND", raising=False)
    monkeypatch.setenv("VIEW_CONCEPT_JAZZ", "/bin/jazz")
    session.bind_agent("jazz", name="writer")
    argv = resolve(session).args(session, {"agent_session": ""})
    assert argv == [
        "/bin/jazz",
        "--no-tui",
        "run",
        "--agent",
        "writer",
        "--approval-policy",
        "read-only",
    ]


def test_detect_names_the_running_agent():
    from view_concept.agents import detect

    assert detect({"CLAUDE_CODE_SESSION_ID": "c1"}) == ("claude", "c1")
    assert detect({"CODEX_THREAD_ID": "x1"}) == ("codex", "x1")
    assert detect({"JAZZ_AGENT_PROCESS": "1"}) == ("jazz", "")
    assert detect({}) == ("", "")


def test_a_branch_review_thread_starts_from_the_folder(tmp_path, fake_claude):
    s = Session("gate", tmp_path)
    s.create("The gate", "rework the gate", kind="code", repo=str(tmp_path))
    s.bind_agent("claude", "main-1")
    threads.create(s, "", "", "", "why a gate?")
    t = wait_idle(s, "t1")
    assert t["forked_from"] == ""
    (call,) = calls(fake_claude)
    assert "--resume" not in call["args"]
    assert "starts from the session folder" in call["prompt"]
    assert "## Initial request\nrework the gate" in call["prompt"]
    assert call["prompt"].endswith("why a gate?")


def test_an_explanation_thread_starts_from_the_folder(session, fake_claude):
    session.bind_agent("claude", "main-1")
    assert session.coordinated and not session.is_feature and session.fork_parent() == ""
    threads.create(session, "s2", "Le cache", "", "why a cache?")
    t = wait_idle(session, "t1")
    assert t["forked_from"] == ""
    (call,) = calls(fake_claude)
    assert "--resume" not in call["args"]
    assert "the context below is where the explanation stands now" in call["prompt"]
    assert "# view-concept context · kv-cache · role thread" in call["prompt"]
    assert "### 2. Cache (s2)\nLe cache." in call["prompt"]


def test_the_briefing_gives_the_vocabulary_read_up_to_the_passage(session):
    from view_concept.agents import ClaudeBackend

    plan = session.read_plan()
    plan["lexicon"].append({"term": "cache", "section": "s2", "definition": "stored keys"})
    session.plan_path.write_text(json.dumps(plan))
    thread = {"id": "t1", "section": "s1", "quote": "attention"}
    text = threads._briefing(session, thread, ClaudeBackend())
    assert "read the document up to section 1" in text
    assert "clé | key (vecteur)" in text and "cache (stored keys)" not in text
    assert "skills loaded above" not in text and "not a section of the explanation" in text
    general = threads._briefing(session, {**thread, "section": "", "quote": ""}, ClaudeBackend())
    assert "read the whole document" in general and "cache (stored keys)" in general


def test_a_thread_on_an_agent_question(session, fake_command):
    from view_concept.agents import ClaudeBackend

    session.add_question("Keep the cache?", ["yes", "no"], background="It stores the keys.")
    with pytest.raises(SessionError):
        session.new_thread(question="q9")
    threads.create(session, "", "", "", "what does no change?", question="q1")
    t = wait_idle(session, "t1")
    assert t["question"] == "q1"
    text = threads._briefing(session, t, ClaudeBackend())
    assert "the agent question q1: « Keep the cache? »" in text
    assert "options: yes | no" in text and "background: It stores the keys." in text
    assert "to understand it before answering it" in text
    b = session.answer_question("q1", ["no"])
    assert b["answers"] == [{"question": "q1", "choices": ["no"], "text": "", "threads": ["t1"]}]
    out = format_batch("kv-cache", b, session.read_plan()["outline"], session.read_questions())
    assert "answer to q1 « Keep the cache? »: no\n    (from side thread t1: threads/t1.json)" in out
    with pytest.raises(SessionError):  # the answer points to it
        threads.delete(session, "t1")
    with pytest.raises(SessionError):  # only an open question takes a new thread
        session.new_thread(question="q1")


def test_an_answer_without_threads_names_none(session):
    session.add_question("Keep the cache?", ["yes", "no"])
    session.add_question("Why?")
    assert "threads" not in session.skip_question("q1")["answers"][0]
    assert "threads" not in session.unclear_question("q2", "what cache?")["answers"][0]


def test_use_as_answer_drafts_the_answer(session, tmp_path, monkeypatch):
    script = tmp_path / "drafter"
    script.write_text(
        f"#!{sys.executable}\nimport sys\nprompt = sys.stdin.read()\n"
        "print('**choice:** no' if 'Write my answer' in prompt else 'It changes the reads.')\n"
        "print('choice: maybe')\nprint('answer: Drop it, the reads are cheap.')\n"
    )
    script.chmod(0o755)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    session.add_question("Keep the cache?", ["yes", "no"])
    threads.create(session, "", "", "", "what does no change?")
    wait_idle(session, "t1")
    with pytest.raises(SessionError):  # not opened on a question
        threads.send(session, "t1", "", draft=True)
    threads.create(session, "", "", "", "what does no change?", question="q1")
    wait_idle(session, "t2")
    threads.send(session, "t2", "", draft=True)
    t = wait_idle(session, "t2")
    asked, reply = t["messages"][-2:]
    assert asked == {**asked, "text": "Draft my answer to q1", "draft": True}
    assert reply["draft"] == {"choices": ["no"], "text": "Drop it, the reads are cheap."}
    assert "draft" not in t["messages"][1]
    session.skip_question("q1")
    with pytest.raises(SessionError):  # the question is closed
        threads.send(session, "t2", "", draft=True)


def test_use_as_answer_on_claude_holds_the_turn_to_a_schema(session, fake_claude):
    session.add_question("Keep the cache?", ["yes", "no"])
    threads.create(session, "", "", "", "what does no change?", question="q1")
    wait_idle(session, "t1")
    threads.send(session, "t1", "", draft=True)
    t = wait_idle(session, "t1")
    reply = t["messages"][-1]
    assert reply["draft"] == {"choices": ["no"], "text": "Drop it, the reads are cheap."}
    assert reply["text"] == "**Choice:** no\n\nDrop it, the reads are cheap."
    first, second = calls(fake_claude)
    assert "--json-schema" not in first["args"]
    schema = json.loads(second["args"][second["args"].index("--json-schema") + 1])
    assert schema["properties"]["choices"]["items"]["enum"] == ["yes", "no"]
    assert schema["properties"]["choices"]["maxItems"] == 1
    assert "`choices`" in second["prompt"] and "choice: <option>" not in second["prompt"]


def test_read_draft_keeps_real_options_only():
    q = {"options": ["a", "b"], "multi": False}
    assert threads._read_draft("choice: c\nchoice: b\nchoice: a\nanswer:", q) == {
        "choices": ["b"],
        "text": "",
    }
    multi = {**q, "multi": True}
    text = "choice: a\nchoice: b\nanswer: both,\nfor speed."
    assert threads._read_draft(text, multi) == {"choices": ["a", "b"], "text": "both, for speed."}


def test_a_thread_on_a_doc_gets_the_doc_from_the_worktree(tmp_path):
    from view_concept.agents import ClaudeBackend
    from view_concept.context import build

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Tool\n\nThe keys 1 to 4.\n")
    s = Session("gate", tmp_path)
    s.create("The gate", "rework the gate", kind="code", repo=str(repo))
    s.add_doc("README.md", "the install")
    thread = {"id": "t1", "section": "doc:README.md", "quote": "The keys"}
    text = threads._briefing(s, thread, ClaudeBackend())
    assert "Passage: the doc README.md (a file of the repository): « The keys »" in text
    assert "## Doc of the passage: README.md" in text and "The keys 1 to 4." in text
    listed = build(s, "thread", ["x"], "doc:")
    assert "## Doc set of the passage\n- README.md — the install" in listed
