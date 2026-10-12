"""The section frame: the separate web page an HTML section runs in.

An HTML section (sections/<id>.html, see store.py) is not pasted into the page: the page
draws it in an <iframe> whose `sandbox` gives it an origin of its own, as claude.ai draws
an artifact. Its scripts run there, its styles apply only there, and neither it nor the
page can reach into the other. The separation is between the section and the page only:
the section may load from any site.

The page does not serve the section's file as it is: it adds a short head, FRAME_JS, which
tells the page the height of the section's content (the frame takes that height). The
published page and the vault note add the same head. Kept apart from the server so
publishing and exporting do not import FastAPI.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent / "static"
# What the iframe of a section frame allows: scripts, and links that open a new tab.
# No allow-same-origin: the section gets an origin of its own, so it cannot reach the page.
SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms"

_HEAD = re.compile(r"<head\b[^>]*>", re.I)
_HTML = re.compile(r"<html\b[^>]*>", re.I)
_DOCTYPE = re.compile(r"^\s*<!doctype\b[^>]*>", re.I)


def frame_js() -> str:
    return (STATIC / "frame.js").read_text(encoding="utf-8")


def inject(document: str, head: str) -> str:
    """`document` with `head` written at the start of its head: after <head>, else after
    <html>, else after the doctype, else at the very start. The section's own head comes
    after it, so the section can override what it sets."""
    for pattern in (_HEAD, _HTML, _DOCTYPE):
        m = pattern.search(document)
        if m:
            return document[: m.end()] + head + document[m.end() :]
    return head + document
