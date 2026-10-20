"""The notice when the agent is done: the server tells a phone when a session starts
waiting for the user.

A session waits for the user when its agent has stopped until the user answers: open
questions (in scoping, or the phase awaiting-answer), or a button the page shows
(« Approve plan », « Approve model », « Write docs », « Create PR ») with no answer sent yet. When a
session starts waiting, or waits on something new (another question), the server sends a
notice to every subscribed phone. A stalled run (an agent that stopped with an error, a
launch that never started) sends none: it shows only in the page.

Notices come only to the home-screen app: on an iPhone a page open in the browser cannot
receive them. The user turns them on once per phone (« notices » in the ⋯ menu): the app
installs its service worker (static/sw.js, served at /sw.js), and gives the server a
subscription, kept in <home>/push.json with the server's own keys (VAPID). From then on
every session of the server notifies that phone. The server hands each notice to the push
service of the phone's maker, which delivers it: the machine needs the internet, and the
notice crosses the push service, encrypted for the phone. The service worker shows it
under the session's tag, so a session's new notice replaces its previous one, and shows
none while that session is open and in view on the phone.

push.json: {public, private (PEM), subscriptions: [{endpoint, keys}], notified: {slug:
the waiting it was last notified of, "" once it stopped waiting}}."""

from __future__ import annotations

import base64
import json
import sys
import threading
from pathlib import Path
from typing import Any

from .store import HOME, SESSIONS, SLUG_RE, Session, SessionError, _read_json, _write_json

PUSH = HOME / "push.json"
_LOCK = threading.Lock()
# Who the push service may contact about this server's notices (VAPID's `sub` claim).
CONTACT = "mailto:view-concept@localhost"
APPROVALS = {
    "awaiting-approval": ("approve-plan", "plan ready · waiting for your approval"),
    "awaiting-model": ("approve-model", "model ready · waiting for your approval"),
    "awaiting-docs": ("write-docs", "code carries the model · waiting for « Write docs »"),
    "awaiting-pr": ("create-pr", "docs written · waiting for « Create PR »"),
}


class PushError(SessionError):
    pass


def _path(path: Path | None) -> Path:
    return path or PUSH


def _load(path: Path | None = None) -> dict[str, Any]:
    data = _read_json(_path(path), {})
    data.setdefault("subscriptions", [])
    data.setdefault("notified", {})
    return data


