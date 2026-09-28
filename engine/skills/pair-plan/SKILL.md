---
name: pair-plan
description: Use when the pair task is in the planning phase: explore, then write the plan for engineer approval.
---

# pair-plan

Reads: `pair status`, `pair find`, `pair/learnings/<domain>.md`, the scope's `RULES.md`.
Writes: `pair/tasks/<id>/plan.md` and `log.md`. Nothing else — not one line of code.

## Procedure

1. **Restate the goal in one line.** If the requirement is ambiguous, ask **one** question. Not
   three; the one that would change the plan.

2. **Explore before deciding.**
   ```
   pair find "<the topic>"
   pair find --rule <ID>          # the exact text of a rule
   ```
   Read the files you are likely to touch. Note what already exists and can be reused — reuse is
   worth more than a tidy new module.

3. **Draft the plan** from `pair/engine/templates/plan.md`.
   - One file per step. If a step genuinely needs several, ask for a batch grant **before**
     approval: `pair grant-batch --step <n> --paths "<glob>" --max-files <n>`.
   - New code: `stub` → `test` → `code`.
   - Changed behaviour: `test` → `code`.
   - Legacy code with no tests: `char` first, to buy coverage before changing anything.
   - After a `test` step the next step (other than a `doc` step) must be `code`: never leave two
     red tests for one step to clear.
   - Cite the lessons you applied by ID.

4. **Run `pair plan-check`** and fix what it names, until it passes. It checks the things an
   engineer should not have to check by hand.

5. **Present the global view — ten lines at most** — and end with:
   "Challenge anything. When ready, run `pair approve`."

6. **On a challenge:** revise the plan, log the decision, go back to step 4.

## Two failure modes to avoid

- **A plan that is a to-do list.** Every step names a *behaviour*, not an activity. "add validation"
  is an activity; "rejects a negative amount" is a behaviour, and it tells you what the test says.
- **A step that cannot go green alone.** Wiring and registration usually need two files. Plan that
  as one `code` step with a batch grant, rather than a red step no single step can clear.

## In solo mode

The engineer writes the plan. You comment on it: what is missing, what looks risky, what you would
do differently. You do not write `plan.md`.
