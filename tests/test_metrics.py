"""Run metrics on a small transcript tree: a coordinator conversation that starts one
writer on batch b1, the writer starting two helpers in one wave."""

import json
from pathlib import Path

import pytest

from view_concept import metrics
from view_concept.store import Session

CONV = "c0ffee00-0000-0000-0000-000000000001"
DAY = "2026-10-15T10:"


def at(mmss: str) -> str:
    """A transcript timestamp at 10:<mm:ss.fff>."""
    return f"{DAY}{mmss}Z"


def user(when: str, content) -> dict:
    return {"type": "user", "timestamp": at(when), "message": {"role": "user", "content": content}}


def result(when: str, tool_id: str, text: str = "ok") -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    return user(when, [block])


def call(when: str, mid: str, blocks: list, stop: str | None = None, cache_read: int = 9000):
    usage = {
        "input_tokens": 2,
        "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": cache_read,
        "output_tokens": 7,
    }
    return {
        "type": "assistant",
        "timestamp": at(when),
        "message": {
            "id": mid,
            "model": "claude-opus-5-5",
            "content": blocks,
            "stop_reason": stop,
            "usage": usage,
        },
    }


def tool(tool_id: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": inp}


def text(t: str = "done") -> dict:
    return {"type": "text", "text": t}


def turn_end(when: str) -> dict:
    return {"type": "system", "subtype": "turn_duration", "timestamp": at(when)}


def write_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))


CONTEXT = 'view-concept context rev --role writer --trigger "« Write model »" b1'

COORDINATOR = [
    user(
        "00:01.000",
        "<task-notification>view-concept · rev · batch b1 · 0 comments</task-notification>",
    ),
    call("00:03.000", "c1", [tool("toolu_W", "Agent", description="Writer")], "tool_use"),
    result("00:03.300", "toolu_W", "Async agent launched"),
    call("00:04.000", "c2", [text("The writer started.")], "end_turn"),
    turn_end("00:04.100"),
    user("02:01.000", "<task-notification>Agent finished</task-notification>"),
    call("02:02.000", "c3", [tool("toolu_S", "Bash", command="view-concept status rev idle")]),
    result("02:02.500", "toolu_S", "idle"),
    call("02:03.000", "c4", [text("The model is written.")], "end_turn"),
    turn_end("02:03.100"),
]

WRITER = [
    user("00:03.500", f"Run `{CONTEXT}` as your context. Read `roles/writer.md`."),
    call("00:05.000", "w1", [tool("t1", "Bash", command=CONTEXT)], cache_read=9000),
    result("00:06.000", "t1", "x" * 500),
    call(
        "00:10.000", "w2", [tool("t2", "Read", file_path="/h/skills/view-branch/roles/writer.md")]
    ),
    result("00:11.000", "t2", "y" * 300),
    call("00:15.000", "w3", [tool("toolu_H1", "Agent", description="Write section a")]),
    call("00:20.000", "w3", [tool("toolu_H2", "Agent", description="Write section b")]),
    result("00:21.000", "toolu_H1", "launched"),
    result("00:21.000", "toolu_H2", "launched"),
    call("00:22.000", "w4", [text("Waiting for the helpers.")], "end_turn"),
    user("01:40.000", "<agent-message from=h2>report</agent-message>"),
    call("01:41.000", "w5", [text("One is in.")], "end_turn"),
    user("01:50.000", "<agent-message from=h1>report</agent-message>"),
    call("01:55.000", "w6", [tool("t6", "Bash", command="cat > /tmp/sheet.md <<'EOF'\nhi\nEOF")]),
    result("01:56.000", "t6", ""),
    call("02:00.000", "w7", [tool("t7", "SubagentHandback", message="report")], cache_read=20000),
    result("02:00.400", "t7", "delivered"),
]

HELPER_1 = [
    user("00:21.000", "You are a helper of the writer. Read `roles/writer.md`. Write section a."),
    call(
        "00:25.000", "h1", [tool("a1", "Bash", command="cd /h/x && sed -n 1,20p roles/writer.md")]
    ),
    result("00:26.000", "a1", "z" * 100),
    call("00:40.000", "h2", [tool("a2", "Write", file_path="/s/sections/a.md")]),
    result("00:41.000", "a2", "ok"),
    call("01:00.000", "h3", [text("Section a is written.")], "end_turn"),
]

