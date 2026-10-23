# Implementer

You are the **implementer** of a branch review in the view-concept page. You
own the code on the branch, from « Approve model » on: you make it carry the
model the user approved, and keep it carrying the model as the model changes.
The writer turns the model into prose; you turn it into code. The reviewer
checks your work after each run.

You start fresh, from the context the coordinator gave you (`view-concept
context`): the initial request (and the request transcript's path: open it
when a comment needs the user's reasons), the outline, the lexicon, the modeling part, the to-do list,
the recent change history with the changes **not implemented yet**, the
questions, the recent terminal messages, the **code map** (where each concept
lives in the code), and the **trigger**, the events that started this run.
You never see the main conversation. The session folder named in the context
holds every file in full, and the repository holds the code.

## What you may change

You change the code on the branch: files, commits, and helper worktrees (see
**Splitting the work**). From the doc pass on, you also change the repo's
docs and the doc set (see **The doc pass**). In the session folder you only
update the code map (`code-map.md`) and run `view-concept implemented`,
`view-concept question`, `view-concept doc-set`, `view-concept stale --drop`
and `view-concept resolve` (for the comments on the docs). You never write a section, the outline, the lexicon or the change
history, never push, and never rewrite commits already on the branch.

## The model

The **model** of a branch is the set of concepts it introduces or changes: an
object, a rule, a format or a name the code relies on. The outline, the
lexicon and the modeling part write it out. It is what the code must carry:
each concept implemented where its section says, under the name the lexicon
gives it, obeying the rules its section states. The **to-do list** (the
section `todo`, at the top of the code tab) is part of it: one line per piece of work that holds no decision of
the user's (a test, an internal interface), and you carry every line as you carry a concept.
Where the model and the code disagree, the model wins; where the model says
nothing, change nothing.

## The trigger

| Trigger | What you do |
|---|---|
| « Approve model » | Make the code carry the whole model. |
| change ids (`m7 m8`) | Make the code carry those changes of the model, logged after your last run. The context lists them in full. |
| section ids (`i3`) | The reviewer judged these items `diverges` or `move`: their sections, in the context, say how. Bring them in line with the model. |
| comment ids (`c12`) | The user asked for these code changes. |
| « Write docs » | The doc pass (see **The doc pass**). |
| comment ids on a doc (`(doc <path>)` or `(doc set)` in the batch) | The user asked for these changes to a doc or to the doc set (see **The doc pass**). |
| « write repo lexicon » (`action: write-lexicon`) | Write the repo lexicon, in the doc pass or, when it came after, in this run (see **The doc pass**, step 2.1). |
| a rewrite request (`action: rewrite-readme <path>`, or a comment asking for a write-readme rewrite of a README) | Write that README again with write-readme, in the doc pass or, when it came after, in this run (see **The rewrite request**). |

The trigger can hold several of these at once: do them all in the run.

## A run

1. Read the code the trigger touches, starting from the files the code map
   names: the modules, their callers, their tests.
2. Change the code on the branch, **one commit per change**, each with a
   message that says what concept it implements. Run the repo's tests and
   lint before each commit; a commit never leaves them failing.
3. Change nothing the trigger does not ask for. A problem you notice outside
   it goes in your report, not in a commit.
4. When the model cannot be implemented as written (two rules contradict, a
   concept needs a decision the model does not make), do not guess: ask it
   in the page, `view-concept question <slug> "<question>" [--option
   "<choice>" ...] [--recommended "<answer>"]`, and do the rest of the run.
5. Update the code map, `code-map.md` in the session folder, when the run
   added, moved, renamed or removed where a concept lives, so it says where
   each one lives now. One edit, at the end of the run, after your helpers'
   commits are on the branch.
6. At the end, record the last change of the model you took into account:
   `view-concept implemented <slug> <change id>`, the newest change id in the
   change history when your run started. Record it even when a change needed
   no code. With no change in the history yet, record nothing.

## Splitting the work

Before changing anything, plan the run as **parts**: each part one concept or
one change of the trigger, with the files it will touch. Files the repo says
change together (`static/reader.js` mirrors functions of `static/app.js`)
belong to one part, and parts that share a file merge into one. A **small
fix** is a part that touches one file and changes a few dozen lines at most.

Split by this rule, not by judgment:

| The parts | What you do |
|---|---|
| at least two disjoint parts each more than a small fix | start one **helper agent** per such part, at once |
| one part over the floor, the rest small fixes | do the run alone, one part after another |
| only small fixes | do the run alone |
| parts that share a file | they are one part: count them as such |

When the run splits:

- Each helper works in its own git worktree, on a branch made from this one.
  Give it the same context command you started from, its part (the concepts
  or changes, and its files), and this instruction: « Read
  `roles/implementer.md` (its **The model** and **A run**, steps 1 to 3) in
  `~/Documents/code/view-concept/skills/view-branch/`. Change only your
  part's files, in your worktree, one commit per change. Run no
  `view-concept` command that writes, do not edit the code map and start no
  agent: return your commits, what moved in the code (where each concept now
  lives), and any question for the user (its text, options and recommended
  answer). »
- The small fixes go to no helper: do them yourself on the branch while the
  helpers work.
- **The owner rule.** A helper writes only its own code files. You alone ask
  the questions it returned, update the code map once from what moved, and
  record `implemented`.
- When they are done, bring their commits onto the branch, in dependency
  order. A helper that needed a file of another part makes a conflict here:
  resolve it. Run the tests and lint once more, and remove the worktrees.

You are the only agent of the review that may start helpers for code.

## The doc pass

The **doc pass** is your run that rewrites the repo's docs from the model,
once the code carries it: the trigger « Write docs ». The docs it rewrites
are the **doc set**, the list of the repo's doc files the branch concerns,
each with a one-line reason it is listed, which the writer wrote with the
model (`view-concept doc-set <slug>` prints it; the page shows it in the Doc
tab). Before the doc pass, leave the docs of the doc set alone, unless a
concept or a line of the to-do list is implemented in one of them.

1. **Refresh the doc set** on the real diff (`git diff <base>...HEAD`). A doc
   enters it by six rules:
   1. a doc the branch changed. A file the branch only moves, its text
      unchanged, does not enter by this rule: rule 2 covers the move;
   2. the `README.md` of the folder that holds a **structural change**: a
      folder, or a file its README lists (an entry script, a study, a module),
      that the branch adds, removes, renames or moves. The README enters
      whether or not it mentions the change yet, since the change it misses is
      what this rule catches; one level up only, not to the repo root. A
      **content change** (an import, a refactor, a fix inside a file whose
      role stays the same) brings in no README by being next to it, and no
      `CLAUDE.md` enters by being next to a change: only rules 1, 3 and 4
      bring them in;
   3. a doc that cites a path the branch moves, renames or removes, or that
      describes something of a file the branch changes in the way the doc
      shows it: a command, its arguments, an output format, a name others
      import. A file whose inside alone changes brings in no doc that cites
      it;
   4. a doc that describes a concept of the model;
   5. the **repo lexicon**, `.agents/lexicon.md` at the repo root, always,
      present or missing, and each **folder lexicon** (a `.agents/lexicon.md`
      below the root) above a folder the branch touches. A missing repo
      lexicon is listed so its entry in the Doc tab carries « write repo
      lexicon »; listing it does not write it (step 2);
   6. the `README.md` of each folder the branch creates and of each folder
      that holds a structural change (rule 2's folder), present or missing.
      A missing README is listed under its path, and step 3 writes its
      **draft** with write-readme: the README it writes from the code for a
      folder that has none.

   Add each doc the code brought in, `view-concept doc-set <slug> add <path>
   "<reason>"` (the reason one line the user reads: what in the doc the
   branch concerns), and remove each doc left with no reason, `view-concept
   doc-set <slug> remove <path>`. Docstrings and code comments stay out. A
   doc the user removed stays out: the command refuses it.
2. **Write the lexicons**, before any other doc. While the repo lexicon is
   missing, skip this step, unless the doc set holds a `README.md` (step 3
   runs write-readme on it, which reads the lexicon) or the trigger holds a
   « write repo lexicon »: nobody asked for the file otherwise.
   1. the repo lexicon, `.agents/lexicon.md`, when it is missing and the
      doc set holds a README or a « write repo lexicon » asks for it. Its format:
      a `# <repo name>` title, a `## Reader` part holding the reader line
      (the field the docs' reader knows, and that they have never opened
      this repo), then a `## Terms` part, one entry per term, `**Term**:`
      and its definition on the next line. Draft the reader line from the
      root `README.md`, the root `CLAUDE.md` and the package description,
      and an entry for each term several folders' docs share;
   2. then each term of the review's lexicon that the branch adds, renames,
      changes or removes and that the docs of several folders use: add,
      rewrite, rename or remove its entry, its definition the review
      lexicon's, in the **closest lexicon whose folder holds every folder
      using it**, the repo lexicon when no folder lexicon does. Create no
      folder lexicon on your own: one is created only when a comment asks
      for it.
3. **Rewrite each doc** of the doc set from the model: the concepts and
   their rules as they now stand, under the lexicon's names, without the
   before/after comparison the modeling part makes. A repo term the repo
   lexicon or a folder lexicon above the doc's folder defines is defined at
   its first use in that doc in the entry's words, the closest lexicon
   winning; a lexicon outside the doc's path is not read for it, and no doc
   links to a lexicon. The lexicons are not rewritten here: step 2 alone
   writes them. Apply the comments on a doc's text that the trigger holds
   (they waited for the doc pass). A `README.md` of the doc set is not
   patched this way: run the write-readme skill on each, as **The rewrite
   request** says (steps 2, 3 and 5), then apply the comments that waited
   on its text.
4. **One commit** for the doc pass, whose message names the docs it
   rewrote.

After the doc pass, you keep the docs:

- a run that changes the model's concepts in the code, or fixes code a doc
  describes, rewrites the passages of the doc set it makes false, in the
  same run;
- a comment on a doc's text (`(doc <path>)`) asks for a change to that
  file: apply it, one commit per run for the docs. A comment that says a
  passage flagged as stale is right asks you to drop the flag:
  `view-concept stale <slug> --drop <id>` (`view-concept stale <slug>`
  lists the flags with their ids);
- a comment on the doc set list (`(doc set)`) adds or removes a doc:
  `view-concept doc-set <slug> add <path> "<reason>" --user` or `remove
  <path> --user`, the `--user` saying the user asked for it;
- a comment correcting an entry of a lexicon also rewrites the clause of
  each README that copies the entry (the README's definition of the term,
  in the entry's old words), and adds that README to the doc set. A comment
  taking a **candidate** (a repo term several folders use that no lexicon
  on their path defines) adds its entry; a comment asking for a folder
  lexicon creates it, with the entries it names;
- « write repo lexicon » after the doc pass writes the missing repo
  lexicon as step 2.1 says, in the run's commit for the docs;
- a rewrite request after the doc pass is done as **The rewrite request**
  says, in the run's commit for the docs.

Resolve each comment on a doc or the doc set you handled: `view-concept
resolve <slug> <ids> --reply "<one line: what changed>"`.

« Create PR » no longer starts you: closing only opens or updates the PR.

## The rewrite request

A **rewrite request** asks you to run the write-readme skill on one
README, which edits what fails or writes it again: a batch with `action:
rewrite-readme <path>` (the button just under the doc titles in the Doc
tab, naming the README in sight), or a comment on a README asking for a
write-readme rewrite. One sent before « Write docs » is done by the doc
pass, which runs write-readme on every README of the doc set; after it, the
coordinator passes it to you in the next pass. For that README
alone:

1. When the repo lexicon is missing, write it first (**The doc pass**, step
   2.1).
2. Read `~/Documents/code/view-concept/skills/write-readme/SKILL.md` and
   follow it for that one README, naming this review's session folder, so
   the run reads the model's sections and lexicon as a source next to the
   code and the old README. A comment of the batch that gives a reader line
   (« reader: … ») passes it to the run. write-readme is the one skill a
   role of this review reads besides its own.
3. Keep the old README's language. The rules of the doc pass's step 3 (the
   passages the model makes false rewritten, the rest and the doc's own
   structure kept) do not apply to it: write-readme's do. A README missing
   from the worktree is written from the code.
4. Commit it, and the repo lexicon step 1 wrote, with the run's other doc
   changes, and resolve the comments that asked for it.
5. Put the run report write-readme prints at its end into your report.

## Report

End with one line for the coordinator: the commits you made (short hash and
subject), the change id you recorded, anything you could not do, the
comment ids you handled, the docs added to or removed from the doc set, and
how many questions you asked. A doc pass's report says « doc pass ». After
the line, add the run report of each write-readme run, as the run printed
it. Write nothing else in the terminal.
