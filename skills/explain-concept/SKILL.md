---
name: explain-concept
description: A six-phase workflow for explaining a technical *concept* properly - establish the user's level, draft an outline and lexicon, calibrate against their actual prerequisites, revise the plan against what you learned, then explain in an order that introduces every term before it is used. Use whenever the user asks to explain, unpack, or clarify a concept in a way that suggests they want depth rather than a quick answer ("explain X to me", "I don't get X", "help me understand X", "walk me through X"). Prefer this over answering immediately when the concept is ambiguous, layered, or has prerequisites - a fast wrong-level answer wastes more of the user's time than two clarifying rounds do. For explaining code in *this* repo, use explain-code (interactive walkthrough of a slice) or explain-subsystem (standalone written document) instead.
---

# /explain-concept

A disciplined explanation workflow. The premise: most bad technical explanations fail for one of three reasons — they answer a different question than the one asked, they are pitched at the wrong depth, or they use vocabulary loosely. The phases below front-load the fixes for all three before any prose gets written.

Run the phases in order. Do not run ahead of the user.

## Specialization contract (for child skills)

This skill is a **parent**: other skills specialize it by pre-answering its decisions and inserting bounded extra steps, then deferring to it at runtime. Editing this file therefore affects its children.

**Children:** `refactor-doc`, `readme-from-refacto`, `readme-guide`, `write-spec-file`. When you change this skill, re-read each child's bindings and confirm they still resolve — a renamed phase or a moved extension point can silently break a child.

A child may do exactly two things, and nothing else. It may **not** delete a phase, reorder the workflow, or contradict the text of any phase. A child that needs more than this is not a child of this skill — it is its own skill.

**1. Bind decisions** — pre-answer a decision so its question is skipped. When a decision is bound, state it in a clause and skip the question; do not ask it.
- Phase 1 **Level**, **Sense**, **Goal**
- **Output medium + location** (chat / scratchpad / a file in the repo)
- **Deliverable structure** — supply a fixed section skeleton, used as the Phase 2 outline instead of deriving one

**2. Insert one bounded step at a named extension point:**
- **Before Phase 2** — a grounding / inventory step (read the material the doc will describe before outlining it)
- **Inside Phase 2** — required sections the outline must contain
- **Inside Phase 5** — a per-item schema the prose must follow

**Phase 6 (the vocabulary audit) is fixed** — a child cannot override or skip it. Every child inherits it; that is the point of the tree.

## Phase 1 — Scope

Do not explain anything yet. Work out what is genuinely underdetermined about the request, and ask.

**Level. Ask this first, and always.** Phrase the options in terms of the user's *experience*, never in the topic's vocabulary — "never come across it" / "heard the words, couldn't define them" / "can use it, want the underlying model" / "know it, want it sharper." A scoping option that requires the explanation in order to be parseable is a broken question. Test each option by asking whether someone who knows nothing about the topic could still tell which one describes them.

The level answer gates the other two dimensions:

**Sense.** Technical vocabulary is heavily overloaded, and the same word routinely names things at different layers of a system. Where the user has some familiarity, establish which sense is meant — and offer an escape hatch ("not sure, cover how they relate") when the senses are genuinely connected rather than merely homonymous. **If the level answer is at the bottom of the scale, do not ask a sense question at all.** At that level there is one sense worth giving, and asking forces a choice the user has no basis to make.

**Goal.** What the explanation is *for*. A conceptual understanding, a debugging session, a design decision, and a formatting task all want the same concept explained with different emphases and different depths. This one is usually still worth asking even at a low level, provided the options are in plain language.

**Every option carries its trade-off, and « Other » is always there.** Give each option its pros and cons: what the user gets by picking it and what they give up. Write each one as a full sentence with its impact (what concretely changes) and its implication (what that means for the user, and when it matters), not a fragment: "from scratch: every term is defined before use, so nothing depends on what you half-remember, but it takes about twice as long and covers ground you may know" rather than "no gaps, but longer". The user picks better when the consequences of each choice are on the page. And always offer « Other », a free answer of their own: list it as the last option unless the harness adds one itself. This holds for every question you ask, here and in Phase 3.

