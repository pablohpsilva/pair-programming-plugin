# pair — Open gaps in the SPEC

Found by reading `pair-SPEC.md` v0.1 end to end on 2026-09-27. Nothing here is a change to the
spec yet: each row is a question with a proposed answer, awaiting the engineer. Accepted
answers move to `SPEC-CHANGES.md` and then into the SPEC itself.

Status: `open` · `accepted` (recorded in SPEC-CHANGES.md) · `rejected`.
**All 19 were answered on 2026-09-27 and applied to the SPEC.** G20, raised afterwards, was resolved on 2026-09-28 by D12: `pair init` commits `githooks/commit-msg` and `pair doctor` checks that `core.hooksPath` activates it. **G21 is open**, found on 2026-09-28 while writing `engine/schemas/state.schema.json`: the schema had to enumerate `evidence.result`, and the SPEC attests only two of its values.
Three answers went against the proposal written below — G7 (both config files strict), G13 (rule
IDs must be globally unique) and G14 (the plan hash is stored per step) — and G4 gained an escape
hatch, because requiring a char step to raise coverage would otherwise have made a
characterization test of already-covered behaviour impossible to write at all. The proposals below
are left as they were; the SPEC is the record of what was decided.

| # | Where | Gap | Blocks | Status |
|---|---|---|---|---|
| G1 | §24, §19.1, §8.4 | pair cannot build pair: the engine lives on a protected path | step 3 | **accepted** (DECISIONS.md G1) |
| G2 | §24 | Build step 2's "done when" lists tests that need steps 7 and 8 | step 2 | accepted |
| G3 | §12.4 B1, §11.1 | Human-only detection is per *subcommand*, but three actions differ by flag or sub-subcommand | step 3 | **accepted, changed** |
| G4 | §8.1, §8.2 | Changed-line coverage requirement for `char` steps is undefined in effect | step 2 | accepted (+escape) |
| G5 | §18, G1 | The running engine is one `pair upgrade` behind the source being written | step 3 | accepted |
| G6 | §7.3, §12.4 F6/F11 | Phase `done` row is unreachable, and F6 passes `log.md` before any phase check | step 3 | accepted |
| G7 | §5.2, §5.4 | Unknown key: exit 1 in `config.toml`, warn-and-ignore in `local/config.toml` | step 1 | **accepted, changed** |
| G8 | §7.2, §18 | Two `format` numbers (`config.format`, `state.format`); relationship undefined | step 1 | accepted |
| G9 | §7.4 | No stated behaviour for a transition command run from the wrong phase | step 1 | accepted |
| G10 | §8.2 | No stated behaviour for `pair done` when the step file has no changes | step 2 | accepted |
| G11 | §12.4 F3 | The anti-forgery regex also blocks legitimate agent prose | step 3 | accepted |
| G12 | §8.1, §8.4 | A repo with migrations but no `migrate_check` command can never touch them | step 2 | accepted |
| G13 | §14.5 | `find --rule ID` when the same ID is defined in two places | step 5 | **accepted, changed** |
| G14 | §13.1 `approval` | Whether the plan hash is read at the ok commit or at head — a naive read breaks reopen | step 7 | **accepted, changed** |
| G15 | §10.5 | Rewriting "Last used" inside a lessons file has no pinned line format | step 4 | accepted |
| G16 | §5.1 | No policy for bumping `governance`, or its effect on a live approval | step 4 | accepted |
| G17 | §17, §12.4 F4 | `local/active` can point at a task whose folder is absent on the checked-out branch | step 2 | accepted |
| G18 | §22 | Missing acceptance tests: `red` gate with an empty test command; a range containing a merge commit | step 7 | accepted |
| G19 | §21 | No eval for the SessionStart injection (T2), and E12's "two sources disagree" setup is unspecified | step 4 | accepted |
| G20 | §4, §11.4, §22 C32 | C32 asserts no vendor reference in *generated files*, but nothing enforces it in *commit messages* at write time | step 6 | **resolved** (D12) |
| G21 | §7.2, §8.2 | `evidence.result` has no defined value for a step kind that runs no command (`doc`, `config`), nor for a `stub` step whose scope reports "no tests collected" | step 2 | **open** |
| G22 | §8.1 | A `char` step's escape line must be "in the step report", but the report is written *after* `pair done` runs | step 2 | **accepted, implemented** |

---

## Resolve before build step 1

### G7 — Config strictness differs between the two config files
§5.2: an unknown key in `config.toml` makes every command exit 1. §5.4: unknown keys in
`local/config.toml` are ignored with a warning. Probably deliberate — a personal file must not
brick a teammate's checkout — but the spec never says so, and an implementer will make them
match by accident.

