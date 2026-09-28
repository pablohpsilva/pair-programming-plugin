"""The three hooks (SPEC 12).

Three properties matter more than brevity here:

- **It fails closed.** Any exception, or an invalid config, exits 2 with the reason on stderr, which
  blocks the call [V: exit 2 blocks].
- **It decides by payload shape, not tool name.** The matcher is `*` because an enumerated one fails
  open: `MultiEdit` was named four times in the SPEC and never fired, while `Agent` — which
  delegates work — was not named at all [V T5/T6]. A payload it cannot classify gets `ask`.
- **Every deny message is an instruction.** The reason reaches the model verbatim and the model acts
  on it [V T3b], so each one names the next action rather than only what was refused.
"""

import json
import os
import pathlib
import re
import shlex
import sys

# hooks.json runs this file as a script (`python3 .../lib/pair/hook.py pre`), so `lib/` is not on
# the path yet. Put it there before importing the package.
if __package__ in (None, ""):                                       # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.version_info < (3, 11):                                      # pragma: no cover
    # Exit 2 blocks the tool call, which is the right outcome: pair cannot judge it.
    sys.stderr.write(
        f"pair hook: needs Python 3.11 or newer (this is {sys.version.split()[0]}) — it reads TOML "
        f"with the standard library's tomllib (D2). Point the hook at a newer python3.\n")
    raise SystemExit(2)

from pair import clock, config as config_mod, files, flow, globs, paths, state as state_mod

# The payload itself is built in `flow`, which owns every phrase that names a phase (SPEC 12.3).
MAX_CONTEXT = flow.MAX_CONTEXT
DOCTOR_LIMIT = flow.DOCTOR_LIMIT

FORGED_APPROVAL = re.compile(r"(?im)^\s*[-*]?\s*\[[xX]\].*\b(approved|granted)\b")

PATH_KEYS = ("file_path", "notebook_path", "path", "filePath")
WRITE_HINTS = ("content", "contents", "new_string", "old_string", "text", "patch", "edits",
               "replace_all", "data", "body")
DELEGATION_KEYS = ("prompt", "subagent_type")

# A path alone does not mean a write: `Read` carries `file_path` too, and the agent is *told* to
# read the likely files before planning (SPEC 9.2). So the file rows apply to a **write-capable**
# payload — the qualifier SPEC 12.2 already uses for the unclassifiable case. A path-carrying
# payload from a tool on neither list is unclassifiable, so it asks rather than passing.
WRITER_TOOLS = frozenset(("Write", "Edit", "MultiEdit", "NotebookEdit", "Create", "Patch",
                          "ApplyPatch", "StrReplace", "str_replace_editor"))
READER_TOOLS = frozenset(("Read", "NotebookRead", "View", "Glob", "Grep", "LS", "List",
                          "WebFetch", "WebSearch"))

# SPEC 12.4 B1: the only pair invocations an agent may run.
AGENT_SAFE = {
    "status": (), "find": (), "diff": (), "plan-check": (), "done": (), "rework": (),
    "reopen": (), "pause": (), "index": (), "doctor": (), "export": (),
}
AGENT_SAFE_SUB = {"lesson": ("propose",)}
REPORT_FORBIDDEN = ("--write",)

GIT_WRITE = frozenset("""
add commit push merge rebase reset checkout switch restore stash apply am cherry-pick revert tag
update-ref update-index config rm mv clean worktree filter-branch notes
""".split())
GIT_BRANCH_WRITE = ("-d", "-D", "-m", "-M")

WRITE_COMMANDS = frozenset("""
tee sed perl mv cp rm touch truncate dd ln chmod chown install rsync unzip tar
""".split())
INTERPRETERS = frozenset(("python", "python3", "node", "ruby", "perl"))
CODE_FLAGS = ("-c", "-e")
CODE_WRITE_HINTS = ("open(", "write", "fs.", "File.")
PREFIX_WORDS = frozenset(("env", "sudo", "nohup", "time", "command"))
SEGMENT_SPLIT = re.compile(r"(?:\|\||&&|;|\||\n)")
REDIRECT = re.compile(r"^(?:\d*>>?|&>)$")
SAFE_REDIRECTS = ("/dev/null", "/dev/stderr", "/dev/stdout")

