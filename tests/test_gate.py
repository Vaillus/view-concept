import pytest
from fastapi.testclient import TestClient

from view_concept import gate, server
from view_concept.store import Session

OWNER = "hugo@lysk.ai"


@pytest.mark.parametrize(
    ("logins", "owner", "passes"),
    [
        ([OWNER], OWNER, True),
        ([f" {OWNER} "], OWNER, True),
        ([], OWNER, False),
        ([OWNER, OWNER], OWNER, False),
        (["someone@lysk.ai"], OWNER, False),
        ([OWNER], None, False),
        ([OWNER], "  ", False),
    ],
)
def test_allows_only_the_owner_login_once(logins, owner, passes):
    assert gate.allows(logins, owner) is passes


@pytest.fixture
def clients(session, monkeypatch):
    """Two clients on the page's app behind the gate: one on the remote port (the test
    client's port, 80), one on the local port (the gate told the remote port is another)."""
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, session.dir.parent))
    remote = TestClient(gate.TailnetGate(server.app, 80, OWNER))
    local = TestClient(gate.TailnetGate(server.app, 5081, OWNER))
    return remote, local


def test_remote_port_is_behind_the_gate(clients):
    remote, _ = clients
    login = gate.LOGIN_HEADER.decode()
    assert remote.get("/api/s/kv-cache").status_code == 403
    assert remote.get("/api/s/kv-cache", headers={login: "x@lysk.ai"}).status_code == 403
    r = remote.get("/api/s/kv-cache", headers={login: OWNER})
    assert r.status_code == 200 and r.json()["slug"] == "kv-cache"
    assert remote.get("/s/kv-cache", headers={login: OWNER}).status_code == 200


def test_local_port_answers_without_a_login(clients):
    _, local = clients
    assert local.get("/api/health").status_code == 200
    assert local.get("/api/s/kv-cache").status_code == 200


def test_unset_owner_refuses_the_remote_port(session, monkeypatch):
    monkeypatch.setattr(server, "Session", lambda slug: Session(slug, session.dir.parent))
    remote = TestClient(gate.TailnetGate(server.app, 80, None))
    r = remote.get("/api/health", headers={gate.LOGIN_HEADER.decode(): OWNER})
    assert r.status_code == 403


def test_ports_and_owner_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("VIEW_CONCEPT_REMOTE_PORT", raising=False)
    monkeypatch.delenv("VIEW_CONCEPT_OWNER_LOGIN", raising=False)
    assert gate.remote_port() == 5081 and gate.owner_login() is None
    monkeypatch.setenv("VIEW_CONCEPT_REMOTE_PORT", "6000")
    monkeypatch.setenv("VIEW_CONCEPT_OWNER_LOGIN", OWNER)
    assert gate.remote_port() == 6000 and gate.owner_login() == OWNER
