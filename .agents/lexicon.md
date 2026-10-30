# view-concept

## Reader
Uses a coding agent (Claude Code, Codex or another) from the terminal and knows git, pull requests and Markdown; has never opened this repo.

## Terms

**Skill**:
A `SKILL.md` file of instructions an agent loads when you name it (`/build-feature`, `/write-readme`).

**Page**:
The local web page that renders a session's files in the browser and sends your comments back to the agent.

**Session**:
One explanation or review, with its files and comments, kept in `~/.view-concept/sessions/<slug>/`.

**Comment batch**:
The comments and answers you send from the page to the agent at once, with « Send ».

**Side thread**:
A separate, read-only conversation opened from the page to discuss a passage; the session never sees it.

**Coordinator**:
The main session of a skill that only routes each batch to a role agent and does none of the work itself.

**Role agent**:
An agent the coordinator starts for one part of the work, from the session folder: the scoper, the planner or the writer, and on a feature the implementer, the reviewer or the documenter.

**Direct path**:
A request for an explanation run through the six phases of `/view-concept`, for a straightforward explanation.

**Scoping path**:
A request for an explanation whose subject is drawn first, for an idea that needs morphing before it can be explained.

**Pin**:
A record of an open point on an element of the drawing, kept in the pin file, that the scoper closes once it is settled.

**Pin file**:
`pins.json` in the session folder: every pin of the session, open and closed.

**Hole**:
A pin of `/build-feature`: something of the drawing only you can settle.

**Supposition**:
A pin of `/build-feature`: the scoper's answer from the code, for you to approve or correct.

**Probe**:
A pin of `/view-concept` on an element you drew, asking what you actually believe on that point.

**Correction**:
A pin of `/view-concept` on an element you drew, stating that it is wrong or imprecise, and the fix.

**Tension**:
A pin of `/view-concept` on two of your elements that do not sit together, or on one that contradicts your goal.

**Choice**:
A pin of `/view-concept` where the subject has several framings, asking which one the explanation follows.

**Lead**:
A pin of `/view-concept` beside an element, offering something the agent found, with its sources when it looked it up.

**Channel**:
The path a section's script uses to ask an agent for data: frame, page, server, small agent, and back.

**Small agent**:
A headless, read-only agent the server starts to answer one request of the channel.

**Parameters file**:
`params.json` in the session folder, kept by the server for the sections that use the channel: what each one's script saved and the answers it received.

**Feature**:
A `/build-feature` session: a feature designed concepts first, from its model to its implementation, its docs and its PR.

**Triage**:
A `/triage-code` session: quickly written code given a verdict per item, then restructured.

**Docs review**:
A `/review-docs` session: a repo's docs on a scope, with no branch to model.

**Model**:
The concepts a branch introduces or changes, with their rules, written out in the sections of its review.

**Doc set**:
The list of the repo's docs a review concerns, each with the reason it is listed, shown in the Doc tab.

**Doc pass**:
The phase of a feature, started by « Write docs », that carries the model into the docs of the doc set through agents of its own, never the implementer: the documenter, then a write-readme agent per README for its skeleton, a document-feature agent for the folder models, and the documenter again, which in any other doc corrects only the sentences the code contradicts.

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
A paragraph, a list, a table or a code block of a doc; write-readme checks those of a README's skeleton one by one.

**README's skeleton**:
The passages of a README that write-readme alone holds: the first sentence and the status line at the top, the file map under `## Files`, the usage under `## Usage`, and a section the repo's conventions impose (such as a study header).

**Folder model**:
Every passage of a README outside the README's skeleton: the rules to know to use the folder without a mistake, held by document-feature.

**Draft**:
The outcome of write-readme for a folder with no README: the README's skeleton written from the code.

**Edit**:
The outcome of write-readme on an existing README, unless a rewrite was asked for: only the passages of its skeleton that fail a check change; the folder model stays word for word.

**Failure indicator**:
The share of the passages of an existing README's skeleton that fail write-readme's checks, counted before the edit, with a mention of a failing structure.

**Full rewrite**:
The outcome of write-readme that writes an existing README's skeleton again from the code alone, without reading the old one, and copies the folder model after it, on your request only.

**Rewrite request**:
What you send to have a README's skeleton written again from the code, its folder model copied after it word for word: the Doc tab's button, a comment, or `/write-readme <folder> rewrite`.

**Missing fact**:
A fact the old README said that its full rewrite, a rewrite of its folder model or a restructuring says neither in words nor by a link; the agent proposes to keep it or leave it, and you decide.