DENY = "deny"
ASK = "ask"
PASS = "pass"
STRICTNESS = {PASS: 0, ASK: 1, DENY: 2}


class Decision:
    def __init__(self, verdict, reason=None, row=None):
        self.verdict = verdict
        self.reason = reason
        self.row = row

    @property
    def blocking(self):
        return self.verdict in (DENY, ASK)

    def __repr__(self):
        return f"Decision({self.verdict}, {self.row})"


def passed(row=None):
    return Decision(PASS, row=row)


def deny(row, reason):
    return Decision(DENY, reason, row)


def ask(row, reason):
    return Decision(ASK, reason, row)


def strictest(decisions):
    found = passed()
    for decision in decisions:
        if STRICTNESS[decision.verdict] > STRICTNESS[found.verdict]:
            found = decision
    return found


# -- the file rows -------------------------------------------------------------------------------

def decide_file(context, target, payload):
    layout, config = context.layout, context.config
    rel = layout.rel(target)
    if rel is None:
        return deny("F1", f"PAIR-006: `{target}` is outside this repository. Work inside "
                          f"{layout.root}.")
    protected = config.protected(rel)
    if protected:
        return deny("F2", f"PAIR-006: `{rel}` is a protected path ({protected}) — agents never "
                          f"edit it. If it must change, ask the engineer.")
    forged = forged_approval(payload)
    if forged:
        return deny("F3", "PAIR-005: that looks like a forged approval. Write it as prose, "
                          "without a checkbox.")

    state = context.state
    if state is None or not state.is_open:
        return deny("F4", context.no_task_reason())
    task_dir = f"pair/tasks/{state.task}/"
    if rel.startswith("pair/tasks/") and not rel.startswith(task_dir):
        return deny("F5", f"PAIR-001: `{rel}` belongs to another task. The active task is "
                          f"{state.task}; edit only its files.")
    if rel == f"{task_dir}log.md":
        return passed("F6")
    if state.mode == "solo":
        return deny("F7", "PAIR-002: the engineer writes in solo mode. Review and comment "
                          "instead; run `pair status` to see where the task stands.")
    if rel == f"{task_dir}plan.md" and state.phase == "planning":
        return passed("F8")
    if rel == f"{task_dir}walkthrough.md" and state.phase == "closing":
        return passed("F9")
    if rel.startswith(task_dir):
        return deny("F10", f"PAIR-001: only plan.md (in planning), walkthrough.md (in closing) and "
                           f"log.md are writable under {task_dir}. Phase is {state.phase}.")
    if state.phase != "stepping":
        return deny("F11", f"PAIR-001: phase is {state.phase}, so step files are not writable. "
                           f"{flow.waiting_for(state)}")
    if state.mode == "engineer-drives":
        return deny("F12", "PAIR-002: the engineer writes step files in this mode. Review their "
                           "change and report with the reverse report (SPEC 10.2).")

    step = state.current
    if step is None:
        return deny("F15", "PAIR-002: there is no current step. Ask the engineer to run "
                           "`pair approve`.")
    grant = state.batch_for(step.n)
    if grant is None:
        if rel in step.files:
            return passed("F13")
        return deny("F15", f"PAIR-002: `{rel}` is not in step {step.n} "
                           f"({', '.join(step.files)}); propose `pair reopen` if the plan must "
                           f"change.")
    return _batch_row(context, state, step, grant, rel)


