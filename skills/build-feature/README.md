# build-feature

The `/build-feature` skill: `SKILL.md` is what the coordinator follows, the main session of a skill that only routes each comment batch to a role agent and does none of the work itself, and `roles/` holds the instructions of those role agents, each a fresh agent that owns one part of the work.

## Files

```
SKILL.md                  # the coordinator: the flow of a feature, which role each event goes to
roles/scoper.md           # the drawing of the problem and its pins, built with the user before the model
roles/planner.md          # the outline and the lexicon: converted from the drawing, or scoped in an older session
roles/writer.md           # the sections that write the model out, the to-do list, the first doc set
roles/implementer.md      # the code on the branch from « Approve model » on; it touches no doc
roles/reviewer.md         # the code checked against the model, item by item
roles/documenter.md       # the doc pass: the doc set, the docs that are not READMEs, the commit
roles/planning-rules.md   # the rules for changing the outline and the lexicon, read by the planner and the writer
```
