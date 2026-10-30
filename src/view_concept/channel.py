"""The channel: a section's script asks a small agent for data.

Any HTML section's script can ask an agent for data and draw the answer itself, apart from
comments and comment batches, and without its section being redrawn. Inside the section's
frame the script calls `viewConcept.ask(key, instruction, schema)` (frame.js); the request
goes from the frame to the page (app.js), from the page to the server (server.py), and the
server runs it here: it starts a small agent, holds its answer to the request's JSON
schema, keeps the answer in the parameters file as the section's `received[key]` (store.py)
and sends it back the same way. A failure (the agent fails, the call times out, the answer
breaks the schema) reaches the script as an error.

The small agent is not the scoper: it is one headless, read-only turn on the side threads'
agent runner (agents.py), started for this request alone and never forking the main
conversation. It knows only what the request and the session's files tell it: the
instruction, the schema, the section's entry of the parameters file (what the script saved
and received so far: on the prerequisite tree, the branch walked) and the context a side
thread on that section gets (`view-concept context --role thread`). On an agent that can
hold a turn to a schema (Claude's `--json-schema`) the answer is held to it there; on any
other the agent is asked for the JSON in its answer's text, which is read back and checked
here (`check`), as the « use as answer » turn of a side thread is.

`check` knows the part of JSON Schema a section's request needs: `type` (one or a list),
`enum`, `const`, `properties`, `required`, `additionalProperties` (false or a schema),
`items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `minimum`, `maximum`, `anyOf`;
any other keyword is not checked.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from .agents import TurnState, resolve
from .context import build
from .store import Session, SessionError
from .threads import working_dir

# Seconds a small agent has to answer one request.
CHANNEL_TIMEOUT = 180.0


class ChannelError(SessionError):
    """A request the small agent did not answer: its failure, a timeout, a broken schema."""


def ask(s: Session, sid: str, key: str, instruction: str, schema: Any) -> Any:
    """Run the request `key` of section `sid`'s script: a small agent answers
    `instruction` with data held to `schema`. The answer is kept as the section's
    `received[key]` and returned."""
    if not instruction.strip():
        raise SessionError("a request needs an instruction")
    if not isinstance(schema, dict):
        raise SessionError("a request's schema is a JSON object")
    entry = s.section_params(sid)  # refuses a section that is not an HTML section
    if not key.strip():
        raise SessionError("a request needs a key")
    try:
        backend = resolve(s)
    except ValueError as e:
        raise SessionError(str(e)) from e
    thread: dict[str, Any] = {"id": "channel", "agent_session": "", "messages": []}
    args = backend.args(s, thread, fork=False)
    if backend.structured:
        args += backend.schema_args(schema)
    briefing = _briefing(s, sid, entry)
    prompt = backend.prompt(thread, briefing, _request(instruction, schema, backend.structured))
    try:
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=CHANNEL_TIMEOUT,
            cwd=working_dir(s),
        )
    except subprocess.TimeoutExpired as e:
        raise ChannelError(f"no answer within {CHANNEL_TIMEOUT:.0f} seconds") from e
    except OSError as e:
        raise ChannelError(f"could not start {args[0]}: {e}") from e
    reply: dict[str, Any] = {"text": ""}
    turn = TurnState()
    for line in proc.stdout.splitlines(keepends=True):
        backend.feed(line, thread, reply, turn)
    turn.noise += [line for line in proc.stderr.splitlines() if line.strip()]
    backend.close(thread, reply, turn, proc.returncode)
    if turn.failed:
        raise ChannelError(turn.error or f"exit code {proc.returncode}")
    if turn.structured is not None:
        answer = turn.structured
    else:
        answer = read_answer(reply["text"].strip() or turn.final_text)
    problems = check(answer, schema)
    if problems:
        raise ChannelError("the answer breaks the schema: " + "; ".join(problems[:5]))
    s.set_received(sid, key, answer)
    return answer


def _briefing(s: Session, sid: str, entry: dict[str, Any]) -> str:
    """What the small agent starts from: who asks, its rules, the section's entry of the
    parameters file, and the context a side thread on the section gets."""
    lines = [
        f"[view-concept channel request · section {sid}]",
        f"The script of the section {sid!r} of the view-concept session {s.slug!r} ({s.dir})"
        " asks you for data, which it draws itself. You answer this one request and end.",
        "- Your tools are read-only: read any file, search the web when a fact needs it,"
        " but change nothing.",
        "- Answer with the data only, in the shape the JSON schema below gives: no prose"
        " around it, no comment inside it.",
        "- The section's parameters, what its script saved and the answers it received"
        " before this request (on a prerequisite tree, the branch the user walked):",
        json.dumps(entry, ensure_ascii=False),
        "",
        build(s, "thread", [f"a request of the script of section {sid}"], sid),
    ]
    return "\n".join(lines)


def _request(instruction: str, schema: dict[str, Any], structured: bool) -> str:
    """The message of the request: the instruction, and on an agent the server cannot
    hold to the schema, the schema the JSON of its answer must follow."""
    text = f"Instruction: {instruction.strip()}"
    if structured:
        return text
    return (
        f"{text}\n\nReply with one JSON value and nothing else, in a ```json block, valid"
        f" against this JSON schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


FENCE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def read_answer(text: str) -> Any:
    """The JSON value an answer's text carries: the whole text, else its ```json block,
    else its first object or array."""
    candidates = [text.strip(), *(m.group(1).strip() for m in FENCE.finditer(text))]
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise ChannelError("the answer holds no JSON")


TYPES: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def check(value: Any, schema: Any, at: str = "$") -> list[str]:
    """The ways `value` breaks `schema` (the part of JSON Schema the module docstring
    names), each with where; empty when it holds."""
    if not isinstance(schema, dict):
        return []
    problems: list[str] = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(TYPES.get(t, lambda _: True)(value) for t in types):
            return [f"{at} is not of type {' or '.join(map(str, types))}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{at} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        problems.append(f"{at} is not {schema['const']!r}")
    if "anyOf" in schema and all(check(value, sub, at) for sub in schema["anyOf"]):
        problems.append(f"{at} matches none of anyOf")
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        problems += [f"{at}.{k} is missing" for k in schema.get("required", []) if k not in value]
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                problems += check(v, props[k], f"{at}.{k}")
            elif extra is False:
                problems.append(f"{at}.{k} is not allowed")
            elif isinstance(extra, dict):
                problems += check(v, extra, f"{at}.{k}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{at} has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{at} has more than {schema['maxItems']} items")
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(value):
                problems += check(v, schema["items"], f"{at}[{i}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{at} is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{at} is longer than {schema['maxLength']}")
    if TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{at} is under {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{at} is over {schema['maximum']}")
    return problems
