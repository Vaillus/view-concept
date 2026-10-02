# Related work

Survey made on 2026-10-02 from web searches and the projects' READMEs. Star counts and feature lists are as reported then; some details come from short summaries of the READMEs and should be checked before relying on them.

## Summary

The **comment loop** (the agent writes a document, the user selects passages in a browser, comments on them, and the comments go back to the agent) is a busy niche: at least five tools do it, and Claude Code is adding a basic version to its VS Code extension. Nothing found combines it with an explanation method or a concepts-first branch review, which is what view-concept adds.

## Tools with the same comment loop

| Project | What it does | How it compares to view-concept |
|---|---|---|
| [Plannotator](https://github.com/backnotprop/plannotator) | A Claude Code hook that runs when Claude exits plan mode. It opens the plan in a browser, where the user selects text to delete it, comment on it or suggest a replacement, then approves or sends the feedback. It also annotates code diffs, and a plan is shared through its URL (plan and comments are compressed into it). | The most visible one. It works on Claude's built-in plan only: no explanation, no lexicon, no review steps. |
| [Interactive Plan Editor](https://dev.to/eduardmaghakyan/building-a-local-pr-review-interface-for-claude-code-plans-57o2) | Same hook as Plannotator. It shows the plan in a GitHub-style review page; « Request Changes » sends the inline comments back as one bundle. | Close to « Approve plan » with a comment batch, and nothing beyond that. |
| [reviewable-html-workbench](https://github.com/u-ichi/reviewable-html-workbench) (~300 stars) | A plugin for Claude Code and Codex. The agent writes HTML documents, the user comments in the margin, the agent reads the comments with an `ingest-review` command and replies in the same thread, and the page re-renders. | The closest in spirit: the document is where the conversation happens. It is general-purpose, with no explanation method behind it, and the agent sees comments only when it runs the command. |
| [claude-review (Ch00k)](https://github.com/Ch00k/claude-review) (~30 stars) | Comments on Markdown in the browser, reload when the file changes, and `/cr-address` hands the threads to Claude, which can reply. | Same pattern, small scale. |
| [claude-review (Palarix)](https://github.com/Palarix/claude-review) | A VS Code extension: inline comments on Markdown, sent to the Claude Code session. | Same pattern, in the editor. |
| [Margin](https://margindoc.dev/guides/comment-on-ai-generated-html) | A browser extension for anchored comments on HTML written by Claude Code or Codex. | Same pattern, as an extension. |
| Claude Code itself | The [changelog](https://code.claude.com/docs/en/changelog) lists a full Markdown view of plans in the VS Code extension, with comments. See also [issue #44787](https://github.com/anthropics/claude-code/issues/44787), which asks for a dedicated code review mode. | The basic loop is becoming part of the product, so the loop alone does not set view-concept apart. |

AI code-review tools ([PR-Agent, Gito and others](https://dev.to/rahulxsingh/15-open-source-ai-code-review-tools-2026-605)) are a different category: they send the diff to an LLM and post the bugs it finds as inline comments on the PR. They review the code for the human; they do not build the human's understanding.

## What view-concept does that none of them do

- **An explanation method in the page.** The other tools let the user annotate whatever the agent produced. view-concept runs `explain-concept`: the user approves the outline and the lexicon before any prose is written, a vocabulary audit flags undefined terms, and hovering a lexicon term shows its definition.
- **A concepts-first branch review.** `view-branch` first settles the model (the concepts the branch introduces), then sends agents to bring the code in line with it, then gives each item a verdict against it.
- **What changed in a rewrite.** The page highlights the words changed since the user last read a section, and `seen.json` keeps what was read across reloads. The others only re-render.
- **A live channel to the session.** `view-concept watch` runs under `Monitor`, so comment batches reach the session as they are sent, and Claude can put questions to the user in the page. The others wait for a slash command or act only at the plan-mode hook.
- **Model changes that feed the PR.** Corrections accepted in a branch review are recorded with `view-concept change` and become the Decisions section of the PR description.

## The problem in the literature: comprehension debt

**Comprehension debt** is the gap between how much code a system holds and how much of it any human understands; it grows when AI-generated code ships faster than people can read it.

- [Addy Osmani, O'Reilly Radar](https://www.oreilly.com/radar/comprehension-debt-the-hidden-cost-of-ai-generated-code/) named and described it.
- [Comprehension Debt in GenAI-Assisted Software Engineering Projects](https://arxiv.org/pdf/2604.13277) (arXiv, 2026) studies it in projects.
- An Anthropic study of 52 engineers found that those who used AI scored 50% on a follow-up comprehension quiz, against 67% for those who coded by hand, with the largest drop on debugging questions.
- The common answer, for example in [Augment Code's guide](https://www.augmentcode.com/guides/comprehension-debt-ai-code-review), is to stop reading every diff and review the specs, executable architecture checks, evals and instruction files instead, keeping line-level review for security-critical code.

view-concept takes the other route: it rebuilds the human's understanding, concepts first, before the code is judged. The honest pitch is: "the comment loop is common; this is the explanation and review method built on top of it."
