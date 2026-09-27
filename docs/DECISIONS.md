# pair — Decisions

Answers to SPEC §2, confirmed by the engineer on 2026-09-27.
Where an answer changes the spec, the change is recorded in `SPEC-CHANGES.md` and the
row below says which sections it touches. **This file records what was decided; the SPEC
stays the source of truth for behaviour.**

| # | Decision | Answer | Status |
|---|---|---|---|
| D1 | Tool and directory name | `pair` → `<repo>/pair/` | default kept |
| D2 | CLI and hook language | Python ≥ 3.11; **stdlib only at runtime**, dev-only test deps allowed | clarified |
| D3 | File formats | TOML (human) / JSON (machine) / Markdown (documents), with a hand-rolled TOML writer | default kept |
| D4 | Engine distribution | Vendored in `pair/engine/`, replaced by `pair upgrade` | default kept |
| D5 | Where humans approve | A terminal in v1; in-session approval named as a v2 item | extended |
| D6 | Commit authorship | **Engineer always. No `Co-Authored-By`, no vendor reference anywhere** | changed |
| D7 | CI platform | GitHub Actions first; `pair check` stays CI-agnostic | default kept |
| D8 | Operating systems | Linux and macOS; Windows through WSL only | default kept |
| D9 | License | MIT | default kept |
| D10 | Initial governance version | `0.1` | default kept |
| D11 | Scope of enforcement | **Every** change outside `pair/` goes through a task (pointer files excepted) | default kept |
| G1 | Where the engine's source lives in this repo | `<root>/engine/`; `pair/engine/` is a vendored copy | new |

---

## D1 — Name

CLI `pair`, directory `<repo>/pair/`, skills `pair`, `pair-plan`, `pair-step`, `pair-close`,
commit trailers `Pair-*`, engine rule prefix `PAIR-`. No renaming needed anywhere.

## D2 — Language

- **Shipped engine** (`engine/lib/pair/**`, `engine/bin/pair`, the hook): Python ≥ 3.11,
  **standard library imports only**, no network calls (SPEC §19.2 stands unchanged).
- **The engine's own test suite** may use `pytest` and `coverage.py`. They are dev-only:
  never imported by shipped code, installed by CI, and listed in a dev requirements file.
- Why: SPEC §22 needs a test runner, dogfooding from build step 3 needs a Cobertura-producing
  coverage tool, and C29 explicitly names pytest's exit code 5.
- Consequence for build step 1: a runtime-import test asserts that no module under
  `engine/lib/pair/` imports anything outside the stdlib.

## D3 — Formats

`tomllib` reads TOML but cannot write it, so the engine ships a **narrow TOML emitter**
covering only the shapes pair writes — tables, arrays of tables, strings, numbers, booleans,
string arrays, dates — with round-trip tests. Files it writes: `rules/waivers.toml`,
`rules/baseline.toml`, `rules/boundaries.toml`, `scopes/**/scope.toml`, `config.toml`.
Human-facing config stays hand-editable, which is the reason TOML was chosen.

## D4 — Distribution

`pair/engine/` is committed in every consuming repo and replaced as a unit by
`pair upgrade --from <path|git-url@tag>`, which runs the format migrations (SPEC §18).
Confirmed independently of spike T1: if T1 fails, the *plugin* is loaded from a git
marketplace while the CLI stays vendored (§23 T1 fallback).

## D5 — Approvals

v1: human-only commands require stdin and stdout to be TTYs and read the confirmation from
`/dev/tty` (SPEC §11.1 layer 1). The engineer keeps a second terminal beside the session.

Additions accepted:
- SPEC §25 gains a line committing in-session approval to v2 rather than leaving it open.
- The confirmation path lives behind **one function** (`confirm(prompt, expect) -> bool` in
  `engine/lib/pair/tty.py`) so a session-UI channel can replace it without touching commands.
- Spike T4 decides how much layer 1 is really worth; the spec is updated with the result.

## D6 — Authorship

Commits are authored by the engineer's git identity. **No `Co-Authored-By` trailer, and no
reference to Claude, Claude Code or any vendor in any generated file, commit message,
template or default config.**

Follow-up (D6b), accepted: the `[agent]` config table and `agent.trailer` are deleted, and
CI stops trying to recognise "an agent commit". The `protected` gate is redefined as:

> **any** commit touching a protected path (§19.1) must be a `Pair-Action` commit whose
> action is permitted to write those paths (§11.2).

This is strictly stronger than the current rule — it also catches a human hand-editing
`pair/rules/` outside a `pair waive` — and needs no agent identity. §15.2's "and only when it
has no agent trailer" clause is dropped; the TTY check already makes `baseline --lower`
human-only. Touches §5.1, §11.3, §13.1, §15.2.

## D7 — CI

`pair init` generates `.github/workflows/pair.yml` from `templates/ci-github.yml`.
`pair check <gate> --base <sha> --head <sha>` takes plain SHAs and knows nothing about the
platform, so another CI is only another template. Other platforms stay out of v1 (§25).

## D8 — Platforms

Linux and macOS. This licenses `/dev/tty`, `os.isatty`, and POSIX-only command splitting in
the Bash hook (§12.4). Windows through WSL; native Windows stays in §25.

## D9 / D10

MIT `LICENSE` at the repo root. `governance = "0.1"`, cited in plans and on every CLI commit
as `Pair-Governance: 0.1`. It versions the **rule registry** and moves independently of
`engine/VERSION`.

## D11 — Enforcement

Every commit touching a file outside `pair/` must be a `Pair-Action: ok` or
`Pair-Action: revert` commit, or CI's `commits` gate fails. Pointer files (§4) are the only
exception. Accepted consequence: a one-line README fix needs a task (`doc` step, `solo` mode
if the engineer writes it). Uniform whoever held the keyboard, which is the point.

## G1 — Engine source location (new decision, resolves a contradiction)

SPEC §24 says "from step 3 on, build the engine with pair itself", but §19.1 makes
`pair/engine/**` a protected path agents may never edit and §8.4 says files under `pair/`
belong to no scope and cannot be step files. As written, **pair cannot build pair**.

Resolution:

| Path | What it is |
|---|---|
| `<root>/engine/` | The engine's **source**. An ordinary scope (`pair/scopes/engine/scope.toml`), so the agent writes it one file per validated step like any other code. Tests at `engine/tests/`, spike results at `engine/tests/FINDINGS.md`. |
| `<root>/pair/engine/` | A **vendored copy**, refreshed with `pair upgrade --from .`. Exercises §18 for real and keeps §3's layout true for consuming repos. |

Tier 0 protection stays absolute; the hook, the `protected` gate and scope resolution need no
special case. SPEC §3 continues to describe consuming repos exactly as written; a new §3.2
describes this repo.

Open operational point, see `GAPS.md` G5: while `pair/engine/` is the copy that runs, the tool
in use is one `pair upgrade` behind the code just written.