def _keys(path: Path | None = None) -> dict[str, Any]:
    """The server's VAPID keys, made the first time they are needed."""
    data = _load(path)
    if data.get("public") and data.get("private"):
        return data
    try:
        from cryptography.hazmat.primitives import serialization
        from py_vapid import Vapid02
    except ImportError as e:
        raise PushError(f"notices need pywebpush: reinstall view-concept ({e})") from e
    v = Vapid02()
    v.generate_keys()
    raw = v.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    data["public"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    data["private"] = v.private_pem().decode()
    _write_json(_path(path), data)
    return data


def public_key(path: Path | None = None) -> str:
    """The key a phone subscribes with (applicationServerKey)."""
    with _LOCK:
        return str(_keys(path)["public"])


def _sessions(root: Path | None = None) -> list[Session]:
    root = root or SESSIONS
    if not root.is_dir():
        return []
    return [
        Session(d.name, root)
        for d in sorted(root.iterdir())
        if SLUG_RE.match(d.name) and (d / "plan.json").exists()
    ]


def _waiting_key(s: Session) -> str:
    try:
        w = waiting(s)
    except SessionError:
        return ""
    return w[0] if w else ""


def subscribe(
    subscription: dict[str, Any], path: Path | None = None, root: Path | None = None
) -> None:
    """Keep a phone's subscription: from now on every session notifies it. A session
    already waiting when notices are turned on did not start waiting: no notice for it."""
    endpoint = str(subscription.get("endpoint", ""))
    keys = subscription.get("keys") or {}
    if not endpoint.startswith("https://") or not keys.get("p256dh") or not keys.get("auth"):
        raise PushError("not a push subscription")
    with _LOCK:
        data = _keys(path)
        subs = [s for s in data["subscriptions"] if s.get("endpoint") != endpoint]
        data["subscriptions"] = [*subs, {"endpoint": endpoint, "keys": keys}]
        for s in _sessions(root):
            data["notified"].setdefault(s.slug, _waiting_key(s))
        _write_json(_path(path), data)


def unsubscribe(endpoint: str, path: Path | None = None) -> None:
    with _LOCK:
        data = _load(path)
        data["subscriptions"] = [s for s in data["subscriptions"] if s.get("endpoint") != endpoint]
        _write_json(_path(path), data)


def waiting(s: Session) -> tuple[str, str] | None:
    """What session `s` waits for: (key, text of its notice), None when it waits for
    nothing. The key changes when it waits on something new."""
    status = s.read_status()
    phase = status.get("phase", "")
    since = str(status.get("since", ""))
    batches = s.read_comments()["batches"]
    if phase in APPROVALS:
        action, text = APPROVALS[phase]
        if any(b.get("action") == action and str(b.get("sent", "")) >= since for b in batches):
            return None  # answered: the agent is on its way
        return f"{phase}@{since}", text
    if phase not in ("scoping", "awaiting-answer"):
        return None
    open_ = [q for q in s.read_questions() if q.get("status") == "open"]
    if not open_:
        return None
    if any(b.get("action") == "go-on" and str(b.get("sent", "")) >= since for b in batches):
        return None  # the writer goes on
    n = len(open_)
    text = f"{n} question{'s' if n > 1 else ''}"
    if phase == "awaiting-answer":
        outline = [x.get("id") for x in s.read_plan().get("outline", [])]
        written = s.read_sections()
        anchors = [
            outline.index(q["section"]) + 1
            for q in open_
            if q.get("section") in outline and q.get("section") in written
        ]
        if anchors:
            text = f"paused after section {max(anchors)} · {text}"
    return "q:" + ",".join(sorted(str(q.get("id")) for q in open_)), text


def notices(path: Path | None = None, root: Path | None = None) -> list[dict[str, str]]:
    """The notices to send now: one per session that started waiting, or waits on
    something new, since the last check; records what each session waits for. Nothing
    while no phone is subscribed."""
    with _LOCK:
        data = _load(path)
        if not data["subscriptions"]:
            return []
        out = []
        notified = data["notified"]
        changed = False
        for s in _sessions(root):
            try:
                w = waiting(s)
                title = str(s.read_plan().get("title", s.slug))
            except SessionError:
                continue
            key = w[0] if w else ""
            if notified.get(s.slug, "") == key:
                continue
            notified[s.slug] = key
            changed = True
            if w:
                out.append({"slug": s.slug, "title": title, "body": w[1]})
        if changed:
            _write_json(_path(path), data)
        return out


def send(notice: dict[str, str], path: Path | None = None) -> int:
    """Send `notice` to every subscribed phone; returns how many took it. A subscription
    the push service says is gone is dropped."""
    try:
        from py_vapid import Vapid02
        from pywebpush import WebPushException, webpush
    except ImportError as e:
        raise PushError(f"notices need pywebpush: reinstall view-concept ({e})") from e
    with _LOCK:
        data = _keys(path)
    key = Vapid02.from_pem(data["private"].encode())
    sent, gone = 0, []
    for sub in data["subscriptions"]:
        try:
            webpush(
                sub,
                json.dumps(notice),
                vapid_private_key=key,
                vapid_claims={"sub": CONTACT},
                ttl=3600,
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                gone.append(sub["endpoint"])
            print(f"view-concept: notice not sent: {e}", file=sys.stderr)
        except Exception as e:  # the network: the next notice tries again
            print(f"view-concept: notice not sent: {e}", file=sys.stderr)
    for endpoint in gone:
        unsubscribe(endpoint, path)
    return sent


def check_and_send(path: Path | None = None) -> None:
    for notice in notices(path):
        send(notice, path)
