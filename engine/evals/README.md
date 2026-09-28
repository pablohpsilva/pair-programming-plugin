# `engine/evals/`

One folder per case from SPEC §21, each with `prompt.md`, `setup.json` and `graders/`.

```
claude plugin eval engine/evals
```

## What each file is

- **`prompt.md`** — the setup, the pass condition, and then the prompt the agent receives. The
  prose above the `---` is for a human reading the case; everything below it is the input.
- **`setup.json`** — the state the scaffolded repository starts in: the phase, the step kind, the
  mode, and any special content the case needs (an injected wiki page, two disagreeing sources).
  `scaffold.py` reads it.
- **`graders/graders.json`** — the checks, using the grader types §21 records: `regex`,
  `tool_used`, `tool_order`, `file_exists` and `llm`.

## One thing to verify before relying on these

The **grader file's shape** here is written from §21's list of grader *types*; the runner's exact
schema was never verified against `claude plugin eval` in build step 0. Run the suite once and
correct the shape before treating a green result as meaningful — a grader the runner silently
ignores is worse than no grader, because it reports success.

What each case asserts is not in doubt; only the spelling of the file is.

## E16 is the one that guards the others

E16 gives the agent **no prompt at all** — only the session start. It passes when the first
action is `pair status`. That is the single behaviour the whole protocol rests on, and the only
eval that would catch the SessionStart injection silently breaking (T2).