**Proposed:** keep both behaviours and add one sentence to §5.4 giving the reason.
Add a test: an unknown key in each file, asserting exit 1 and exit 0 + warning respectively.

### G8 — Two `format` numbers
`config.toml` has `format = 1` ("pair/ layout version", §18) and `state.json` has
`"format": 1`. §18 defines only `config.format` and the engine's `SUPPORTED_FORMAT`.

**Proposed:** one layout version governs both. `config.format` is authoritative; `state.format`
records the version a task's state was written at, migrations update both, and a command
reading a `state.json` whose `format` exceeds `SUPPORTED_FORMAT` exits 1 with "upgrade the
engine". State it in §18.

### G9 — Wrong-phase transitions
§7.4 gives each command a `from → to` but never says what happens when it is run from another
phase — `pair ok` in `stepping`, `pair approve` in `review`, `pair done` in `closing`.

**Proposed:** one rule in §7.4: a transition command run outside its `from` phase exits 1,
names the current phase, and prints the valid next action — the same wording `pair status`'s
"waiting for" line uses. One test per command.

## Resolve before build step 2

### G2 — Build step 2 cannot meet its own acceptance criteria
§24 step 2 is "done when C3–C13, C16, C21–C29 pass", but:
- **C23** (a batch-granted refactor across 3 files with `include_tests`) needs `pair grant-batch`,
  which §24 schedules for step 8.
- **C27** (a `revert --step n` commit passes CI `commits`; `baseline --lower` passes CI
  `coverage`) needs the CI gates, which §24 schedules for step 7.

**Proposed:** move C23 to step 8. Split C27: the reverting and lowering *behaviour* stays in
step 2, the two "passes CI" assertions move to step 7. Update both rows of §24.

### G4 — Changed lines on a `char` step
§8.1 requires `char` steps to satisfy "coverage passes (full suite green)" and says nothing
about changed lines; §8.2 excludes test files from the changed-line set. A char step only ever
writes test files, so its changed-line requirement is vacuously met — but §8.1's `code` row
states the 100% rule explicitly and `refactor` says "same as `code`", so the omission reads
like an oversight.

**Proposed:** say it outright in §8.1: "`char`: no changed-line requirement — a char step
writes only test files, which §8.2 excludes." Also state that a `refactor` step that only
deletes lines trivially meets COV-002.

### G10 — `pair done` with nothing changed
Not specified. Silently recording green evidence for an empty step would let a step be
"validated" without work.

**Proposed:** `pair done` exits 1 with "no changes in `<path>` — write the step or run
`pair rework`" when the step file set has no diff against HEAD and contains no untracked file.

### G12 — Migrations without a `migrate_check`
§8.1 requires a `migration` step's scope to have a non-empty `migrate_check` that exercises up
and down. `migrations`-class files are allowed for no other kind. So in a repo whose migration
tool has no down path, migration files can never be changed through pair — and by D11 they
cannot be changed outside pair either.

**Proposed:** confirm this is intended (it is a strong, defensible position), and add the
escape hatch explicitly: such a change goes through `pair expedite` or a Tier 1 waiver, and
`pair doctor` names any scope holding migration files without a `migrate_check`.

### G17 — Stale `local/active` after a branch switch
`local/active` is per checkout (§17). Checking out another branch leaves it pointing at a task
whose `pair/tasks/<id>/` does not exist there. Hook rule F4 then reads a missing state file —
§12.2 says any exception exits 2, so every file edit is blocked with a confusing reason.

**Proposed:** F4 treats a missing task folder as "no active task" and denies with
"`local/active` names <id>, which does not exist on this branch — run `pair resume <id>` on its
branch, or `pair start`". `pair status` reports the same. Test it.

## Resolve before build step 3 (the hook)

### G3 — Human-only detection needs flags, not just subcommands
§12.4 B1 denies "a human-only subcommand (§11.1), or a subcommand the hook can't determine".
But §11.1's list is not subcommand-shaped throughout:
- `report --write` is human-only; plain `pair report` is not.
- `lesson accept|edit|reject|dispute` are human-only; `lesson propose` is not.
- `baseline --lower` and `waive --remove` are variants of already human-only commands (harmless).

