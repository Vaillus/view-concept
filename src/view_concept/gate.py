"""The tailnet gate: who may reach the page through the remote port.

The server listens on two ports in one process. The local port (VIEW_CONCEPT_PORT, 5080)
answers the Mac's browser and the agents' commands, with no check. The remote port
(VIEW_CONCEPT_REMOTE_PORT, 5081) is the only one `tailscale serve` exposes, and serves the
whole page behind the tailnet gate: Tailscale forwards each request with the sender's
login in `Tailscale-User-Login` (absent for a tagged device), and the gate lets a request
through only when that header appears exactly once and equals the owner login
(VIEW_CONCEPT_OWNER_LOGIN). Any other request gets a 403. Copied from anki-assistant's
gate.
"""

from __future__ import annotations

import json
import os

from starlette.types import ASGIApp, Receive, Scope, Send

LOGIN_HEADER = b"tailscale-user-login"
DEFAULT_REMOTE_PORT = 5081


def remote_port() -> int:
    return int(os.environ.get("VIEW_CONCEPT_REMOTE_PORT") or DEFAULT_REMOTE_PORT)


def owner_login() -> str | None:
    return os.environ.get("VIEW_CONCEPT_OWNER_LOGIN") or None


def allows(logins: list[str], owner: str | None) -> bool:
    """Whether a request carrying these `Tailscale-User-Login` values may pass: exactly one,
    equal to the owner login (surrounding spaces ignored). An unset owner refuses all."""
    if not owner or not owner.strip():
        return False
    return len(logins) == 1 and logins[0].strip() == owner.strip()


async def _forbid(scope: Scope, send: Send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": "Forbidden"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class TailnetGate:
    """One ASGI app over both listening sockets: a request that arrived on the remote port,
    or on a port it cannot tell (fail closed), passes only when `allows` lets it; a request
    on any other port goes straight to the app. The port comes from the socket, never from
    the request."""

    def __init__(self, app: ASGIApp, remote_port: int, owner: str | None) -> None:
        self.app = app
        self.remote_port = remote_port
        self.owner = owner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        server = scope.get("server")
        if server is not None and server[1] != self.remote_port:
            await self.app(scope, receive, send)
            return
        logins = [v.decode("latin-1") for k, v in scope["headers"] if k.lower() == LOGIN_HEADER]
        if allows(logins, self.owner):
            await self.app(scope, receive, send)
            return
        await _forbid(scope, send)