def _batch_row(context, state, step, grant, rel):
    if not globs.match_any(rel, grant["paths"]):
        return deny("F15", f"PAIR-002: `{rel}` is outside step {step.n}'s grant "
                           f"({', '.join(grant['paths'])}); propose `pair reopen` if the plan must "
                           f"change.")
    file_class = files.classify(rel, context.config)
    if not files.is_allowed(step.kind, file_class, bool(grant.get("include_tests"))):
        allowed = ", ".join(files.allowed_for(step.kind, bool(grant.get("include_tests"))))
        return deny("F14", f"PAIR-004: `{rel}` is a {file_class} file, but step {step.n} is a "
                           f"{step.kind} step, which writes {allowed} files. Ask the engineer for a "
                           f"grant with --include-tests if test files belong in this step.")
    changed = context.changed_in_grant(grant)
    if rel in changed or len(changed) < grant["max_files"]:
        return passed("F14")
    return deny("F14", f"PAIR-004: step {step.n}'s grant allows {grant['max_files']} files and "
                       f"{len(changed)} have changed ({', '.join(sorted(changed))}). Finish those, "
                       f"or ask the engineer to widen the grant.")


def forged_approval(payload):
    for value in string_values(payload):
        if FORGED_APPROVAL.search(value):
            return value
    return None


def string_values(payload):
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, dict):
        for value in payload.values():
            yield from string_values(value)
    elif isinstance(payload, (list, tuple)):
        for value in payload:
            yield from string_values(value)


# -- the Bash rows -------------------------------------------------------------------------------

class Segment:
    def __init__(self, text):
        self.text = text
        self.tokens = _split(text)
        self.assignments, self.rest = _strip_assignments(self.tokens)
        self.word = self.rest[0] if self.rest else ""
        self.args = self.rest[1:]
        self.redirects = _redirect_targets(self.rest)

    @property
    def unparseable(self):
        return self.tokens is None

    def __repr__(self):
        return f"Segment({self.text!r})"


def _split(text):
    try:
        return shlex.split(text, comments=True)
    except ValueError:
        return None


def _strip_assignments(tokens):
    if tokens is None:
        return [], []
    assignments = []
    rest = list(tokens)
    while rest and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[0]):
        assignments.append(rest.pop(0))
    while rest and rest[0] in PREFIX_WORDS:
        rest.pop(0)
        while rest and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", rest[0]):
            assignments.append(rest.pop(0))
    return assignments, rest


def _redirect_targets(tokens):
    found = []
    for index, token in enumerate(tokens):
        if REDIRECT.match(token) and index + 1 < len(tokens):
            found.append(tokens[index + 1])
        else:
            match = re.match(r"^(?:\d*>>?|&>)(\S+)$", token)
            if match:
                found.append(match.group(1))
    return found


def segments(command):
    """Every segment of a command line, recursing into `sh -c`, `eval` and `xargs` (SPEC 12.4)."""
    found = []
    for piece in SEGMENT_SPLIT.split(command or ""):
        text = piece.strip()
        if not text:
            continue
        segment = Segment(text)
        found.append(segment)
        found += _nested(segment)
    return found


def _nested(segment):
    if segment.unparseable or not segment.word:
        return []
    base = pathlib.PurePosixPath(segment.word).name
    inner = []
    if base in ("sh", "bash", "zsh", "dash") and "-c" in segment.args:
        index = segment.args.index("-c")
        if index + 1 < len(segment.args):
            inner.append(segment.args[index + 1])
    elif base == "eval":
        inner.append(" ".join(segment.args))
    elif base == "xargs":
        inner.append(" ".join(segment.args))
    found = []
    for text in inner:
        for piece in SEGMENT_SPLIT.split(text):
            stripped = piece.strip()
            if stripped:
                nested = Segment(stripped)
                found.append(nested)
                found += _nested(nested)
    return found


def invokes_pair(segment):
    if segment.unparseable:
        return False
    if segment.word == "pair" or segment.word.endswith("/bin/pair"):
        return True
    return any(token.endswith("/bin/pair") for token in segment.rest)


