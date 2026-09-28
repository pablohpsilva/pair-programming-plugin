# pair — Build step 0: spikes for T1–T7

SPEC §23 tags seven facts **[T]** — "test before relying on it". This document is the runbook.
Nothing here is engine code; the goal is to learn whether the spec's assumptions hold, and to
record the answers in `engine/tests/FINDINGS.md` before build step 1 starts.

**Who does what**

| Spike | Fact | Who runs it | Why |
|---|---|---|---|
| T1 | A plugin loads from a folder inside the repo as a local marketplace | **human** | `/plugin` is a slash command in the interactive client; the agent cannot type it |
| T2 | A SessionStart hook's output reaches the model's context | **human** | Needs a *fresh* session started after the hook is installed |
| T3 | Hook `deny` is honoured in every permission mode, including bypass | **human** | Needs `--dangerously-skip-permissions`, which cannot be set from inside a session |
| T4 | The Bash tool runs without a TTY | **agent** | Pure shell probing, no session restart |
| T5 | Exact `tool_input` field names for the file tools | **both** | Human installs the logging hook; the agent then triggers each tool |
| T6 | PreToolUse fires for a subagent's tool calls | **both** | Human installs the hook; the agent dispatches the subagent |
| T7 | The llm-wiki layout (`wiki/`, `raw/`, `CLAUDE.md`) | **human** | Needs a real llm-wiki, or its documentation |

**Order:** T4 first (free, no setup). Then build the fixture repo and do T5 and T6 (one hook
serves both). Then T2 and T3 (same fixture, new sessions). T1 last, because its result decides
whether the fixture layout is the one we ship. T7 is independent.

**Recording.** Each spike writes one section of `engine/tests/FINDINGS.md`, in this shape:

```markdown
## T4 — The Bash tool runs without a TTY
- **Verdict:** confirmed | false | partly (<one line>)
- **Tested on:** <date> · Claude Code <version> · <os>
- **Evidence:**
  ```
  <the command and its real output — pasted, never paraphrased>
  ```
- **Spec impact:** none | §<n>: <the change to make>
```

