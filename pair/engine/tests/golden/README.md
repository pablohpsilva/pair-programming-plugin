# `engine/tests/golden/`

Expected output, byte for byte. One file per case, named `<command>[.<case>].<ext>`:

```
status.review.txt          pair status, phase review
status.line.no-task.txt    pair status --line with no active task
status.json                pair status --json
check.commits.fail.txt     pair check commits, one failure per line
session-start.txt          the SessionStart injection (SPEC 12.3)
plan.new.md               a plan rendered from the template
```

## Updating

```
PAIR_UPDATE_GOLDEN=1 pytest engine/tests
```

rewrites every golden file from actual output and **fails anyway**, so a run that updates can never
be mistaken for a run that passed. The diff then goes in the step report: a changed golden file is a
changed contract, and review is the whole point of having it in git.

## What may go in one

Only output that is **deterministic by construction**. Anything that varies is either seamed
(`clock.now`, §MODULES) or excluded from the comparison by the test, never normalised inside the
golden file itself — a golden file with a regex in it is not a golden file.

The two that bite:

- **Timestamps.** Tests pin `clock.now`. A golden file containing a real wall-clock time is a bug.
- **Paths.** Absolute paths differ per machine. Commands print repo-relative paths (that is the
  requirement, not the workaround); where an absolute path is unavoidable, the test replaces the
  repo root with `<root>` before comparing.

Commit SHAs are allowed, because the fixtures fix their dates and so their SHAs (see
`fixtures/README.md`).

## The size limit

A golden file longer than about 40 lines is usually a test that has stopped asserting anything. If
the output is genuinely that long, assert the part that matters and leave the rest to a smoke test.
`--json` output is the exception: it is compared whole, because every key of it is a contract.
