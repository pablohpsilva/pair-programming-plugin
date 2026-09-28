# Spike findings (SPEC §23)

One section per [T] fact. Verdicts come from real runs; evidence is pasted, never paraphrased.
Runbook: `docs/SPIKES.md`. Spec changes caused by a finding go to `docs/SPEC-CHANGES.md`.

| # | Fact | Verdict | Spec impact |
|---|---|---|---|
| T1 | A plugin loads from an in-repo folder as a local marketplace | **confirmed** | §3, §3.2, §4, §11.2, §11.4, §18 — see below |
| T2 | A SessionStart hook's output reaches the model's context | **confirmed, with a ~2 KB ceiling** | §9.1, §12.3 — see below |
| T3 | Hook `deny` is honoured in every permission mode | **confirmed** (one gap: `Write` under bypass) | §11.1, §12.4, §19 — see below |
| T4 | The Bash tool runs without a TTY | **confirmed (stronger than assumed)** | §11.1 — see below |
| T5 | Exact `tool_input` field names for the file tools | **partly confirmed** (`Write`, `Bash`) | §12.4 — see T3 below |
| T6 | PreToolUse fires for a subagent's tool calls | not run | — |
| T7 | The llm-wiki layout (`wiki/`, `raw/`, `CLAUDE.md`) | not run | — |

---

## T4 — The Bash tool runs without a TTY

- **Verdict: confirmed, and more strongly than §11.1 assumed.** The Bash tool has no TTY on any
  of the three standard streams, and `/dev/tty` cannot even be *opened* — the controlling
  terminal is not merely redirected, it is absent from the process.
- **Tested on:** 2026-09-27 · Claude Code 2.1.267 · macOS 26.3.1 · Python 3.14.6 · darwin,
  from an interactive session running in a real terminal (`TERM=xterm-256color`, `CLAUDECODE=1`).
- **Evidence:**

```
$ python3 -c 'import sys; print("stdin",sys.stdin.isatty(),"| stdout",sys.stdout.isatty(),"| stderr",sys.stderr.isatty())'
stdin False | stdout False | stderr False

$ test -t 0 && echo "stdin IS a tty" || echo "stdin is NOT a tty"
stdin is NOT a tty

$ python3 -c 'open("/dev/tty","w")'
OSError: [Errno 6] Device not configured: '/dev/tty'

$ python3 -c 'print(open("/dev/tty").readline())'
read from /dev/tty: FAILED: OSError [Errno 6] Device not configured: '/dev/tty'
```

- **Why the second half matters more than the first.** §11.1's TTY check would be weak if the
  agent could open the engineer's terminal directly — `os.isatty` says nothing about that, since
  a process with piped stdio can still open `/dev/tty` and reach the controlling terminal. Here
  it cannot: `ENXIO`/"Device not configured" means the Bash tool's process has **no controlling
  terminal at all**. So layer 1 of §11.1 is genuine enforcement in this environment, not a speed
  bump: an agent cannot satisfy the confirmation prompt, and cannot fake one by writing to the
  engineer's screen either.
- **Spec impact:** none required. §11.1 stands as written. Two additions worth making:
  - §11.1 mechanism 1 should say *why* it works — the check is `os.isatty` **and** a successful
    `open("/dev/tty")`; the second is the one that cannot be spoofed by a wrapper that fakes a
    pty on stdio. Recommend requiring both.
  - §11.1's "stated limitation" paragraph stays accurate and unchanged: an agent running as the
    same OS user can still start its own pty (`script`, `expect`, `pty.spawn`) and drive the CLI
    through it. That is the bypass the paragraph already describes, and CI (§13) remains the
    backstop. **Not yet tested** — a follow-up probe (T4b) should try
    `python3 -c 'import pty,os; pty.spawn(["pair","ok"])'` once the CLI exists, and §22 should
    carry a test that the confirmation still refuses when it cannot read the expected token.
- **Caveat on generality:** one environment (macOS, this client version). Re-check on Linux and
  under `ssh`/`tmux` before treating it as a portable guarantee; D8 limits us to Linux and macOS,
  so a Linux run is the only other case that matters.

---

## T1 — A plugin loads from a folder inside the repo

