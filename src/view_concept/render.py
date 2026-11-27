"""Markdown rendering shared by the page (server.py) and the published page (publish.py),
so a section reads the same in both. Kept apart from the server so publishing does not
import FastAPI.

The page also renders its own copy of a Markdown section (`render_page`), with each block
an inline edit can open marked by its source span: the exact part of the section's file
the block was rendered from. A block is a paragraph, a list item, an ATX heading or a
table cell. Its span is written on its element as `data-span`, an opaque string the page
sends back when it saves the block:

- `L<s>-<e>`: lines s..e-1 of the file (0-based, markdown-it's `map`), for a paragraph, a
  heading, a list item (the lines of its first paragraph only: a nested item is a block
  of its own) and a quoted paragraph;
- `C<line>:<a>-<b>`: a table cell, characters a..b-1 of its row's line, the cell's
  trimmed content between its two pipes.

The `<p>` of a paragraph carries it; in a tight list, where the paragraph has no `<p>`,
the `<li>` does. The block's editable text leaves the Markdown markers of its lines out
(the `>` of a quote, a list marker and its indent, a heading's `#`s, a cell's spaces; a
cell's `\\|` reads `|`), and `replace_block` writes them back around the new text. A
block whose lines markdown-it read otherwise than as written (a tab it expanded) gets no
span and does not open. The published page keeps `md`, so its HTML carries no span, and
the green highlight, which compares rendered words, is the same with or without them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin

md = (
    MarkdownIt("commonmark", {"html": True})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, double_inline=True)
)

# A list marker in a line's prefix, which a continuation line writes as spaces.
_LIST_MARKER = re.compile(r"[-*+]|\d{1,9}[.)]")
# What a line's prefix may hold: indentation, the `>` of a quote, list markers.
_PREFIX = re.compile(r"[ \t>*+\-\d.)]*")
# The container prefix of a table row: the `>` of quotes and indentation.
_ROW_PREFIX = re.compile(r"(?:[ \t]*>)*[ \t]*")


@dataclass
class Block:
    """A block of a Markdown section, found in its file: its span, its editable text, and
    what saving needs to write the markers back."""

    span: str
    text: str
    kind: str  # "lines" (a paragraph, a list item, a quote), "heading" or "cell"
    start: int  # its first line
    end: int  # one past its last line
    prefixes: list[str] = field(default_factory=list)  # each line's markers and indent
    suffix: str = ""  # a heading's closing `#`s and trailing spaces
    a: int = 0  # a cell's content: characters a..b-1 of line `start`
    b: int = 0


def _line_block(lines: list[str], start: int, end: int, content: str) -> Block | None:
    """A paragraph (alone, in a quote or in a list item) as lines start..end-1, its
    editable text taken from markdown-it's content: each line's text with its markers
    and indent left out."""
    parts = content.split("\n")
    if len(parts) != end - start:
        return None
    prefixes, texts = [], []
    for src, part in zip(lines[start:end], parts, strict=True):
        text = part.lstrip(" \t")
        kept, bare = text.rstrip(), src.rstrip()
        if not kept or not bare.endswith(kept):
            return None
        prefix = bare[: len(bare) - len(kept)]
        if not _PREFIX.fullmatch(prefix):
            return None
        prefixes.append(prefix)
        texts.append(text)
    texts[-1] = texts[-1].rstrip()
    return Block(f"L{start}-{end}", "\n".join(texts), "lines", start, end, prefixes)


def _heading_block(lines: list[str], start: int, content: str) -> Block | None:
    """An ATX heading's one line: its text between its `#`s and the closing ones. An
    empty heading's prefix (`#` alone) gains the space a heading's text needs after it."""
    line = lines[start]
    m = re.search(r"#{1,6}[ \t]*", line)
    if m is None or not _PREFIX.fullmatch(line[: m.start()]):
        return None
    k = m.end()
    if not line[k:].startswith(content):
        return None
    prefix = line[:k]
    if not prefix.endswith((" ", "\t")):
        prefix += " "
    return Block(
        f"L{start}-{start + 1}",
        content,
        "heading",
        start,
        start + 1,
        [prefix],
        suffix=line[k + len(content) :],
    )


def _cell_ranges(line: str) -> list[tuple[int, int]]:
    """The cells of a table row's line, each as the range of its raw text between two
    unescaped pipes, split as markdown-it splits it: a leading and a trailing pipe open
    and close the row."""
    lead = _ROW_PREFIX.match(line)
    start = lead.end() if lead else 0
    stop = len(line.rstrip())
    body = line[start:stop]
    cuts, escaped = [], False
    for i, ch in enumerate(body):
        if ch == "|" and not escaped:
            cuts.append(start + i)
        escaped = ch == "\\"
    bounds = [start - 1, *cuts, stop]
    ranges = [(bounds[i] + 1, bounds[i + 1]) for i in range(len(bounds) - 1)]
    if body.startswith("|"):
        ranges = ranges[1:]
    if cuts and cuts[-1] == stop - 1 and len(body) > 1:
        ranges = ranges[:-1]
    return ranges


def _cell_block(line: str, n: int, raw: tuple[int, int], content: str) -> Block | None:
    """A table cell: the trimmed raw text of its range, checked against markdown-it's
    content, where `\\|` reads `|`. An empty cell's span is the empty point one space
    past its opening pipe, so a save inserts there and keeps the padding."""
    a, b = raw
    seg = line[a:b]
    if seg.strip():
        a += len(seg) - len(seg.lstrip())
        b -= len(seg) - len(seg.rstrip())
    else:
        a = b = min(a + 1, b)
    text = line[a:b].replace("\\|", "|")
    if text != content:
        return None
    return Block(f"C{n}:{a}-{b}", text, "cell", n, n + 1, a=a, b=b)


def _annotate(text: str) -> tuple[list[Token], dict[str, Any], dict[str, Block]]:
    """The tokens of `text` with `data-span` set on each block's element, the env the
    renderer needs, and the blocks by span."""
    env: dict[str, Any] = {}
    tokens = md.parse(text, env)
    lines = text.split("\n")
    found: dict[str, Block] = {}
    row: tuple[int, list[tuple[int, int]]] | None = None
    cell = 0
    for i, tok in enumerate(tokens):
        block, target = None, tok
        if tok.type == "paragraph_open" and tok.map:
            block = _line_block(lines, tok.map[0], tok.map[1], tokens[i + 1].content)
            if tok.hidden:
                # A tight list's item: its <li> carries the span, when the paragraph opens it.
                target = tokens[i - 1]
                if target.type != "list_item_open":
                    block = None
        elif tok.type == "heading_open" and tok.map and tok.markup.startswith("#"):
            block = _heading_block(lines, tok.map[0], tokens[i + 1].content)
        elif tok.type == "tr_open" and tok.map:
            row, cell = (tok.map[0], _cell_ranges(lines[tok.map[0]])), 0
        elif tok.type in ("th_open", "td_open") and row is not None:
            n, ranges = row
            if cell < len(ranges):
                block = _cell_block(lines[n], n, ranges[cell], tokens[i + 1].content)
            cell += 1
        if block is not None:
            target.attrSet("data-span", block.span)
            found[block.span] = block
    return tokens, env, found


def render_page(text: str) -> tuple[str, dict[str, str]]:
    """The page's copy of a Markdown section: its HTML with `data-span` on each block an
    inline edit opens, and each block's editable text by span."""
    tokens, env, found = _annotate(text)
    html = md.renderer.render(tokens, md.options, env)
    return html, {span: b.text for span, b in found.items()}


