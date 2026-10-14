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