- **Verdict: partly confirmed.** A folder inside the repo does register as a marketplace and
  install as a plugin, non-interactively, and its components load **in place from the source
  directory**. Two sub-questions remain open and need an interactive session: whether the skill
  reaches the model's context, and whether a *clone* can load the plugin from committed project
  settings alone.
- **Tested on:** 2026-09-28 · Claude Code 2.1.267 · macOS 26.3.1 · darwin. Fixtures:
  `/tmp/pair-spike-plugin` (installed) and `/tmp/pair-spike-clone` (cold clone, never installed).
- **T1 is not human-only.** `docs/SPIKES.md` marked it human because `/plugin` is interactive.
  There is a full non-interactive CLI — `claude plugin validate | marketplace add | install |
  list | details | uninstall | marketplace remove` — so phases 1 and 2 ran from the Bash tool.
  Only the in-session checks need a person.

### T1.1 — The §3 layout validates, including a self-rooted marketplace

`marketplace.json` and `plugin.json` side by side in `pair/engine/.claude-plugin/`, with the
plugin entry's `source` being `"./"` (the marketplace root *is* the plugin), is legal:

```
$ claude plugin validate ./pair/engine
Validating marketplace manifest: /private/tmp/pair-spike-plugin/pair/engine/.claude-plugin/marketplace.json
✔ Validation passed
```

`validate` auto-detects a marketplace manifest and validates each entry's `plugin.json` through
it, so one command checks both files. A missing `author` is a warning, not an error; so is a
missing `version`.

### T1.2 — Install works at **project** scope and writes a committable file

```
$ claude plugin marketplace add ./pair --scope project
✔ Successfully added marketplace: pair-local (declared in project settings)

$ claude plugin install pair@pair-local --scope project --json
{"command":"install","outcome":"ok","plugin":"pair@pair-local","pluginId":"pair@pair-local",
 "scope":"project","message":"Successfully installed plugin: pair@pair-local (scope: project)"}
```

It wrote `.claude/settings.json` **in the repo**, and left `~/.claude/settings.json` untouched
(verified: `pair-local` absent from user `extraKnownMarketplaces`, no `pair` key in user
`enabledPlugins`):

```json
{
  "extraKnownMarketplaces": {
    "pair-local": { "source": { "source": "directory", "path": "/private/tmp/pair-spike-plugin/pair" } }
  },
  "enabledPlugins": { "pair@pair-local": true }
}
```

**The path it writes is absolute**, so the file as generated is machine-specific and cannot be
committed as-is. Hand-writing `"path": "./pair"` is accepted by the file format — see T1.5 for
whether a clone honours it.

### T1.3 — Components load **in place** from the source directory

The install does create a copy under `~/.claude/plugins/cache/pair-local/pair/<version>/`, which
looks like a copied plugin. It is not what gets loaded. A skill added to the **source** after
install, with no reinstall and no version change, appears in the inventory while the cache copy
stays stale:

```
$ claude plugin details pair          # before
  Skills (1)  pair

# added pair/engine/skills/second/SKILL.md in the source, changed plugin.json description

$ claude plugin details pair          # after, no reinstall
  Skills (2)  pair, second

$ grep description ~/.claude/plugins/cache/pair-local/pair/unknown/.claude-plugin/plugin.json
  "description": "Spike variant B: no pinned version"     # stale
$ ls ~/.claude/plugins/cache/pair-local/pair/unknown/skills/
  pair                                                    # stale: no `second`
```

**This resolves G5.** Editing `engine/` in this repo takes effect at the next session start or
`/reload-plugins` — no `pair upgrade`, no version bump, no reinstall. The source-vs-vendored-copy
split costs a session restart, not a release cycle.

### T1.4 — The computed version is `unknown` for a local-directory marketplace

| `plugin.json` | Recorded version | Cache dir |
|---|---|---|
| `"version": "0.0.1"` | `0.0.1` | `…/pair/0.0.1` |
| no `version` field | `unknown` | `…/pair/unknown` |

The documented "commit SHA" rule applies to a relative path inside a **git-hosted** marketplace.
A marketplace added from a local directory is not git-hosted even when the directory sits in a git
repository, so an unpinned manifest yields `unknown`.