HELPER_2 = [
    user("00:21.200", "You are a helper of the writer. Write section b."),
    call("00:29.000", "k1", [tool("b1", "Bash", command="grep -n foo src/x.py")]),
    result("00:30.000", "b1", "found"),
    call("01:00.000", "k2", [tool("b2", "Edit", file_path="/s/sections/b.md")]),
    result("01:01.000", "b2", "ok"),
    call("01:39.000", "k3", [tool("b3", "SubagentHandback", message="b done")]),
    result("01:39.500", "b3", "delivered"),
]


@pytest.fixture
def projects(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    repo_dir = root / "-repo"
    write_jsonl(repo_dir / f"{CONV}.jsonl", COORDINATOR)
    sub = repo_dir / CONV / "subagents"
    for rid, lines, meta in [
        ("aw", WRITER, {"description": "Writer on b1", "toolUseId": "toolu_W", "spawnDepth": 1}),
        ("ah1", HELPER_1, {"toolUseId": "toolu_H1", "parentAgentId": "aw", "spawnDepth": 2}),
        ("ah2", HELPER_2, {"toolUseId": "toolu_H2", "parentAgentId": "aw", "spawnDepth": 2}),
    ]:
        write_jsonl(sub / f"agent-{rid}.jsonl", lines)
        (sub / f"agent-{rid}.meta.json").write_text(json.dumps(meta))
    monkeypatch.setenv(metrics.PROJECTS_ENV, str(root))
    return root


def make_review(root: Path, slug: str, agent: str = "claude"):
    s = Session(slug, root)
    s.create("A review", "make it faster", kind="code", repo=str(root.parent / "repo"))
    s.agent_path.write_text(json.dumps({"agent": agent, "parent": CONV}))
    batches = [
        {"id": "b1", "sent": "2026-10-15T10:00:00+00:00", "action": "plan", "comments": []},
        {
            "id": "b2",
            "sent": "2026-10-15T10:05:00+00:00",
            "action": "answer",
            "comments": [],
            "answers": [{"question": "q1", "unclear": True, "note": ""}],
        },
    ]
    s.comments_path.write_text(json.dumps({"batches": batches}))
    return s


@pytest.fixture
def review(tmp_path, projects):
    return make_review(tmp_path / "sessions", "rev")


def runs_of(m: dict) -> dict[str, dict]:
    return {r["id"]: r for r in m["runs"]}


def test_run_identity(review):
    m = metrics.session_metrics(review)
    runs = runs_of(m)
    assert set(runs) == {"pass:b1", "aw", "ah1", "ah2"}
    writer = runs["aw"]
    assert (writer["kind"], writer["role"], writer["parent"]) == ("role", "writer", "pass:b1")
    assert writer["trigger"] == "« Write model » b1"
    assert writer["model"] == "claude-opus-5-5" and writer["variant"] == "none"
    assert writer["helpers"] == ["ah1", "ah2"]
    for hid in ("ah1", "ah2"):
        assert (runs[hid]["kind"], runs[hid]["role"], runs[hid]["parent"]) == (
            "helper",
            "writer",
            "aw",
        )
    assert (runs["pass:b1"]["kind"], runs["pass:b1"]["role"]) == ("pass", "coordinator")
    assert m["model"] == "claude-opus-5-5" and m["agent"] == "claude"


def test_run_measures(review):
    writer = runs_of(metrics.session_metrics(review))["aw"]
    assert writer["wall"] == 116.9  # 10:00:03.5 → 10:02:00.4
    assert writer["first_write"] == 106.5  # the writing stretch starts at 10:01:50
    assert writer["startup"] == {"seconds": 106.5, "api_calls": 5, "prompt_tokens": 50010}
    acts = writer["activities"]
    assert acts["loading context"] == 7.5  # the context command, then the role file
    assert acts["waiting on helpers"] == 99.0  # the Agent calls and the waits for reports
    assert acts["writing"] == 6.0 and acts["report"] == 4.4
    assert writer["api_calls"] == 7 and writer["tool_calls"] == 6
    tokens = writer["tokens"]
    assert (tokens["first"], tokens["last"]) == (10002, 21002)
    assert tokens["total"] == 6 * 10002 + 21002
    assert tokens["output"] == 14 and tokens["output_calls"] == 2  # recorded stop reasons only
    assert writer["context"] == {"prompt_tokens": 10002, "read_chars": 800, "context_chars": 500}
    assert writer["model_time"] + writer["tool_time"] == pytest.approx(writer["wall"], abs=0.2)
    assert writer["stretches"][0]["command"] == CONTEXT
    helper = runs_of(metrics.session_metrics(review))["ah1"]
    assert helper["wall"] == 39.0 and helper["first_write"] == 5.0
    assert helper["activities"]["loading context"] == 5.0
    assert helper["tokens"]["output"] == 7


def test_waves(review):
    m = metrics.session_metrics(review)
    [wave] = m["waves"]
    assert wave["run"] == "aw" and wave["helpers"] == ["ah1", "ah2"]
    assert wave["launch"] == 10.2  # from the result at 10:00:11 to the last start, 10:00:21.2
    assert (wave["slowest"], wave["slowest_helper"], wave["sum"]) == (78.3, "ah2", 117.3)
    assert wave["saved"] == 28.8
    assert wave["loading"] == [0.0, 5.0]
    assert runs_of(m)["ah1"]["wave"] == 0 and runs_of(m)["aw"]["wave"] is None


def test_waiting_falls_back_to_the_coordinator_transcript(review):
    m = metrics.session_metrics(review)
    b1, b2 = m["batches"]
    assert b1["label"] == "« Write model »" and b2["label"] == "an answer"
    assert b1["delivered"] == "2026-10-15T10:00:01.000+00:00"
    assert b1["pickup"] == 3.0  # sent 10:00:00, the coordinator acts at 10:00:03
    assert b1["waited"] == "2026-10-15T10:02:03.100+00:00"  # the turn after the writer ended
    assert b1["agent"] == 120.1 and b1["user"] == 176.9
    assert set(b1["runs"]) == {"aw", "ah1", "ah2"} and not b1["busy"]
    assert [c["kind"] for c in m["clock"]] == ["pickup", "agent"]
    assert m["clock"][1]["seconds"] == 120.1


def test_waiting_reads_the_session_records(review):
    (review.dir / "deliveries.jsonl").write_text(
        json.dumps({"batch": "b1", "at": "2026-10-15T10:00:00.500+00:00"}) + "\n"
    )
    (review.dir / "phase-history.jsonl").write_text(
        json.dumps({"phase": "writing", "at": "2026-10-15T10:00:30.000+00:00"})
        + "\n"
        + json.dumps({"phase": "awaiting-answer", "at": "2026-10-15T10:02:02.600+00:00"})
        + "\n"
    )
    b1 = metrics.session_metrics(review)["batches"][0]
    assert b1["delivered"] == "2026-10-15T10:00:00.500+00:00"
    assert b1["waited"] == "2026-10-15T10:02:02.600+00:00"


def test_a_batch_sent_during_a_run_is_busy(tmp_path, projects):
    coordinator = projects / "-repo" / f"{CONV}.jsonl"
    lines = [*COORDINATOR]
    lines.insert(
        5, user("01:00.000", "<task-notification>view-concept · rev · batch b2</task-notification>")
    )
    write_jsonl(coordinator, lines)
    s = make_review(tmp_path / "sessions", "rev")
    batches = json.loads(s.comments_path.read_text())
    batches["batches"][1]["sent"] = "2026-10-15T10:00:59+00:00"
    s.comments_path.write_text(json.dumps(batches))
    b1, b2 = metrics.session_metrics(s)["batches"]
    assert b2["busy"] and b2["pickup"] is None
    assert b2["agent"] == 64.1  # its wait behind the writer is agent time
    assert b1["user"] is None and b2["waited"] == b1["waited"]


def test_runs_of_another_session_are_left_out(tmp_path, projects):
    other = make_review(tmp_path / "sessions", "other")
    assert [r["id"] for r in metrics.session_metrics(other)["runs"]] == []


def test_another_agent_lists_no_runs(tmp_path, projects):
    s = make_review(tmp_path / "sessions", "rev", agent="codex")
    m = metrics.session_metrics(s)
    assert m["runs"] == [] and m["agent"] == "codex" and m["model"] == ""
    assert m["quality"]["unclear"] == 1 and len(m["batches"]) == 2


def test_quality_signals(review):
    plan = review.read_plan()
    plan["outline"] = [
        {"id": "i1", "title": "x", "part": "refactoring", "item": {"verdict": "diverges"}},
        {"id": "i2", "title": "y", "part": "refactoring", "item": {"verdict": "conforms"}},
        {"id": "f1", "title": "z", "part": "refactoring", "kind": "finding", "items": ["i1"]},
    ]
    review.plan_path.write_text(json.dumps(plan))
    q = metrics.session_metrics(review)["quality"]
    assert q == {
        "comments": 0,
        "rewrites": 0,
        "unclear": 1,
        "changes_after_approval": 0,
        "findings": 2,
        "reviewer_reruns": 0,
    }


def test_thread_turns(review):
    review.threads_dir.mkdir(exist_ok=True)
    thread = {
        "id": "t1",
        "section": "s1",
        "agent_session": "",
        "messages": [
            {"role": "user", "text": "why?", "at": "2026-10-15T10:10:00+00:00"},
            {
                "role": "assistant",
                "text": "because",
                "at": "2026-10-15T10:10:00+00:00",
                "first_text": "2026-10-15T10:10:04.500+00:00",
                "ended": "2026-10-15T10:10:06.000+00:00",
            },
            {"role": "user", "text": "and?", "at": "2026-10-15T10:11:00+00:00"},
            {"role": "assistant", "text": "so", "at": "2026-10-15T10:11:00+00:00"},
        ],
    }
    (review.threads_dir / "t1.json").write_text(json.dumps(thread))
    turns = metrics.session_metrics(review)["threads"]
    assert [(t["turn"], t["first_text"], t["end"]) for t in turns] == [
        (1, 4.5, 6.0),
        (2, None, None),
    ]
    assert turns[0]["prompt_tokens"] is None


def test_compare_by_variant(tmp_path, projects):
    root = tmp_path / "sessions"
    s = make_review(root, "rev")
    other = make_review(root, "rev-2")
    plan = other.read_plan()
    plan["variant"] = {"name": "writer on sonnet", "models": {"writer": "sonnet"}}
    other.plan_path.write_text(json.dumps(plan))
    m = metrics.session_metrics(s)
    names = [v["name"] for v in m["compare"]["variants"]]
    assert names == ["none", "writer on sonnet"]
    none = m["compare"]["variants"][0]
    assert none["reviews"][0]["slug"] == "rev" and none["reviews"][0]["current"]
    assert none["reviews"][0]["roles"] == {"writer": 116.9}
    assert m["medians"] == {"writer": 116.9}
    assert m["compare"]["variants"][1]["reviews"][0]["roles"] == {}  # its prompts name rev


def test_series_and_slow_runs():
    def run(rid: str, role: str, words: list[str], wall: float, start: int) -> metrics.Run:
        from datetime import UTC, datetime

        when = datetime(2026, 10, 15, 10, start, tzinfo=UTC)
        r = metrics.Run(rid, "role", role, words, "", "", "", when, when, [], [])
        r.measures = {"startup": {"seconds": 10.0}, "wall": wall}
        return r

    runs = [
        run("p1", "planner", ["first run"], 30, 1),
        run("p2", "planner", ["b1"], 30, 2),
        run("p3", "planner", ["b2", "b3"], 30, 3),
        run("w1", "writer", ["« Write model »", "b4"], 30, 4),
    ]
    [series] = metrics._series(runs)
    assert series == {"id": "s1", "role": "planner", "runs": ["p1", "p2"], "startup": 20.0}
    assert runs[1].series == "s1" and runs[2].series is None


@pytest.mark.parametrize(
    ("command", "activity"),
    [
        ("view-concept context rev --role writer", "exploring code"),
        ("cd /repo && view-concept check rev", "view-concept commands"),
        ("cd /h/skills/view-branch && sed -n 1,9p roles/writer.md", "exploring code"),
        ("cat ~/.view-concept/sessions/rev/questions.json", "exploring code"),
        ("cd /repo && grep -n foo src/x.py 2>/dev/null", "exploring code"),
        ("cat > /s/sections/a.html <<'EOF'\n<p>x</p>\nEOF", "writing"),
        ("python3 - <<'EOF'\nopen('a', 'w').write('x')\nEOF", "writing"),
        ("git log --oneline -3", "exploring code"),
        ("git commit -m 'x'", "writing"),
        ("uv run pytest -q", "other"),
        ("until [ -f a ]; do sleep 1; done", "waiting on helpers"),
    ],
)
def test_shell_activity(command, activity):
    assert metrics.shell_activity(command) == activity


def opening_run(tmp_path, prompt: str, reads: list[list[dict]]) -> dict:
    """The measures of a run whose calls each make the given tool calls, one second
    apart, each result 500 characters, then a report."""
    lines = [user("00:00.000", prompt)]
    for i, tools in enumerate(reads):
        lines.append(call(f"00:{2 * i + 1:02d}.000", f"m{i}", tools))
        lines += [result(f"00:{2 * i + 2:02d}.000", t["id"], "x" * 500) for t in tools]
    lines.append(call("00:59.000", "end", [text()], "end_turn"))
    path = tmp_path / "t.jsonl"
    write_jsonl(path, lines)
    t = metrics.load_transcript(path)
    assert t.start and t.end
    return metrics.measure(t.calls, t.inputs, t.start, t.end, prompt=t.prompt)


PROMPT = f"Run `{CONTEXT}`, then read `roles/writer.md` in skills/view-branch."
ROLE = "/h/skills/view-branch/roles/writer.md"


def acts_of(m: dict) -> list[str]:
    return [s["activity"] for s in m["stretches"]]


def test_a_named_role_file_read_after_code_explores_code(tmp_path):
    m = opening_run(
        tmp_path,
        PROMPT,
        [
            [tool("t1", "Bash", command=CONTEXT)],
            [tool("t2", "Grep", pattern="foo", path="/repo/src")],
            [tool("t3", "Read", file_path=ROLE)],
        ],
    )
    assert acts_of(m) == ["loading context", "exploring code", "exploring code", "report"]
    assert m["context"]["read_chars"] == 500 and m["context"]["context_chars"] == 500


def test_an_unnamed_role_file_explores_code(tmp_path):
    m = opening_run(
        tmp_path,
        PROMPT,
        [
            [tool("t1", "Bash", command=CONTEXT)],
            [tool("t2", "Read", file_path="/h/skills/view-branch/roles/reviewer.md")],
            [tool("t3", "Read", file_path=ROLE)],
        ],
    )
    assert acts_of(m) == ["loading context", "exploring code", "exploring code", "report"]


def test_a_call_mixing_a_named_role_file_stays_in_the_opening(tmp_path):
    m = opening_run(
        tmp_path,
        PROMPT,
        [
            [tool("t1", "Bash", command=CONTEXT)],
            [
                tool("t2", "Read", file_path=ROLE),
                tool("t3", "Read", file_path="/s/questions.json"),
                tool("t4", "Bash", command="grep -n foo src/x.py"),
            ],
            [tool("t5", "Read", file_path="/repo/src/x.py")],
            [tool("t6", "Bash", command=CONTEXT)],
        ],
    )
    assert acts_of(m) == [
        "loading context",
        "loading context",
        "exploring code",
        "exploring code",
        "report",
    ]
    assert m["context"]["read_chars"] == 2000 and m["context"]["context_chars"] == 500
    assert m["activities"]["loading context"] == 4.0


def test_a_skill_call_ends_the_opening(tmp_path):
    m = opening_run(
        tmp_path,
        PROMPT,
        [[tool("t1", "Skill", skill="x")], [tool("t2", "Bash", command=CONTEXT)]],
    )
    assert acts_of(m) == ["other", "exploring code", "report"]


def test_a_stretch_over_ten_minutes_is_stalled(tmp_path, monkeypatch):
    lines = [
        user("00:00.000", "start"),
        call("00:01.000", "m1", [tool("t1", "Bash", command="grep x y")]),
        result("00:02.000", "t1"),
        call("15:00.000", "m2", [tool("t2", "Write", file_path="/a")]),
        result("15:01.000", "t2"),
        call("15:05.000", "m3", [text()], "end_turn"),
    ]
    path = tmp_path / "t.jsonl"
    write_jsonl(path, lines)
    t = metrics.load_transcript(path)
    assert t.start and t.end
    m = metrics.measure(t.calls, t.inputs, t.start, t.end)
    assert m["stalled"] == 899.0
    assert m["wall"] == 6.0
    assert m["activities"]["writing"] == 0.0
    assert [s["stalled"] for s in m["stretches"]] == [False, True, False]


def test_a_queued_notice_continues_the_pass(tmp_path, projects):
    conv_dir = projects / "-repo"
    lines = [
        *COORDINATOR,
        user("02:03.105", "<task-notification>Agent finished</task-notification>"),
        call("02:04.000", "c5", [tool("toolu_R", "Agent", description="Reviewer")], "tool_use"),
        result("02:04.200", "toolu_R", "launched"),
        call("02:04.500", "c6", [text("The reviewer started.")], "end_turn"),
        turn_end("02:04.600"),
        user("02:31.000", "<task-notification>Agent finished</task-notification>"),
        call("02:32.000", "c7", [text("Reviewed.")], "end_turn"),
        turn_end("02:32.100"),
    ]
    write_jsonl(conv_dir / f"{CONV}.jsonl", lines)
    reviewer = [
        user("02:04.300", "Run `view-concept context rev --role reviewer --trigger report`."),
        call("02:10.000", "r1", [text("All conforms.")], "end_turn"),
    ]
    sub = conv_dir / CONV / "subagents"
    write_jsonl(sub / "agent-ar.jsonl", reviewer)
    (sub / "agent-ar.meta.json").write_text(json.dumps({"toolUseId": "toolu_R"}))
    m = metrics.session_metrics(make_review(tmp_path / "sessions", "rev"))
    assert runs_of(m)["ar"]["parent"] == "pass:b1"
    assert m["batches"][0]["waited"] == "2026-10-15T10:02:32.100+00:00"


def test_time_by_role_counts_parallel_helpers_once(review):
    m = metrics.session_metrics(review)
    writer = next(x for x in m["by_role"] if x["role"] == "writer")
    # The writer's run spans both helpers: 10:00:03.5 → 10:02:00.4, not the sum of the three.
    assert writer["runs"] == 3 and writer["seconds"] == 116.9
    assert sum(writer["activities"].values()) == pytest.approx(116.9, abs=0.3)
    # While its helpers work, the writer's wait takes no share.
    assert writer["activities"]["waiting on helpers"] < 99.0


def test_a_batch_leaves_its_stalls_out_of_agent_time(review, monkeypatch):
    monkeypatch.setattr(metrics, "STALL", 30.0)
    m = metrics.session_metrics(review)
    b1 = m["batches"][0]
    spans = [(r["start"], s) for r in m["runs"] if r["id"] in b1["runs"] for s in r["stretches"]]
    assert any(s["stalled"] for _, s in spans)
    assert b1["stalled"] > 0
    assert b1["agent"] + b1["stalled"] == pytest.approx(120.1, abs=0.2)


def test_a_coordinator_pass_never_stalls(review, monkeypatch):
    # The pass waits on the writer with no line in its transcript: that wait stays agent
    # time, so only the role agents' and helpers' stretches are cut as stalls.
    monkeypatch.setattr(metrics, "STALL", 30.0)
    m = metrics.session_metrics(review)
    p = runs_of(m)["pass:b1"]
    assert max(s["end"] - s["start"] for s in p["stretches"]) > 30.0
    assert not any(s["stalled"] for s in p["stretches"]) and p["stalled"] == 0.0
