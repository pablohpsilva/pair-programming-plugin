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
| D12 | Files outside `pair/` | **Allowed.** `.claude/settings.json` and `githooks/commit-msg` join the three in §4 | changed |
| D13 | Skill folder names | Kept as `{pair,pair-plan,pair-step,pair-close}`; the docs spell the invoked names `pair:pair-plan`, … | clarified |
| D14 | Where the `pair` CLI ships | In the plugin's `bin/`, so it is on the agent's PATH — accepting that the plugin is terminal-only | new |
| D6b | Reach of the no-vendor-reference rule | Extends to this spec's own prose, not only to commits and generated output | extended |
| D15 | Scope of everything pair installs | **Project only.** No command writes to `~/.claude/`, uses `--scope user`, or touches global git config | new |
| D16 | The four shared build artifacts | `docs/MODULES.md` is an **enforced** layering contract; `engine/schemas/` ships but is read only by tests; fixtures are **built** by `build.sh`, never committed | new |

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

---

## D12 — Files outside `pair/` are allowed (2026-09-28)

§4 forbade any file outside `pair/` beyond the three pointer files. Two things wanted a fourth,
and the engineer allowed both after the mechanism was verified in build step 0.

**`.claude/settings.json`** is the whole install story, and it costs a colleague nothing. It
declares `extraKnownMarketplaces.pair-local` with a **relative** `"path": "./pair"` and
`enabledPlugins."pair@pair-local": true`. Measured (T1.8): the relative path resolves against the
project directory, **no install record is created**, nothing is written to the engineer's own
settings, and the plugin loads at the first session that accepts the workspace-trust dialog.
Verified to survive repeated cloning.

**`githooks/commit-msg`** enforces D6 at write time. It is **not** the same kind of win: measured,
`core.hooksPath` is local git config and a clone does **not** inherit it, so the committed hook is
inert until each engineer runs `git config core.hooksPath githooks`. `pair doctor` checks
`git config --get core.hooksPath` and prints the command when it is unset. Because the setting
takes exactly one directory, `doctor` reports a conflict with another tool's hooks directory rather
than overwriting it.

Consequences: §4 gains both rows and a paragraph separating their activation costs; `pair init`
merges only its two keys and never writes `.claude/settings.local.json`, which would shadow the
declaration for one engineer; §11.4 step 6 no longer tells a colleague to install anything; and
`pair doctor` grows two checks. The cloud-session fallback stays documented, because a cloud
session never shows the trust dialog.

## D13 — Skill folder names stay; the docs name the invocation (2026-09-28)

Skills are namespaced `<plugin>:<folder>`, so §3's folders surface as `pair:pair`,
`pair:pair-plan`, `pair:pair-step`, `pair:pair-close`. Renaming the folders to `{pair,plan,step,
close}` would read better at the call site; the engineer kept the folder names. Every place that
names a skill — §9.1's phase map, §9.2–§9.4's headings, §21's eval prompts — uses the prefixed
form, recorded in the new §3.3.

## D14 — The CLI ships in the plugin's `bin/` (2026-09-28)

A plugin's `bin/` is on the agent's shell PATH while the plugin is enabled, so `pair` is a bare
command in an agent session with no PATH setup and no wrapper. §12.4's Bash rows already parse a
bare `pair` command word, which is now the normal case rather than a fallback.

The accepted cost: a plugin with a top-level `bin/` is not installable on the hosted web and
desktop products. pair is a terminal tool regardless — §11.1's human-only commands require a TTY
(T4) and CI invokes the CLI by path — so nothing in the spec worked in a hosted session anyway.
`pair doctor` does not treat a hosted session as supported.

One wrinkle, recorded in §3.3: PATH comes from the **plugin root**, so the `pair` an agent session
runs is always the vendored `pair/engine/bin/pair`, never `<root>/engine/bin/pair`. In this
repository that is precisely why §3.2 refreshes the vendored copy at each build-step boundary.

## D6b — The no-vendor-reference rule reaches this spec's prose (2026-09-28)

D6 said "no reference to the vendor at all". Asked whether that covered the spec's own prose, where
the platform was named five times, the engineer said yes. §1, §0's `[V]` note, §2's engine row, §3's
`marketplace.json` comment and §23's title now say "the host CLI" or "an agent".

