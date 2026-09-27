# Spec changes

| Date | Section | Change | Why |
|---|---|---|---|
| 2026-09-27 | §2 D2, §19.2 | "Standard library only" now means **at runtime**; the engine's own test suite may use pytest and coverage.py as dev-only dependencies | §22 needs a test runner and dogfooding needs Cobertura output; C29 already names pytest's exit code 5 |
| 2026-09-27 | §2 D5, §11.1, §25 | v1 stays terminal-only, but §25 names in-session approval as a v2 item, and the confirmation is isolated behind one function (`tty.confirm`) | Keeps the v2 path open without widening v1 scope |
| 2026-09-27 | §2 D6, §5.1, §11.3, §13.1, §15.2 | Commits are authored by the engineer with **no `Co-Authored-By` and no vendor reference anywhere**. The `[agent]` config table is deleted. The `protected` gate no longer keys on "agent commit" | Engineer's decision: no vendor reference in generated output. The gate becomes stronger, not weaker (see details) |
| 2026-09-27 | §3 (new §3.2), §24 | In this repo the engine's **source** lives at `<root>/engine/`; `pair/engine/` is a vendored copy refreshed by `pair upgrade --from .` | Resolves a contradiction: §24 asks pair to build pair, while §19.1 protects `pair/engine/**` and §8.4 gives files under `pair/` no scope |
| 2026-09-27 | §24 | G2: step 2's acceptance list drops C23 (needs `grant-batch`, step 8) and C27's two CI assertions (need step 7) | Step 2 could not pass its own criteria |
| 2026-09-27 | §8.1, §10.2, §22 C22 | G4: a `char` step must raise the scope's line or branch coverage, with a `⚠️ no coverage gain: <reason>` escape recorded in the evidence, and refuses when the scope has no baseline entry | A char step exists to buy coverage on untested code, so it must buy some — without making an already-covered behaviour impossible to pin |
| 2026-09-27 | §3.2 | G5: during development the plugin and CLI load from `engine/`; `pair upgrade --from .` refreshes `pair/engine/` at each build-step boundary | A step must take effect without a human-only upgrade commit, while still exercising §18 for real |
| 2026-09-27 | §7.3 | G6: `log.md` is writable in every phase of an active task, and the `done` row is unreachable | The hook was right; the table was a simplification |
| 2026-09-27 | §5.4 | G7: an unknown key in `local/config.toml` now **exits 1**, as in `config.toml` | A typo such as `user` for `me` must fail loudly, not leave a default handle nobody chose |
| 2026-09-27 | §18 | G8: one layout version governs both `config.format` and `state.format` | A task started before an upgrade must stay readable after it |
| 2026-09-27 | §7.4 | G9: a transition command run outside its `from` phase exits 1, names the phase and the next action | Behaviour was undefined for every command |
| 2026-09-27 | §7.4 | G10: `pair done` refuses a step whose file set has no diff and no untracked file | One ok commit must always mean one real change (PAIR-003) |
| 2026-09-27 | §12.4 F3 | G11: the deny message tells the agent to rephrase; the false positive is accepted and tested | Failing closed on forged approvals is right; the cost is one rephrasing |
| 2026-09-27 | §8.1, §11.2 | G12: migrations with no `migrate_check` stay blocked; the ways out are `expedite` or a Tier 1 waiver, and `doctor` names such scopes | An irreversible migration deserves the friction, but the dead end must be visible at setup |
| 2026-09-27 | §6.2, §11.2, §13.1 | G13: rule IDs are **unique across the repo**; `doctor` and CI `format` fail on a duplicate | `find --rule` then always has exactly one row to return |
| 2026-09-27 | §7.2, §7.4, §13.1 | G14: the approved plan hash is stored **per step** (`approved_plan_sha256`) and compared at that ok commit | A `reopen` must not invalidate steps validated under the earlier plan |
| 2026-09-27 | §10.5 | G15: the lesson line and confirmation sub-line get an exact regex grammar, with round-trip tests | Three commands rewrite that file; an example is not a contract |
| 2026-09-27 | §6.3 (new) | G16: a human bumps `governance` alongside the rules; `state.governance` is captured at `start`; a mid-task bump is logged, not blocking | A rule change must not interrupt work in progress |
| 2026-09-27 | §12.4 F4, §11.5 | G17: an absent task folder means "no active task" with an actionable message, never exit 2 | An ordinary `git checkout` must not block every edit with an opaque error |
| 2026-09-27 | §22 | G18: C34 (`red` gate with an empty test command), C35 (a range containing a merge commit), C36 (an `approval` run across a `reopen`) | Three paths every real PR depends on, none of them tested |
| 2026-09-27 | §21 | G19: new eval E16 (SessionStart injection) and a concrete fixture for E12 | T2 is validated once by a spike; nothing kept it working |
| 2026-09-27 | §12.4 B1/B4, §11.1, §22 | G3: B1 is inverted into an **allowlist** of agent-safe `pair` forms; everything else denies, including anything the hook cannot parse | A denylist fails open when someone forgets a flag — which is exactly how `report --write` slipped through |