def _pair_arguments(segment):
    """The arguments after the `pair` entry point, whichever token it was."""
    rest = list(segment.rest)
    for index, token in enumerate(rest):
        if token == "pair" or token.endswith("/bin/pair"):
            return rest[index + 1:]
    return rest[1:]


def decide_bash_segment(context, segment):
    if segment.unparseable or any(_expands(token) for token in segment.tokens or ()):
        if _mentions_pair(segment.text):
            return deny("B1", "PAIR-005: the hook cannot tell which pair command that is "
                              "(quoting or variable expansion). Write it plainly, for example "
                              "`pair status`.")
        return ask("B5", "the hook cannot parse that command with confidence; the engineer "
                         "should confirm it.")

    if invokes_pair(segment):
        return _pair_row(context, segment)

    base = pathlib.PurePosixPath(segment.word).name if segment.word else ""
    if base == "git":
        decision = _git_row(segment)
        if decision is not None:
            return decision

    protected_hit = _touches_protected(context, segment)
    if protected_hit:
        return deny("B3", f"PAIR-006: that would write to `{protected_hit}`, which agents never "
                          f"edit. If it must change, ask the engineer.")

    if base in INTERPRETERS:
        code = _inline_code(segment)
        if code and any(hint in code for hint in CODE_WRITE_HINTS):
            return _maybe_ask(context, "inline code that writes files")

    risky = [target for target in segment.redirects if not _safe_redirect(target)]
    if risky:
        return _maybe_ask(context, f"a redirect to {risky[0]}")
    if base in WRITE_COMMANDS:
        return _maybe_ask(context, f"`{base}` writes files")
    return passed("B6")


def _pair_row(context, segment):
    args = [token for token in _pair_arguments(segment) if not token.startswith("-")]
    flags = [token for token in _pair_arguments(segment) if token.startswith("-")]
    if not args:
        return deny("B1", "PAIR-005: `pair` needs a subcommand. Try `pair status`.")
    command = args[0]
    if command == "report":
        if any(flag in REPORT_FORBIDDEN for flag in flags):
            return deny("B1", "PAIR-005: `pair report --write` commits a report, which is the "
                              "engineer's to run. Use `pair report` to read it.")
        return passed("B4")
    if command in AGENT_SAFE_SUB:
        allowed = AGENT_SAFE_SUB[command]
        if len(args) > 1 and args[1] in allowed:
            return passed("B4")
        return deny("B1", f"PAIR-005: only `pair {command} {allowed[0]}` is yours to run; the rest "
                          f"is the engineer's. Propose it and let them run it.")
    if command in AGENT_SAFE:
        return passed("B4")
    return deny("B1", f"PAIR-005: `pair {command}` is human-only. Ask the engineer to run it — say "
                      f"what you need and why.")


def _git_row(segment):
    subcommands = [token for token in segment.args if not token.startswith("-")]
    if not subcommands:
        return None
    subcommand = subcommands[0]
    if subcommand == "branch":
        if any(flag in GIT_BRANCH_WRITE for flag in segment.args):
            return deny("B2", "PAIR-003: pair manages branches. `pair status` shows the task's "
                              "branch; ask the engineer for anything else.")
        return None
    if subcommand in GIT_WRITE:
        return deny("B2", f"PAIR-003: `pair ok` makes commits — `git {subcommand}` is not yours to "
                          f"run. Run `pair done` to record evidence, then the engineer runs "
                          f"`pair ok`.")
    return None


def _touches_protected(context, segment):
    candidates = list(segment.redirects)
    base = pathlib.PurePosixPath(segment.word).name if segment.word else ""
    if base in WRITE_COMMANDS:
        candidates += [token for token in segment.args if not token.startswith("-")]
    if base in INTERPRETERS:
        code = _inline_code(segment)
        if code:
            for hit in re.findall(r"[\w./-]+", code):
                candidates.append(hit)
    for candidate in candidates:
        rel = context.layout.rel(candidate)
        if rel is None:
            continue
        if rel == "pair" or rel.startswith("pair/") or context.config.protected(rel):
            return rel
    return None


