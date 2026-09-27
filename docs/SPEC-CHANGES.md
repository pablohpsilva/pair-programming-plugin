# Spec changes

| Date | Section | Change | Why |
|---|---|---|---|
| 2026-09-27 | §2 D2, §19.2 | "Standard library only" now means **at runtime**; the engine's own test suite may use pytest and coverage.py as dev-only dependencies | §22 needs a test runner and dogfooding needs Cobertura output; C29 already names pytest's exit code 5 |
| 2026-09-27 | §2 D5, §11.1, §25 | v1 stays terminal-only, but §25 names in-session approval as a v2 item, and the confirmation is isolated behind one function (`tty.confirm`) | Keeps the v2 path open without widening v1 scope |
| 2026-09-27 | §2 D6, §5.1, §11.3, §13.1, §15.2 | Commits are authored by the engineer with **no `Co-Authored-By` and no vendor reference anywhere**. The `[agent]` config table is deleted. The `protected` gate no longer keys on "agent commit" | Engineer's decision: no vendor reference in generated output. The gate becomes stronger, not weaker (see details) |
| 2026-09-27 | §3 (new §3.2), §24 | In this repo the engine's **source** lives at `<root>/engine/`; `pair/engine/` is a vendored copy refreshed by `pair upgrade --from .` | Resolves a contradiction: §24 asks pair to build pair, while §19.1 protects `pair/engine/**` and §8.4 gives files under `pair/` no scope |

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
