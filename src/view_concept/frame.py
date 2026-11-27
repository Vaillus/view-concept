"""The section frame: the separate web page an HTML section runs in.

An HTML section (sections/<id>.html, see store.py) is not pasted into the page: the page
draws it in an <iframe> whose `sandbox` gives it an origin of its own, as claude.ai draws
an artifact. Its scripts run there, its styles apply only there, and neither it nor the
page can reach into the other. The separation is between the section and the page only:
the section may load from any site.

The page does not serve the section's file as it is: it adds a short head, which defines
the theme tokens (`tokens_css`), keeps the prose written straight in the body and the
figure captions to the page's text width, centred, adds the base style (static/frame.css:
the Markdown sections' size and line height, a type scale, data tables that scroll
sideways, and the component kit, classes such as .label, .panel or .tabs a section reuses
instead of inventing its own), and loads static/frame.js. The base style is a default:
each of its rules has zero specificity (:where()), so a section's own rule wins. The theme
tokens are the named colours of the page (--bg, --ink, --accent, --flag… of
terminal.css) and its light or dark mode: a frame is a separate web page, where the
page's names would mean nothing, so the head brings them, and the page tells the frame
which theme it is in, at load and at every change of theme. A section paints with
var(--ink) and matches the page without copying its palette. Where no page tells it, the
section takes the page's default theme: Catppuccin Latte in light mode, Tokyo Night in
dark mode. frame.js also tells the page the height of the section's content, which the
frame takes, and brings passages back across the separation: the reader's selection goes
to the page, which comments or asks on it as on a passage of a Markdown section; the
page sends the passages its comments and side threads quote, which frame.js highlights,
and a passage to reveal; a click on a side thread's passage goes to the page, which
opens that thread. The page also sends the words added since the highlight baseline,
found by comparing the file's visible text now and then, and the lexicon terms and
audited words, which frame.js underlines by painting over the words, never wrapping
them; the term under the pointer goes back to the page, which shows its tip. The
published page and the vault note add the same head. Kept apart from the server so
publishing and exporting do not import FastAPI.

An inline edit opens one block of an explanation section: a paragraph, a list item, a
heading or a table cell. The page cannot find an HTML section's block by its lines, so
the server writes a block mark on each one as it serves the file to the frame
(`mark_blocks`: `data-block="<n>"`, counted in document order outside scripts, styles and
templates), never in the file; a block a script draws has none and does not open. The
text an edit changes is the block's runs of text, the text nodes between its tags (a
nested block's left out), and the save finds block n again in the file with the same
parser (`block_runs`, `replace_runs`), so the tags stay as they are.
"""

from __future__ import annotations

import html
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

# The frame is wider than the page's text column, for the figures; the prose written
# straight in the body, and every figure caption, keeps that column's width and is
# centred on it, as the prose of a Markdown section. The centring is !important, since a
# section's own `p { margin: … }` would undo it; the width has no weight (:where()), so a
# section may widen its prose.
_PROSE_CSS = (
    "body > :where(p, ul, ol, blockquote, h3, h4), :where(figcaption) "
    "{ max-width: 78ch; margin-left: auto !important; margin-right: auto !important; }\n"
)


def tokens_css() -> str:
    """The stylesheet of a frame head: the theme tokens, that is every theme's palette
    (themes.css) and the semantic names bound onto it (the :root block of terminal.css),
    without the skin's styles; the width of the section's prose; and the base style with
    its component kit (frame.css), last, every rule of it overridable by the section."""
    terminal = (STATIC / "terminal.css").read_text(encoding="utf-8")
    m = _TOKENS_BLOCK.search(terminal)
    if not m:
        raise RuntimeError("terminal.css has no :root block of theme tokens")
    themes = (STATIC / "themes.css").read_text(encoding="utf-8")
    base = (STATIC / "frame.css").read_text(encoding="utf-8")
    return themes + "\n" + m.group(0) + "\n" + _PROSE_CSS + base


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


# ---- block marks: the blocks of an HTML section an inline edit opens ----

# The elements that are blocks: a paragraph, a list item, a heading, a table cell.
BLOCK_TAGS = frozenset({"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th"})
# Elements whose content is no text of the section: neither marked nor a run.
_UNREAD = frozenset({"script", "style", "template"})
# Elements with no end tag.
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
    | {"track", "wbr", "param"}
)
# A start tag that closes an open <p>, as the browser does.
_CLOSES_P = frozenset(
    {"address", "article", "aside", "blockquote", "details", "dialog", "div", "dl", "dd"}
    | {"dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4"}
    | {"h5", "h6", "header", "hgroup", "hr", "li", "main", "menu", "nav", "ol", "p", "pre"}
    | {"section", "table", "ul"}
)
# The elements a closing search stops at, by the tag that searches.
_STOPS = {
    "p": frozenset({"table", "td", "th", "button", "template", "caption"}),
    "li": frozenset({"ul", "ol", "table", "td", "th"}),
    "cell": frozenset({"table"}),
}


class Block:
    """Block n of an HTML section as its file holds it: where its start tag's name ends
    (the mark goes there), its content (from the end of its start tag to its end tag or
    its first nested block), and its runs of text, each as a raw range of the file."""

    def __init__(self, name_end: int, open_end: int) -> None:
        self.name_end = name_end
        self.open_end = open_end
        self.content_end: int | None = None
        self.runs: list[list[int]] = []


