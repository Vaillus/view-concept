"""Publishing: a session's explanation as a published page, hosted in the pages repo.

A published page is a read-only copy of a session's explanation, as one self-contained
`<slug>/index.html`: the title, the date of the publish, then the published sections (the
explanation sections that are written, in outline order, numbered by their position in
the outline), with every lexicon term underlined and its tip shown on hover. Its CSS and
JavaScript are written in (static/published.html, published.css, reader.js, and the
omarchy skin); only KaTeX and Mermaid load from the web, as in the page. An image a
section takes from this machine is copied into `<slug>/assets/`. It leaves out the plan,
comments, threads, highlights and audit underlines.

The pages repo is a public GitHub repository whose GitHub Pages site serves its `main`
branch as-is (a `.nojekyll` at its root), together with its clone on this machine
(VIEW_CONCEPT_PAGES, default <home>/pages). One folder per published session, named by
its slug; the link is the site's address followed by `<slug>/`. The site's address is
VIEW_CONCEPT_PAGES_URL when set, else derived from the clone's `origin` remote. With no
clone, the first publish sets the repository up with `gh` (VIEW_CONCEPT_PAGES_REPO names
it, default `explanations`).

To publish is to build the published page into the clone, commit and push it, and write
the session's publish record (store.py); to unpublish is to delete the folder, commit
and push the deletion, and delete the record. A code session is never published: it
cites your repositories, and the pages repo is public.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urlparse

from .render import md
from .store import HOME, Session, SessionError

STATIC = Path(__file__).parent / "static"
DEFAULT_REPO = "explanations"
PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
IMG_SRC_RE = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
# An image src that is already on the web, or inside the page: left as it is.
WEB_SRC_RE = re.compile(r"^(https?:|data:|//)", re.I)
REMOTE_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def pages_dir() -> Path:
    """The clone of the pages repo."""
    return Path(os.environ.get("VIEW_CONCEPT_PAGES") or HOME / "pages").expanduser()


def say(text: str) -> None:
    print(f"view-concept: {text}", file=sys.stderr)


def run(
    args: list[str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a command (git or gh), its output captured. With `check`, a failure raises a
    SessionError carrying the command's stderr."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise SessionError(f"`{args[0]}` is not installed") from e
    if check and r.returncode != 0:
        detail = (r.stderr or r.stdout).strip()
        raise SessionError(f"`{' '.join(args)}` failed: {detail}")
    return r


# ---- the published page ----
def build(s: Session, folder: Path, published: date | None = None) -> None:
    """Write the published page of `s` into `folder` (replaced entirely): index.html and
    the images it takes from this machine, under assets/."""
    plan = s.read_plan()
    sections = s.published_sections(plan)
    if not sections:
        raise SessionError(f"{s.slug} has no written explanation section to publish")
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    assets = Assets(s.dir, folder / "assets")
    blocks = []
    for sec in sections:
        body = assets.rewrite(md.render(sec["markdown"]))
        blocks.append(
            f'<section class="sec" id="sec-{html.escape(sec["id"])}">\n'
            f'<h2><span class="num">{sec["number"]}</span> {html.escape(sec["title"])}</h2>\n'
            f'<div class="body">\n{body}</div>\n</section>'
        )
    # The hover text of a term, as the server renders it for the page.
    lexicon = [
        {
            "term": str(t.get("term") or ""),
            "section": str(t.get("section") or ""),
            "tip_html": md.renderInline(str(t.get("tip") or t.get("definition") or "")),
        }
        for t in plan["lexicon"]
    ]
    values = {
        "title": html.escape(str(plan["title"]).strip() or s.slug),
        "date": (published or date.today()).isoformat(),
        "skin": _static("themes.css") + _static("terminal.css"),
        "css": _static("published.css"),
        "sections": "\n".join(blocks),
        # "<" escaped, so no text of the lexicon can close the script element.
        "lexicon": json.dumps(lexicon, ensure_ascii=False).replace("<", "\\u003c"),
        "script": _static("reader.js"),
    }
    page = PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], _static("published.html"))
    (folder / "index.html").write_text(page, encoding="utf-8")


def _static(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


class Assets:
    """The images a published page takes from this machine: each `<img src>` that is not
    on the web is copied into the page's assets/ folder and pointed there."""

    def __init__(self, session_dir: Path, folder: Path) -> None:
        self.session_dir = session_dir
        self.folder = folder
        self.names: dict[Path, str] = {}  # source file -> its name under assets/

    def rewrite(self, rendered: str) -> str:
        return IMG_SRC_RE.sub(self._rewrite_one, rendered)

    def _rewrite_one(self, m: re.Match[str]) -> str:
        src = html.unescape(m.group(3)).strip()
        if not src or WEB_SRC_RE.match(src):
            return m.group(0)
        path = self._resolve(src)
        if not path.is_file():
            say(f"image not found, its link is left as it is: {src}")
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}assets/{html.escape(self._copy(path))}{m.group(2)}"

    def _resolve(self, src: str) -> Path:
        if src.lower().startswith("file://"):
            return Path(unquote(urlparse(src).path))
        path = Path(unquote(src)).expanduser()
        return path if path.is_absolute() else self.session_dir / path

    def _copy(self, path: Path) -> str:
        path = path.resolve()
        if path in self.names:
            return self.names[path]
        name, n = path.name, 1
        while name in self.names.values():
            n += 1
            name = f"{path.stem}-{n}{path.suffix}"
        self.folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.folder / name)
        self.names[path] = name
        return name


