"""Session notes: one Obsidian note per session, the session's node in the vault's graph.

Off unless VIEW_CONCEPT_SESSION_NOTES names a folder. Then `view-concept new` writes
<folder>/<slug>.md for each session it creates, and `view-concept note` writes it for an
existing one. The note holds no text of the session: its frontmatter says which session
it is, and its links line holds a wikilink to each session it is linked to, which
Obsidian's graph draws as an edge.

    ---
    type: view-concept-session
    aliases:
      - "<title>"
    workflow: <workflow>
    url: <the session's page>
    ---
    Liens : [[<slug>]] [[<slug>]]

A note that exists is never written again: adding a link appends a wikilink to its links
line, so what the user wrote in the note stays.
"""

import json
import os
import re
from pathlib import Path

NOTE_TYPE = "view-concept-session"
LINKS_LABEL = "Liens :"
_LINKS_LINE = re.compile(r"^Liens\s*:.*$", re.MULTILINE)


def notes_dir() -> Path | None:
    """The folder session notes go to, or None when they are off."""
    value = os.environ.get("VIEW_CONCEPT_SESSION_NOTES", "").strip()
    return Path(value).expanduser() if value else None


def note_text(title: str, workflow: str, url: str, links: list[str]) -> str:
    # A JSON string is a valid YAML double-quoted scalar, whatever the title holds.
    return (
        "---\n"
        f"type: {NOTE_TYPE}\n"
        "aliases:\n"
        f"  - {json.dumps(title, ensure_ascii=False)}\n"
        f"workflow: {workflow}\n"
        f"url: {url}\n"
        "---\n"
        f"{_links_line(links)}\n"
    )


def _links_line(links: list[str]) -> str:
    return " ".join([LINKS_LABEL, *(f"[[{slug}]]" for slug in links)])


def write_note(
    folder: Path, slug: str, title: str, workflow: str, url: str, links: list[str]
) -> tuple[Path, bool]:
    """Write the note of session `slug`, or add `links` to the one that exists.
    Returns the note's path and whether it was created."""
    path = folder / f"{slug}.md"
    if path.exists():
        add_links(path, links)
        return path, False
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(note_text(title, workflow, url, _unique(links)), encoding="utf-8")
    return path, True


def add_links(path: Path, links: list[str]) -> list[str]:
    """Append a wikilink to each of `links` the note does not link to yet, on its links
    line (added at the end of the note when the user removed it). Returns the links
    added."""
    text = path.read_text(encoding="utf-8")
    new = [s for s in _unique(links) if not re.search(rf"\[\[{re.escape(s)}(\||\]\])", text)]
    if not new:
        return []
    added = " ".join(f"[[{s}]]" for s in new)
    m = _LINKS_LINE.search(text)
    if m:
        line = m.group(0).rstrip()
        text = f"{text[: m.start()]}{line} {added}{text[m.end() :]}"
    else:
        text = f"{text.rstrip(chr(10))}\n\n{_links_line(new)}\n"
    path.write_text(text, encoding="utf-8")
    return new


def _unique(links: list[str]) -> list[str]:
    return list(dict.fromkeys(links))