A hook matching only the first token after `pair` will either let `pair report --write` through
(a hole in PAIR-005) or deny `pair report` (breaking the agent's use of §20).

**Proposed:** §11.1 gains a machine-readable table of (subcommand, sub-subcommand, required
flag) triples, and B1 matches on the triple. Anything it cannot parse confidently — quoted
arguments, variable expansion, an unknown subcommand — denies. Tests: `pair report` passes,
`pair report --write` denies, `pair lesson propose "x" --domain d` passes,
`pair lesson accept 1` denies.

### G6 — Phase `done`, and `log.md` bypassing the phase check
Two small inconsistencies:
1. §7.3's `done` row says the agent may edit nothing, but `pair close` clears `local/active`,
   so F4 already denies everything. The row is unreachable.
2. F6 passes the active `log.md` before F11 checks the phase, so §7.3's per-phase columns are
   not actually what the hook enforces for `log.md` — it is always writable while a task is
   active. That matches §3.1 ("yes, active task only, append-only") and is probably right.

**Proposed:** keep the hook as it is and fix the prose: §7.3 gains a footnote that `log.md` is
writable in every phase of an active task, and that phase `done` is unreachable because
`local/active` is cleared. No behaviour change.

### G11 — The anti-forgery regex has real false positives
F3 denies any file write whose string fields contain a line matching
`(?im)^\s*[-*]?\s*\[[xX]\].*\b(approved|granted)\b`. That also blocks the agent from writing a
walkthrough's `## Waivers used` section as a checklist, or quoting a waiver line
("- [x] approved by @ana on 2026-09-27") into `log.md`.

**Proposed:** keep the rule — failing closed on forged approvals is correct, and the cost is
one rephrasing — but make the deny message say so: "PAIR-005: that looks like a forged
approval. Write it as prose without a checkbox." Test both the true positive and the
false positive.

### G5 — The engine you run is behind the engine you write
With G1 accepted, the agent writes `<root>/engine/**` while Claude Code loads the plugin and
the CLI from the vendored `<root>/pair/engine/**`. Every step would need a `pair upgrade --from .`
to take effect, and `pair upgrade` is human-only and commits — so it cannot sit inside a step.

**Proposed:** during development of pair itself, point both entry points at the source:
`/plugin marketplace add ./engine` (subject to spike T1) and `PATH` → `<root>/engine/bin`.
`pair/engine/` is then a **release artifact**, refreshed by `pair upgrade --from .` at the end
of each build step, which is also how C20 and §18 get exercised. Record it in the new §3.2.

## Resolve at the step that needs them

### G13 — `find --rule ID` with two definitions
§14.5 returns "the rule's defining table row (or section) exactly". A scope `RULES.md` may
define a `SCOPE-` id that another scope also uses, and a project could shadow an id.
**Proposed:** return every match in §6.2 precedence order, each with its source path, and never
merge them.

### G14 — Where the `approval` gate reads the plan hash
§13.1: the gate fails when "the SHA-256 of `plan.md` at the ok commit's parent differs from
`state.approval.plan_sha256`". After a `reopen` and re-approval the hash changes, so ok commits
made before the reopen carry the old hash. The gate only works if **both** sides are read at
that ok commit — the plan file from its parent, the expected hash from the `state.json` in the
ok commit itself. An implementation that reads `state.json` at head fails every pre-reopen
commit.
**Proposed:** say this explicitly in §13.1, and add a CI test with a reopen in the history.

### G15 — Pinning the lessons file format
§10.5 shows a lesson line carrying `Last used: <date>` and confirmations as indented
sub-lines. `pair close` rewrites "Last used" in place, `lesson accept` appends either a new
lesson or a `confirmed` sub-line, and merges may duplicate sub-lines. That needs an exact
grammar, not an example.
**Proposed:** build step 4 defines the line grammar as a regex in the spec, with round-trip
tests over a file containing: a plain lesson, one with confirmations, a disputed one, and
duplicate confirmations from a merge.

### G16 — Bumping `governance`
Nothing says who bumps it, when, or what happens to a task approved under the previous version.
**Proposed:** it is bumped by a human in the same commit that changes `engine/defaults/rules.md`;
`state.governance` is captured at `pair start` and never rewritten; a mid-task bump is logged as
a `note` and does not invalidate `state.approval`. `pair doctor` lists tasks running on an
older governance version.

### G18 / G19 — Test and eval coverage holes
§22 has no CI test for the `red` gate when the scope's `test` command is empty (possible for
`_repo`), and none for a range containing a merge commit (§13.1 excludes them — untested).
§21 has no eval for the SessionStart injection that T2 is meant to validate, and E12's "two
sources disagree" has no setup.
**Proposed:** add the two CI tests in step 7, and in step 4 add E16 (a session with no user
prompt: the agent's first action is `pair status`) plus a concrete E12 fixture (a `docs` page
and a `llm-wiki` page giving different rounding rules).

