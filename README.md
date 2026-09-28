# pair

**The engineer decides. The agent proposes, writes one file per validated step, and shows its
evidence before anything is committed.**

pair is a plugin plus a CLI. The plugin puts four skills and three hooks into an agent session; the
CLI is the only thing that changes state, and the commands that grant permission or move work
forward need a human at a terminal.

```
pair status          # where the task stands, and whose turn it is
pair start <id>      # begin a task (human only)
pair doctor          # check the setup and print what is missing
```

## The flow

`planning → stepping → review → closing → done`

One approved step is one file is one commit. `pair done` runs the step's evidence — a test that
fails for the right reason, a suite that is green with the changed lines covered — and the engineer
runs `pair ok` only after reading it. CI re-checks the outcome on every pull request, because the
hook is a heuristic at the moment of the edit and the history is the guarantee.

## Repository layout

| Path | What it is |
|---|---|
| `engine/` | the engine's **source**: `lib/pair/`, `bin/pair`, `skills/`, `hooks/`, `defaults/`, `schemas/`, `templates/`, `tests/` |
| `pair/` | this repository's own pair folder, with `pair/engine/` a vendored copy refreshed by `pair upgrade --from .` |
| `docs/pair-SPEC.md` | the source of truth for what pair does |
| `docs/pair-DESIGN.md` | why it works this way |
| `docs/MODULES.md` | the module map — **enforced**: imports point strictly downwards |
| `docs/DECISIONS.md`, `docs/GAPS.md`, `docs/SPEC-CHANGES.md` | what was decided, what is still open, what changed in the spec and why |
| `docs/archive/` | how the idea evolved. History only; never build from it |

## Running it here

```
python3 -m pytest engine/tests        # the whole suite
./engine/bin/pair doctor              # pair, checking itself
./engine/bin/pair check all --base <sha> --head HEAD
```

The engine imports the standard library only, and needs Python 3.11 or newer. Test-only
dependencies are in `engine/requirements-dev.txt`; a test asserts that nothing shipped imports
them.

## Two things worth knowing before changing anything

- **`docs/MODULES.md` is a contract, not a diagram.** Every module carries an integer layer and may
  import only a strictly lower one. It has already caught two real ordering mistakes.
- **pair writes nothing outside the repository.** Not `~/.claude/`, not a user-scoped install, not
  global git config. C37 runs the whole install flow with `$HOME` pointed at an empty directory and
  asserts it stays empty.
