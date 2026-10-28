# build-feature

The feature skill: `SKILL.md` is what the main session, the coordinator, follows, and `roles/` holds the instructions of the agents it starts, each a fresh agent that owns one part of the session.

## Files

```
SKILL.md                  # the coordinator: the flow of a feature, which role each event goes to
roles/planner.md          # the outline and the lexicon during scoping, and the first code map
roles/writer.md           # the sections that write the model out, the to-do list, the first doc set
roles/implementer.md      # the code on the branch from « Approve model » on, then the doc pass
roles/reviewer.md         # the code checked against the model, item by item
roles/planning-rules.md   # the rules for changing the outline and the lexicon, read by the planner and the writer
```
