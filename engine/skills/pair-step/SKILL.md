---
name: pair-step
description: Use when the pair task is in the stepping or review phase: work exactly one step, show evidence, wait for validation.
---

# pair-step

One step. One file. Evidence the engineer can read. Then stop.

## Stepping (agent-drives)

1. `pair status` — the current step, its kind, its file.

2. Write the step, by kind:
   - **`test` / `char`** — write the test. Arrange–Act–Assert, one behaviour, a name that states
     the behaviour (TEST-002…004). Then ask yourself the devil's-advocate questions: what input
     breaks this, what happens at zero, at the boundary, with the wrong type, twice in a row? Add
     the cases that apply. A `char` step must state which existing behaviour it pins.
   - **`stub`** — signatures only. Bodies raise "not implemented" or return a zero value. Nothing
     that could accidentally pass a test.
   - **`code`** — the minimum that makes the failing test pass. Not the design you would like; the
     code the test demands. The next step can take it further.
   - **`refactor`** — no behaviour change. If a test has to change, you needed a batch grant with
     `--include-tests`.

3. `pair done`. If it fails, read the reason — it names the next action — fix the step's file, run
   it again. **After two failed attempts, stop and report.** A third attempt at the same wall is
   how a small misunderstanding becomes an hour.

4. Post the step report (`pair/engine/templates/step-report.md`) and append it to `log.md`. Copy the
   evidence from `pair done` **verbatim**. Never paraphrase a test result: the number of passing
   tests and the coverage figures are the whole point of showing them.

## Review

Wait. That is the work.

- The engineer asks for a change in chat → `pair rework "<their words>"`, then back to stepping.
- The engineer asks "why" → answer at L2, and log `note: explain`.
- The engineer says nothing → say nothing. They are reading.

Do not start the next step. Do not run `pair ok`. Do not tidy anything up while waiting.

## After a correction

Propose one lesson: `pair lesson propose "<text>" --domain <domain>`.

## Engineer-drives and solo

You do not write step files. After the engineer runs `pair done`, review what they wrote in chat,
with the reverse report: `👀 Noticed · ⚠️ Risk · 💡 Suggest · ❓ Question`, one line each.

## Never

- touch a file outside the step — propose `pair reopen` if the plan is wrong;
- run `pair ok`;
- skip `pair done` and describe the result instead.
