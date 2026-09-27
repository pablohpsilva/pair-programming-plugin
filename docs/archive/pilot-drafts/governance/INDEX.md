# Governance Index — v0.1 (pilot)

**Load only what the task needs.** Find your task type below, load those files, and cite the rule IDs you applied in `plan.md`.

## What to load
| Task type | Load |
|---|---|
| Any task | `RULE-TIERS.md`, `PAIRING.md`, `COMMUNICATION.md` |
| Writing or changing tests | + `testing/WRITING-TESTS.md`, `testing/COVERAGE.md` |
| Writing production code | + `testing/COVERAGE.md`, `architecture/boundaries.yaml` |
| Touching more than one module | + `architecture/boundaries.yaml` (a check is required) |
| Bug fix | + `testing/WRITING-TESTS.md` (TEST-010) |

## Rule registry
Each rule is defined **once**, and other files reference its ID. `enforced-by` says how the rule is checked: aim to move rules from `judgment` towards `tool`.

| ID | Rule (short) | Tier | Defined in | Enforced by | Owner |
|---|---|---|---|---|---|
| TIER-001 | Rules have tiers 0–3; lessons never override Tier 0–1 | 0 | RULE-TIERS.md | judgment | @TODO |
| PAIR-001 | No edits without an active task and an approved plan | 0 | PAIRING.md | tool: hook + CI `scope` | @TODO |
| PAIR-002 | Only files in "Allowed files" may change | 0 | PAIRING.md | tool: hook + CI `scope` | @TODO |
| PAIR-003 | One file per step, validated before the next | 0 | PAIRING.md | tool: hook (ask) + CI `step-commits` | @TODO |
| PAIR-004 | Batch mode only via an explicit, scoped, expiring grant | 0 | PAIRING.md | tool: hook + CI `step-commits` | @TODO |
| PAIR-005 | Only humans approve plans | 0 | PAIRING.md | tool: hook | @TODO |
| PAIR-006 | Agents never edit protected paths | 0 | PAIRING.md | tool: hook + CI `protected` + CODEOWNERS | @TODO |
| PAIR-007 | Engineer corrections become proposed lessons | 2 | PAIRING.md | judgment | @TODO |
| COMM-001 | Brief by default (plan ~10 lines, step ~8 lines) | 2 | COMMUNICATION.md | template | @TODO |
| COMM-002 | Depth on demand: L1 / L2 / L3 | 2 | COMMUNICATION.md | judgment | @TODO |
| COMM-003 | Evaluate challenges honestly, then follow the decision | 1 | COMMUNICATION.md | judgment | @TODO |
| COMM-004 | State uncertainty; verify, never invent | 0 | COMMUNICATION.md | judgment | @TODO |
| TEST-001 | Test written first, seen failing for the right reason | 0 | testing/WRITING-TESTS.md | tool: CI `red-first` | @TODO |
| TEST-002…010 | How tests are written | 2 | testing/WRITING-TESTS.md | judgment | @TODO |
| COV-001 | ≥ 95% line and branch per package | 0 | testing/COVERAGE.md | tool: `task coverage` | @TODO |
| COV-002 | 100% of changed lines covered | 0 | testing/COVERAGE.md | tool: CI `diff-cover` | @TODO |
| COV-003 | Coverage never decreases (ratchet) | 0 | testing/COVERAGE.md | tool (later): baseline file | @TODO |
| COV-004 | Exclusions need a reason and a human approver | 0 | testing/COVERAGE.md | judgment (tool later) | @TODO |
| ARCH-001 | Dependencies only as allowed in boundaries.yaml | 0 | architecture/boundaries.yaml | tool: CI `boundaries` | @TODO |

## Rules for rules
- **One page per rule file** (about 60 lines). Split a file when it grows past that.
- New rules get the next free ID and are **added here first**.
- Ask in this order: *Can a tool enforce it? Can a template make it the default?* Only if both answers are no, write prose.
- Only humans change governance. Agents propose changes in chat or in a lesson.

## Rules changelog
| Version | Date | Change | Trigger |
|---|---|---|---|
| 0.1 | YYYY-MM-DD | Pilot set created | — |
