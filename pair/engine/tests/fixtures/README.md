# `engine/tests/fixtures/`

Each fixture is a directory holding a `build.sh` and the files it copies in. **No fixture contains
a committed git repository.** `build.sh` constructs the repo from scratch, at test time, into a
directory the test hands it.

## Why built, not committed

A nested `.git` cannot be committed to this repo without either a submodule or renaming the
directory, and both turn every `git log`, `git status` and worktree operation in a test into a
special case. pair's CLI is mostly git, so the fixtures are mostly git: the part that would be
hardest to trust is exactly the part a committed fixture obscures.

Building also makes the history **legible**. A test that depends on "a commit whose trailer is
`Pair-Action: ok`" can point at the line of `build.sh` that wrote it. A packed object cannot be
read in review.

The cost is speed. Mitigated by building each fixture **once per test session** and copying the
tree per test — `engine/tests/conftest.py` owns that, so no test calls `build.sh` directly.

## The contract

```
engine/tests/fixtures/<name>/build.sh <target-dir>
```

- `<target-dir>` MUST be empty or absent; `build.sh` creates it.
- Exit 0 means the repo is ready. Any failure exits non-zero with a message on stderr.
- `build.sh` runs with `set -euo pipefail` and uses only git, coreutils and python3.
- It MUST NOT read anything outside its own directory and `<target-dir>`, and MUST NOT write
  outside `<target-dir>` — no `~/.gitconfig`, no `/tmp` scratch outside the target (D15, §4).
- It sets `user.name`, `user.email`, `commit.gpgsign=false` and `core.hooksPath` **locally**, so the
  build is identical whatever the engineer's global git config says.
- Timestamps are fixed through `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE`, so commit SHAs are stable
  and a golden file may name one.
- It never invokes `pair`. A fixture is the *starting state*; the test drives the CLI.

## Fixtures

| Name | What it is | First needed by |
|---|---|---|
| `minimal-python` | One package (`packages/billing`) with pytest, a hand-written `pair/` tree with `_repo` and one scope, and two commits of history. | build step 1 |
