"""Markdown rendering shared by the page (server.py) and the published page (publish.py),
so a section reads the same in both. Kept apart from the server so publishing does not
import FastAPI."""

from __future__ import annotations

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

md = (
    MarkdownIt("commonmark", {"html": True})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, double_inline=True)
)
