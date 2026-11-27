"""The frame head's stylesheet: tokens_css() carries the theme tokens, the prose width
and the base style with its component kit, every base-style rule a default."""

from __future__ import annotations

import re

from view_concept import frame

_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _base_selectors() -> list[str]:
    """The selector of each rule of the base style (static/frame.css)."""
    css = _COMMENT.sub("", (frame.STATIC / "frame.css").read_text(encoding="utf-8"))
    return [" ".join(s.split()) for s in re.findall(r"([^{}]+)\{", css)]


def _single_where(selector: str) -> bool:
    """Whether `selector` is one :where(...) group from start to end: zero specificity."""
    if not selector.startswith(":where("):
        return False
    depth = 0
    for i, ch in enumerate(selector):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(selector) - 1
    return False


def test_tokens_css_carries_tokens_prose_width_and_base_style() -> None:
    css = frame.tokens_css()
    assert "--ink:" in css and "--om-" in css
    assert "max-width: 78ch" in css
    base = (frame.STATIC / "frame.css").read_text(encoding="utf-8")
    assert css.endswith(base)
    assert css.index("max-width: 78ch") < css.index(base)


def test_every_base_style_selector_has_zero_specificity() -> None:
    selectors = _base_selectors()
    assert selectors
    for selector in selectors:
        assert _single_where(selector), selector


def test_type_scale_variables_exist() -> None:
    css = frame.tokens_css()
    for name, size in (("--fs-body", "14px"), ("--fs-small", "12px"), ("--fs-label", "11px")):
        assert f"{name}: {size}" in css
    assert re.search(r":where\(body\)\s*\{[^}]*font-size: var\(--fs-body\)", css)
    assert re.search(r":where\(body\)\s*\{[^}]*line-height: 1\.64", css)
    assert re.search(r":where\(body\)\s*\{[^}]*font-family: var\(--mono\)", css)


def test_kit_classes_are_defined() -> None:
    selectors = " ".join(_base_selectors())
    kit = (".label", ".chip", ".panel", ".pair", ".steps", ".callout", ".defaults")
    tabs = (".tab-row", ".tab", '.tab[aria-selected="true"]', ".tab-panel[hidden]")
    for cls in kit + tabs:
        assert cls in selectors, cls


# ---- block marks and runs of text ----

GATE = """<html><head><style>p { color: red }</style></head><body>
<h2>The gate</h2>
<p>A gate removes segments that are mostly <strong>silence</strong> &amp; noise.</p>
<ul><li>the ratio <em>r</em><ul><li>on 20 ms frames</li></ul> per segment</li><li>two
<li>three</ul>
<table><tr><td>a<td>b &lt; c</tr></table>
<template><p>kept for later</p></template>
<script>
chart.append(Object.assign(document.createElement("p"), {textContent: "<p>42</p>"}));
</script>
</body></html>"""


def test_block_marks_number_the_blocks_written_in_the_file():
    marked = frame.mark_blocks(GATE)
    assert re.sub(r' data-block="\d+"', "", marked) == GATE
    assert re.findall(r'<(\w+) data-block="(\d+)"', marked) == [
        ("h2", "1"),
        ("p", "2"),
        ("li", "3"),
        ("li", "4"),
        ("li", "5"),
        ("li", "6"),
        ("td", "7"),
        ("td", "8"),
    ]
    # The paragraph the script draws, and the template's, have none.
    assert "<p>kept for later</p>" in marked and '"<p>42</p>"' in marked


def _texts(n: int) -> list[str]:
    runs = frame.block_runs(GATE, n)
    assert runs is not None
    return runs.texts


def test_a_blocks_runs_of_text_stop_at_its_nested_block():
    runs = frame.block_runs(GATE, 3)
    assert runs is not None
    assert runs.texts == ["the ratio ", "r"]  # " per segment", after the nested list, is none
    assert GATE[slice(*runs.content)] == "the ratio <em>r</em>"
    assert _texts(2) == [  # entities decoded, as the frame reads them
        "A gate removes segments that are mostly ",
        "silence",
        " & noise.",
    ]
    assert _texts(5) == ["two\n"]  # closed by the next <li>
    assert _texts(8) == ["b < c"]
    assert frame.block_runs(GATE, 9) is None


def test_replacing_runs_keeps_the_tags_and_escapes_the_new_text():
    after = ["A gate drops a segment when its ", "silence", " ratio < 1 & more."]
    new, before, written = frame.replace_runs(GATE, 2, after)
    assert before == "A gate removes segments that are mostly <strong>silence</strong> &amp; noise."
    assert written == (
        "A gate drops a segment when its <strong>silence</strong> ratio &lt; 1 &amp; more."
    )
    assert new == GATE.replace(before, written)


def test_an_element_the_file_holds_empty_gets_no_mark():
    doc = '<table><tr><td>a</td><td id="n">  </td><td></td></tr></table><p>b</p>'
    marked = frame.mark_blocks(doc)
    assert re.findall(r'<(\w+) data-block="(\d+)"', marked) == [("td", "1"), ("p", "2")]
    assert '<td id="n">  </td><td></td>' in marked
    assert _runs(doc, 2) == ["b"]


def _runs(doc: str, n: int) -> list[str]:
    runs = frame.block_runs(doc, n)
    assert runs is not None
    return runs.texts
