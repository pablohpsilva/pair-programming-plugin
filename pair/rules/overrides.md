# Project rules

Only the engine defines Tier 0. Project rules use `PROJ-` and tier 1–3.

| ID | Rule | Tier | Enforced by |
|---|---|---|---|
| PROJ-001 | `docs/pair-SPEC.md` is the source of truth; when it is undefined or contradictory, stop and propose a change rather than guessing | 1 | review, SPEC-CHANGES.md |
| PROJ-002 | An accepted spec change is recorded in `docs/SPEC-CHANGES.md` in the same commit that applies it | 1 | review |
| PROJ-003 | No commit message, generated file or template names an AI vendor or product | 1 | githooks/commit-msg, C32 |