**One exception, deliberate:** literal command invocations stay. `claude plugin eval` in §21 and
`claude plugin marketplace add` in §4 are executable commands, not references — removing the binary
name would make the instruction unfollowable. The rule is about attribution and branding, and a
command that must be typed is neither.

## D15 — Everything pair installs is project-scoped (2026-09-28)

pair configures one repository. It MUST NOT change how the engineer's other repositories behave.
So no command writes to `~/.claude/` — not `settings.json`, not `plugins/` — none uses
`--scope user`, and none touches global git config. `core.hooksPath` is set repository-locally.

Where an engineer might reasonably want a user-scoped install, `pair doctor` prints the
project-scoped command and leaves the choice to them: that is a decision about their own machine,
not one pair makes on their behalf.

The host CLI's own cache under `~/.claude/plugins/` belongs to the client. pair does not read,
write or clean it; `doctor` reports what it finds there and touches nothing.

Enforced, not just stated: C37 runs `init`, `doctor`, `baseline`, `upgrade` and a full task with
`$HOME` pointed at an empty directory and asserts the directory is still empty, and that no
argument list contains `--scope user` or `git config --global`.

Build step 0 is the evidence this is achievable: the entire install flow ran at project scope and
left the engineer's settings untouched (T1.2).

---

## D16 — MODULES.md is enforced, schemas are for tests, fixtures are built (2026-09-28)

Three questions asked before build step 1, because all three would otherwise be answered by whoever
wrote the first module, silently and per file. SPEC §3.4 records the result; C38–C40 enforce it.

### `docs/MODULES.md` is enforced, not prose

Every module of `engine/lib/pair/` carries an integer **layer**, and a module may import another
`pair` module only when its layer is strictly lower. C38 reads the table and walks the AST.

A prose module map would have been free to write and worth nothing by step 5: pair's own rules say
enforce with tools, not prose (P9), and a boundaries gate for *other* repos (§13 `boundaries`, ARCH-001)
while the engine's own layering went unchecked would be the clearest possible case of not eating the
cooking. The layer rule is deliberately the cheapest one that works — strictly-lower ordering makes
the graph acyclic by construction, so there is no cycle detection to write and no allow-list per
module to maintain. Two modules in the same layer can never import each other, which is the single
most common way a dependency graph rots.

A listed module MAY be absent: the table is the plan as much as the map, and the build steps fill it
in. A module on disk that is **not** listed fails, because that is how a module appears without
anyone deciding which layer it belongs to.

The four layer-1 modules that exist only because of D2 — `globs`, `tomlio`, `schema`, `gitcmd` — are
named in `MODULES.md` with that reason attached, so a later reader does not "simplify" one away by
reaching for a dependency.

### `engine/schemas/` ships, and only tests read it

The engine validates with hand-written standard-library checks (`schema.py`), because D2 allows no
runtime dependency. The schemas are a **second, independent** statement of each format, and C39 uses
them twice: it validates the SPEC's own literal example against the schema, so a format that changes
in one place and not the other fails immediately; and it asserts that `jsonschema` and `schema.py`
reach the same verdict, so a divergence is reported as a bug in the module that actually ships.

Rejected: keeping the schemas out of the shipped tree. They are small, they are the clearest
documentation of each format that exists, and a consuming repo that vendors the engine gets the
second leg of C39 for free — the leg that checks the production validator.

`jsonschema` is in `engine/requirements-dev.txt`. C31 reads the AST of every shipped file to prove
nothing imports it, or pytest, or coverage.

### Fixtures are built by `build.sh`, never committed

A committed `.git` inside this repository needs either a submodule or a renamed directory, and both
turn every `git log`, `git status` and worktree call in a test into a special case — exactly the
calls that most need to be trusted, since the CLI is mostly git.

Building also makes the history reviewable. A test that depends on "a commit whose trailer is
`Pair-Action: ok`" can point at the line of `build.sh` that wrote it; a packed object cannot be read
in a pull request.

The cost is speed, and it is paid once: `conftest.py` builds each fixture once per session and copies
the tree per test. `build.sh` fixes `user.name`, `user.email` and the commit dates, so SHAs are
reproducible and a golden file may name one. It never invokes `pair`: a fixture is the starting
state, and a fixture built by the code under test proves nothing.

`conftest.py` also points `$HOME` and git's global and system config at empty directories for the
whole session. C37 asserts that no command writes outside the repository (D15); doing it everywhere
means a command that reaches for `~/.claude/` fails in whichever test provoked it, not only in C37.