**Spec impact (§18):** `engine/VERSION` must be mirrored into `plugin.json.version` by
`pair upgrade`, or `claude plugin list` and `pair doctor` have no version to compare. Since
loading is in place (T1.3), pinning the version costs nothing in development.

### T1.5 — A clone does **not** pick the plugin up from committed project settings (open)

With every trace of the marketplace and install removed from this machine
(`known_marketplaces.json` and `installed_plugins.json` both verified clean), a cold clone whose
committed `.claude/settings.json` declares both `extraKnownMarketplaces` and `enabledPlugins`
does not resolve the plugin:

```
$ cd /tmp/pair-spike-clone && claude plugin list | grep pair-local
(nothing)
$ claude plugin marketplace list | grep pair-local
(nothing)
```

Isolated the cause: rewriting the declared path from `"./pair"` to an absolute
`/private/tmp/pair-spike-clone/pair` changes nothing, so **the path form is not the problem.**
This matches the documented requirement that a repository-declared marketplace loads only after
the workspace-trust dialog, which no shell command shows.

**Still open — phase 3, needs an interactive session:** whether accepting the trust dialog in the
clone makes the plugin load. The answer decides §11.4 step 6:

- **If yes:** a committed `.claude/settings.json` with a relative path is the install story, and
  no engineer ever runs `/plugin install`. §4 then has a **fourth pointer file outside `pair/`**,
  which contradicts it as written — see the note on G20 below.
- **If no:** every engineer runs `claude plugin marketplace add ./pair --scope local` plus an
  install after cloning, and `pair doctor` must detect the missing install and print that command.

Either way, a **cloud session never shows the trust dialog**, so the committed route cannot be
the only route.

### T1.6 — The skill reaches context, the hook fires, and `CLAUDE_PLUGIN_ROOT` is the source

Interactive session at `/tmp/pair-spike-plugin`, 2026-09-28, reported verbatim by the engineer:

```
PAIR_PLUGIN_HOOK_RAN root=/private/tmp/pair-spike-plugin/pair/engine project=/private/tmp/pair-spike-plugin

- pair:pair — "Spike skill. If you can read this, say PAIR_PLUGIN_LOADED_4K2."
  (invoked; it resolved to /private/tmp/pair-spike-plugin/pair/engine/skills/pair and returned
  its body, so it's genuinely loading from disk, not just listed)
- pair:second — "A second skill added to the source after install."
```

Four things are now settled:

1. **The plugin's own `hooks/hooks.json` fires at SessionStart.** §12 can ship its hooks inside
   the plugin; no `.claude/settings.json` hook entry is needed for them.
2. **`${CLAUDE_PLUGIN_ROOT}` is the in-repo source directory** — `…/pair/engine`, not
   `~/.claude/plugins/cache/…`. §12.1's hook commands may reference
   `${CLAUDE_PLUGIN_ROOT}/bin/pair` and reach the vendored engine directly. Combined with T1.3,
   a hook edit is live at the next session start.
3. **`${CLAUDE_PROJECT_DIR}` is the repo root**, so a hook reaches project data as
   `${CLAUDE_PROJECT_DIR}/pair/…`. This is the only legal route: component paths may not escape
   the plugin directory (T1 docs), so the hook cannot climb out of `pair/engine/` by relative path.
4. **T1.3 holds in a real session**, not just in `claude plugin details`: `pair:second`, added to
   the source after install, loaded and was invocable.

**New finding — skills are namespaced `<plugin>:<skill-dir>`.** §3 names the skill folders
`{pair,pair-plan,pair-step,pair-close}`, which would surface as `pair:pair`, `pair:pair-plan`,
`pair:pair-step`, `pair:pair-close`. Renaming the folders to `{pair,plan,step,close}` gives
`pair:pair`, `pair:plan`, `pair:step`, `pair:close`. §3 and §21's eval prompts both name skills,
so this has to be decided before build step 1 writes them.

### T1.7 — A machine-level registration serves every project, and wins over a project path

First clone run, 2026-09-28: the session at `/tmp/pair-spike-clone` **did** load the plugin and
quote the canary — but it resolved the marketplace to the **original** repository:

```
pair@pair-local is active, resolved through the pair-local marketplace
  (./pair → /private/tmp/pair-spike-plugin/pair/engine)
PAIR_PLUGIN_HOOK_RAN root=/private/tmp/pair-spike-plugin/pair/engine
```