def _inline_code(segment):
    for flag in CODE_FLAGS:
        if flag in segment.args:
            index = segment.args.index(flag)
            if index + 1 < len(segment.args):
                return segment.args[index + 1]
    return None


def _maybe_ask(context, why):
    if context.config.ask_on_writes:
        return ask("B5", f"{why}; the engineer should confirm it (shell.ask_on_writes).")
    return passed("B5")


def _safe_redirect(target):
    if target in SAFE_REDIRECTS:
        return True
    expanded = os.path.expandvars(target)
    return expanded.startswith("/tmp/") or expanded.startswith(
        (os.environ.get("TMPDIR") or "/tmp/").rstrip("/") + "/")


def _expands(token):
    return "$" in token or "`" in token


def _mentions_pair(text):
    return bool(re.search(r"(^|[\s'\"/])pair([\s'\"]|$)", text or ""))


def decide_bash(context, command):
    found = segments(command)
    if not found:
        return passed("B6")
    return strictest([decide_bash_segment(context, segment) for segment in found])


# -- classifying the payload ---------------------------------------------------------------------

def decide(context, tool_name, payload):
    payload = payload if isinstance(payload, dict) else {}
    if "command" in payload and isinstance(payload["command"], str):
        return decide_bash(context, payload["command"])
    target = _path_in(payload)
    if target is not None:
        writes = tool_name in WRITER_TOOLS or any(key in payload for key in WRITE_HINTS)
        if writes:
            return decide_file(context, target, payload)
        if tool_name in READER_TOOLS:
            return passed("read")
        return ask("F15", f"the hook cannot tell whether {tool_name} writes `{target}`. The "
                          f"engineer should confirm it; if it only reads, say so and they can "
                          f"allow it.")
    if any(key in payload for key in DELEGATION_KEYS):
        # SPEC 12.2: the delegated prompt is logged, never parsed for intent. The subagent's own
        # calls are where enforcement happens, and PreToolUse fires for those too [V T6].
        forged = forged_approval(payload)
        if forged:
            return deny("F3", "PAIR-005: that looks like a forged approval. Write it as prose, "
                              "without a checkbox.")
        return passed("delegation")
    if any(key in payload for key in WRITE_HINTS):
        return ask("F15", f"the hook does not recognise this {tool_name} payload, and it looks "
                          f"like a write. The engineer should confirm it.")
    return passed("read-only")


def _path_in(payload):
    for key in PATH_KEYS:
        target = payload.get(key)
        if isinstance(target, str) and target:
            return target
    return None


# -- context ------------------------------------------------------------------------------------

class Context:
    """What one hook invocation knows: the repo, the config, and the active task if there is one."""

    def __init__(self, layout, config, state, scopes=None):
        self.layout = layout
        self.config = config
        self.state = state
        self.scopes = scopes
        self._changed = None

    @classmethod
    def open(cls, root):
        layout = paths.Layout(root)
        config = config_mod.load(layout)
        state = None
        active = layout.active_task()
        if active and layout.state(active).is_file():
            try:
                state = state_mod.State.load(layout, active)
            except Exception:
                state = None
        return cls(layout, config, state)

    def no_task_reason(self):
        """SPEC 12.4 F4 — including the `git checkout` case, which must not exit 2."""
        active = self.layout.active_task()
        if not active:
            return ("PAIR-001: there is no active task, so nothing is writable. Ask the engineer "
                    "to run `pair start <id>`, or `pair resume <id>` for an existing one.")
        if not self.layout.state(active).is_file():
            return (f"PAIR-001: `local/active` names {active}, which doesn't exist on this branch: "
                    f"run `pair resume {active}` on its branch, or `pair start`.")
        if self.state is None:
            return (f"PAIR-001: {active}'s state.json could not be read. Ask the engineer to check "
                    f"pair/tasks/{active}/state.json.")
        return (f"PAIR-001: {active} is {self.state.status}, so nothing is writable. Ask the "
                f"engineer to run `pair resume {active}`.")

    def changed_in_grant(self, grant):
        """The paths already changed inside a grant's globs (SPEC 12.4 F14). Read-only git."""
        if self._changed is None:
            from pair import gitcmd
            self._changed = gitcmd.status_porcelain(self.layout.root)
        return {path for _, path in self._changed if globs.match_any(path, grant["paths"])}