### G20 — C32 has no runtime counterpart
D6 forbids any AI vendor reference in generated output, and §22 C32 asserts it for generated
*files*. Nothing checks a **commit message** as it is written. In this repo that hole was closed
on 2026-09-27 with `githooks/commit-msg` plus `git config core.hooksPath githooks` — refuses a
`Co-Authored-By:` naming an AI vendor, a `Claude-Session:`/`Generated-By:` trailer, or a session
link; a human co-author trailer still passes; `--no-verify` overrides it visibly.

Whether pair should do this for consuming repos is undecided, and it is not a free change:

- **§4 says `pair init` MUST NOT create files outside `pair/`** beyond the three pointer files. A
  root `githooks/` would be a fourth. Avoidable: ship the hook *inside* the engine
  (`pair/engine/githooks/commit-msg`) and have `init` only run
  `git config core.hooksPath pair/engine/githooks` — a config change, not a new file.
- **`core.hooksPath` is exclusive.** Setting it silently disables any hooks the project already
  has in `.git/hooks/`. `init` must detect that and either refuse or chain to the existing
  directory; `doctor` should report when the path is unset or points elsewhere.
- **It is per-clone**, since git config is not committed. `init` sets it; `doctor` must check it,
  or the guarantee quietly lapses for everyone who cloned.

**Proposed:** build step 6 (`init`, `doctor`) ships the hook inside the engine, `init` offers the
`core.hooksPath` line after checking for existing hooks, `doctor` verifies it, §4 gains a note
that the only thing outside `pair/` is a git *config* value, and the commit-message rule joins
the registry as a Tier 0 engine rule enforced by "git hook + CI `format`".

---

## G21 — what `evidence.result` is when nothing ran

**Where:** §7.2 (`state.json`), §8.2 (evidence mechanics), §8.4 (empty commands).

§7.2's example shows `"result": "red"` and `"result": "green"`, and §8.2 says which command each kind
runs: `stub` and `test` run `test`; `char`, `code` and `refactor` run `coverage`. It says nothing
about the other three kinds, and two cases have no value to record:

1. **`doc` and `config` steps run no command.** Is `evidence` absent, `null`, or a third result?
   `pair ok` needs an answer, because it stores hashes of the file set (§8.2) and those belong in
   `evidence`, so `evidence` cannot simply be missing.
2. **A `stub` step whose scope reports "no tests collected."** §8.4 gives `no_tests_exit_codes` and
   C29 says such a step *passes* with pytest's exit code 5 — but a passing stub is not `green`, and
   calling it `red` would make the `red` CI gate (§13) inspect a run that never had a test to fail.
   The gate skips `stub`, so nothing breaks today; the value stored is still undefined.
3. **A `migration` step** presumably runs `migrate_check`, which §8.2 never says.

**Found by:** writing the schema for `state.json`. The enum could not be written without deciding
this, and guessing would have put four invented values into a file that the CLI is then tested
against.

**Proposed:** `result` ∈ `red | green | none`, where `none` means no command was defined for the
kind, plus `no-tests` for case 2 so that C29's pass is distinguishable in `log.md` and in
`pair status`. §8.2 gains a row per kind, including `migration` → `migrate_check`. The schema keeps
`red | green` until this is decided, and cites this gap.

**Blocks:** build step 2 (evidence). Step 1 does not touch it.

---

## G22 — where `pair done` looks for a char step's escape line

**Where:** §8.1 (the `char` escape), §9.3 step 3–4, §10.2.

§8.1 says a `char` step whose coverage did not rise passes only when "the step report carries a line
`⚠️ no coverage gain: <reason>`", and that `done` records it verbatim. But §9.3's procedure runs
`pair done` at step 3 and posts the step report at step 4 — so at the moment `done` runs, the report
does not exist yet. Read literally, the escape can never be taken.

**Resolved by reading "the step report" as "the report in `log.md`", which is where a step report
lives (§10.2).** `pair done` scans the task's `log.md` for a `⚠️ no coverage gain:` line inside an
entry for *this* step, and records it verbatim in the evidence. When it is absent, `done` fails with
a message naming the file to append it to — so §9.3's loop still works: `done` fails, the agent
appends the line and runs `done` again.

The alternative — a `--no-coverage-gain "<reason>"` flag on `pair done` — was rejected: the reason
has to reach the engineer's eyes in the report they are about to read, and a flag would let it be
passed without ever being written down.

Implemented as `evidence.find_no_gain_note`, covered by C22.
