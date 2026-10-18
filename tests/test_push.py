import pytest

from view_concept import push

SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}


@pytest.fixture
def push_file(tmp_path):
    return tmp_path / "push.json"


def test_waiting_names_what_the_session_waits_for(session):
    assert push.waiting(session) is None
    session.write_status("awaiting-model")
    assert push.waiting(session) == (
        f"awaiting-model@{session.read_status()['since']}",
        "model ready · waiting for your approval",
    )
    session.add_batch([], "", "approve-model")
    assert push.waiting(session) is None
    session.write_status("writing")
    session.add_question("PR or merge?", ["PR", "merge"], section="s1")
    session.add_question("Which port?")
    assert push.waiting(session) == ("q:q1,q2", "paused after section 1 · 2 questions")


def test_scoping_questions_wait_without_a_section(session):
    session.write_status("scoping")
    session.add_question("Which port?")
    assert push.waiting(session) == ("q:q1", "1 question")


def test_a_notice_when_a_session_starts_waiting(session, push_file, monkeypatch):
    monkeypatch.setattr(push, "_keys", lambda path=None: {**push._load(path), "public": "p"})
    root = session.dir.parent
    assert push.notices(push_file, root) == []  # no phone subscribed
    session.write_status("awaiting-model")
    push.subscribe(SUB, push_file, root)
    # Already waiting when notices were turned on: it did not start waiting.
    assert push.notices(push_file, root) == []
    session.add_batch([], "", "approve-model")
    assert push.notices(push_file, root) == []
    session.write_status("awaiting-answer")
    session.add_question("Which port?")
    got = push.notices(push_file, root)
    assert got == [{"slug": "kv-cache", "title": "Le KV cache", "body": "1 question"}]
    assert push.notices(push_file, root) == []  # one notice per waiting
    session.add_question("And the login?")
    assert push.notices(push_file, root)[0]["body"] == "2 questions"


def test_subscribe_needs_a_push_subscription(push_file, monkeypatch):
    monkeypatch.setattr(push, "_keys", lambda path=None: {**push._load(path), "public": "p"})
    with pytest.raises(push.PushError):
        push.subscribe({"endpoint": "http://x", "keys": {}}, push_file)


def test_keys_are_made_once(push_file):
    key = push.public_key(push_file)
    assert key and push.public_key(push_file) == key


def test_send_hands_the_notice_to_every_phone(push_file, monkeypatch):
    import pywebpush

    push.subscribe(SUB, push_file)
    push.subscribe({**SUB, "endpoint": "https://push.example/gone"}, push_file)
    sent = []

    class Gone:
        status_code = 410

    def webpush(sub, data, **kw):
        if sub["endpoint"].endswith("gone"):
            raise pywebpush.WebPushException("gone", response=Gone())
        sent.append((sub["endpoint"], data))

    monkeypatch.setattr(pywebpush, "webpush", webpush)
    n = push.send({"slug": "s", "title": "t", "body": "b"}, push_file)
    assert n == 1 and sent[0][0] == SUB["endpoint"]
    assert [s["endpoint"] for s in push._load(push_file)["subscriptions"]] == [SUB["endpoint"]]
