# Planning rules

The rules every agent that changes the outline or the lexicon of a branch
review follows: the planner during scoping, the writer after « Write model ».
Your role file says when you apply them.

## The model

The **model** of a branch is the set of concepts it introduces or changes. A
**concept** is an object, a rule, a format or a name the code relies on: « a
gate drops a segment when its silence ratio exceeds the threshold ». A UI
element, a file, a function or a table row is not a concept: it is where a
concept is implemented. Name the concept; name the part only to say where
it lives.

The model starts from the concepts the repo's docs already define; the
modeling part covers only what the branch adds or changes.

A branch with no diff yet (the design comes first, the code after) still gets
a model: the proposed one. Say so in the model sheet, and mark each concept
you propose yourself, as opposed to one the user asked for, so the user reads
the modeling part as a proposal to approve, not a description to check.

## The reader

The reader is the user, who asked for the branch. What they stated is
**known**: the initial request (their messages in the request transcript,
when the review followed a conversation), their answers, their comments, the
terminal messages. The agent's messages in the transcript are proposals, not
decisions: settle each one like any other point of the model, and ask what
you would ask anyway. Never explain back what is known: an answer or a
comment changes the model as if it had been written that way from the first
pass, and no section mentions it. Spend the text on what is **new to the
user**:

- a **finding**: the code does something the user did not say, or does not
  do what they said; a doc that is missing or that the code contradicts;
- a **decision made for them**: a choice the request left open that the
  branch or an agent settled, a default taken on a skipped question;
- a **consequence**: what the change does to a concept that existed before,
  an edge case, an interaction between two concepts, a name that clashes.

When the request says little (« review my branch »), the branch itself is
what is new: the concepts are, but the problems the user gave as the reason
for the branch still are not.

## Writing the outline and the lexicon

Never edit `plan.json` by hand: it holds the initial request, the base branch
and the workflow too, and one bad rewrite loses them. Write the outline, the
lexicon or both with

```bash
view-concept plan <slug> <file>    # or - to read stdin
```

where the file is `{"outline": [...], "lexicon": [...]}`, either key alone
when only one changes. Each key replaces the whole list: start from the
current one (`plan.json`, or the context) and change what you mean to. The
command refuses an outline entry without an id or a title, a repeated id, and
a lexicon entry whose section is not in the outline or whose `kind` is
neither `core` nor `peripheral`.

## The outline