def blocks(text: str) -> dict[str, Block]:
    """The blocks of a Markdown section, by span."""
    return _annotate(text)[2]


def _continuation(prefix: str) -> str:
    """The prefix of a line added after a block's last line: the first line's, its list
    markers written as spaces."""
    return _LIST_MARKER.sub(lambda m: " " * len(m.group()), prefix)


def replace_block(text: str, block: Block, new: str) -> tuple[str, str, str]:
    """`text` with `block`'s editable text replaced by `new`, its markers written back:
    each new line takes the old line's prefix while there is one, then the first line's
    with its list markers as spaces, an empty line that prefix with no trailing space; a
    heading or a cell stays one line, and a `|` typed in a cell is written `\\|`.
    Returns (the new file, the block's raw text before, after)."""
    lines = text.split("\n")
    if block.kind == "cell":
        cell = " ".join(new.split("\n")).replace("|", "\\|")
        line = lines[block.start]
        lines[block.start] = line[: block.a] + cell + line[block.b :]
        return "\n".join(lines), line[block.a : block.b], cell
    if block.kind == "heading":
        new_lines = [block.prefixes[0] + " ".join(new.split("\n")) + block.suffix]
    else:
        new_lines = []
        for i, part in enumerate(new.split("\n")):
            prefix = block.prefixes[i] if i < len(block.prefixes) else ""
            if i >= len(block.prefixes):
                prefix = _continuation(block.prefixes[0])
            new_lines.append(prefix + part if part.strip() else prefix.rstrip())
    before = "\n".join(lines[block.start : block.end])
    lines[block.start : block.end] = new_lines
    return "\n".join(lines), before, "\n".join(new_lines)
