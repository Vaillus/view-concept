import json
import sys

import pytest
from fastapi.testclient import TestClient

from view_concept import channel, server
from view_concept.store import Session

SCHEMA = {
    "type": "object",
    "required": ["concepts"],
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "gloss"],
                "properties": {"name": {"type": "string"}, "gloss": {"type": "string"}},
            },
        }
    },
}
ROW = {"concepts": [{"name": "vector", "gloss": "An ordered list of numbers."}]}

# Stands in for `claude -p` held to a schema: records its arguments and prompt, then
# returns the structured answer the environment names.
FAKE_CLAUDE = """\
import json, os, sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "prompt": prompt}) + "\\n")
answer = json.loads(os.environ["FAKE_ANSWER"])
print(json.dumps({"type": "system", "subtype": "init", "session_id": "small-1"}))
print(json.dumps({"type": "result", "is_error": False, "result": json.dumps(answer),
                  "structured_output": answer}))
"""

# Stands in for an agent that cannot be held to a schema: it answers in text.
FAKE_COMMAND = """\
import os, sys
prompt = sys.stdin.read()
with open(sys.argv[0] + ".calls", "a") as f:
    f.write(prompt + "\\n=====\\n")
print("Here it is:")
print("```json")
print(os.environ["FAKE_ANSWER"])
print("```")
"""


@pytest.fixture
def drawing(session):
    plan = session.read_plan()
    plan["outline"].insert(0, {"id": "scoping", "title": "Scoping", "part": "scoping"})
    session.plan_path.write_text(json.dumps(plan))
    (session.sections_dir / "scoping.html").write_text('<p id="e1">self-attention</p>')
    return session


def fake(tmp_path, monkeypatch, name, source, answer):
    script = tmp_path / name
    script.write_text(f"#!{sys.executable}\n{source}")
    script.chmod(0o755)
    monkeypatch.setenv("FAKE_ANSWER", json.dumps(answer))
    return script


def test_check_holds_an_answer_to_its_schema():
    assert channel.check(ROW, SCHEMA) == []
    assert channel.check({"concepts": [{"name": 3}]}, SCHEMA) == [
        "$.concepts[0].gloss is missing",
        "$.concepts[0].name is not of type string",
    ]
    assert channel.check([], {"type": "object"}) == ["$ is not of type object"]
    closed = {"type": "object", "additionalProperties": False, "properties": {"a": {"enum": [1]}}}
    assert channel.check({"a": 2, "b": 0}, closed) == [
        "$.a is not one of [1]",
        "$.b is not allowed",
    ]
    assert channel.check([1, 2], {"type": "array", "maxItems": 1}) == ["$ has more than 1 items"]


def test_read_answer_finds_the_json_of_a_text_answer():
    assert channel.read_answer('{"a": 1}') == {"a": 1}
    assert channel.read_answer('Here:\n```json\n{"a": [1]}\n```\nDone.') == {"a": [1]}
    assert channel.read_answer('The row is {"a": 2}, as asked.') == {"a": 2}
    with pytest.raises(channel.ChannelError, match="no JSON"):
        channel.read_answer("no idea")


def test_a_request_is_answered_by_a_small_agent_held_to_its_schema(drawing, tmp_path, monkeypatch):
    script = fake(tmp_path, monkeypatch, "claude", FAKE_CLAUDE, ROW)
    monkeypatch.setenv("VIEW_CONCEPT_CLAUDE", str(script))
    plan = drawing.read_plan()
    del plan["workflow"]  # a session that forks its threads: its small agents still never do
    drawing.plan_path.write_text(json.dumps(plan))
    drawing.bind_agent("claude", "main-1")
    assert drawing.fork_parent() == "main-1"
    drawing.save_params("scoping", {"answers": {"dot product": "yes"}})
    answer = channel.ask(drawing, "scoping", "dot product", "List its prerequisites.", SCHEMA)
    assert answer == ROW
    assert drawing.section_params("scoping")["received"] == {"dot product": ROW}
    (call,) = [json.loads(line) for line in (tmp_path / "claude.calls").read_text().splitlines()]
    args, prompt = call["args"], call["prompt"]
    assert "--resume" not in args  # a small agent never forks the main conversation
    assert json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
    assert "[view-concept channel request · section scoping]" in prompt
    assert '{"saved": {"answers": {"dot product": "yes"}}, "received": {}}' in prompt
    assert "# view-concept context · kv-cache · role thread" in prompt
    assert prompt.endswith("Instruction: List its prerequisites.")


def test_an_agent_without_schemas_answers_in_text_checked_on_reading(
    drawing, tmp_path, monkeypatch
):
    script = fake(tmp_path, monkeypatch, "answer", FAKE_COMMAND, ROW)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    assert channel.ask(drawing, "scoping", "k", "List them.", SCHEMA) == ROW
    prompt = (tmp_path / "answer.calls").read_text()
    assert "valid against this JSON schema" in prompt and '"required": ["concepts"]' in prompt
    monkeypatch.setenv("FAKE_ANSWER", json.dumps({"concepts": "none"}))
    with pytest.raises(channel.ChannelError, match="breaks the schema"):
        channel.ask(drawing, "scoping", "k2", "List them.", SCHEMA)
    assert "k2" not in drawing.section_params("scoping")["received"]


def test_the_page_reaches_the_channel_through_the_server(drawing, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, drawing.dir.parent))
    client = TestClient(server.app)
    url = "/api/s/kv-cache/params/scoping"
    script = fake(tmp_path, monkeypatch, "answer", FAKE_COMMAND, ROW)
    monkeypatch.setenv("VIEW_CONCEPT_AGENT_COMMAND", str(script))
    body = {"key": "dot product", "instruction": "List them.", "schema": SCHEMA}
    assert client.post(f"{url}/ask", json=body).json() == {"answer": ROW}
    assert client.get(url).json()["received"] == {"dot product": ROW}
    monkeypatch.setenv("FAKE_ANSWER", "[]")
    r = client.post(f"{url}/ask", json=body)
    assert r.status_code == 502 and "breaks the schema" in r.json()["detail"]
