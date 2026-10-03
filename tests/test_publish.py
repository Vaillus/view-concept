import json
import re
import subprocess

import pytest
from test_cli import view_concept

from view_concept import publish as pub
from view_concept.store import Session, SessionError

IFRAME = '<iframe srcdoc="&lt;script&gt;let a = 1 &lt; 2;&lt;/script&gt;"></iframe>'


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout


def rich(session, tmp_path):
    """The kv-cache session with a refactor section, an image, an interactive figure and
    a lexicon tip that tries to close the script element."""
    plan = session.read_plan()
    plan["outline"].insert(1, {"id": "r1", "title": "Refactor", "part": 2})
    plan["lexicon"].append({"term": "cache", "section": "s2", "definition": "</script> *mémoire*"})
    session.plan_path.write_text(json.dumps(plan))
    (session.sections_dir / "r1.md").write_text("Part 2 only.")
    (session.dir / "fig.png").write_bytes(b"png")
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "fig.png").write_bytes(b"other png")
    (session.sections_dir / "s2.md").write_text(
        "Le cache.\n\n![a](fig.png) ![b](https://example.com/b.png)\n\n"
        f'<img src="{other / "fig.png"}"> <img src="missing.png">\n\n{IFRAME}\n'
    )
    return session


def test_build_shows_the_explanation_sections(session, tmp_path):
    out = tmp_path / "out"
    pub.build(rich(session, tmp_path), out)
    page = (out / "index.html").read_text()
    titles = re.findall(r'<h2><span class="num">(\d+)</span> ([^<]*)</h2>', page)
    assert titles == [("1", "Attention"), ("3", "Cache")]  # numbered by outline position
    assert "Part 2 only." not in page
    assert "<title>Le KV cache</title>" in page and "published " in page
    assert "{{" not in page and "katex@0.16.22" in page and "mermaid@11" in page
    assert IFRAME in page


def test_build_embeds_the_lexicon(session, tmp_path):
    out = tmp_path / "out"
    pub.build(rich(session, tmp_path), out)
    page = (out / "index.html").read_text()
    raw = re.search(r'<script type="application/json" id="lexicon">(.*?)</script>', page, re.S)
    assert raw and "</" not in raw[1]
    lexicon = json.loads(raw[1])
    assert lexicon[1] == {
        "term": "cache",
        "section": "s2",
        "tip_html": "</script> <em>mémoire</em>",  # inline HTML passes, as in the page
    }


def test_build_copies_local_images(session, tmp_path, capsys):
    out = tmp_path / "out"
    pub.build(rich(session, tmp_path), out)
    page = (out / "index.html").read_text()
    assert '<img src="assets/fig.png"' in page and '<img src="assets/fig-2.png">' in page
    assert (out / "assets" / "fig.png").read_bytes() == b"png"
    assert (out / "assets" / "fig-2.png").read_bytes() == b"other png"
    assert 'src="https://example.com/b.png"' in page
    assert '<img src="missing.png">' in page and "missing.png" in capsys.readouterr().err


def test_build_needs_a_written_section(tmp_path):
    s = Session("empty", tmp_path)
    s.create("Empty")
    with pytest.raises(SessionError, match="no written explanation section"):
        pub.build(s, tmp_path / "out")


@pytest.mark.parametrize(
    "remote, url",
    [
        ("git@github.com:Vaillus/explanations.git", "https://vaillus.github.io/explanations/"),
        ("git@github.com:Vaillus/explanations", "https://vaillus.github.io/explanations/"),
        ("https://github.com/Vaillus/explanations.git", "https://vaillus.github.io/explanations/"),
        ("https://github.com/Vaillus/explanations", "https://vaillus.github.io/explanations/"),
        ("git@github.com:Vaillus/vaillus.github.io.git", "https://vaillus.github.io/"),
    ],
)
def test_base_url_from_remote(remote, url):
    assert pub.base_url_from_remote(remote) == url


def test_base_url_from_an_unknown_remote():
    with pytest.raises(SessionError, match="VIEW_CONCEPT_PAGES_URL"):
        pub.base_url_from_remote("/some/local/repo.git")


@pytest.fixture
def pages(tmp_path, monkeypatch):
    """A clone of the pages repo whose origin reads as GitHub but pushes to a local bare repo."""
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(bare))
    clone = tmp_path / "pages"
    git("clone", "-q", str(bare), str(clone))
    git("config", "user.name", "Test", cwd=clone)
    git("config", "user.email", "test@example.com", cwd=clone)
    git("checkout", "-q", "-b", "main", cwd=clone)
    (clone / ".nojekyll").write_text("")
    git("add", ".nojekyll", cwd=clone)
    git("commit", "-q", "-m", "serve files as they are", cwd=clone)
    git("push", "-q", "-u", "origin", "main", cwd=clone)
    git("remote", "set-url", "origin", "git@github.com:Vaillus/explanations.git", cwd=clone)
    git("config", "remote.origin.pushurl", str(bare), cwd=clone)
    monkeypatch.setenv("VIEW_CONCEPT_PAGES", str(clone))
    monkeypatch.delenv("VIEW_CONCEPT_PAGES_URL", raising=False)
    return bare