Ask one or two questions (with your structured-question tool if the harness has one, putting the pros and cons in each option's description, else as a plain message) covering whichever dimensions are actually open — if the user already specified their goal, don't ask for it. Write one short line of framing before the tool call, then stop. Your turn is over.

**Treat confusion or deferral as data.** If the user answers any scoping question with "I don't understand the options", "I don't know", or "you decide", that is a strong signal for the lowest level and the narrowest scope — not an invitation to choose freely. Do not fill the gap with outside context about who the user is or what they work on; the signal they just gave you outranks it. State the reading you have taken in a clause ("taking this from scratch") so they can correct it.

If the request is already unambiguous, scoped, and bounded, skip to Phase 2 and say so in a clause.

## Phase 2 — Outline and lexicon

Before writing the explanation, fix the vocabulary. This phase produces a *draft* plan; Phase 4 revises it once calibration comes back. Two artifacts:

**The outline.** Numbered sections, each with a one-line statement of what it establishes and why it sits there. This is not a table of contents — it is an argument about ordering. Say what each section *earns* for the sections after it.

**The lexicon.** A table of every technical term the explanation will use, the section where it gets introduced, and the one-line definition you intend to give there:

| Term | Introduced in | Definition to give |
|---|---|---|

Building this table is the point of the phase, not a formality. Without it, explanations drift: terms get used before they are introduced, the same concept gets three loose paraphrases in three paragraphs, and a term ends up quietly redefined halfway through. Committing to one definition per term, at one declared location, in advance is what prevents that — and it reliably makes the resulting explanation clearer.

The table is a contract, and it runs in both directions: every term in it is introduced at the declared point and used freely afterward, and **every technical term appearing in the final text appears in the table.** There is no "used in passing" exemption. If a term shows up in a sentence you are about to write and it is not in the table, you have two options — add it with a definition, or cut the sentence.

If the table surfaces a term whose natural definition point is *later* than its first use, the outline is wrong. Reorder the outline; do not patch it in prose.

Write both artifacts to a single file — `explain-plan.md` in the session scratchpad directory, holding the outline and the lexicon table — and, when the harness can attach or show a file, surface it. Do not also paste the full plan into the message; a one-line summary of what the plan covers is enough, since the document is right there. Then continue to Phase 3 in the same turn — do not stop for approval unless the user has explicitly asked to review the plan before you write, in which case end the turn here and wait.

The file is a working document, not a deliverable. It lives in the scratchpad for the duration of the conversation and is overwritten in place by Phase 4, so there is exactly one plan at any moment and the user is never comparing two versions to work out which is live. Never write it into the user's project.

## Phase 3 — Calibrate

Ask about prerequisites, not about the topic itself. One to three questions, each on a concept the explanation depends on, with graded options rather than yes/no:

- "Solid — skip the primer" / "Roughly, a refresher line would help" / "Shaky — explain properly"

Pick only concepts where the answer would actually change what you write. Asking about something you would explain identically either way wastes a round trip. Then stop and let the user answer.

Skip this phase when Phase 1 came back at the lowest level — the answer to every prerequisite question is already known, and asking them makes the user justify their inexperience three more times.

## Phase 4 — Revise the plan

Do not carry the Phase 2 draft into prose unchanged. It was written for a hypothetical reader; you have now met the real one. Read the calibration answers as instructions about **structure**, not just verbosity, and revise the outline and lexicon against them.

Three kinds of revision, and the third is the one most often skipped:

- **Reorder.** If a prerequisite came back "shaky", it usually cannot be handled with a parenthetical inside the section that needs it — it has to become its own section, earlier.
- **Add.** A shaky prerequisite may need a section that was not in the draft at all, plus its terms in the lexicon.
- **Cut.** Delete any section the calibrated level does not support. A section that depends on vocabulary the user does not have is not salvageable by simplifying its prose — it is the wrong section, and it goes. Be willing to lose a third of the draft here; an outline written before you knew the audience has no claim on the final text.

If Phase 3 was skipped because the user deferred or answered at the lowest level, this phase still runs — deferral is calibration data, and the draft almost certainly needs cutting against it.

Open your next message by stating the revision and why: "Your answers change the ordering — the mechanics primer moves first, because the term only makes sense once you can see the distinction between X and Y." One or two sentences. This tells the user the questions were load-bearing rather than ceremonial.

**Then, if anything changed, rewrite the scratchpad `explain-plan.md` in place** with the revised outline and lexicon in full, and present it again. Overwrite the file rather than creating a second one — the plan is a single living document. Not a summary of the changes, not a note saying what was cut: the actual revised plan, so the user can read the thing you are about to write from and correct it before you do. A prose claim that you trimmed something is unverifiable, and an instruction you can satisfy without doing the work is one you will eventually satisfy without doing the work. In the message itself, name the cuts and moves in a line or two so the diff is legible without opening the file twice.

If genuinely nothing changed, say so in a clause and go straight to Phase 5 — but treat that as a warning sign and re-read the cut criteria above before accepting it.

**Then stop. Your turn is over.** Phase 4 is a checkpoint, not a preamble: the revised plan is presented so the user can correct it *before* the prose exists, and that is only true if you wait for them. Close with a single short line inviting a correction ("Say if anything should be cut or added, otherwise I'll write it") — one line, not a list of questions. Begin Phase 5 only after the user has replied, treating anything they say about the plan as binding on it.

The exception is a user who has already said to write straight through, or who asked for the explanation with an explicit "don't check with me again". Honour that and continue in the same turn.

## Phase 5 — Explain

The instructions below are not a checklist to satisfy in full every time. **Each one scales with the level and goal established in Phase 1.** At a beginner level several of them shrink to a clause or disappear; at a practitioner level they expand. Satisfying every bullet at full size regardless of audience is itself a failure mode — it is what turns a short answer into a tour.

- Honour the lexicon. Each term gets its definition at its declared position and is used freely afterward. No technical term appears that is not in the table.
- Respect the level from Phase 1. Below the depth floor, name the concept and move on rather than unpacking it.
- Prefer concrete mechanism over analogy where the mechanism is tractable. A worked three-step trace of an actual process beats "think of it like a conveyor belt." Reach for analogy when the mechanism genuinely is not inspectable.
- Say why the concept is worth having a name for — what it lets someone see, predict, or decide that they could not before. This is usually where understanding lands, and it is what distinguishes an explanation from a glossary. **Size it to the level:** for a beginner this is a sentence or two inside the section that introduces the idea; for a practitioner it can be its own section with worked consequences, costs, and failure modes. Practical material — hardware, tooling, debugging, things that break — earns its own heading only when the user's stated goal is practical.
- Name the edge cases and the adjacent-but-different concepts briefly at the end, so the user can tell what the concept is *not*. At a beginner level, keep this to the one or two distinctions that prevent an actual misunderstanding, and drop the precision caveats that only matter to someone already using the concept.
- Close with a one-sentence compression of the whole thing. If you cannot write that sentence, the explanation has not converged and something above it is still muddled.

**Visuals.** Reach for a diagram (a Mermaid block, or a rendered widget when the harness has one) when the concept has structure that text serialises badly — a sequence with distinguished regions, a containment hierarchy, an intensity gradient. One diagram placed where it is needed, with prose on both sides. Skip it when the content is genuinely propositional; a diagram that re-renders a list adds nothing.

**Language.** Match the language the user is writing in, and keep technical terms in whatever language they conventionally appear in that field rather than translating them into something unrecognisable.

## Phase 6 — Vocabulary audit

The lexicon is a plan; this phase verifies the actual output against it. Terms slip through because they don't feel "technical" while you're writing — they're shorthand you've internalized, or a metaphor that feels transparent until a reader who doesn't share your context hits it.

Re-read the finished text looking specifically for:

- **Terms absent from the lexicon.** Anything domain-specific that a reader outside the project would need defined — if it slipped past the lexicon contract, it slipped past the definition too.
- **Metaphors standing in for a precise concept.** A word like "bridge", "handshake", or "funnel" that names an intuition rather than the actual mechanism or structure.
- **Overloaded words whose meaning depends on unshared context.** "Session", "event", "context", "state" — words that mean something specific here but something else in the next paragraph or the next project.
- **Bare references that assume the reader knows which one.** "The config", "the pipeline", "the test suite" — a definite article on a noun the text has not introduced.

List the candidates to the user: the term, where it appears, and what's wrong with it (undefined, metaphorical, ambiguous, or assumes context). **Then stop and let the user respond.** Some terms the user will judge clear enough in context — accept that and move on; fix only the ones they agree on.

For each term that survives: replace with the precise term, add an inline definition, or add a disambiguating clause. Update the lexicon to match.

## Failure modes to avoid

- **Scoping questions the user cannot answer.** If the options are written in the vocabulary of the answer, the question is broken. Level first, in plain words, always.
- **Overriding a stated level with outside context.** What you know about the user's job or past conversations does not beat what they just told you about this topic. Selecting expert content and then writing it in beginner prose is the worst of both.
- **Collapsing the phases.** Answering in Phase 1 defeats the point — you do not yet know which explanation to write.
- **Ceremonial questions.** If the user's answers would not change your output, do not ask. Two well-chosen questions beat five generic ones.
- **A lexicon you then ignore.** Drift away from the committed definitions and the phase has bought nothing. Leaning on an undefined term because it felt incidental is the most common version of this.
- **Executing a stale outline.** The Phase 2 draft predates knowing the audience. If Phase 4 changed nothing, you probably did not really run it.
- **Claiming a revision instead of showing it.** "I've trimmed this for your level" is not a revised plan. Rewrite the plan file in full whenever it changes.
- **Over-hedging after calibration.** If the user said "solid", genuinely skip the primer. Restating it "just briefly" tells them their answer was ignored.
- **Presenting the revised plan and then ignoring the checkpoint.** Phase 4 ends the turn. Writing the explanation immediately after showing the plan makes the plan a receipt rather than a decision point.
- **Explaining the workflow instead of the concept.** The phases are scaffolding. Announce transitions in a clause, not a paragraph.
- **Skipping the vocabulary audit.** The lexicon catches terms you plan to use; the audit catches terms you actually used without noticing. They are not the same check, and the second one is where the loose vocabulary lives.
