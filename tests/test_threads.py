import json
import sys
import time

import pytest

from view_concept import threads
from view_concept.store import SessionError, format_batch

# Stands in for `claude -p`: records its arguments and prompt, then streams a reply.
FAKE = """\
import json, sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "prompt": prompt}) + "\\n")
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
    monkeypatch.setattr(threads, "CLAUDE", str(script))
    return script


def calls(script):
    return [json.loads(line) for line in (script.parent / "claude.calls").read_text().splitlines()]


def wait_idle(session, tid):
    for _ in range(100):
        if not threads.is_running(session, tid):
            return session.read_thread(tid)
        time.sleep(0.05)
    raise AssertionError("thread still running")


def test_first_turn_forks_the_main_session(session, fake_claude):
    session.bind_parent("main-1")
    t = threads.create(session, "s2", "Le cache", "", "why a cache?")
    assert t["id"] == "t1" and t["state"] == "running"
    t = wait_idle(session, "t1")
    assert t["state"] == "idle" and t["claude_id"] == "child-1"
    assert t["forked_from"] == "main-1"
    assert [m["role"] for m in t["messages"]] == ["user", "assistant"]
    assert t["messages"][1]["text"] == "Short \n\nanswer."
    (call,) = calls(fake_claude)
    assert call["args"][call["args"].index("--resume") + 1] == "main-1"
    assert "--fork-session" in call["args"]
    assert call["args"][call["args"].index("--tools") + 1 :][:3] == ["Read", "Grep", "Glob"]
    assert "§2 Cache (s2): « Le cache »" in call["prompt"]
    assert call["prompt"].endswith("why a cache?")


def test_later_turns_resume_the_thread(session, fake_claude):
    session.bind_parent("main-1")
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


def test_bind_parent_and_thread_ids(session):
    assert session.read_parent() == ""
    assert session.bind_parent("a") and not session.bind_parent("a")
    assert session.bind_parent("b") and session.read_parent() == "b"
    assert [session.new_thread()["id"] for _ in range(2)] == ["t1", "t2"]
    with pytest.raises(SessionError):
        session.read_thread("../plan")


def test_comment_from_a_thread(session):
    b = session.add_batch([{"section": "s1", "text": "rewrite it", "thread": "t3"}])
    out = format_batch("kv-cache", b, session.read_plan()["outline"])
    assert "(from side thread t3: threads/t3.json)" in out
