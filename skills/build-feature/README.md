# build-feature

The `/build-feature` skill: `SKILL.md` is what the coordinator follows, the main session of a skill that only routes each comment batch to a role agent and does none of the work itself, and `roles/` holds the instructions of those role agents, each an agent the coordinator starts for one part of the work, from the session folder.

## Files

```
SKILL.md                  # the coordinator: the flow of a feature, which role each event goes to
roles/scoper.md           # the drawing of the problem, its pins and its lexicon, built with the user before the model
roles/planner.md          # the outline converted from the drawing, the scoper's lexicon carried into it; in a session started before the scoper, both scoped with the user
roles/writer.md           # the sections that write the model out, the to-do list, the first doc set
roles/implementer.md      # the code on the branch from « Approve model » on; it touches no doc
roles/reviewer.md         # the code checked against the model, item by item
roles/documenter.md       # the doc pass: the doc set, the docs that are not READMEs, the commit
roles/planning-rules.md   # the rules for changing the outline and the lexicon, read by the planner and the writer
```

## The drawing and its pins

The **drawing** is the scoping section, the section of the outline marked `"part": "scoping"` (`sections/scoping.html`), in which the scoper draws the problem with you before any model is written, redrawn once per comment batch; an **element** is one piece of it, with an id of its own (`e1`, `e2`…) that pins and comments name. What the scoper adds to what you said is one of three things:

- a fact the code or the docs state about today: drawn solid, as a settled part of the drawing, with its file and line beside it, and no pin; you correct it by a comment, like anything drawn solid;
- a **hole**, a pin of `/build-feature`: something of the drawing only you can settle (a **pin** is a record of an open point on an element of the drawing, kept in the pin file, that the scoper closes once it is settled: [`src/view_concept/README.md`](../../src/view_concept/README.md#pins));
- a **supposition**, a pin of `/build-feature`: a decision the scoper makes in your place, drawn for you to approve or correct. Its box carries the « agree » button, whose comment « agreed » approves it; a hole has none, since it asks for your own answer. An approved supposition is a decision of the model: the planner states it as one, never as a fact of the code.

The rest of the drawing follows `/view-concept`'s ([`skills/view-concept/README.md`](../view-concept/README.md#the-drawing-and-its-pins)): the scoper closes with no comment of yours the pins a later decision makes moot or contradicts, reads a sent thread whole, and writes the scoping lexicon from its first drawing on. Two differences: what the thread agent proposed in a sent thread that you never answered opens as a supposition, not a lead, and an entry of the scoping lexicon carries a `kind`, `core` for a term the feature introduces or changes, `peripheral` for any other.