The clone's own `pair/engine/` was never read, even though its committed `.claude/settings.json`
declares `"path": "./pair"` and the clone contains that directory. `pair-local` was registered on
the machine at the time (`known_marketplaces.json` → `installLocation:
/private/tmp/pair-spike-plugin/pair`), and that registration answered.

**So this run does not test the clone story.** What it does establish:

1. **A marketplace registered once on a machine serves every project that enables the plugin.**
   The project only has to say `"pair@pair-local": true` under `enabledPlugins`; it does not need
   its own `extraKnownMarketplaces` entry, and any entry it has can be ignored.
2. **A project-declared relative path did not override the machine registration**, and no warning
   or error said so. An engineer whose machine has a stale `pair-local` pointing at another
   checkout would silently run that checkout's engine against this repo's `pair/` data. §11.2
   `pair doctor` must compare the resolved plugin root against `${CLAUDE_PROJECT_DIR}/pair/engine`
   and fail when they differ — this is a real, silent, cross-repo failure mode, not a nicety.

### T1.8 — A committed `.claude/settings.json` is the whole install story

Cold re-run, 2026-09-28. Preconditions verified before the session: `pair-local` absent from
`known_marketplaces.json`, `installed_plugins.json` and the user's `enabledPlugins`; the original
source moved to `/tmp/pair-spike-plugin-MOVED` so no stale absolute path could answer; the clone
holding its own `pair/engine/` and the committed relative `"path": "./pair"`.

The session loaded the plugin, quoted the canary, and listed both skills. Machine state written
by that session:

```
known_marketplaces.json pair-local:
  { "source": { "source": "directory", "path": "/private/tmp/pair-spike-clone/pair" },
    "installLocation": "/private/tmp/pair-spike-clone/pair" }

installed_plugins.json pair@pair-local:  null
~/.claude/settings.json:                 no pair keys
```

**Verdict: confirmed.** Three facts, each with a consequence:

1. **A relative `path` in a project's `extraKnownMarketplaces` resolves against the project
   directory.** `./pair` became `/private/tmp/pair-spike-clone/pair`, the clone's own copy.
2. **No install record is created, and none is needed.** `installed_plugins.json` has no entry;
   the plugin loads from the marketplace directory itself. There is nothing to go stale, and
   nothing per-machine to keep in sync.
3. **Nothing was written to the user's settings.** The whole declaration lives in the repository.

So `pair init` writes a committed `.claude/settings.json` with those two keys and a **relative**
path, and a colleague who clones the repo gets the engine by accepting the workspace-trust dialog.
No `/plugin install`, no `claude plugin` command, no per-engineer setup step.

**The cost, and it is a real one:** this is a **fourth pointer file outside `pair/`**, which §4
forbids as written. It is the same collision as the open G20 (the `commit-msg` hook), and the two
should be decided together. Two further limits belong in §11.4:

- **A cloud session never shows the workspace-trust dialog**, so the committed route cannot be the
  only documented route; the `claude plugin marketplace add ./pair --scope local` + `install` pair
  of commands stays as the fallback, and `pair doctor` should print them when the plugin is absent.
- **A machine-level registration wins silently over the project's own path** (T1.7), so
  `pair doctor` must compare the resolved plugin root against `${CLAUDE_PROJECT_DIR}/pair/engine`.

### T1.9 — One residual, low priority

Does `/reload-plugins` pick up an edit to `hooks.json`, not just to a skill? T1.3 and T1.6 proved
it for skills, and `${CLAUDE_PLUGIN_ROOT}` is the live source directory, so the mechanism is the
same — but §12's development loop depends on it, and it has not been run. Fixtures are still in
place at `/tmp/pair-spike-clone` if it is worth two minutes.

### Two findings that reach beyond T1

- **`claude plugin details <name>` is a ready-made `doctor` check.** It prints the component
  inventory and a projected token cost (`Always-on: ~45 tok`), and marks a hooks-only component
  `harness-only — no model context cost`. §11.2 should have `pair doctor` shell out to it, or at
  least assert the skill count, rather than re-deriving the inventory.
