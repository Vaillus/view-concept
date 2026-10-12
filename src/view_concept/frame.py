"""The section frame: the separate web page an HTML section runs in.

An HTML section (sections/<id>.html, see store.py) is not pasted into the page: the page
draws it in an <iframe> whose `sandbox` gives it an origin of its own, as claude.ai draws
an artifact. Its scripts run there, its styles apply only there, and neither it nor the
page can reach into the other. The separation is between the section and the page only:
the section may load from any site.

The page does not serve the section's file as it is: it adds a short head, which
defines the theme tokens (`tokens_css`) and loads static/frame.js. The theme tokens are
the named colours of the page (--bg, --ink, --accent, --flag… of terminal.css) and its
light or dark mode: a frame is a separate web page, where the page's names would mean
nothing, so the head brings them, and the page tells the frame which theme it is in, at
load and at every change of theme. A section paints with var(--ink) and matches the page
without copying its palette. Where no page tells it, the section takes the page's default
theme: Catppuccin Latte in light mode, Tokyo Night in dark mode. frame.js also tells the
page the height of the section's content, which the frame takes, and brings passages
back across the separation: the reader's selection goes to the page, which comments or
asks on it as on a passage of a Markdown section; the page sends the passages its
comments and side threads quote, which frame.js highlights, and a passage to reveal.
Term underlines and change highlights stay outside the frame. The published page and
the vault note add the same head. Kept apart from the server so publishing and exporting
do not import FastAPI.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).parent / "static"
# What the iframe of a section frame allows: scripts, and links that open a new tab.
# No allow-same-origin: the section gets an origin of its own, so it cannot reach the page.
SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms"

_HEAD = re.compile(r"<head\b[^>]*>", re.I)
_HTML = re.compile(r"<html\b[^>]*>", re.I)
_DOCTYPE = re.compile(r"^\s*<!doctype\b[^>]*>", re.I)


# The semantic layer of the omarchy skin: the first :root block of terminal.css.
_TOKENS_BLOCK = re.compile(r"^:root \{.*?^\}", re.M | re.S)


def tokens_css() -> str:
    """The theme tokens: every theme's palette (themes.css) and the semantic names bound
    onto it (the :root block of terminal.css), without the skin's styles."""
    terminal = (STATIC / "terminal.css").read_text(encoding="utf-8")
    m = _TOKENS_BLOCK.search(terminal)
    if not m:
        raise RuntimeError("terminal.css has no :root block of theme tokens")
    return (STATIC / "themes.css").read_text(encoding="utf-8") + "\n" + m.group(0) + "\n"


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


class _VisibleText(HTMLParser):
    """Collects the text of a document outside its <script> and <style> elements."""

    HIDDEN = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(document: str) -> str:
    """The visible text of an HTML section: the words written in its file, outside its
    scripts and styles, whitespace collapsed. Text a script draws when the section runs
    does not count: the precedence check and the agents' context run without a browser."""
    parser = _VisibleText()
    parser.feed(document)
    parser.close()
    return " ".join(" ".join(parser.parts).split())
