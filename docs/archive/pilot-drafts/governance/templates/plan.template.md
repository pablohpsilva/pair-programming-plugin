# Task <task-id>: <title>

<!-- Global view: keep everything above "Allowed files" to ~10 lines. -->
🎯 **Goal:** <observable outcome, one line> (requirement: <link or feature file>)
🧭 **Approach:** <how, one or two lines; name any existing code being reused>
🔎 **Explored:** <what I searched for existing work, and what I found>
📚 **Rules & lessons applied:** <IDs, e.g. TEST-001, COV-002, lesson billing#3>
🔀 **Alternatives:** <one alternative and why it was rejected>
⚠️ **Risks / open questions:** <one per line, or "none">
👥 **Mode:** agent drives | engineer drives | engineer solo · Governance v0.1

## Allowed files
<!-- The hook and CI read this list. Exact paths or globs, one per line, in backticks. -->
- `packages/<domain>/<pkg>/tests/<file>`
- `packages/<domain>/<pkg>/src/<file>`

## Step map
<!-- One file per step. Tests come before the code they drive. -->
| # | File | Kind | Behavior |
|---|---|---|---|
| 1 | `…/tests/<file>` | red | <behavior the test pins down> |
| 2 | `…/src/<file>` | green | <minimum code to pass> |
| 3 | `…/src/<file>` | refactor | <optional: cleanup with tests green> |

## Tests first
- Scenarios: <happy path, edge cases, error paths>
- What would slip through: <the bug these tests might still miss, and how we cover it>

<!-- Optional: add a "## Batch grant" (PAIRING.md) or "## Waiver" (RULE-TIERS.md) section here. -->

## Approval
<!-- ONLY A HUMAN edits the line below. The hook blocks agents from writing a ticked approval. -->
- [ ] Approved by @<engineer> on <YYYY-MM-DD>