Where reality differs from the spec, the change goes to `docs/SPEC-CHANGES.md` and then into
`pair-SPEC.md`. `engine/tests/FINDINGS.md` is the first file created under `engine/`
(see DECISIONS.md G1 — the engine's source lives at `<root>/engine/`, not under `pair/`).

---

## The fixture repo

T2, T3, T5 and T6 need a throwaway repo with hooks installed. Do **not** install spike hooks
into this repo: they would fire on every tool call of the session building pair. Build the
fixture outside it. T1 is the exception and is described in its own section.

Run once, in a terminal (human):

```bash
export SPIKE=/tmp/pair-spike
rm -rf "$SPIKE" && mkdir -p "$SPIKE/.claude" "$SPIKE/src" && cd "$SPIKE"
git init -q && git config user.email you@example.com && git config user.name You
printf 'x = 1\n' > src/x.py
printf '# spike fixture\n' > README.md
git add -A && git commit -qm "fixture"
```

The logging hook, used by T5 and T6 — it records every PreToolUse payload and always allows:

```bash
cat > "$SPIKE/hooklog.py" <<'PY'
import json, pathlib, sys
raw = sys.stdin.read()
pathlib.Path("/tmp/pair-spike/hooklog.jsonl").open("a").write(raw.replace("\n", " ") + "\n")
PY

cat > "$SPIKE/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash",
        "hooks": [ { "type": "command",
                     "command": "python3 \"$CLAUDE_PROJECT_DIR/hooklog.py\"" } ] }
    ]
  }
}
JSON
```

Then start a session in the fixture: `cd /tmp/pair-spike && claude`.

---

## T4 — The Bash tool runs without a TTY  · agent

**Why it matters.** §11.1 layer 1 refuses human-only commands unless stdin and stdout are TTYs,
then reads the confirmation from `/dev/tty`. If the Bash tool has a TTY — or can simply *open*
`/dev/tty` even when its stdin is a pipe — then layer 1 is decoration and the spec overstates it.

**Run** (agent, in any session):

```bash
python3 -c 'import sys; print("isatty in/out/err:", sys.stdin.isatty(), sys.stdout.isatty(), sys.stderr.isatty())'
test -t 0 && echo "stdin IS a tty" || echo "stdin is NOT a tty"
python3 -c 'open("/dev/tty","w").write("WROTE TO /dev/tty\n")' 2>&1 | head -3
python3 - <<'PY' 2>&1 | head -5
import signal
def bail(*a): raise SystemExit("read from /dev/tty: BLOCKED (timed out)")
signal.signal(signal.SIGALRM, bail); signal.alarm(3)
try:
    print("read from /dev/tty:", repr(open("/dev/tty").readline()))
except Exception as e:
    print("read from /dev/tty: FAILED:", type(e).__name__, e)
PY
echo "TERM=$TERM  SHLVL=$SHLVL"
```

**Look for**
- `isatty` on stdin/stdout. Any `True` weakens layer 1.
- Whether `open("/dev/tty","w")` succeeds. If it does, the agent shares the engineer's terminal.
- Whether reading `/dev/tty` blocks, fails, or — the worst case — returns text the agent supplied.

**If it's false** (a TTY is present, or `/dev/tty` is readable): §11.1 keeps the TTY check as a
speed bump but must stop claiming it is a real control. The honest layering becomes: the hook
(layer 2) is the barrier, CI (§13) is the backstop, and §11.1's "stated limitation" paragraph is
promoted from a footnote to the opening sentence. Feeds directly into D5's v2 session-UI note.

---

## T5 — Exact `tool_input` field names  · human installs, agent triggers

**Why it matters.** §12.2 names `file_path`, `notebook_path` and `command`. Hook rules F1, F2,
F5 and F13 all resolve a path out of `tool_input`. A wrong or missing field name means the hook
silently fails open on that tool.

**Run.** With the fixture session open, ask the agent to perform each of these against
`/tmp/pair-spike`, one at a time:
1. `Write` a new file `src/new.py`.
2. `Edit` `src/x.py` (single replacement).
3. `MultiEdit` `src/x.py` — **and note whether the tool exists at all in this version**.
4. `NotebookEdit` on a notebook created first with `Write` (`nb.ipynb`, minimal valid JSON).
5. `Bash`: `echo hi`.

Then inspect the log:

```bash
python3 - <<'PY'
import json
for line in open("/tmp/pair-spike/hooklog.jsonl"):
    d = json.loads(line)
    print(d.get("tool_name"), "→", sorted((d.get("tool_input") or {}).keys()))
PY
head -1 /tmp/pair-spike/hooklog.jsonl | python3 -m json.tool | head -40
```

**Look for**
- The exact key holding the path, per tool. Absolute or relative?
- The top-level envelope: `hook_event_name`, `tool_name`, `tool_input`, `cwd`, `session_id`,
  `transcript_path`, and whether `$CLAUDE_PROJECT_DIR` was set.
- Which tools actually exist. If `MultiEdit` is gone, the hooks.json matcher and §22's hook test
  list shrink accordingly.
- For NotebookEdit: whether there are *two* path-ish fields.

**If it's false:** §12.2 gets the real field names, and F3's "every string value in `tool_input`"
already covers the forged-approval scan regardless. Update the `hooks.json` matcher in §12.1.

---

## T6 — PreToolUse fires for a subagent's tool calls  · human installs, agent triggers

**Why it matters.** §12.2 asserts "the same rules apply". If hooks do not fire for subagents,
an agent can delegate an edit and walk straight through PAIR-001/002/006.

**Run.** In the fixture session, with the logging hook installed:

```bash
: > /tmp/pair-spike/hooklog.jsonl    # clear the log first
```

Then ask the agent to dispatch a subagent whose whole job is: "write the file
`/tmp/pair-spike/src/from_subagent.py` containing `y = 2`, then stop". Afterwards:

```bash
ls -l /tmp/pair-spike/src/from_subagent.py
python3 - <<'PY'
import json
for line in open("/tmp/pair-spike/hooklog.jsonl"):
    d = json.loads(line)
    ti = d.get("tool_input") or {}
    print(d.get("tool_name"), ti.get("file_path"), "| session:", d.get("session_id"))
PY
```

Second half — does a **deny** from the hook actually stop a subagent? Swap the hook for a
denying one and repeat:

```bash
cat > /tmp/pair-spike/hookdeny.py <<'PY'
import json, sys
sys.stdin.read()
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "SPIKE-T6: denied"}}))
PY
```
(point `.claude/settings.json` at `hookdeny.py`, restart the session, repeat the subagent task)

**Look for**
- One log line per subagent tool call, with the file path present.
- Whether the same `session_id` is reused or a child id appears — the hook needs to find
  `local/active` from `cwd`/`CLAUDE_PROJECT_DIR`, so confirm those are still set for subagents.
- Whether the file was created despite the deny.

**If it's false:** the §23 T6 fallback (the bootstrap skill forbids delegating edits, CI is the
backstop) is not enough on its own to keep PAIR-006 at Tier 0. Record it as a known hole, state
it in §19, and add an eval: "delegate this edit to a subagent" must be refused.

