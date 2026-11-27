"""The page's copy of a Markdown section: each block's source span, its editable text, and
the save that writes the markers back around new text."""

from __future__ import annotations

import re

from view_concept.render import blocks, md, render_page, replace_block

SECTION = r"""## Thresholds ##

A **gate** sits before
  the transcriber.

- the silence ratio of a segment,
  measured on 20 ms frames
  - frames under -40 dB count as silent
- the threshold

> Silence is not noise:
> a quiet room still has a floor.

| silence gate | ratio or length |
|---|---|
| ratio \| x | length |

$$
r > 0.8
$$
"""


def _save(span: str, new: str) -> tuple[str, str, str]:
    return replace_block(SECTION, blocks(SECTION)[span], new)


def test_each_block_carries_its_span_and_editable_text():
    html, spans = render_page(SECTION)
    assert spans == {
        "L0-1": "Thresholds",
        "L2-4": "A **gate** sits before\nthe transcriber.",
        "L5-7": "the silence ratio of a segment,\nmeasured on 20 ms frames",
        "L7-8": "frames under -40 dB count as silent",
        "L8-9": "the threshold",
        "L10-12": "Silence is not noise:\na quiet room still has a floor.",
        "C13:2-14": "silence gate",
        "C13:17-32": "ratio or length",
        "C15:2-12": "ratio | x",
        "C15:15-21": "length",
    }
    assert '<h2 data-span="L0-1">' in html
    assert '<li data-span="L5-7">' in html  # a tight list: the <li> carries it
    assert '<td data-span="C15:2-12">' in html
    # A display maths block opens nothing.
    assert html.count("data-span") == len(spans)


def test_the_spans_change_no_rendered_word():
    """The green highlight compares the rendered words of the page's copy with the shared
    renderer's: the span attributes change none of them."""
    html, _ = render_page(SECTION)
    assert re.sub(r' data-span="[^"]*"', "", html) == md.render(SECTION)


def test_a_loose_list_item_opens_on_its_first_paragraph():
    text = "1. one\n\n   two\n2. three\n"
    html, spans = render_page(text)
    assert spans == {"L0-1": "one", "L2-3": "two", "L3-4": "three"}
    assert '<li>\n<p data-span="L0-1">one</p>' in html


def test_a_paragraph_save_replaces_its_lines_only():
    new, before, after = _save("L2-4", "A gate drops a segment\nwhen its **ratio** exceeds it.")
    assert new == SECTION.replace(
        "A **gate** sits before\n  the transcriber.",
        "A gate drops a segment\n  when its **ratio** exceeds it.",
    )
    assert before == "A **gate** sits before\n  the transcriber."
    assert after == "A gate drops a segment\n  when its **ratio** exceeds it."


def test_a_heading_save_keeps_its_markers_on_one_line():
    new, before, after = _save("L0-1", "The\nthresholds")
    assert new.splitlines()[0] == "## The thresholds ##"
    assert (before, after) == ("## Thresholds ##", "## The thresholds ##")


def test_a_list_item_save_leaves_its_nested_item_in_place():
    new, _, after = _save("L5-7", "the ratio\nof silent frames\nin a segment")
    assert after == "- the ratio\n  of silent frames\n  in a segment"
    assert "  in a segment\n  - frames under -40 dB count as silent\n- the threshold" in new


def test_a_quoted_paragraph_save_puts_the_quote_back_on_each_line():
    _, _, after = _save("L10-12", "Silence is not noise.\n\nA quiet room\nhas a floor.")
    assert after == "> Silence is not noise.\n>\n> A quiet room\n> has a floor."


def test_a_cell_save_escapes_a_typed_pipe_and_stays_on_one_line():
    new, before, after = _save("C15:2-12", "ratio | length\nor both")
    assert (before, after) == (r"ratio \| x", r"ratio \| length or both")
    assert new.splitlines()[15] == r"| ratio \| length or both | length |"
    _, spans = render_page(new)
    assert spans["C15:2-25"] == "ratio | length or both"


def test_an_empty_padded_cell_saves_inside_its_pipes():
    text = "| a | b |\n|---|---|\n| a |   |\n"
    spans = render_page(text)[1]
    assert spans["C2:6-6"] == ""
    new, before, after = replace_block(text, blocks(text)["C2:6-6"], "x")
    assert (before, after) == ("", "x")
    assert new.splitlines()[2] == "| a | x  |"


def test_an_empty_heading_saves_as_a_heading():
    text = "#\n\nbody\n"
    new, _, after = replace_block(text, blocks(text)["L0-1"], "foo")
    assert after == "# foo"
    assert render_page(new)[0].startswith("<h1")
