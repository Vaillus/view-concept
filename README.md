# view-concept

view-concept is a local web page where your coding agent (Claude Code, Codex, Jazz, or any agent that follows a skill and runs shell commands) writes explanations and code reviews, and where you read and comment on them. Each tool is a **skill** (a `SKILL.md` file of instructions the agent loads when you name it): `/view-concept`, `/view-branch`, `/view-refactor`.

The agent writes plain files; the **page** renders them in your browser as they are written. You select passages, comment on them, and « Send » posts all your comments at once, as one **comment batch**, to the agent session, which revises the text. One explanation or review, with its files and comments, is a **session**.

![An explanation in the page: hovering a term shows its definition, and the review pane holds the comments with the agent's replies](docs/screenshots/explanation.png)

## Why a page

In the terminal, a long explanation scrolls away, you cannot point at the sentence you did not understand, and each revision is a new copy to compare with the old one. In the page, the text stays put, comments are anchored to their passage, and a rewritten section highlights what changed.

The page is built around **explain-concept**, a skill that holds an explanation method. Two of its rules show in the page:

- **The plan comes before the prose.** The **plan** is the outline plus the **lexicon**, the list of every term the explanation uses, with the section that introduces it and its definition. You approve the plan before any paragraph is written.
- **Every term is defined before it is used.** Hovering a lexicon term shows its definition, and a final **vocabulary audit** flags terms that slipped through undefined.

## What a session looks like

You type `/view-concept explain KKT conditions`. The agent asks one or two questions in the terminal about your level and goal, then opens the page.

1. **Plan.** The agent writes the outline and the lexicon in the Plan tab. You correct it or click « Approve plan ».
2. **Prose.** The agent writes the sections one by one; the page re-renders as each one lands.
3. **Comments.** Select a passage, « + comment », repeat, then « Send ». The agent edits the sections, replies to each comment, and the words it changed stay highlighted until your next batch.
4. **Side threads.** To discuss a passage before asking for a change, select it and click « ask ». A **side thread** is a separate, read-only conversation forked from the session, so it knows the discussion so far; the session never sees it. (On Claude Code and Codex it forks the real conversation; on any other agent it is briefed from the session's files.)

![The Plan tab waiting for approval](docs/screenshots/plan.png)

![A side thread open on a section](docs/screenshots/side-thread.png)

The page and the terminal talk through the session's files: the page appends each batch to an inbox file, and the agent listens on that file, with `view-concept watch` under a background monitor (Claude Code) or `view-concept wait` called after each turn (every other agent), and revises.

## Three skills

| Skill | Use it to |
|---|---|
| `/view-concept` | understand a concept, as described above |
| `/view-branch` | review a branch you are building, concepts first |
| `/view-refactor` | decide what stays in quickly written code, then restructure it |

A **branch review** (`/view-branch`) first writes the concepts the branch introduces, with their rules; you correct them and approve. The agent then fixes the code to match, and the Refactor tab lists each changed file with its **verdict** (the decision recorded for that item) and a chart of how the files relate. « Create PR » opens the pull request.

![The Refactor tab of a branch review: one verdict per item, then the structure chart](docs/screenshots/branch-review.png)

`/view-refactor` works the same way on existing code: each item gets a triage verdict (`keep`, `move`, `split`, `merge`, `throw`, `separate-pr`), then the agent applies it on the current branch or splits it into PRs reviewed with `/view-branch`.

## Install

You need [uv](https://docs.astral.sh/uv/) and one of the agents below. No API key: side threads run on the agent you already use.

**Claude Code** — as a plugin, nothing else to set up (the `view-concept` command is bundled):

```bash
claude plugin marketplace add Vaillus/view-concept
claude plugin install view-concept@view-concept
```

Then type `/view-concept:view-concept explain KKT conditions` (Claude Code prefixes plugin skills with the plugin name), or just ask for an explanation in the page.

**Jazz** — as a plugin; `/view-concept`, `/view-branch` and `/view-refactor` become slash commands:

```bash
jazz plugin add Vaillus/view-concept
jazz plugin inspect io.github.vaillus.view-concept
jazz plugin trust io.github.vaillus.view-concept
jazz plugin enable io.github.vaillus.view-concept
```

**Codex** — the skills are plain `SKILL.md` folders, and the command comes from `uv`:

```bash
git clone https://github.com/Vaillus/view-concept.git ~/Documents/code/view-concept
uv tool install -e ~/Documents/code/view-concept          # the view-concept command
mkdir -p ~/.codex/skills
ln -s ~/Documents/code/view-concept/skills/* ~/.codex/skills/
```

Codex needs to write `~/.view-concept` and start a local server, so run it with a sandbox that allows both (for example `--sandbox danger-full-access`). Name the skill in your request: `$view-concept explain KKT conditions`.

**Any other agent** that can read a `SKILL.md` and run shell commands works the same way: install the command as above, point the agent at `skills/`, and set `VIEW_CONCEPT_AGENT_COMMAND` to a program that answers a prompt read on stdin (see [`docs/reference.md`](docs/reference.md#agents)) so side threads have something to run.

Start a new session and type the command to check.

## Further reading

- [`docs/reference.md`](docs/reference.md): commands, session files, page controls, configuration.
- [`docs/related-work.md`](docs/related-work.md): similar tools and what this one adds.
- Development: `uv sync && uv run pytest`, then `uv run ruff check --fix . && uv run ruff format . && uv run ty check .`. After changing the server, run `view-concept stop`.