---

## Details of the accepted changes

**Applied to `pair-SPEC.md` on 2026-09-27.** Each block records what changed, for the record.

### C1 · §2 D2 and §19.2 — stdlib only, at runtime

- §2 D2 default becomes: "Python ≥ 3.11. **Shipped code imports the standard library only**;
  the engine's own test suite may use pytest and coverage.py as dev-only dependencies."
- §19.2 first bullet becomes: "The engine's **shipped code** is standard library only and makes
  no network calls, except `pair upgrade --from <git-url>` through `git`. Dev-only test
  dependencies are declared in `engine/requirements-dev.txt` and are never imported by shipped
  code."
- §22 gains a CLI test: **C31** — no module under `engine/lib/pair/` imports a non-stdlib module.

### C2 · §2 D5, §11.1 and §25 — approvals

- §11.1 mechanism 1 gains: "The confirmation is read through a single function
  (`engine/lib/pair/tty.py::confirm`) so the channel can be replaced without touching commands."
- §25's first bullet changes from "out of scope" to: "Approvals inside the Claude Code session.
  v1 uses the terminal (D5); **planned for v2** behind `tty.confirm`."

### C3 · §2 D6, §5.1, §11.3, §13.1, §15.2 — authorship

1. **§5.1** — delete the whole `[agent]` table (`names`, `email`, `trailer`).
2. **§11.3** — delete the `Co-Authored-By: Claude <noreply@anthropic.com>` line from the example
   commit message, and delete the bullet "**The `Co-Authored-By` line** (from `agent.trailer`) is
   added only in agent-drives mode."
3. **§13.1** — delete the definition "**Agent commit:** a commit with a `Co-Authored-By`
   trailer naming one of `agent.names`, or whose author email equals a non-empty `agent.email`."
4. **§13.1 `protected` gate** — replace "An agent commit touches a protected path" with:

   > **Any** commit touching a protected path (§19.1) that is not a `Pair-Action` commit whose
   > action is permitted to write those paths (§11.2). `Pair-Action: ok` may touch
   > `rules/baseline.toml` only to increase values.

5. **§15.2** — in "CI `coverage` accepts a decrease only in such a commit, and only when it has
   no agent trailer", delete ", and only when it has no agent trailer".
6. **New, repo-wide rule** for §19.2: no generated file, template, default config, commit
   message or skill text names a specific AI vendor or product.
7. **§22** gains a CI test: **C32** — a human hand-edit of `pair/rules/overrides.md` outside a
   `Pair-Action` commit fails the `protected` gate (this is the behaviour the old rule missed).

### C4 · New §3.2 and §24 — where the engine's source lives

Add after §3.1:

> ### 3.2 This repository (building pair itself)
>
> pair's own repo is laid out differently from a consuming repo, because `pair/engine/**` is a
> protected path (§19.1) and files under `pair/` belong to no scope (§8.4):
>
> | Path | What it is |
> |---|---|
> | `engine/` | The engine's **source**: `lib/pair/`, `bin/pair`, `skills/`, `hooks/`, `defaults/`, `templates/`, `migrations/`, `tests/`. An ordinary scope, declared in `pair/scopes/engine/scope.toml`, so it is written one file per validated step like any other code. |
> | `pair/engine/` | A **vendored copy** of `engine/`, refreshed with `pair upgrade --from .` at the end of each build step. It is a release artifact, never edited by hand. |
> | `docs/` | This spec, the design document, DECISIONS.md, GAPS.md, SPEC-CHANGES.md. |
>
> While developing pair, the plugin and the CLI are loaded from `engine/` directly (`PATH` →
> `engine/bin`, and see §23 T1), so a step takes effect without an upgrade. §3's layout describes
> every *consuming* repo and is unaffected.

And in §24, the note under the table becomes: "From step 3 on, build the engine with pair itself:
test first, one file per step, writing `engine/**` as a normal scope (§3.2)."