---

## T2 — SessionStart output reaches the model's context  · human

**Why it matters.** §12.3 injects the whole bootstrap skill plus `pair status` at session start.
If that output is discarded, every session begins with the agent unaware there is a task.

**Run.** In the fixture, install a canary SessionStart hook — test **both** output shapes,
plain stdout first:

```bash
cat > /tmp/pair-spike/sshook.py <<'PY'
print("PAIR_CANARY_7Q3 the active pair task is 999-canary, phase stepping")
PY
cat > /tmp/pair-spike/.claude/settings.json <<'JSON'
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR/sshook.py\"" } ] } ] } }
JSON
```

Start a **new** session in `/tmp/pair-spike` and, as the very first message, ask:
*"Without running any tool: what is PAIR_CANARY_7Q3, and which pair task is active?"*

Then repeat with the structured form:

```bash
cat > /tmp/pair-spike/sshook.py <<'PY'
import json
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "PAIR_CANARY_7Q3 the active pair task is 999-canary, phase stepping"}}))
PY
```

**Look for**
- Whether the model can quote the canary with no tool call. That is the whole test.
- Which of the two shapes works (if both do, prefer the structured one).
- How large an injection survives — repeat with a ~150-line body, the size of a real SKILL.md,
  and check the canary is still quotable when placed at the *end* of it.
- Whether it also fires on `--continue` / `--resume`, and whether a `source` field distinguishes
  startup from resume.

**If it's false:** §12.3 loses the skill injection and falls back to the skill *description*
triggering the `pair` skill (§9.1 "Loaded"). Then `UserPromptSubmit` (which stays) carries
`pair status --line` and must also carry a one-line "read the pair skill" instruction, and §22
gains a hook test for it.

---

## T3 — `deny` is honoured in every permission mode  · human

**Why it matters.** The hook is layer 2 of PAIR-005 and the only live enforcement of
PAIR-001/002/006 during a session. If bypass mode skips hooks, an engineer who runs
`--dangerously-skip-permissions` silently turns off every Tier 0 rule.

**Run.** Install the denying hook from T6 (`hookdeny.py`, matcher `Edit|Write|MultiEdit|Bash`).
Then, in a fresh session per mode, ask the agent to write `/tmp/pair-spike/src/canary.py`:

```bash
: > /tmp/pair-spike/denied.txt
rm -f /tmp/pair-spike/src/canary.py
cd /tmp/pair-spike && claude                                  # default mode
cd /tmp/pair-spike && claude --permission-mode acceptEdits    # accept-edits
cd /tmp/pair-spike && claude --dangerously-skip-permissions   # bypass
ls -l /tmp/pair-spike/src/canary.py   # after each: absent = deny honoured
```

Also check the settings key §23 T3 names, whose exact value is unverified:

```bash
cat > /tmp/pair-spike/.claude/settings.json.probe <<'JSON'
{ "permissions": { "disableBypassPermissionsMode": "disable" } }
JSON
```
Merge that key into the fixture's settings, then launch with `--dangerously-skip-permissions`
again and see whether the client refuses to start, warns, or ignores it.

