# Building pair
- `docs/pair-SPEC.md` is the source of truth; `docs/pair-DESIGN.md` explains intent.
  `docs/archive/` is history only: never build from it.
- Work one build step from SPEC §24 at a time. Stop at the end of each step and wait for review.
- Before writing code for a step, list the spec sections you'll implement and any gaps you see.
- Never guess past the spec: when something is undefined or contradictory, stop, propose a fix
  to the spec, and wait for approval. Record accepted changes in docs/SPEC-CHANGES.md.
- Tests first for every module. A step is done only when its acceptance tests in SPEC §22 pass.
- Python ≥ 3.11, standard library only (SPEC D2).
- Step 0 needs the human for T1–T3; prepare the spike instructions and wait.
