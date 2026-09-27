# Lessons — <domain>

Lessons agents learned from engineers in this domain. **Tier 2 only**: a lesson never overrides a Tier 0 or Tier 1 rule.

- **Loaded** at plan time; the plan cites the lesson numbers it applied.
- **Added** only after the engineer accepts a proposed lesson. Nothing is stored silently.
- **3 confirmations** → propose promoting the lesson into a rule (a human edits governance).
- **Disputed** → mark it `⚠️ disputed` and let the engineer decide to keep, edit or delete it.
- **Unused for 90 days** → flag it at the monthly retro.
- **Never** include secrets, personal data or customer data.

Copy this file to `learnings/<domain>.md` for each domain (for example `learnings/billing.md`). Tier 3 style choices go to `learnings/engineer-preferences.md` in the same format.

## Lessons
<!-- Format: N. [domain] lesson. Source: task <id> step <n>, @engineer. Confirmations: <k> (tasks: <ids>) -->
1. [example] Money amounts use Decimal, never float. Source: task 000 step 2, @engineer. Confirmations: 1 (tasks: 000)