**Look for**
- Whether `canary.py` exists after each run. It must not, in all three modes.
- Whether the deny *reason* is shown to the model (it must be — F-row messages tell the agent
  what to do instead).
- The accepted value of `disableBypassPermissionsMode` (`"disable"`? a boolean? something else)
  and whether it belongs in `settings.json` or only in managed/enterprise settings.
- Plan mode: is the hook even reached, or is the tool blocked earlier?

**If it's false** (bypass skips hooks): §19 gains a hard statement — bypass mode voids pair's
in-session guarantees — `pair init` writes the `disableBypassPermissionsMode` key with whatever
value T3 proves works, `pair doctor` fails when it is missing, and §11.1's "stated limitation"
must say that CI is then the only real enforcement.

---

## T1 — A plugin loads from a folder inside the repo  · agent, then human

**Status, 2026-09-28.** Phases 1 and 2 are **done** — see `engine/tests/FINDINGS.md` T1.1–T1.5.
What follows is the original runbook; the parts already answered are marked. Only **phase 3**
below is still owed, and it needs a person. The `/plugin` slash commands are not the only route:
`claude plugin validate | marketplace add | install | list | details` all run non-interactively.

### Phase 3 — the in-session checks (human)

Two fixtures are prepared and left in place:

| Fixture | State | What it answers |
|---|---|---|
| `/tmp/pair-spike-plugin` | marketplace added and plugin installed at project scope | canary, hook firing, `${CLAUDE_PLUGIN_ROOT}`, `/reload-plugins` |
| `/tmp/pair-spike-clone` | cold clone, nothing installed, committed relative path in `.claude/settings.json` | whether the workspace-trust dialog is what a clone needs (T1.5) |

1. Open a session at `/tmp/pair-spike-plugin` and ask: *"Is the pair plugin loaded? Which skills
   do you have?"* Look for the canary `PAIR_PLUGIN_LOADED_4K2` and for a second skill named
   `second`.
2. In the same session, look for the hook line `PAIR_PLUGIN_HOOK_RAN root=<…> project=<…>` and
   **paste both paths back**. Whether `root` is the source directory or
   `~/.claude/plugins/cache/…` decides how §12.1 writes every hook command.
3. Edit `pair/engine/hooks/hooks.json` there (change the echoed string), run `/reload-plugins`,
   and see whether the new string appears without a reinstall. T1.3 proved this for a *skill*;
   hooks are the case §12 depends on.
4. Open a session at `/tmp/pair-spike-clone`, accept the workspace-trust dialog, and ask the same
   question. If the plugin loads, a committed `.claude/settings.json` is the whole install story
   and §4 gains a fourth pointer file; if it does not, §11.4 step 6 must spell out the two
   commands each engineer runs after cloning.

---

**Why it matters.** D4 vendors the engine at `pair/engine/` and expects Claude Code to load it
from there as a local marketplace. If it cannot, the plugin ships from a git marketplace while
the CLI stays vendored (§23 T1 fallback) — which changes §3, §11.4 step 6 and `pair upgrade`.

**Note.** The exact `marketplace.json` schema is *part of what this spike verifies* — the
skeleton below is a starting point, not a fact. Read the current plugin documentation first;
`/plugin` and the `claude-code-guide` agent are both good sources. Record the real schema in
FINDINGS.md, because §3 and §11.4 will quote it.

**Run.** In a fresh throwaway repo (so a broken marketplace cannot affect this one):

```bash
export P=/tmp/pair-spike-plugin
rm -rf "$P" && mkdir -p "$P/engine/.claude-plugin" "$P/engine/skills/pair" "$P/engine/hooks"
cd "$P" && git init -q

cat > engine/.claude-plugin/plugin.json <<'JSON'
{ "name": "pair", "description": "Spike: does a local folder load as a plugin?", "version": "0.0.1" }
JSON

cat > engine/.claude-plugin/marketplace.json <<'JSON'
{ "name": "pair-local", "owner": { "name": "spike" },
  "plugins": [ { "name": "pair", "source": "./", "description": "spike" } ] }
JSON

cat > engine/skills/pair/SKILL.md <<'MD'
---
name: pair
description: Spike skill. If you can read this, say PAIR_PLUGIN_LOADED_4K2.
---
Say PAIR_PLUGIN_LOADED_4K2 when asked whether the pair plugin is loaded.
MD

cat > engine/hooks/hooks.json <<'JSON'
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
    "command": "echo PAIR_PLUGIN_HOOK_RAN ${CLAUDE_PLUGIN_ROOT}" } ] } ] } }
JSON

git add -A && git commit -qm "spike plugin"
```