The outline (`outline` in `plan.json`, one entry `{"id", "title", "earns"}`
per section, and `"overview": true` on the model sheet's) follows the
skeleton below. An **outline entry** holds two texts the user reads, and
nothing else:

- `title`: high-level and short, the subject or the point. It is the first
  thing read in the outline, and the `earns` under it already says what the
  section gives, so it need not make the claim too.
- `earns`: one sentence saying what the section gives the user, one point
  they should get quickly. An `earns` that names two points is two sections.
  `view-concept plan` refuses one over 200 characters.

No notes for the writer: the writer works from the same outline the user
sees, with the rest of its context, and finds a section's example itself.
What you learned in the code goes in the code map.

The skeleton:

1. **The model sheet.** The section the user reads first and keeps in mind
   while the code changes. Its job is an intuitive view of the change:
   enough for the user to see what changes and why, and to take the
   decisions of the sections after it knowing the whole. Show more than you
   tell (a before/after of the example the request is about, a mockup of
   the page or the output, a diagram) and keep the text short; the form is
   yours to choose. Lay out the subjects the next sections discuss, and
   where each sits in the change, without repeating the outline's `earns`.
   Never retell the request. When the branch has no diff yet, say here that
   the model is a proposal. End with a **to-do list**: one line per point
   that fails the section test (see point 2). The sheet holds no list of the
   defaults taken: each one is written at the end of the section it touches
   (see **The question test**), and one that touches no section, only a line
   of the to-do list, is written in that line.
2. **One section per point new to the user** (see **The reader**) that
   passes the **section test**: it holds a decision the user makes or must
   make, or a consequence they will notice. Order them by the concepts they
   touch, so the points about one concept sit together. A point that fails
   the test (a doc that is out of date, which source a part of the branch
   came from, how the tests are built, code nothing in the app shows) gets
   no section: it is a line of the sheet's to-do list, which the implementer carries and the reviewer checks.
3. **A section per concept only when it needs one**: the user did not state
   its rules, they take more than its lexicon entry can say, and it passes
   the same section test. A concept the user named and described gets none:
   its lexicon entry is enough.
4. **Further directions.** The last section: about three ways to push the
   concepts further, each marked « fits this PR » or « follow-up ».

A « Today » or « What goes wrong » section is written only when the request
does not state them, and then before the model sheet: the user does not need
their own problem told back to them.

Section ids are stable: when you reorder, keep each section's id and change
its position. The page anchors the user's comments to ids.

## The lexicon

Every term that is not plain language gets an entry in `lexicon` of
`plan.json`: `{"term", "section", "kind", "definition", "tip"}`, where
`section` is the term's **home section**, the one that introduces it, and
`kind` its **term kind**:

- `core`, a **core concept**: a term the model introduces or changes. The
  prose of its home section defines it. An entry without `kind` is one. A
  core concept the user named and described, which gets no section of its
  own (skeleton point 3), is the exception: its tip alone carries it, no
  sentence of a section defines it, and its home section is the first
  section that uses it.
- `peripheral`, a **peripheral concept**: a term that is not plain language
  and that the model does not change (« FSRS », « rslib »). It gets its hover
  tip only: no sentence of a section's body defines it. Its home section is
  the first section that uses it.

Only the agents see the kind: the page underlines both the same way. (A
refactor section's `"kind": "finding"` shares the key name only.) **Plain
language** is the everyday words a reader understands with no knowledge of
the project or its field; the writer judges it while writing, with no list
to check against. A word the user uses every day is not plain language for
that reason: « FSRS » still gets its tip.

The `definition` is one line; the `tip` (written with the section's prose, by
the writer) is the hover text. Write both for someone who has read the
sections in order up to the home section and nothing after. A term the user
introduced keeps its definition to one line in their own words.

**The precedence rule.** Every text about a term (its introducing prose, its
`definition`, its `tip`) uses only terms whose home section is at or before
its own. When it needs a later term, reorder the outline or say the idea in
plain words; never point ahead. A **forward reference** is a `definition` or
`tip` that uses a later term; an **early use** is a term that appears in a
section placed before its home section. `view-concept check <slug>` lists
both.

The model sheet is the one exception: it lays out what the sections after it
discuss, so it may name a core concept whose home section comes later, and
that section defines it. Its outline entry carries `"overview": true`, so the
check reports no early use in it.

No location details in a `definition` or a `tip` (a file, a key, a section
number): a file the reader needs goes in the home section's prose. A `tip`
does not repeat what other entries define.

## The change history

Log every change of the model at once, one entry each:

```bash
view-concept change <slug> "<what changed, in a few words>" --by <planner|writer> --cause <ids>
```

A change of the model is a concept added, removed, renamed, merged or split, a
rule or a relation changed, a section added, moved or removed. A **listed
default** (see **The question test**) is a change too: log it with the
section it touches (« listed default: the client keeps its operations ·
touches tests »), so the writer, who reads the change history, writes its
line. A wording fix that leaves the model as it was gets none. Say the change in a few words
(« gate split into silence gate and length gate »), longer only when the
change itself is large. No implementation details: no files, no « what the
branch does now ». `--cause` gives the ids of the events that led to it
(questions `q3`, comments `c7`, terminal messages `tm2`); leave it out for a
change you make on your own judgment.

## Questions to the user

Every question you put to the user goes to the page:

```bash
view-concept question <slug> "<question>" [--option "<choice>" ...] [--multi] \
    [--recommended "<answer>"] [--background "<text>"] [--section <id>]
```

Never ask in the terminal: you do not have one. The user owns the
repository, and the goal is fixed (decide what the branch should be, and get
it there): never ask their level, their goal, or whether they know a
prerequisite.

**The question test.** Ask a question only when its answer changes what the
user sees, does or risks. A decision that fails it (the shape of an internal
interface, an operation nobody sees) is yours: take a default, a **listed
default**, and log it as a change of the model naming the section it
touches (see **The change history**). The writer states it in the « Default
taken » line at the end of that section, which the user corrects by
commenting on it. Ask the questions that pass, the frontier first (those
whose answer depends on no other open question), each with `--recommended`
when you have a suggestion. A question
the code, the session files or a command can answer is not a question for the
user: look it up, and so is one the request already settles. Never ask again a question the context lists, open,
deferred, answered or skipped. A skipped question means: use your default,
which the writer states the same way, in the « Default taken » line at the
end of the section the decision touches, and only there.

**A design question asked in scoping carries its background.** A design
question chooses between designs, as opposed to a fact you can look up. The
user can only choose when they know the mechanism the choice changes and
everything each option costs, so give both in `--background`, which the page
shows folded under the question:

- **Today**: the existing mechanism the question is about, in two or three
  sentences, on a real example (a real session, a real file, a command and
  its output). Never ask about a mechanism you have not described.
- **Per option, what it keeps and what it loses.** When the choice touches an
  area (of a page, a file format, a command), list every capability of that
  area first, and say per option whether it is kept, lost, or could be
  brought back and how. List them all in this one question: a cost that comes
  out later turns one decision into several.

The question's text stays one or two lines; the background holds the rest.
The background serves the user in scoping, before the model exists, and no
agent reads it. A question asked at the end of a section (a section question,
a deferred question asked again) carries none: the section explains it, and
states each option's cost.

**An unclear answer.** The user answers « I don't understand » when they
cannot choose before the model explains what the question needs. It arrives
as `q3 unclear « … » (…): <note>`, the note saying what is missing (it may be
empty), and the question is now **deferred**. In scoping it goes quiet, the
**quiet deferral**: until its anchor section is written, nobody rewords it,
asks it again, or asks a new question about it, whatever its note says. The
note only says what the section must explain, even when it reads as an
answer. Instead:

1. Make sure the outline explains what the note says is missing (without a
   note, the mechanism the question's text and options are about): extend
   the section that should hold it, or add one where it belongs.
2. Anchor the question to that section, the one after which it can be
   answered: `view-concept anchor <slug> <qid> <section id>`. The
   prerequisites of the anchor section come before it, by the precedence
   rule.
3. Log the change of the model, with the question as its cause.

The writer asks it again after writing the anchor section. A waiting
question that another answer makes obsolete is closed by the agent that sees
it, naming that answer (`view-concept answered <slug> <qid> --text
"Obsolete: <the answer that settled it>"`), and is never asked again.

**An up-front answer.** A design question answered in scoping is a decision
of the model sheet, and a concept the writer knows the user has: no section
explains it, and the model sheet states it in a line.

**A section question.** A decision only the model's explanation makes
answerable may be asked at the end of the section that explains it: ask it
with `--section <id>`. The page shows it at the end of that section once the
section is written, and in the scope block until then. Ask a decision the
user can answer from its background in scoping, without `--section`: an
answer given early shapes the whole model.

**Provenance stays out of the prose.** Which question or comment a decision
came from is logged in the change history (`--cause`), not written into a
section. A section never cites a question id.

During a grill (the context says « A grill is running »), work the outline as
a design tree: ask every decision whose prerequisites are settled, each with
its recommended answer and, in scoping, its background. An unclear answer during a grill
is deferred as in scoping. When no decision is left, say so in your report.
