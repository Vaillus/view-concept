# skills

The skills, each a `SKILL.md` file of instructions an agent loads when you name it (`/build-feature`, `/write-readme`), written for any agent that reads a `SKILL.md` and runs shell commands. The Claude Code plugin installs them from this folder.

## Files

| Skill | Use it to |
|---|---|
| [`/view-concept`](view-concept/SKILL.md) | understand a concept, in the page, in six phases |
| [`/build-feature`](build-feature/README.md) | design and build a feature concepts first, from its model to its docs and PR, with an agent per role |
| [`/triage-code`](triage-code/SKILL.md) | decide what stays in quickly written code, then restructure it |
| [`/review-docs`](review-docs/SKILL.md) | bring a repo's docs up to date, with no branch to review |
| [`/write-readme`](write-readme/SKILL.md) | write a folder's README from its code, or bring an existing one up to standard, in the terminal, with no page |
| [`/document-feature`](document-feature/README.md) | carry a feature's concepts into the repo's READMEs once its code is written; `/build-feature` runs it on « Write docs » |
| [`/explain-concept`](explain-concept/SKILL.md) | the explanation method alone, answered in the terminal, with no page |
