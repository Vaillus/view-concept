# view-concept

## Reader
Uses a coding agent (Claude Code, Codex or another) from the terminal and knows git, pull requests and Markdown; has never opened this repo.

## Terms

**Skill**:
A `SKILL.md` file of instructions an agent loads when you name it (`/view-branch`, `/write-readme`).

**Page**:
The local web page that renders a session's files in the browser and sends your comments back to the agent.

**Session**:
One explanation or review, with its files and comments, kept in `~/.view-concept/sessions/<slug>/`.

**Comment batch**:
The comments and answers you send from the page to the agent at once, with « Send ».

**Side thread**:
A separate, read-only conversation forked from the session to discuss a passage; the session never sees it.

**Branch review**:
A `/view-branch` session: the review of a branch you are building, through the model of what it introduces.

**Docs review**:
A `/view-docs` session: a repo's docs on a scope, with no branch to model.

**Model**:
The concepts a branch introduces or changes, with their rules, written out in the sections of its review.

**Doc set**:
The list of the repo's docs a review concerns, each with the reason it is listed, shown in the Doc tab.

**Doc pass**:
The implementer's run, started by « Write docs », that rewrites the docs of the doc set from the model.

**Structural change**:
A folder, or a file its README lists, that the branch adds, removes, renames or moves.

**Write order**:
The order the doc pass writes the docs in: each folder after its subfolders, the central subtrees first, `CLAUDE.md` last.

**Central subtree**:
A folder and what it holds, that carries a core concept of the branch's model according to the code map; the doc pass writes it before the other docs.

**Sentence test**:
A sentence the doc pass adds or changes in a `CLAUDE.md` stays only if, without it, an agent would act otherwise; the rest of the file is not tested.

**Minor doc**:
A doc of the doc set the doc pass touched only for a detail with no effect on its meaning, classed so by the agent with a one-line reason.

**Review list**:
The docs of the doc set the Doc tab asks you to read, the minor docs left out.

**Stale passage**:
A passage of a doc of the doc set that the model contradicts, flagged by the reviewer after the doc pass.

**Passage**:
A paragraph, a list, a table or a code block of a doc; write-readme checks those of a README one by one.

**Draft**:
The outcome of write-readme for a folder with no README: written from the code.

**Edit**:
The outcome of write-readme on an existing README, unless a rewrite was asked for: only the passages that fail a check change.

**Failure indicator**:
The share of an existing README's passages that fail write-readme's checks, counted before the edit, with a mention of a failing structure.

**Full rewrite**:
The outcome of write-readme that writes an existing README again from the code alone, without reading the old one, on your request only.

**Rewrite request**:
What you send to have a README written again from scratch: the Doc tab's button, a comment, or `/write-readme <folder> rewrite`.

**Missing fact**:
A fact the old README said that its full rewrite says neither in words nor by a link; the agent proposes to keep it or leave it, and you decide.