- **A plugin's `bin/` is on the Bash tool's `PATH` while the plugin is enabled.** That is a real
  option for shipping the `pair` CLI (§3 puts it at `engine/bin/pair`) — but a plugin with a
  top-level `bin/` is not installable on claude.ai or Cowork. This is a §2-level decision and is
  not recorded in DECISIONS.md yet.

---

## T2 — SessionStart output reaches the model's context

- **Verdict: confirmed, with a limit that changes the design.** A `SessionStart` hook's
  `additionalContext` does reach the model. But only the **first ~2 KB** does: a larger payload is
  written to a file and the model receives a 2 KB preview plus that file's path. §12.3 as written —
  "outputs the text of `skills/pair/SKILL.md` plus `pair status`" — could not have worked.
- **Tested on:** 2026-09-28 · fixture `/tmp/pair-spike-t2`, a project-declared
  `.claude/settings.json` hook emitting structured `hookSpecificOutput.additionalContext`:
  149 lines / 15 667 bytes, `PAIR_SOURCE_FIELD` on line 2, the canary `PAIR_CANARY_7Q3` deliberately
  placed on the **last but one** line.
- **Evidence** — the session's own account, first message, no tool calls:

```
1. PAIR_CANARY_7Q3 — I don't have it. The SessionStart hook's additionalContext was too large
   (15.3KB) and got persisted to a file; only the first 2KB preview reached me, which is all
   "line NNN: pair bootstrap filler …" repeats. … i.e. exactly the part that was truncated away.
2. Active pair task / phase / mode — also not available to me. Same reason.
3. PAIR_SOURCE_FIELD = startup — this one I do have; it's on the second line of the preview.
```

  The model offered to read the persisted file at
  `~/.claude/projects/-private-tmp-pair-spike-t2/<session>/tool-results/hook-<id>-2-additionalContext.txt`.
  That it *can* is not a rescue: reaching it costs a tool call, so anything past 2 KB is not
  "context the session starts with".

### What this settles

1. **Structured output works.** `hookSpecificOutput.additionalContext` is delivered; the earlier
   plugin-hook runs (T1.6) already showed plain stdout is delivered too. Both shapes work.
2. **There is a `source` field on the event's stdin**, value `startup` on a fresh session. §12.3's
   `session-start` can distinguish a start from a resume, and MUST be idempotent regardless.
3. **Order matters more than size.** The first 2 KB survives and everything after it does not, so
   the injection must be **most-important-first**. The fixture put the canary last precisely to
   catch this, and it did.

### Spec impact

- **§12.3 rewritten.** `session-start` emits under 2 KB, ordered `pair status --line` → next action
  naming the phase's skill → one line of protocol. It MUST NOT embed `skills/pair/SKILL.md`.
  Truncation at any point may cost detail but never the phase or the next action. `pair doctor`
  fails above 1 800 bytes, leaving headroom.
- **§9.1 changed.** The bootstrap skill is **loaded by its description**, not injected. The
  documented fallback has become the primary mechanism; the injection's job is narrower — make the
  first action unambiguous.
- **§23 T2** → `[V 2026-09-28]`, partly: arrives, but truncated.

### T2b — The hook fires on resume, and injections accumulate

`claude --continue` in the same fixture, 2026-09-28. The session's own account:

```
resume.

A second SessionStart hook block just arrived (a resume injection) and its preview shows
PAIR_SOURCE_FIELD=resume. That supersedes the earlier one I quoted, which read startup — so if
you want the current value, it's resume; the startup value came from the first injection in
this session.
```

Two facts, and the second is the dangerous one:

1. **The hook fires on `--continue`, with `source=resume`.** A resumed session is not blind.
2. **Injections accumulate rather than replace.** Both blocks were in context, and the model had to
   *reason* about which one superseded the other. After two resumes a session holds three `pair:`
   blocks, and nothing in the text itself says which is current — the model inferred it from
   arrival order, which is not something to depend on.

**Spec impact (§12.3), correcting an earlier assumption.** Before this run the plan was that
`session-start` could skip re-injecting on resume. That is exactly wrong: skipping leaves the
session holding only the *stale* block. The rule is the opposite — inject on every `source`, and
make each block self-dating and self-superseding, with a UTC timestamp and an explicit
"supersedes any earlier pair: block" clause on the first line. `pair doctor` checks for both.