Then, in a session opened at `/tmp/pair-spike-plugin`:

```
/plugin marketplace add ./engine
/plugin install pair@pair-local
```
Restart the session, then ask: *"Is the pair plugin loaded? Which skills do you have?"*

Finally, repeat the whole thing with the folder at the **vendored** location the spec actually
uses — `mkdir -p pair && git mv engine pair/engine`, then `/plugin marketplace add ./pair/engine` —
since that, not `./engine`, is the path §3 ships.

**Look for**
- Whether `marketplace add` accepts a **relative in-repo path** at all, and whether it wants the
  folder containing `.claude-plugin/` or the `.claude-plugin/` folder itself.
- Whether the skill appears in the session's skill list and the canary can be quoted.
- Whether the plugin's own `hooks/hooks.json` fires, and what `${CLAUDE_PLUGIN_ROOT}` expands to
  — §12.1 depends on it resolving to the plugin folder, and this also re-checks V2.
- Whether installation state lives in the repo or in the user's home. If it is per-user, every
  engineer must run `/plugin install` after clone, and §11.4 step 6 must say so.
- Whether editing a skill or hook on disk takes effect after a restart, without reinstalling —
  this decides how painful G5 (source vs vendored copy) really is.

**If it's false:** take the §23 T1 fallback. The engine's *plugin* half (skills + hooks) is
published as a git marketplace and installed by URL; `pair/engine/` keeps the CLI, defaults,
templates and migrations. §3, §4, §11.4 and §18 all need the split written in, and `pair doctor`
gains a check that the installed plugin version matches `engine/VERSION`.

---

## T7 — The llm-wiki layout  · human

**Why it matters.** §14.2 detects an llm-wiki by "a folder containing `wiki/`, `raw/` and
`CLAUDE.md`", and §14.1 indexes only `wiki/**/*.md`, never `raw/`, `log/` or `audit/`. C19
asserts that exclusion. If the real layout differs, detection silently finds nothing — or worse,
indexes raw source material.

**Run.** Against a real llm-wiki checkout, if one is available:

```bash
W=~/wikis/<a-real-llm-wiki>
ls -a "$W"
find "$W" -maxdepth 2 -type d | sort
ls "$W"/wiki | head
find "$W"/wiki -name '*.md' | wc -l
head -30 "$W"/CLAUDE.md
```

**Look for**
- The real top-level folder names, and whether `wiki/`, `raw/` and `CLAUDE.md` are all present.
- Whether compiled pages are Markdown under `wiki/`, and how deep.
- Any other folder that must never be indexed (`log/`, `audit/`, `.cache/`, embeddings).
- Whether a machine-readable marker exists (a manifest, a config file) that beats
  folder-name sniffing.

**If it's false, or no llm-wiki is at hand:** keep detection **configurable** rather than
hard-coded — §14.2 gains a `[[sources]]` entry with an explicit `include`/`exclude` glob pair and
defaults matching whatever T7 found — and a manual path always remains allowed. C19's fixture
then asserts the configured exclusion, not the hard-coded folder names.

---

## Definition of done for build step 0

- `engine/tests/FINDINGS.md` has a section per T1–T7, each with a verdict and pasted evidence.
- Every "If it's false" branch that fired has a row in `docs/SPEC-CHANGES.md`.
- `pair-SPEC.md` is updated so no [T] tag remains untested; confirmed facts become [V] with the
  date, disproved ones are rewritten.
- Nothing in `/tmp/pair-spike*` is needed any more, and no spike hook is left installed in this
  repo or in `~/.claude/settings.json`.
