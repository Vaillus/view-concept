# Planning rules

The rules every agent that changes the outline or the lexicon of an
explanation follows: the planner until « Approve plan » on the direct path,
or at « End scoping » on the scoping path, when it converts the drawing; the
writer after either. Your role file says when you apply them.

## The two paths

A request for an explanation takes one of two paths. Your context tells you
which: a session is on the **scoping path** when its outline holds a section
with `"part": "scoping"` (the **drawing**, shown in the page's scoping tab),
and on the **direct path** otherwise.

- **The direct path** runs the six **phases** of an explanation: Scope,
  Outline and lexicon, Calibrate, Revise the plan, Explain, Vocabulary
  audit. The planner runs the first four and stops for « Approve plan »;
  the writer runs the last two.
- **The scoping path** draws the subject first: the scoper builds the
  drawing with the user, one comment batch after another, until « End
  scoping ». The planner then converts the drawing into the outline and the
  lexicon, and the writer writes the report from it, with no « Approve
  plan » stop.

| phase | direct path | scoping path |
|---|---|---|
| Scope | the planner asks the user's level, the sense of the word and the goal | not asked: they come out of the drawing as it grows |
| Outline and lexicon | the planner drafts the plan | the planner converts the drawing at « End scoping » |
| Calibrate | the planner asks one to three questions on the prerequisite concepts | the probes on the elements the user drew, and the prerequisite tree with its yes, quickly or no on each concept |
| Revise the plan | the planner revises the draft and stops for « Approve plan » | no revision and no stop: the writer starts once the planner has converted the drawing |
| Explain | the writer | the writer, from the drawing |
| Vocabulary audit | the writer | the writer |

## The plan

The **plan** is the outline and the lexicon of `plan.json`. The plan fixes
the vocabulary before any prose is written: most bad technical explanations
answer a different question than the one asked, are pitched at the wrong
depth, or use vocabulary loosely, and the plan front-loads the fixes for all
three.

### Writing it

Never edit the outline or the lexicon of `plan.json` by hand: the file holds
the initial request and the workflow too, and one bad rewrite loses them.
Write the outline, the lexicon or both with

```bash
view-concept plan <slug> <file>    # or - to read stdin
```

where the file is `{"outline": [...], "lexicon": [...]}`, either key alone
when only one changes. Each key replaces the whole list: start from the
current one (`plan.json`, or the context) and change what you mean to. The
command refuses an outline entry without an id or a title, a repeated id,
and a lexicon entry whose section is not in the outline.

The one field you write by hand is `revision`, the line the page shows above
the outline (Revise the plan, a default taken): change that field alone, and
keep every other field of the file as it is.

### The outline

The outline (`outline`, one entry `{"id", "title", "earns"}` per section) is
an argument about ordering, not a table of contents: each section sits where
the sections before it give it what it needs.

- `title`: short, the subject or the point of the section.
- `earns`: one sentence saying what the section gives the sections after
  it, at most 200 characters, since the user reads it in the page's
  outline. An `earns` that names two points is two sections.

No notes for the writer: the writer works from the same outline the user
sees, with the rest of its context.

Section ids are stable: when you reorder, keep each section's id and change
its position. The page anchors the user's comments to ids. On the scoping
path the drawing's entry (`"part": "scoping"`) stays the outline's first
entry, unchanged: an outline written without it loses the scoping tab.

### The lexicon

Every technical term the explanation will use gets an entry in `lexicon`:
`{"term", "section", "definition", "tip"}`, where `section` is the term's
**home section**, the one that introduces it, `definition` the one-line
meaning the plan commits to before the prose, and `tip` the hover text the
writer adds when it writes the home section.

The lexicon is a contract in both directions: every term in it is introduced
at its home section and used freely after, and **every technical term in the
final text is in the lexicon**. There is no « used in passing » exemption: a
term about to be written that is not in it gets added with a definition, or
the sentence goes. Committing to one definition per term, at one place, in
advance is what keeps terms from being used before they are introduced,
paraphrased three ways, or quietly redefined.

When a term's natural definition point comes later than its first use, the
outline is wrong: reorder it, do not patch it in prose.

**The first-use reader.** The page shows a term's `tip` when the reader
hovers any use of it, so it is read mid-sentence, far from the section that
introduced the term; without a `tip`, the page falls back to `definition`.
Write both for the **first-use reader**: someone who has read the sections
in order up to the term's home section and nothing after. A text that works
for this reader works for anyone who has read further; the reverse fails.

**The precedence rule.** Every text about a term (its introducing prose, its
`definition`, its `tip`) uses only terms whose home section is at or before
that term's home section. When it needs a later term, reorder the outline or
say the idea in plain words; never point ahead (« see section 7 »). A term
spelled like a common word counts as used wherever the word appears. Two
breaches have names: a **forward reference** (a `definition` or `tip` uses a
term whose home section comes later) and an **early use** (a term appears in
the prose of a section placed before its home section). `view-concept check
<slug>` lists both.

**The hover text.** Three hard constraints on a `tip`, which bind
`definition` too:

1. It obeys the precedence rule.
2. No location details: nothing that says where the thing lives or came from
   (a file, a key, a script, a section number, a former name) instead of
   what it is. Those go in the home section's prose, as citations in a code
   session.
3. It does not repeat what other lexicon entries define. A term that groups
   other terms with the same home section names the group and what it is
   for, not each member.

Beyond these, say plainly and briefly what the thing is, as a reader meeting
it for the first time needs it. Markdown and `$…$` are allowed. The `tip`
agrees with `definition` and with what the home section says.

**The repo's lexicons** (a code session, one about a repository). Read them
before writing yours. The **repo lexicon** is `.agents/lexicon.md` at the
repo root: it opens on the reader line (the field the repo's docs assume
their reader knows), then defines once each term the repo's folders share. A
**folder lexicon** is a `.agents/lexicon.md` in a folder below the root, in
the same format, for the terms only the folders under it share. Read the
repo lexicon first, then each folder lexicon above the folders the
explanation covers; where two on one path define a term, the one closest to
the folder wins. A repo term one of them defines keeps that entry's name,
and its `definition` is the entry's, unless the explanation is about a
change to it. The folders the explanation covers can reach two definitions
of one term: a shadowed term (one a folder lexicon defines when a lexicon
above it already does) when they lie inside and outside that folder
lexicon, or two sibling folder lexicons that define it differently. Your
lexicon then holds the term twice, each entry named with its folder (« gate
(dataset_tools/) »).

## The reader

**On the direct path**, the reader is the user, reading right after they
asked. What they stated is **known**: the initial request (their messages in
the request transcript, when the explanation followed a conversation), their
answers, their comments, the terminal messages. The plan never spends a
section on what is known: a prerequisite they said they have gets no
section, and a term they used correctly gets a one-line definition, in their
words. This is the rule the writer calls « Never tell back ».

**On the scoping path**, the reader of the report never saw the drawing, and
has the same priors as the person who drew it: the user a few months later,
or someone they send it to. Nearly everything in the report was settled
with the user on the drawing, so « Never tell back » does not hold there:
the report states everything the drawing settled, in full, without saying
who settled it.

## A plan written from a drawing

On the scoping path, the user and the scoper built the drawing first: the
HTML section `sections/scoping.html`, its elements (each with an id, `e1`,
`e2`…), and its **pins**, the records of the open points on its elements
(the context's `## Pins` part: the open ones, then the closed ones with the
note that says how each was settled, and the comments attached to them).
The drawing is the source of the plan and of the report. A pin has one of
five kinds:

| pin | on | asks the user | settled when |
|---|---|---|---|
| **probe** | an element the user drew | what they actually believe on that point | they answer with what they think |
| **correction** | an element the user drew | the element is wrong or imprecise: the pin states the fix | they accept the fix, or defend their point |
| **tension** | two of the user's elements, or one that contradicts their goal | the two do not hold together | they say which side gives way |
| **choice** | the subject, where it has several framings | which framing the explanation follows | they pick one |
| **lead** | beside an element | what the agent found, with its sources when it looked it up | they take it (it is drawn in) or leave it |

The rules of a plan written from a drawing:

- **What the drawing settled is stated.** A closed pin's note says how it was
  settled: an answered probe is what the user believes, an accepted
  correction is the fact, a settled tension states the side that held, a
  settled choice fixes the framing, a taken lead is part of the subject.
- **What was left open is left out.** A probe, a choice or a lead still open
  at « End scoping », or a lead the user left (closed with the note
  « left »), is one the user ignored: write as if it had never been placed.
  The element under an open probe is written as the user drew it, an open
  choice imposes no framing, and an open lead adds nothing.
- **A taken lead keeps its sources.** What it added to the drawing carries
  the sources the scoper drew on it, and the report cites them where it
  states it.
- **The depth the user chose.** The parameters file (the context's
  parameters part, one entry per section whose script uses the channel; the
  drawing's entry is the prerequisite tree's) holds the user's answer on
  each concept of a prerequisite tree: **yes** (they went into it: the
  report explains it, and its own prerequisites they said yes to), **quickly**
  (they skimmed it: one sentence), **no** (they skipped it: name it at most).
  A concept with no answer gets the depth its element needs, no more.
- **The outline.** Its aim is to retranscribe the drawing for a reader who
  never saw it: each part of the drawing becomes a section, or part of one,
  in the order a first reading needs, and none is dropped because the
  drawing already shows it. The drawing's entry stays first and unchanged.
  The report holds only the sections written from the drawing: export and
  publishing leave the drawing out.
- **The lexicon** is born at the conversion: the planner writes it from the
  words of the drawing, then it is kept as **The lexicon** says.
- **No question to the user**, no « Approve plan » stop, no `revision` line.
  A drawing element you find wrong or imprecise, or two elements you find at
  odds (or one at odds with the goal the user stated), goes back to
  scoping: open a **correction** or a **tension** on it,

  ```bash
  view-concept pin <slug> "<the fix, or what does not hold together, in one sentence>" \
      --kind correction|tension --element <id> [--element <id>]
  ```

  (a tension names both elements; the session's phase returns to scoping by
  itself; with no element to name, leave `--element` out and the scoper
  draws one), then stop the run and report « correction opened: back to
  scoping » (or « tension opened »). Never place a probe, a choice or a
  lead: none of the three holds « End scoping » back, so scoping could end
  again with it still open, and the report would leave it out.

### The change history

On the scoping path, log every change of the plan at once, one entry each:

```bash
view-concept change <slug> "<what changed, in a few words>" --by <planner|writer> --cause <ids>
```

A change is a section added, moved, split, merged or removed, or a term
added, removed or renamed; a wording fix gets none. `--cause` gives the ids
of the events that led to it (comments `c7`, terminal messages `tm2`, a batch
`b4`); leave it out for a change made on your own judgment. After a return to
scoping, the change history is how the next conversion and the next writer
run know which points of the drawing changed. The direct path logs no
change.

## Questions to the user (direct path)

An **agent question** is a question put to the user in the page: you have no
terminal. On the direct path the planner asks the Scope and Calibrate
questions, and either agent asks what a comment or a change of scope opens.
On the scoping path no agent asks a question: the pins take their place.

```bash
view-concept question <slug> "<question>" [--option "<choice>" --option "<choice>"] [--multi] \
    [--recommended "<answer>"] [--background "<text>"]
```

`--background` gives what the user needs to know to answer, which the page
shows folded under the question: the mechanism the question is about, as it
is today, in two or three sentences on a real example, and, for a choice,
what each option keeps and loses. When a choice touches an area (of a
system, a format, a tool), list every capability of that area there and say
per option whether it is kept or lost: a cost that comes out later turns one
decision into several. Never ask about a mechanism the user may not know
without it.

`--option` gives the choices (`--multi` lets the user pick several); the
page always adds a free-text field. `--recommended` gives the **recommended
answer**, the one you would pick: an option, which the page preselects, or a
text, which it pre-fills; either is marked « suggested ». Give one whenever
you have a suggestion. Outside the phase `scoping` the command also sets the
phase `awaiting-answer`.

The page shows each open question as a box in the **scope block**, at the
top of the Plan tab. A box has four exits: « Validate » sends the answer,
« Skip » sends « no answer, use your default », « I don't understand »
sends the text field as a note of what is missing (the question becomes
**deferred**), and a box the user leaves alone stays open. They reach you in
your trigger as

```
answer to q1 « <question> »: <choices> — <text>
q3 skipped « <question> » (no answer: use your default)
q4 unclear « <question> » (the user doesn't understand it yet: …): <note>
```

An answer line can be followed by `(from side thread t5: threads/t5.json)`:
the user discussed the question in a side thread first, from its box. Read
the thread when the answer alone leaves you unsure what the user wants or
why; the answer line stays the answer.

### The question flow

- **Ask every question you judge relevant.** The user prefers more questions
  they can ignore to fewer. Ask the **frontier** first: the questions whose
  answer depends on no other open question. A question that depends on an
  open one waits until that one is answered or skipped.
- **Ask only what is open**: nothing the user already said, nothing the
  context lists as asked (open, deferred, answered or skipped). A question
  whose answer would not change what is written is not worth asking. A fact
  the code, the session files or a command can answer is not a question for
  the user: look it up.
- **Add questions as answers arrive.** An answer can open new questions; ask
  them when it does.
- **Never wait on a question** to continue the work that does not depend on
  it. The user will leave many questions unanswered, and that is expected:
  an open box is not a debt.
- **A skipped question** means: use your default. Say in `revision` which
  default you took.
- **An unclear answer** means the user cannot answer before the explanation
  gives them what the question needs. Do not ask it again now. Make sure the
  plan explains what the note says is missing (a section, or a line in the
  one that should hold it), then anchor the question to that section:
  `view-concept anchor <slug> <qid> <section id>`. Once that section is
  written, the writer asks it again under the same id: `view-concept reask
  <slug> <qid> [--text "<…>"]`. The reask removes its background: the
  section above it explains it now, so that section states each option's
  cost. The page then shows it at the end of that section. A second unclear
  answer to the same question: develop that section once and ask again; a
  third takes your default, said in `revision`.
- **A waiting question another answer makes obsolete** is closed by the
  agent that sees it, naming that answer: `view-concept answered <slug>
  <qid> --text "Obsolete: <the answer that settled it>"`.

A **rescoping question** is one asked once the plan exists, because
something moved what the explanation covers (a comment, a terminal message
such as « actually I want this for debugging »). Ask it like any other; the
question flow still holds.

### Grill

A **grill** is an optional interview the user starts from the scope block:
« Grill me » sends a batch with `action: grill`, and your context then says
« A grill is running ». Work the plan as a **design tree**: the decisions it
leaves open, each with the decisions that depend on it (a decision depends on
another when you cannot ask it without guessing the other's answer).

1. Ask every decision of the frontier as an agent question with
   `--recommended`.
2. Find facts yourself, and put only decisions to the user.
3. Each answer settles a decision: fold it into the plan, and ask the
   decisions it unblocks. A skipped decision takes your recommended answer.
4. When no decision is left, resolve the grill batch: `view-concept resolve
   <slug> <batch id> --reply "<one line>"`, which turns « Stop grill » back
   into « Grill me », and say so in your report.

On the scoping path a grill asks no question: read the drawing and the
report for an element wrong or two at odds, open the corrections and
tensions you find (back to scoping), and resolve the grill batch.

## Naming a section to the user

Ids are for the files, never for the user. Wherever the user reads it (a
question, a `resolve` reply, the prose, the plan, your report), name a
section by the number the page shows, in words: « section 6 ». Never write
its id (`s6`, `applied`) or a shorthand such as `§6`, even when a batch
names it so.

## Provenance stays out of the plan and the prose

Which question, comment or side thread a decision came from is never
written into a section, an `earns` or a `tip`: no question id, side thread
or marker (« (q2) », « Asked for by the user », « Proposed. »). On the
scoping path the change history records it (`--cause`).