The cost of getting this wrong is not cosmetic: §7.4 refuses wrong-phase commands, so an agent
acting on a stale phase would be blocked by a message it has no way to explain.

### Not measured

The exact threshold. The evidence says "2KB preview" for a 15 667-byte payload; whether the limit is
2 000, 2 048 or 2 KiB of UTF-8 after JSON decoding is unknown, and whether it counts bytes or
characters is unknown. §12.3's 1 800-byte `doctor` limit is chosen to sit clear of all of them.
A payload just under the line was not tested.

---

## T3 — `deny` is honoured in every permission mode

- **Verdict: confirmed.** A `PreToolUse` hook returning `permissionDecision: "deny"` was reached and
  honoured in all four modes tested, **including `--dangerously-skip-permissions`**. The canary file
  was never created in any run. §11.1's layer 2 and all of §12.4 are genuine enforcement, not
  advisory.
- **Tested on:** 2026-09-28 · fixture `/tmp/pair-spike-t3`, a project-declared `.claude/settings.json`
  `PreToolUse` hook matching `Edit|Write|MultiEdit|Bash|NotebookEdit`, four fresh sessions, same
  first message in each: *"Create the file src/canary.py containing exactly: print(\"T3\")"*.

| Launch | `permission_mode` seen | Tool the session tried | `canary.py` |
|---|---|---|---|
| `claude` | `auto` | `Bash` | absent |
| `claude --permission-mode acceptEdits` | `acceptEdits` | `Write` | absent |
| `claude --permission-mode plan` | `plan` | `Bash`, then `Write` | absent |
| `claude --dangerously-skip-permissions` | `bypassPermissions` | `Bash` | absent |

Evidence, the decisive row:

```
{"at": "2026-09-28T07:43:26+00:00", "tool": "Bash",
 "permission_mode": "bypassPermissions", "tool_input_keys": ["command", "description"]}
canary.py exists : no — deny honoured
```

### What this settles

1. **Bypass mode does not skip hooks.** The `[T]` fallback in §23 — "bypass voids pair's in-session
   guarantees" — is **not** needed. §19 keeps no such warning, and `pair init` does **not** need to
   write a `disableBypassPermissionsMode` key. That probe is now optional curiosity, not a blocker.
2. **The hook is reached in plan mode**, for both `Bash` and `Write`. §12.4 applies there too; the
   tool is not blocked earlier by the client.
3. **The event payload carries `permission_mode`.** §12.4 gains a cheap defensive check: the hook can
   see it is running under `bypassPermissions` and log it, rather than trusting the mode is benign.
   It does not *need* to refuse — deny is honoured — but recording the mode in
   `pair/local/runs/` makes an audit answerable.
4. **The event payload is richer than §12.4 assumed.** Every event carried:
   `cwd`, `effort`, `hook_event_name`, `permission_mode`, `prompt_id`, `scratchpad_dir`,
   `session_id`, `tool_input`, `tool_name`, `tool_use_id`, `transcript_path`.
   `session_id` and `transcript_path` are directly useful — §20's metrics and §10.3's log can tie a
   denied action to the session that attempted it.

### T5, partly answered as a side effect

The `tool_input` keys observed, which is exactly what T5 asks for:

| Tool | `tool_input` keys |
|---|---|
| `Write` | `content`, `file_path` |
| `Bash` | `command`, `description` |

Still unobserved: `Edit`, `MultiEdit`, `NotebookEdit`, `Read`, `Glob`, `Grep`. §12.4's F-rows key on
`file_path` for the write tools, which holds for `Write`; `Edit` and `MultiEdit` remain assumed.

### Two things still open

1. **`Write` under `bypassPermissions` was not exercised.** In mode 4 the session reached for `Bash`
   first, was denied, and stopped — so the confirmation under bypass covers `Bash` only. The file
   tools are what §12.4's F-rows mostly govern. A targeted re-run that forbids `Bash` in the prompt
   would close it.
2. **Whether the deny *reason* reaches the model** was not reported. §12.4's F-row messages exist to
   tell the agent what to do instead (F3's "write it as prose, without a checkbox", F4's "no active
   task"). If `permissionDecisionReason` is swallowed, every one of those strings is decoration and
   §12.4 needs another channel. The fixture's reason string is `PAIR_DENY_5M8`.
