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
| 2026-09-28 | §3.2, §18 | **T1.3**: a plugin in a marketplace added from a local directory loads its components **in place from the source directory** — an edit takes effect at the next session start or `/reload-plugins`, with no reinstall and no version bump. G5's `pair upgrade --from .` at each step boundary is therefore about exercising §18, not about making an edit visible | Measured: a skill added to the source after install appears in `claude plugin details` while the cache copy stays stale |
| 2026-09-28 | §18, §11.2 | **T1.4**: a local-directory marketplace computes the version from `plugin.json.version` alone, and yields `unknown` when it is absent (the commit-SHA rule needs a *git-hosted* marketplace). `pair upgrade` must mirror `engine/VERSION` into `plugin.json.version`, and `pair doctor` compares the two | Without the mirror there is no version for `claude plugin list` or `doctor` to compare, so a stale vendored engine is undetectable |
| 2026-09-28 | §23 T1, §11.2 | **T1 is not human-only**: `claude plugin validate / marketplace add / install / list / details / uninstall` are non-interactive, so the engine can validate and inspect its own installation. §11.2 `pair doctor` should call `claude plugin details pair` (component inventory + projected token cost) instead of re-deriving it | Removes a human step from `pair doctor` and from CI, and gives the token-cost budget in §21 a real number |
| 2026-09-28 | §4, §11.4, §3.2 | **T1.8**: `pair init` writes a committed `.claude/settings.json` declaring `extraKnownMarketplaces` (a **relative** `./pair` path) and `enabledPlugins`. A clone loads the engine by accepting the workspace-trust dialog — no install command, no install record, nothing in user settings. This is a **fourth pointer file outside `pair/`**, which §4 currently forbids | Measured: `installLocation` resolved to the clone's own `pair/`, `installed_plugins.json` had no entry, user settings were untouched. Needs the same decision as G20 |
| 2026-09-28 | §11.2 | **T1.7**: a marketplace registered on the machine resolves **in preference to** the project's own declared path, with no warning, so a stale `pair-local` from another checkout silently runs that engine against this repo's data. `pair doctor` compares the resolved plugin root against `${CLAUDE_PROJECT_DIR}/pair/engine` and fails when they differ | A silent cross-repo failure mode found by measurement, not present in the docs |
| 2026-09-28 | §12.1 | **T1.6**: `${CLAUDE_PLUGIN_ROOT}` is the in-repo source directory (`…/pair/engine`), not the plugin cache, and `${CLAUDE_PROJECT_DIR}` is the repo root. Hook commands use `${CLAUDE_PLUGIN_ROOT}/bin/pair` and reach project data as `${CLAUDE_PROJECT_DIR}/pair/…` — the only legal route, since component paths may not escape the plugin directory | Confirmed in a real session; a hook edit is then live at the next session start |
| 2026-09-28 | §3, §21 | **T1.6**: skills are namespaced `<plugin>:<skill-dir>`, so §3's folders `{pair,pair-plan,pair-step,pair-close}` surface as `pair:pair-plan`, `pair:pair-step`, `pair:pair-close`. Pending the engineer's decision, rename the folders to `{pair,plan,step,close}` | Observed as `pair:pair` and `pair:second` in two sessions; §21's eval prompts name skills, so it must be settled before build step 1 |
| 2026-09-28 | §4, §11.4, §11.2 | **D12**: files outside `pair/` are allowed. `.claude/settings.json` (two keys, relative path, no install step for a clone) and `githooks/commit-msg` join the three pointer files. `pair init` merges only its own keys and never writes `settings.local.json`; `pair doctor` checks `core.hooksPath` and reports a conflict with another tool's hooks directory rather than overwriting it | The install story costs a colleague nothing, and D6 needs write-time enforcement. Verified: relative path resolves per project, no install record, user settings untouched; `core.hooksPath` is not inherited by a clone |
| 2026-09-28 | §3 (new §3.3), §9.1–§9.4, §21 | **D13**: skill folders keep their names; every place that names a skill uses the invoked form `pair:pair-plan`, `pair:pair-step`, `pair:pair-close` | Skills are namespaced `<plugin>:<folder>`; the eval prompts would otherwise miss |
| 2026-09-28 | §3 (new §3.3), §11.1 intro, §11.4 | **D14**: the CLI ships in the plugin's `bin/`, so `pair` is a bare command on the agent's PATH. Accepted cost: the plugin is terminal-only. §3.3 records that PATH resolves to the **vendored** copy, never `<root>/engine/` | Removes a setup step and a whole class of PATH bugs; pair is terminal-only regardless, since human-only commands need a TTY (T4) |
| 2026-09-28 | §1, §0, §2, §3, §23 | **D6b**: the no-vendor-reference rule reaches this spec's prose — five occurrences now read "the host CLI" or "an agent". Literal command invocations (`claude plugin eval`, `claude plugin marketplace add`) stay, since a command that must be typed is not a reference | Engineer's answer when asked whether D6 covered the spec itself |
| 2026-09-28 | §9.1, §12.3, §23 T2 | **T2**: `additionalContext` reaches the model but only the first ~2 KB; the rest is persisted to a file and costs a tool call. `session-start` now emits a **pointer under 2 KB**, ordered `pair status --line` → next action → one protocol line, and MUST NOT embed `skills/pair/SKILL.md`; the skill loads by its description instead. `pair doctor` fails above 1 800 bytes. An event `source` field exists (`startup`), so `session-start` must be idempotent | §12.3 as written could not have worked: a 15 667-byte injection delivered only filler, and the canary placed last was truncated away |
| 2026-09-28 | §12.3, §11.2 | **T2b**: the SessionStart hook fires on `--continue` with `source=resume`, and injections **accumulate** — a resumed session holds both blocks. `session-start` injects on every `source` (never skips), and each block is self-dating and self-superseding: a UTC timestamp plus a "supersedes any earlier pair: block" clause on the first line, both checked by `pair doctor` | Corrects the opposite assumption: skipping on resume would leave only a stale block, and §7.4 would then refuse the agent's commands for reasons it cannot explain |
| 2026-09-28 | §12.4, §19, §23 T3 | **T3**: `deny` is honoured in every permission mode including `--dangerously-skip-permissions`, and the hook is reached in plan mode. The §23 T3 fallback is dropped — §19 carries no bypass warning and `pair init` writes no `disableBypassPermissionsMode` key. §12.4 gains the observed event payload and a rule that every invocation logs `session_id`/`permission_mode`/decision to `pair/local/runs/hooks.jsonl` | The canary was never created in four modes. `permission_mode` and `session_id` in the payload make a denied action attributable, which §20 and §10.3 can use |
| 2026-09-28 | §12.4 | **T3b**: `permissionDecisionReason` reaches the model verbatim and the model acts on it — it quoted the reason, did not retry, and did not fall back to another tool. Every deny message in §12.4 is therefore an instruction to the agent and MUST name the correct next action, not merely state the refusal. Also confirms `Write` is denied under `bypassPermissions`, not just `Bash` | The F-row messages were written as if the agent would read them; now measured that it does. P9: the tool refuses and the refusal carries the correction |
| 2026-09-28 | §12.1, §12.4, §23 T5 | **T5**: field names confirmed for `Write`, `Edit` (plus an undocumented `replace_all`), `Read`, `Bash` and `Agent`. `MultiEdit` — named in four places — never fired and appears not to exist in the client tested; `NotebookEdit`, `Glob`, `Grep` unobserved. **The matcher becomes `*`** and the F/B rows key on payload shape (`file_path`/`notebook_path` → F-rows, `command` → B-rows, anything else write-capable → `ask`) | An enumerated matcher fails open and silently: a renamed or added tool passes unseen. Same allowlist inversion as B1 (G3) |
| 2026-09-28 | §12.1, §23 T6 | **T6**: `PreToolUse` fires for a subagent's own tool calls. The event carries `agent_id` and `agent_type`; `session_id` stays the parent's, so a delegated call is identified by `agent_id`. No rule forbidding subagents is needed. `Agent` is itself a matched call carrying the delegated `prompt`, which the hook logs (length only, never parsed for intent) | Delegation would otherwise have been a complete bypass of §12.4 |
| 2026-09-28 | §14.1, §14.2, §22 C19, §23 T7 | **T7 fallback**: `llm-wiki` folder-name detection removed. The engineer registers the source with a path, and every `llm-wiki` source carries **required** `include`/`exclude` globs; `pair init` offers defaults pre-filled and editable; `exclude` wins; a path matching nothing is reported as an empty source. C19 asserts the configured exclusion, not hard-coded names | No llm-wiki checkout was available to anyone on the project, so the layout is unverifiable. Hard-coding one tool's directory names would be wrong for every other wiki, and wrong silently in both directions |
| 2026-09-28 | §4, §11.2, §22 C37 | **D15**: everything pair installs is project-scoped. No command writes to `~/.claude/`, uses `--scope user`, or touches global git config; `core.hooksPath` is set repository-locally; the host CLI's `~/.claude/plugins/` cache is reported but never touched. New C37 enforces it by running the CLI with `$HOME` pointed at an empty directory | Engineer's decision: a tool that configures one repository must not change how every other repository behaves |
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
| 2026-09-28 | §3 (new §3.4), §3.2, §22 C38–C40, new §22.1 | Four shared build artifacts are named and enforced: `docs/MODULES.md` (layered import contract), `engine/schemas/` (shipped, read only by tests), `engine/tests/fixtures/` (built by `build.sh`, never committed), `engine/tests/golden/` | None of the four appeared anywhere in the spec, so build step 1 would have invented their location and their rules per file (D16) |
| 2026-09-28 | §3 engine tree, §3.2 | `schemas/` added to the vendored engine layout; `docs/` row names `MODULES.md`; `tests/` row names `fixtures/` and `golden/` | The folder contract has to list what is actually shipped |
| 2026-09-28 | §10.7 | The `.ts` row of `import_patterns` now uses TOML multi-line literal strings (`'''…'''`) | **The example was not valid TOML.** A literal string cannot contain `'`, and the regex character class `['"]` does; `tomllib` rejected the block with "Unclosed array". Found by C39 validating the spec's own example |
| 2026-09-28 | §22 C31 | Restated as a check on the AST rather than on imports at runtime | An import inside a `try` or behind a platform check still breaks a colleague who installed nothing |
| 2026-09-28 | §12.2 | The file rows apply to a path on a **write-capable** payload; a path on a known reader passes, and a path from an unknown tool asks | Taken literally, "a `file_path` value → F1–F15" denied every `Read` outside the current step, including the reading §9.2 requires before planning. Found by the F-row tests |

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

---

## 2026-09-28 · §10.7's example did not parse

The TypeScript row of `import_patterns` was written as:

```
".ts" = ['from\s+[''"]([^''"]+)[''"]', 'require\(\s*[''"]([^''"]+)[''"]\s*\)']
```

The intent is the character class `['"]` — a single or a double quote. But TOML's single-quoted
*literal* string cannot contain a single quote at all, and there is no escape inside one, so the
doubled `''` closed the string and reopened it. `tomllib` fails with `Unclosed array (at line 13,
column 20)`.

It is now:

```
".ts" = ['''from\s+['"]([^'"]+)['"]''', '''require\(\s*['"]([^'"]+)['"]\s*\)''']
```

A multi-line literal string may contain single quotes, so the regex reads exactly as intended and
needs no escaping. Verified: `tomllib` parses it to `from\s+['"]([^'"]+)['"]`.

This is the first thing C39 caught, before any of pair's code exists. It is the argument for the
schemas: the format most likely to be wrong is the one nobody has yet had to parse.