def pushed(bare):
    """The commit subjects on the remote's main, latest first, and its files."""
    log = git("--git-dir", str(bare), "log", "--format=%s", "main").splitlines()
    files = git("--git-dir", str(bare), "ls-tree", "-r", "--name-only", "main").splitlines()
    return log, files


def test_publish_republish_unpublish(session, pages):
    url = pub.publish(session)
    assert url == "https://vaillus.github.io/explanations/kv-cache/"
    log, files = pushed(pages)
    assert log[0] == "publish kv-cache" and "kv-cache/index.html" in files
    record = session.read_published()
    assert record["url"] == url and not session.is_out_of_date()

    assert pub.publish(session) == url
    assert len(pushed(pages)[0]) == len(log)  # nothing changed, nothing committed

    (session.sections_dir / "s1.md").write_text("L'attention, réécrite.")
    assert session.is_out_of_date()
    pub.publish(session)
    log, _ = pushed(pages)
    assert log[:2] == ["publish kv-cache", "publish kv-cache"]
    assert not session.is_out_of_date()

    pub.unpublish(session)
    log, files = pushed(pages)
    assert log[0] == "unpublish kv-cache" and not any(f.startswith("kv-cache/") for f in files)
    assert session.read_published() == {}
    with pytest.raises(SessionError, match="not published"):
        pub.unpublish(session)


def test_code_session_is_refused(tmp_path, pages):
    s = Session("branch", tmp_path)
    s.create("A branch", kind="code", repo=str(tmp_path))
    (s.sections_dir / "s1.md").write_text("Cites `src/a.py:1`.")
    with pytest.raises(SessionError, match="code session"):
        pub.publish(s)
    assert pushed(pages)[0] == ["serve files as they are"]


def test_setup_creates_the_pages_repo(session, tmp_path, monkeypatch):
    """With no clone, the first publish creates the repository, clones it, commits
    .nojekyll on main and turns on GitHub Pages; `gh` is stubbed."""
    bare = tmp_path / "remote.git"
    clone = tmp_path / "pages"
    monkeypatch.setenv("VIEW_CONCEPT_PAGES", str(clone))
    monkeypatch.setenv("VIEW_CONCEPT_PAGES_URL", "https://vaillus.github.io/explanations")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    calls = []
    real_run = pub.run

    def fake_run(args, cwd=None, check=True):
        if args[0] != "gh":
            return real_run(args, cwd, check)
        calls.append(args[1:3])
        if args[1:3] == ["api", "user"]:
            return subprocess.CompletedProcess(args, 0, "Vaillus\n", "")
        if args[1:3] == ["repo", "view"]:
            return subprocess.CompletedProcess(args, 1, "", "not found")
        if args[1:3] == ["repo", "create"]:
            git("init", "-q", "--bare", "-b", "main", str(bare))
        elif args[1:3] == ["repo", "clone"]:
            git("clone", "-q", str(bare), args[4])
        elif args[1:3] == ["api", "-X"]:
            return subprocess.CompletedProcess(args, 1, "", "GitHub Pages is already enabled.")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(pub, "run", fake_run)
    url = pub.publish(session)
    assert url == "https://vaillus.github.io/explanations/kv-cache/"
    assert calls == [
        ["api", "user"], ["repo", "view"], ["repo", "create"], ["repo", "clone"], ["api", "-X"]
    ]  # fmt: skip
    log, files = pushed(bare)
    assert log == ["publish kv-cache", "serve files as they are"]
    assert ".nojekyll" in files and "kv-cache/index.html" in files


def test_cli_publish_and_unpublish(tmp_path, pages):
    home = tmp_path / "home"
    s = Session("kv", home / "sessions")
    s.create("KV")
    s.plan_path.write_text(json.dumps({**s.read_plan(), "outline": [{"id": "s1", "title": "A"}]}))
    (s.sections_dir / "s1.md").write_text("Text.")
    r = view_concept(home, "publish", "kv")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "https://vaillus.github.io/explanations/kv/"
    r = view_concept(home, "unpublish", "kv")
    assert r.returncode == 0, r.stderr
    assert pushed(pages)[0][0] == "unpublish kv"
    r = view_concept(home, "unpublish", "kv")
    assert r.returncode == 1 and "not published" in r.stderr
