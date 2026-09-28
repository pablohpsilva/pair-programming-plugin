---
name: pair-close
description: Use when the pair task is in the closing phase: write the walkthrough and hand over for the understanding check.
---

# pair-close

The task is built. What remains is making sure the engineer can carry it without you.

## Procedure

1. **Write `walkthrough.md`** from `pair/engine/templates/walkthrough.md`. Every section is
   required; write "none" where nothing applies. Aim at five minutes of reading — a walkthrough
   nobody finishes protects nobody.

   `## How to roll it back` is the section people skip and the one that matters at 2am. Write the
   actual command, not "revert the commits".

2. **Fill "Possibly stale knowledge"** from `pair/local/find_log/<id>.jsonl`: the pages you read
   during this task whose topic this change touched. Not everything you searched — only what is now
   arguably out of date. Give the path, so the engineer can act on it.

3. **List promotion candidates.** Lessons with at least `learning.promote_after` confirmations are
   worth proposing as rule changes. Text only: you propose, the engineer decides.

4. **Offer the export:** "Run `pair export walkthrough` if you want this in your wiki."

5. **End with:** "Run `pair close` when you can explain this change without me."

That sentence is not a formality. `pair close` asks the engineer, on their terminal, whether they
can explain the change to a colleague without you. If they cannot, the honest answer is no, and the
right next move is for you to explain it — at L2, or L3 if they want the whole thing.

## In solo mode

The engineer writes the walkthrough. You review it: what a colleague would still not understand,
what the rollback section misses.