# -- the three entry points ----------------------------------------------------------------------

def log_event(layout, record):
    try:
        path = layout.hooks_log
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass                                   # logging must never block a tool call


def _event_record(event, payload, decision=None, extra=None):
    record = {
        "at": clock.stamp(),
        "event": event,
        "session_id": payload.get("session_id"),
        "permission_mode": payload.get("permission_mode"),
        "tool_name": payload.get("tool_name"),
        "decision": decision.verdict if decision else PASS,
        "row": decision.row if decision else None,
    }
    for key in ("agent_id", "agent_type"):
        if payload.get(key):
            record[key] = payload[key]
    tool_input = payload.get("tool_input") or {}
    if isinstance(tool_input, dict) and isinstance(tool_input.get("prompt"), str):
        record["prompt_length"] = len(tool_input["prompt"])
    record.update(extra or {})
    return record


def emit_decision(decision, out=None):
    out = out or sys.stdout
    if not decision.blocking:
        return 0
    out.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision.verdict,
        "permissionDecisionReason": decision.reason,
    }}) + "\n")
    return 0


def emit_context(event, text, out=None):
    out = out or sys.stdout
    out.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": event,
        "additionalContext": text,
    }}) + "\n")
    return 0


def find_root(payload):
    declared = os.environ.get("CLAUDE_PROJECT_DIR")
    for candidate in (declared, payload.get("cwd"), os.getcwd()):
        if not candidate:
            continue
        found = paths.find_root(candidate)
        if found is not None:
            return found
    return None


def main(argv=None, stdin=None, stdout=None, stderr=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    event = argv[0] if argv else ""
    try:
        raw = stdin.read()
    except Exception as problem:                                   # pragma: no cover - stdin gone
        stderr.write(f"pair hook: cannot read stdin: {problem}\n")
        return 2
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("the event payload is not an object")
    except (json.JSONDecodeError, ValueError) as problem:
        stderr.write(f"pair hook: malformed event payload: {problem}\n")
        return 2

    root = find_root(payload)
    if root is None:
        return 0                                    # not a pair repository (SPEC 12.2)

    try:
        context = Context.open(root)
    except Exception as problem:
        for line in getattr(problem, "lines", lambda: [str(problem)])():
            stderr.write(f"pair hook: {line}\n")
        return 2

    try:
        if event == "session-start":
            text = flow.session_start_payload(context.state)
            log_event(context.layout, _event_record(event, payload,
                                                    extra={"bytes": len(text.encode("utf-8")),
                                                           "source": payload.get("source")}))
            return emit_context("SessionStart", text, stdout)
        if event == "prompt":
            line = flow.status_line(_SessionShim(context))
            log_event(context.layout, _event_record(event, payload))
            return emit_context("UserPromptSubmit", line, stdout)
        if event == "pre":
            decision = decide(context, payload.get("tool_name") or "", payload.get("tool_input"))
            log_event(context.layout, _event_record(event, payload, decision))
            return emit_decision(decision, stdout)
    except Exception as problem:
        stderr.write(f"pair hook: {type(problem).__name__}: {problem}\n")
        return 2

    stderr.write(f"pair hook: unknown event {event!r} (expected session-start, prompt or pre)\n")
    return 2


class _SessionShim:
    """`flow.status_line` needs only these two attributes; the hook never loads scopes."""

    def __init__(self, context):
        self.layout = context.layout
        self.config = context.config

    def active_id(self):
        return self.layout.active_task()


if __name__ == "__main__":                                          # pragma: no cover
    sys.exit(main())