class _Blocks(HTMLParser):
    """Finds the blocks of a document in order, outside its scripts, styles and
    templates, closing the elements the browser closes without an end tag (a <p> before
    a block, a <li> before the next, a cell before the next cell or row)."""

    def __init__(self, document: str) -> None:
        super().__init__(convert_charrefs=True)
        self.size = len(document)
        self.starts = [0] + [i + 1 for i, ch in enumerate(document) if ch == "\n"]
        self.blocks: list[Block] = []
        # The open elements: tag, its block when it is one, where its start tag starts.
        self.stack: list[tuple[str, Block | None, int]] = []
        self.unread = 0
        self.run: tuple[Block, int] | None = None  # the run being read: its block, start

    def here(self) -> int:
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def end_run(self, at: int) -> None:
        if self.run is not None:
            block, start = self.run
            if at > start:
                block.runs.append([start, at])
            self.run = None

    def pop_through(self, i: int, at: int) -> None:
        """Close the open elements from the top of the stack down to index i."""
        while len(self.stack) > i:
            _, block, _ = self.stack.pop()
            if block is not None and block.content_end is None:
                block.content_end = at

    def find(self, tags: frozenset[str] | set[str], stops: frozenset[str]) -> int | None:
        for i in range(len(self.stack) - 1, -1, -1):
            tag = self.stack[i][0]
            if tag in tags:
                return i
            if tag in stops:
                return None
        return None

    def implied_ends(self, tag: str, at: int) -> None:
        if tag in _CLOSES_P and (i := self.find({"p"}, _STOPS["p"])) is not None:
            self.pop_through(i, at)
        if tag == "li" and (i := self.find({"li"}, _STOPS["li"])) is not None:
            self.pop_through(i, at)
        if tag in ("td", "th") and (i := self.find({"td", "th"}, _STOPS["cell"])) is not None:
            self.pop_through(i, at)
        rows = ("tr", "tbody", "thead", "tfoot")
        if tag in rows and (i := self.find({"tr"}, _STOPS["cell"])) is not None:
            self.pop_through(i, at)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        at = self.here()
        self.end_run(at)
        if self.unread:
            self.unread += tag in _UNREAD
            return
        if tag in _UNREAD:
            self.unread = 1
            return
        self.implied_ends(tag, at)
        if tag in _VOID:
            return
        block = None
        if tag in BLOCK_TAGS:
            text = self.get_starttag_text() or ""
            block = Block(at + 1 + len(tag), at + len(text))
            # The first nested block ends the content of every block it is in, at the
            # start of that block's child that holds it.
            for i, (_, outer, _) in enumerate(self.stack):
                if outer is not None and outer.content_end is None:
                    outer.content_end = self.stack[i + 1][2] if i + 1 < len(self.stack) else at
            self.blocks.append(block)
        self.stack.append((tag, block, at))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.end_run(self.here())

    def handle_endtag(self, tag: str) -> None:
        at = self.here()
        self.end_run(at)
        if self.unread:
            self.unread -= tag in _UNREAD
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self.pop_through(i, at)
                return

    def handle_data(self, data: str) -> None:
        if self.unread or self.run is not None:
            return  # a script's text, or the rest of the run being read
        block = next((b for _, b, _ in reversed(self.stack) if b is not None), None)
        if block is not None:
            self.run = (block, self.here())

    def handle_comment(self, data: str) -> None:  # a comment node ends a text node
        self.end_run(self.here())

    handle_pi = unknown_decl = handle_comment

    def close(self) -> None:
        super().close()
        self.end_run(self.size)
        self.pop_through(0, self.size)


def _blocks(document: str) -> list[Block]:
    parser = _Blocks(document)
    parser.feed(document)
    parser.close()
    return parser.blocks


def mark_blocks(document: str) -> str:
    """The document a section frame receives: `data-block="<n>"` (n = 1, 2, … in document
    order) written on the start tag of every paragraph, list item, heading and table cell
    outside its scripts, styles and templates. The file never holds the marks: a block a
    script draws has none, and does not open."""
    out, last = [], 0
    for n, block in enumerate(_blocks(document), 1):
        out += [document[last : block.name_end], f' data-block="{n}"']
        last = block.name_end
    return "".join(out) + document[last:]


class BlockRuns:
    """Block n found in a document: its runs of text, raw ranges and text (entities
    decoded, as the frame reads them), and its content's raw range."""

    def __init__(self, document: str, block: Block) -> None:
        self.ranges = [(a, b) for a, b in block.runs]
        self.texts = [html.unescape(document[a:b]) for a, b in self.ranges]
        self.content = (block.open_end, block.content_end or len(document))


def block_runs(document: str, n: int) -> BlockRuns | None:
    """Block n of the document (counted as `mark_blocks` counts), or None when it has
    fewer blocks. Its runs of text are its text nodes in order, the content of a nested
    block, a script, a style or a template left out."""
    found = _blocks(document)
    if not 1 <= n <= len(found):
        return None
    return BlockRuns(document, found[n - 1])


def replace_runs(document: str, n: int, after: list[str]) -> tuple[str, str, str]:
    """`document` with the runs of text of block n replaced by `after` (one text per run):
    a run whose text changed is written with `&` and `<` escaped, the others keep their
    raw bytes. Returns (the new document, the block's raw content before, after)."""
    found = block_runs(document, n)
    if found is None or len(after) != len(found.ranges):
        raise ValueError(f"block {n} has not {len(after)} runs of text")
    out = document
    for (a, b), old, new in reversed(list(zip(found.ranges, found.texts, after, strict=True))):
        if new != old:
            out = out[:a] + new.replace("&", "&amp;").replace("<", "&lt;") + out[b:]
    changed = block_runs(out, n)
    assert changed is not None
    a, b = found.content
    c, d = changed.content
    return out, document[a:b], out[c:d]
