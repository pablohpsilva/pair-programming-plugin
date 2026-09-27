# Rule Tiers — TIER-001

Every rule belongs to exactly one tier. The tier says **who can bend it** and **whether agents may learn to change it**.

| Tier | What | Examples (rule IDs) | Engineer can bend? | Agent can learn to change? |
|---|---|---|---|---|
| **0 · Hard** | Safety, process integrity, proof of work | PAIR-001…006, TEST-001, COV-001…004, ARCH-001, COMM-004 | **No.** Change only via an ADR approved by CODEOWNERS | Never |
| **1 · Architectural** | Structure that others rely on | layering, module ownership, contract versioning, COMM-003 | Yes, with a **waiver** in the plan | Proposes only; never self-applies |
| **2 · Engineering** | Good practice with judgment | TEST-002…010, COMM-001/002, PAIR-007, naming, file size, duplication | Yes, with a one-line note in `log.md` | Yes, as a lesson, once the engineer confirms it |
| **3 · Preference** | Taste and style | comment tone, ordering, idioms | Freely | Yes, into `learnings/engineer-preferences.md` |

## Bending a rule (pilot version)
- **Tier 1:** add a `## Waiver` section to the plan before approval:
  ```markdown
  ## Waiver
  Rule: <ID> · Why here: <one line> · Scope: <files> · Expires: end of this task
  Proof of no harm: boundaries + all tests green in CI
  - [ ] Waiver granted by @<engineer>
  ```
  Only a human ticks the box. "No harm" is proven by the gates, not assumed.
- **Tier 2:** the engineer says so in chat; the agent logs `Waived <ID>: <reason>` in `log.md` and proposes a lesson if the choice should repeat.
- **Tier 3:** just do it; propose a preference if it should repeat.

## When a rule keeps getting bent
The same rule waived **3 times** means the rule, or its scope, is wrong. Open a governance change instead of a fourth waiver.

## Conflicts
- A higher tier always wins: Tier 0 > 1 > 2 > 3.
- A lesson never overrides a Tier 0 or Tier 1 rule. If they conflict, flag it to the engineer.
- If the engineer asks to bend a Tier 0 rule, the agent declines **briefly**, says which rule, and offers the ADR route. The agent does not lecture.