# ---- the pages repo ----
def base_url_from_remote(remote: str) -> str:
    """The address of the GitHub Pages site of a GitHub remote (SSH or HTTPS form)."""
    m = REMOTE_RE.match(remote.strip())
    if not m:
        raise SessionError(
            f"cannot tell the GitHub Pages address of the remote {remote!r}; "
            "set VIEW_CONCEPT_PAGES_URL"
        )
    owner, repo = m["owner"].lower(), m["repo"]
    if repo.lower() == f"{owner}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{repo}/"


def base_url(pages: Path) -> str:
    """The address of the pages repo's site: VIEW_CONCEPT_PAGES_URL, else derived from the
    clone's `origin` remote."""
    url = os.environ.get("VIEW_CONCEPT_PAGES_URL", "").strip()
    if url:
        return url if url.endswith("/") else f"{url}/"
    return base_url_from_remote(run(["git", "remote", "get-url", "origin"], cwd=pages).stdout)


def link(pages: Path, slug: str) -> str:
    return f"{base_url(pages)}{slug}/"


def ensure_pages_repo(pages: Path) -> None:
    """Set up the pages repo when there is no clone: create the public GitHub repository
    if it does not exist, clone it, give an empty one a `.nojekyll` on `main` (so GitHub
    Pages serves the files as they are), and turn on GitHub Pages from `main`."""
    if pages.exists():
        return
    name = os.environ.get("VIEW_CONCEPT_PAGES_REPO") or DEFAULT_REPO
    owner = run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    full = f"{owner}/{name}"
    if run(["gh", "repo", "view", full], check=False).returncode != 0:
        say(f"creating the public GitHub repository {full}")
        run(["gh", "repo", "create", name, "--public"])
    say(f"cloning {full} into {pages}")
    pages.parent.mkdir(parents=True, exist_ok=True)
    run(["gh", "repo", "clone", full, str(pages)])
    if run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=pages, check=False).returncode:
        say("committing .nojekyll on main, so GitHub Pages serves the files as they are")
        (pages / ".nojekyll").write_text("")
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=pages)
        run(["git", "add", ".nojekyll"], cwd=pages)
        run(["git", "commit", "-q", "-m", "serve files as they are"], cwd=pages)
        run(["git", "push", "-q", "-u", "origin", "main"], cwd=pages)
    say(f"turning on GitHub Pages for {full}, from main")
    r = run(
        ["gh", "api", "-X", "POST", f"repos/{full}/pages",
         "-f", "source[branch]=main", "-f", "source[path]=/"],
        check=False,
    )  # fmt: skip
    if r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower():
        raise SessionError(f"turning on GitHub Pages failed: {(r.stderr or r.stdout).strip()}")


def _commit_and_push(pages: Path, message: str) -> None:
    """Commit what is staged, if anything, then push (which also sends a commit an earlier
    push failed to send)."""
    staged = run(["git", "diff", "--cached", "--quiet"], cwd=pages, check=False).returncode != 0
    if staged:
        run(["git", "commit", "-q", "-m", message], cwd=pages)
    run(["git", "push", "-q", "origin", "HEAD"], cwd=pages)


def publish(s: Session) -> str:
    """Build the published page of `s` into the pages repo, push it, record the publish
    and return its link. Publishing again replaces the page at the same link."""
    if not s.exists():
        raise SessionError(f"no session {s.slug!r}")
    plan = s.read_plan()
    if plan.get("kind") == "code":
        raise SessionError(
            f"{s.slug} is a code session: it cites your repositories, and the pages repo "
            "is public, so it is not published"
        )
    if not s.published_sections(plan):
        raise SessionError(f"{s.slug} has no written explanation section to publish")
    pages = pages_dir()
    ensure_pages_repo(pages)
    url = link(pages, s.slug)
    build(s, pages / s.slug)
    run(["git", "add", "-A", "--", s.slug], cwd=pages)
    _commit_and_push(pages, f"publish {s.slug}")
    s.write_published(url, s.fingerprint())
    return url


def unpublish(s: Session) -> None:
    """Delete the published page of `s` from the pages repo, push the deletion and delete
    the publish record. The repo's history still holds the old page."""
    pages = pages_dir()
    if not (pages / s.slug).is_dir():
        raise SessionError(f"{s.slug} is not published in {pages}")
    run(["git", "rm", "-r", "-q", "--", s.slug], cwd=pages)
    # Files git did not track (none, unless added by hand) would keep the folder.
    shutil.rmtree(pages / s.slug, ignore_errors=True)
    _commit_and_push(pages, f"unpublish {s.slug}")
    s.delete_published()
