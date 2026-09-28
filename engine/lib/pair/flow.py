"""The task flow: every transition in SPEC 7.4, and the wording `pair status` shows.

One rule shapes the whole module: anything that grants permission or moves work **forward** is
human-only; anything that moves it **back** — `rework`, `reopen`, `pause` — is open to the agent
(SPEC 7.4). The refusals are written as instructions, because the agent reads them (SPEC 12.4).
"""

import re

from pair import (clock, commit, config as config_mod, coverage as coverage_mod, evidence, files,
                  gitcmd, lessons as lessons_mod, log, paths, plan as plan_mod, rules, scopes,
                  state as state_mod, waivers as waivers_mod)
from pair.errors import CheckFailed, Refused, UsageError

TASK_ID = re.compile(state_mod.TASK_ID)

HUMAN_ONLY = ("init", "upgrade", "baseline", "start", "mode", "approve", "ok", "revert", "close",
              "resume", "handoff", "abandon", "grant-batch", "waive", "expedite",
              "lesson-accept", "lesson-edit", "lesson-reject", "lesson-dispute", "report-write")
OWNER_ONLY = ("mode", "approve", "ok", "revert", "close", "grant-batch", "resume", "handoff",
              "abandon")
CONFIRM_WITH_Y = ("init", "upgrade", "baseline")

SKILL_FOR_PHASE = {
    "planning": "pair:pair-plan",
    "stepping": "pair:pair-step",
    "review": "pair:pair-step",
    "closing": "pair:pair-close",
}

WALKTHROUGH_SECTIONS = ("What was built", "Where it fits", "Key decisions", "Waivers used",
                        "How to test it", "How to roll it back", "Possibly stale knowledge",
                        "Lessons")


class Outcome:
    """What a transition produced: lines for a human, data for `--json`."""

    def __init__(self, lines=(), data=None, warnings=()):
        self.lines = list(lines)
        self.data = dict(data or {})
        self.warnings = list(warnings)

    def add(self, line):
        self.lines.append(line)
        return self


class Session:
    """Everything a command needs about this repository, loaded once."""

    def __init__(self, layout, config, scope_set, registry, confirm=None):
        self.layout = layout
        self.config = config
        self.scopes = scope_set
        self.registry = registry
        self._confirm = confirm

    @classmethod
    def open(cls, root=None, confirm=None):
        found = paths.find_root(root)
        if found is None:
            raise CheckFailed(
                "this is not a pair repository: no pair/config.toml here or above. "
                "Run `pair init` in the repository root."
            )
        layout = paths.Layout(found)
        cfg = config_mod.load(layout)
        return cls(layout, cfg, scopes.Scopes.load(layout, cfg), rules.Registry.load(layout),
                   confirm=confirm)

    @property
    def root(self):
        return self.layout.root

    @property
    def me(self):
        return self.config.me

    # -- permission layers -----------------------------------------------------------------
    def require_human(self, command, subject=None):
        """Layer 1 of PAIR-005: a real terminal, and the engineer typing the expected word."""
        from pair import tty
        confirm = self._confirm or tty.confirm
        expect = "y" if command in CONFIRM_WITH_Y else (subject or "y")
        question = (f"Type the task id to confirm `pair {command}`:" if subject
                    else f"Run `pair {command}`? [y/N]")
        if not confirm(question, expect):
            raise Refused(f"`pair {command}` was not confirmed — nothing was changed.")

    def require_owner(self, state, command):
        me = self.config.require_me()
        if me != state.owner:
            raise Refused(
                f"`pair {command}` is for the task's owner, {state.owner} — ask {state.owner} or "
                f"run `pair handoff {me}` from their checkout."
            )
        return me

    # -- loading a task --------------------------------------------------------------------
    def active_id(self):
        return self.layout.active_task()

    def state(self, task_id=None):
        wanted = task_id or self.active_id()
        if not wanted:
            raise CheckFailed(
                "no active task — ask the engineer to run: pair start <id>")
        return state_mod.State.load(self.layout, wanted)

    def require_phase(self, state, command, *allowed):
        if state.phase in allowed:
            return
        raise CheckFailed(
            f"`pair {command}` needs phase {' or '.join(allowed)}, but {state.task} is in "
            f"{state.phase}.", [waiting_for(state)])

    def require_open(self, state, command):
        if not state.is_open:
            raise CheckFailed(
                f"{state.task} is {state.status}, so `pair {command}` does not apply.",
                [f"run `pair resume {state.task}`" if state.status == "paused"
                 else "start a new task with `pair start <id>`"])

    def baselines(self):
        return coverage_mod.Baselines.load(self.layout.baseline)

    def lesson_ids(self):
        return lessons_mod.ids(self.layout)

    # -- writing ---------------------------------------------------------------------------
    def rel(self, path):
        return self.layout.rel(path)

    def task_files(self, state):
        return [self.rel(self.layout.state(state.task)), self.rel(self.layout.log(state.task))]

    def commit_task(self, state, action, subject_line, extra_paths=(), step=None, kind=None,
                    approved_by=None, reverts=None):
        paths_to_commit = self.task_files(state) + [p for p in extra_paths if p]
        return commit.action_commit(self.root, paths_to_commit, action, self.config.governance,
                                    subject_line, task=state.task, step=step, kind=kind,
                                    approved_by=approved_by, reverts=reverts)


# -- the wording `status` and the hook share ----------------------------------------------------

def waiting_for(state):
    """The "waiting for" line of SPEC 11.5 — also every wrong-phase message's next action."""
    if state.status == "paused":
        return f"waiting for: engineer → pair resume {state.task}"
    if state.status == "abandoned":
        return "waiting for: nothing — this task was abandoned"
    if state.status == "closed" or state.phase == "done":
        return "waiting for: nothing — this task is closed"
    if state.phase == "planning":
        return "waiting for: engineer → pair approve (after `pair plan-check` passes)"
    if state.phase == "stepping":
        step = state.current
        where = f"step {step.n} ({step.kind}) {' '.join(step.files)}" if step else "the next step"
        return f"waiting for: agent → write {where}, then pair done"
    if state.phase == "review":
        return "waiting for: engineer → pair ok · pair rework \"<note>\" · pair pause"
    return "waiting for: agent → walkthrough.md, then engineer → pair close"


def next_action(state):
    """One line naming the skill to use, for the SessionStart pointer (SPEC 12.3)."""
    if state is None:
        return "no active task — ask the engineer to run: pair start <id>"
    if not state.is_open:
        return f"{state.task} is {state.status} — ask the engineer to run: pair resume " \
               f"{state.task}"
    skill = SKILL_FOR_PHASE.get(state.phase)
    if state.phase == "review":
        return f"use {skill}: the step is submitted, wait for `pair ok`"
    if state.phase == "stepping":
        step = state.current
        where = f"step {step.n} ({step.kind}) {' '.join(step.files)}" if step else "the next step"
        return f"use {skill}: write {where}, then run `pair done`"
    if state.phase == "planning":
        return f"use {skill}: write the plan, then `pair plan-check`"
    if state.phase == "closing":
        return f"use {skill}: write the walkthrough"
    return "nothing to do"


MAX_CONTEXT = 2000          # SPEC 12.3: only the first ~2 KB of additionalContext reaches the model
DOCTOR_LIMIT = 1800         # `pair doctor` fails above this, leaving headroom


def session_start_payload(state):
    """Under 2 KB, most important first, self-dating and self-superseding (SPEC 12.3).

    It lives here rather than in the hook because it is phase wording, and `pair doctor` has to
    measure the very same bytes the hook would emit.
    """
    head = f"pair @ {clock.short()} (supersedes any earlier pair: block)"
    if state is not None:
        head += f" \u00b7 task {state.task} \u00b7 phase {state.phase} \u00b7 mode {state.mode}"
        step = state.current
        if step is not None:
            head += f" \u00b7 step {step.n} of {state.total_steps} ({step.kind})"
    else:
        head += " \u00b7 no active task"
    lines = [head, next_action(state),
             "The engineer decides. Write one file per validated step. Run `pair status` first."]
    return "\n".join(lines)[:MAX_CONTEXT]


def status_line(session, state=None):
    """`pair status --line` (SPEC 11.5)."""
    if state is None:
        active = session.active_id()
        if not active:
            return "[pair] no active task — ask the engineer to run: pair start <id>"
        if not session.layout.state(active).is_file():
            return (f"[pair] {active} not on this branch — pair resume {active} on its "
                    f"branch, or pair start <new-id>")
        state = state_mod.State.load(session.layout, active)
    step = state.current
    where = f" {state.phase} {step.n}/{state.total_steps}" if step else f" {state.phase}"
    who = "engineer" if state.phase in ("planning", "review") else "agent"
    return f"[pair] {state.task} ·{where} · waiting for {who}"


def status(session, state=None):
    """The five-line `pair status` block (SPEC 11.5)."""
    if state is None:
        active = session.active_id()
        if not active:
            return Outcome([status_line(session)], {"task": None})
        if not session.layout.state(active).is_file():
            return Outcome([status_line(session)], {"task": active, "on_branch": False})
        state = state_mod.State.load(session.layout, active)

    lines = [f"pair · {state.task} · owner {state.owner} · {state.mode} · "
             f"governance {state.governance}"]
    step = state.current
    if step:
        lines.append(f"phase: {state.phase} · step {step.n}/{state.total_steps} "
                     f"({step.kind}) {' '.join(step.files)}")
    else:
        lines.append(f"phase: {state.phase}")
    if step and step.evidence:
        lines.append("evidence: " + _evidence_line(step.evidence))
    lines.append(waiting_for(state))
    following = state.next_pending(after=step.n) if step else state.next_pending()
    if following is not None and (step is None or following.n != step.n):
        lines.append(f"next: step {following.n} ({following.kind}) "
                     f"{' '.join(following.files)} — {following.behavior}")
    if state.expedite:
        lines.append(f"expedite: {state.expedite['reason']} · review due "
                     f"{state.expedite.get('review_due', 'unset')}")
    return Outcome(lines, {"task": state.task, "phase": state.phase, "mode": state.mode,
                           "status": state.status, "owner": state.owner,
                           "step": step.n if step else None, "steps": state.total_steps})


def _evidence_line(record):
    parts = [record.get("result", "?")]
    if record.get("tests"):
        parts.append(record["tests"])
    if record.get("changed_lines_covered") is not None:
        parts.append(f"changed lines {record['changed_lines_covered']}%")
    if record.get("scope_line") is not None:
        parts.append(f"scope {record['scope_line']}%/{record['scope_branch']}% "
                     f"(floor {record.get('floor_line')}/{record.get('floor_branch')})")
    return " · ".join(str(part) for part in parts)


# -- transitions -------------------------------------------------------------------------------

def start(session, task_id, mode="agent-drives", no_branch=False):
    if not TASK_ID.match(task_id or ""):
        raise UsageError(f"{task_id!r} is not a task id: lowercase letters, digits and dashes, "
                         f"2 to 40 characters (SPEC 7.1)")
    if mode not in state_mod.MODES:
        raise UsageError(f"{mode!r} is not a mode ({', '.join(state_mod.MODES)})")
    session.require_human("start", subject=task_id)
    me = session.config.require_me()

    if session.layout.state(task_id).is_file():
        raise CheckFailed(f"task {task_id} already exists on this branch — "
                          f"run `pair resume {task_id}`")
    dirty = [path for path in gitcmd.modified_tracked(session.root)
             if not path.startswith("pair/tasks/")]
    if dirty:
        raise CheckFailed(
            "there are uncommitted changes outside pair/tasks/, and a task must start from a clean "
            "tree (SPEC 7.4)", [*dirty, "commit or stash them, then run `pair start` again"])

    branch = f"pair/{task_id}"
    created = False
    if not no_branch:
        if gitcmd.branch_exists(session.root, branch):
            raise CheckFailed(f"branch {branch} already exists — `git checkout {branch}` and run "
                              f"`pair resume {task_id}`")
        gitcmd.create_branch(session.root, branch)
        created = True
    else:
        branch = gitcmd.current_branch(session.root) or branch

    state = state_mod.State.create(session.layout, task_id, me, branch, mode,
                                   session.config.governance)
    state.add_event("start", me)
    session.layout.task_dir(task_id).mkdir(parents=True, exist_ok=True)
    log.action_entry(session.layout.log(task_id), "start", me,
                     detail=f"mode {mode}" if mode != "agent-drives" else None)
    state.save()
    session.layout.local.mkdir(parents=True, exist_ok=True)
    session.layout.active_file.write_text(task_id + "\n", encoding="utf-8")

    sha, warnings = session.commit_task(state, "start", f"chore(pair): start {task_id}")
    lines = [f"started {task_id} · phase planning · mode {mode}"]
    if created:
        lines.append(f"branch {branch} created and checked out")
    lines.append(next_action(state))
    return Outcome(lines, {"task": task_id, "branch": branch, "commit": sha}, warnings)


def plan_check(session, state=None):
    state = state or session.state()
    plan = plan_mod.load(session.layout.plan(state.task))
    problems = plan_mod.check(plan, state, session.config, session.scopes, session.lesson_ids())
    if problems:
        raise CheckFailed(f"plan-check found {len(problems)} problem"
                          f"{'' if len(problems) == 1 else 's'} in "
                          f"pair/tasks/{state.task}/plan.md", problems)
    return Outcome([f"plan-check passed · {len(plan.rows)} steps"],
                   {"steps": len(plan.rows), "ok": True})


def approve(session, state=None):
    state = state or session.state()
    session.require_phase(state, "approve", "planning")
    session.require_open(state, "approve")
    me = session.require_owner(state, "approve")
    session.require_human("approve", subject=state.task)

    plan = plan_mod.load(session.layout.plan(state.task))
    problems = plan_mod.check(plan, state, session.config, session.scopes, session.lesson_ids())
    if problems:
        raise CheckFailed("approve refuses: plan-check does not pass", problems)

    state.set_steps(plan.as_steps())
    digest = plan_mod.hash_file(session.layout.plan(state.task))
    state.record_approval(me, digest)
    state.lessons_used = plan.lesson_refs
    following = state.first_unfinished()
    state.phase = "stepping" if following else "closing"
    state.current_step = following.n if following else 0
    state.add_event("approve", me)
    log.action_entry(session.layout.log(state.task), "approve", me)
    state.save()

    warnings = list(_overlap_warnings(session, state))
    sha, more = session.commit_task(
        state, "approve", f"chore(pair): approve plan for {state.task}",
        extra_paths=[session.rel(session.layout.plan(state.task))])
    lines = [f"approved · {len(state.data['steps'])} steps · phase {state.phase}",
             next_action(state)]
    return Outcome(lines, {"phase": state.phase, "commit": sha}, warnings + more)


def _overlap_warnings(session, state):
    """SPEC 7.4: warn when approved step files overlap another live task's."""
    mine = {rel for step in state.steps for rel in step.files}
    for other_id in state_mod.find_tasks(session.layout):
        if other_id == state.task:
            continue
        try:
            other = state_mod.State.load(session.layout, other_id)
        except CheckFailed:
            continue
        if other.status not in ("active", "paused", "expedite"):
            continue
        shared = mine & {rel for step in other.steps for rel in step.files}
        if shared:
            yield (f"{other_id} ({other.status}) also has "
                   f"{', '.join(sorted(shared))} in its steps")


def done(session, state=None):
    state = state or session.state()
    session.require_phase(state, "done", "stepping")
    session.require_open(state, "done")
    step = state.current
    if step is None:
        raise CheckFailed(f"{state.task} has no current step — run `pair approve` first")
    scope, trouble = session.scopes.resolve_all(
        [plan_mod.glob_prefix(f) or f for f in evidence.file_set(session.root, state, step,
                                                                 session.config)])
    if scope is None:
        raise CheckFailed(f"step {step.n} {trouble}")

    baselines = session.baselines()
    record, warnings, outcome = evidence.gather(session.layout, session.config, state, step, scope,
                                                baselines)
    evidence.run_log(session.layout, state.task, step.n, outcome)
    step.evidence = record
    step.status = "submitted"
    state.phase = "review"
    me = session.me or state.owner
    state.add_event("done", me)
    log.action_entry(session.layout.log(state.task), "done", me, step=step.n,
                     detail=record["result"], body=record.get("summary"))
    state.save()

    sha, more = session.commit_task(state, "done", f"chore(pair): evidence for step {step.n}",
                                    step=step.n, kind=step.kind)
    lines = [f"step {step.n} ({step.kind}) · {record['result']} · "
             f"{record.get('tests', '')}".rstrip(" · ")]
    if record.get("changed_lines_covered") is not None:
        lines.append(f"changed lines {record['changed_lines_covered']}% · scope "
                     f"{record['scope_line']}%/{record['scope_branch']}% "
                     f"(floor {record['floor_line']}/{record['floor_branch']})")
    if record.get("note"):
        lines.append(record["note"])
    lines.append(waiting_for(state))
    return Outcome(lines, {"step": step.n, "result": record["result"], "commit": sha},
                   warnings + more)


def ok(session, state=None):
    state = state or session.state()
    session.require_phase(state, "ok", "review")
    session.require_open(state, "ok")
    me = session.require_owner(state, "ok")
    session.require_human("ok", subject=state.task)

    step = state.current
    if step is None or not step.evidence:
        raise CheckFailed(f"step {getattr(step, 'n', '?')} has no evidence — run `pair done`")
    recorded = step.evidence.get("files_sha256") or {}
    drifted = evidence.unchanged(session.root, recorded)
    if drifted:
        raise CheckFailed(
            "the step's files changed after `pair done`, so the evidence no longer describes them",
            [*drifted, "run `pair done` again"])

    step_files = list(step.evidence.get("committed_files") or step.files)
    scope, trouble = session.scopes.resolve_all([f for f in step_files])
    if scope is None:
        raise CheckFailed(f"step {step.n} {trouble}")

    # Refuse before anything is written: a failed commit must not leave the phase advanced.
    commit.check_index(session.root, session.task_files(state) + step_files
                       + [session.rel(session.layout.baseline)])

    baselines = session.baselines()
    raised = False
    if step.kind in ("char", "code", "refactor") and step.evidence.get("scope_line") is not None:
        raised = baselines.raise_to(scope.name, step.evidence["scope_line"],
                                    step.evidence["scope_branch"])
        if raised:
            baselines.save()

    step.status = "ok"
    following = state.next_pending(after=step.n)
    state.phase = "stepping" if following else "closing"
    state.current_step = following.n if following else step.n
    state.add_event("ok", me)
    log.action_entry(session.layout.log(state.task), "ok", me, step=step.n)
    state.save()

    plan = None
    try:
        plan = plan_mod.load(session.layout.plan(state.task))
    except CheckFailed:
        pass
    subject_line = commit.subject(step.kind, scope.slug, step.behavior,
                                  plan.title if plan else "")
    extra = list(step_files)
    if raised:
        extra.append(session.rel(session.layout.baseline))
    sha, warnings = session.commit_task(state, "ok", subject_line, extra_paths=extra,
                                        step=step.n, kind=step.kind, approved_by=me)
    lines = [f"step {step.n} committed · {sha[:8]} · {subject_line}"]
    if raised:
        lines.append(f"baseline for {scope.name} raised to {step.evidence['scope_line']}%/"
                     f"{step.evidence['scope_branch']}%")
    lines.append(next_action(state))
    return Outcome(lines, {"step": step.n, "commit": sha, "phase": state.phase,
                           "baseline_raised": raised}, warnings)


def rework(session, note, state=None):
    if not (note or "").strip():
        raise UsageError('pair rework needs a note: pair rework "<what to change>"')
    state = state or session.state()
    session.require_phase(state, "rework", "review")
    step = state.current
    if step is not None:
        step.evidence = None
        step.status = "pending"
    state.phase = "stepping"
    me = session.me or state.owner
    state.add_event("rework", me, note=note)
    log.action_entry(session.layout.log(state.task), "rework", me,
                     step=step.n if step else None, body=note)
    state.save()
    sha, warnings = session.commit_task(state, "rework",
                                        f"chore(pair): rework step {step.n if step else '?'}",
                                        step=step.n if step else None)
    return Outcome([f"step {step.n if step else '?'} back to stepping · {note}",
                    waiting_for(state)], {"phase": "stepping", "commit": sha}, warnings)


def reopen(session, state=None):
    state = state or session.state()
    session.require_phase(state, "reopen", "stepping", "review", "closing")
    locked = [step.n for step in state.steps if step.is_ok]
    state.clear_approval()
    state.phase = "planning"
    me = session.me or state.owner
    state.add_event("reopen", me)
    log.action_entry(session.layout.log(state.task), "reopen", me)
    state.save()
    sha, warnings = session.commit_task(state, "reopen", f"chore(pair): reopen plan for "
                                                          f"{state.task}")
    lines = [f"phase planning · approval cleared"]
    if locked:
        lines.append(f"validated steps stay locked: {', '.join(str(n) for n in locked)}")
    lines.append(next_action(state))
    return Outcome(lines, {"phase": "planning", "locked": locked, "commit": sha}, warnings)


def pause(session, state=None):
    state = state or session.state()
    if state.status != "active":
        raise CheckFailed(f"{state.task} is {state.status}, not active")
    state.status = "paused"
    me = session.me or state.owner
    state.add_event("pause", me)
    log.action_entry(session.layout.log(state.task), "pause", me)
    state.save()
    sha, warnings = session.commit_task(state, "pause", f"chore(pair): pause {state.task}")
    return Outcome([f"{state.task} paused in phase {state.phase}", waiting_for(state)],
                   {"status": "paused", "commit": sha}, warnings)


def resume(session, task_id):
    state = session.state(task_id)
    me = session.require_owner(state, "resume")
    session.require_human("resume", subject=state.task)
    if state.status not in ("paused", "active", "expedite"):
        raise CheckFailed(f"{state.task} is {state.status} and cannot be resumed")
    lines = []
    if state.branch and gitcmd.current_branch(session.root) != state.branch:
        if gitcmd.branch_exists(session.root, state.branch):
            gitcmd.checkout(session.root, state.branch)
            lines.append(f"checked out {state.branch}")
        else:
            lines.append(f"branch {state.branch} is not in this checkout — fetch it first")
    state.status = "active"
    state.add_event("resume", me)
    log.action_entry(session.layout.log(state.task), "resume", me)
    state.save()
    session.layout.local.mkdir(parents=True, exist_ok=True)
    session.layout.active_file.write_text(state.task + "\n", encoding="utf-8")
    sha, warnings = session.commit_task(state, "resume", f"chore(pair): resume {state.task}")
    lines += [f"{state.task} active · phase {state.phase}", next_action(state)]
    return Outcome(lines, {"status": "active", "commit": sha}, warnings)


def handoff(session, handle, state=None):
    if not re.match(state_mod.HANDLE, handle or ""):
        raise UsageError(f"{handle!r} is not a handle: it must look like @bob")
    state = state or session.state()
    session.require_owner(state, "handoff")
    session.require_human("handoff", subject=state.task)
    previous = state.owner
    state.data["owner"] = handle
    state.status = "paused"
    state.add_event("handoff", previous, note=f"to {handle}")
    log.action_entry(session.layout.log(state.task), "handoff", previous, detail=f"to {handle}")
    state.save()
    sha, warnings = session.commit_task(state, "handoff",
                                        f"chore(pair): hand {state.task} to {handle}")
    return Outcome([f"{state.task} now owned by {handle}, paused",
                    f"{handle} checks out {state.branch} and runs `pair resume {state.task}`"],
                   {"owner": handle, "commit": sha}, warnings)


def abandon(session, reason, state=None):
    if not (reason or "").strip():
        raise UsageError('pair abandon needs a reason: pair abandon "<why>"')
    state = state or session.state()
    session.require_owner(state, "abandon")
    session.require_human("abandon", subject=state.task)
    me = state.owner
    state.status = "abandoned"
    state.add_event("abandon", me, note=reason)
    log.action_entry(session.layout.log(state.task), "abandon", me, body=reason)
    state.save()
    if session.layout.active_task() == state.task:
        session.layout.active_file.write_text("", encoding="utf-8")
    sha, warnings = session.commit_task(state, "abandon", f"chore(pair): abandon {state.task}")
    return Outcome([f"{state.task} abandoned · {reason}", "files are kept as they are"],
                   {"status": "abandoned", "commit": sha}, warnings)


def mode(session, new_mode, state=None):
    if new_mode not in state_mod.MODES:
        raise UsageError(f"{new_mode!r} is not a mode ({', '.join(state_mod.MODES)})")
    state = state or session.state()
    if state.phase == "done":
        raise CheckFailed(f"{state.task} is done; its mode cannot change")
    me = session.require_owner(state, "mode")
    session.require_human("mode", subject=state.task)
    was = state.mode
    state.mode = new_mode
    state.add_event("mode", me, note=f"{was} → {new_mode}")
    log.action_entry(session.layout.log(state.task), "mode", me, detail=f"{was} → {new_mode}")
    state.save()
    sha, warnings = session.commit_task(state, "mode", f"chore(pair): {state.task} mode "
                                                        f"{new_mode}")
    lines = [f"mode {was} → {new_mode}"]
    if state.phase == "planning":
        lines.append("update the plan's \U0001F465 Mode line to match")
    return Outcome(lines, {"mode": new_mode, "commit": sha}, warnings)


def grant_batch(session, step_number, patterns, max_files, include_tests=False, state=None):
    state = state or session.state()
    session.require_phase(state, "grant-batch", "planning")
    me = session.require_owner(state, "grant-batch")
    session.require_human("grant-batch", subject=state.task)
    if max_files > session.config.batch_max_files:
        raise CheckFailed(f"--max-files {max_files} is above steps.batch_max_files "
                          f"({session.config.batch_max_files})")
    if max_files < 1:
        raise UsageError("--max-files must be at least 1")
    if not patterns:
        raise UsageError('--paths needs at least one glob, e.g. --paths "packages/billing/**/*.py"')
    state.add_batch(step_number, patterns, max_files, include_tests, me)
    state.add_event("grant-batch", me, note=f"step {step_number}: {', '.join(patterns)}")
    log.action_entry(session.layout.log(state.task), "grant-batch", me, step=step_number,
                     detail=f"{max_files} files")
    state.save()
    sha, warnings = session.commit_task(state, "grant-batch",
                                        f"chore(pair): batch grant for step {step_number}",
                                        step=step_number)
    return Outcome([f"step {step_number} may write up to {max_files} files matching "
                    f"{', '.join(patterns)}"
                    + (" (test files included)" if include_tests else ""),
                    f"list those globs in the plan's step {step_number} row"],
                   {"step": step_number, "commit": sha}, warnings)


def close(session, state=None):
    state = state or session.state()
    session.require_phase(state, "close", "closing")
    me = session.require_owner(state, "close")

    path = session.layout.walkthrough(state.task)
    problems = walkthrough_problems(path)
    if problems:
        raise CheckFailed(f"the walkthrough is not complete: pair/tasks/{state.task}/"
                          f"walkthrough.md", problems)

    session.require_human("close", subject=state.task)
    from pair import tty
    confirm = session._confirm or tty.confirm
    if not confirm("Can you explain this change to a colleague without the agent? [y/N]", "y"):
        raise Refused("close needs a yes to the understanding check — nothing was changed. "
                      "Ask for an explanation at L2 or L3 first.")

    touched = []
    today = clock.today()
    for ref in state.lessons_used:
        found = lessons_mod.LESSON_ID.match(ref)
        if not found:
            continue
        domain = lessons_mod.domain(session.layout, found.group("domain"))
        if domain.set_last_used(ref, today):
            domain.save()
            touched.append(session.rel(domain.path))

    state.phase = "done"
    state.status = "closed"
    state.add_event("close", me)
    log.action_entry(session.layout.log(state.task), "close", me)
    state.save()
    sha, warnings = session.commit_task(
        state, "close", f"docs(pair): close {state.task}",
        extra_paths=[session.rel(path)] + touched)
    if session.layout.active_task() == state.task:
        session.layout.active_file.write_text("", encoding="utf-8")
    lines = [f"{state.task} closed · {sha[:8]}"]
    if touched:
        lines.append("lessons updated: " + ", ".join(touched))
    lines.append("run `pair export walkthrough` to share it outside the repo")
    return Outcome(lines, {"status": "closed", "commit": sha}, warnings)


def walkthrough_problems(path):
    """Every §10.4 section that is missing or empty."""
    if not path.is_file():
        return [f"{path.name} has not been written yet — it needs: "
                + ", ".join(WALKTHROUGH_SECTIONS)]
    text = path.read_text(encoding="utf-8")
    found = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            found[current] = []
        elif current is not None:
            found[current].append(line)
    problems = []
    for name in WALKTHROUGH_SECTIONS:
        if name not in found:
            problems.append(f"`## {name}` is missing")
        elif not "\n".join(found[name]).strip():
            problems.append(f"`## {name}` is empty — write \"none\" if nothing applies")
    return problems


def revert(session, task_id, step_number=None):
    state = session.state(task_id)
    session.require_owner(state, "revert")
    session.require_human("revert", subject=state.task)
    greps = [f"Pair-Task: {state.task}", "Pair-Action: ok"]
    if step_number is not None:
        greps.append(f"Pair-Step: {step_number}")
    found = gitcmd.find_commits(session.root, *greps)
    if not found:
        raise CheckFailed(f"no validated commit found for {state.task}"
                          + (f" step {step_number}" if step_number else ""))
    reverted = []
    for sha in found:                     # find_commits returns newest first, which is the order
        done_ok, output = gitcmd.revert(session.root, sha)
        if not done_ok:
            raise CheckFailed(
                f"reverting {sha[:8]} hit a conflict, so nothing further was reverted",
                [output, "resolve the conflict, then `git revert --continue`, or "
                         "`git revert --abort` to stop"])
        message = commit.message(
            f"revert: {gitcmd.commit_message(session.root, sha).splitlines()[0]}",
            commit.trailers_for("revert", session.config.governance, task=state.task,
                                reverts=sha))
        gitcmd.amend_message(session.root, message)
        reverted.append(sha)
    me = state.owner
    state.add_event("revert", me, note=f"{len(reverted)} commit(s)")
    log.action_entry(session.layout.log(state.task), "revert", me, step=step_number,
                     detail=f"{len(reverted)} commit(s)")
    state.save()
    session.commit_task(state, "revert", f"chore(pair): record revert of {state.task}")
    return Outcome([f"reverted {len(reverted)} commit(s): "
                    + ", ".join(sha[:8] for sha in reverted)],
                   {"reverted": reverted})


# -- expedite (SPEC 16) --------------------------------------------------------------------------

def expedite(session, task_id, test_paths, code_paths, reason, no_branch=False):
    """An incident route that behaves like `start` + `approve`, with the normal evidence rules."""
    if not TASK_ID.match(task_id or ""):
        raise UsageError(f"{task_id!r} is not a task id (SPEC 7.1)")
    if not test_paths or not code_paths:
        raise UsageError('pair expedite needs --test-paths and --paths, each one or more globs')
    if not (reason or "").strip():
        raise UsageError('pair expedite needs --reason "<why this cannot wait>"')
    session.require_human("expedite", subject=task_id)
    me = session.config.require_me()
    if session.layout.state(task_id).is_file():
        raise CheckFailed(f"task {task_id} already exists — run `pair resume {task_id}`")

    for label, patterns in (("--test-paths", test_paths), ("--paths", code_paths)):
        scope, trouble = session.scopes.resolve_all(
            [plan_mod.glob_prefix(pattern) or pattern for pattern in patterns])
        if scope is None:
            raise CheckFailed(f"{label} {trouble} — split the incident into separate tasks "
                              f"(SPEC 16)")

    branch = f"pair/{task_id}"
    if not no_branch and not gitcmd.branch_exists(session.root, branch):
        gitcmd.create_branch(session.root, branch)
    elif no_branch:
        branch = gitcmd.current_branch(session.root) or branch

    state = state_mod.State.create(session.layout, task_id, me, branch, "agent-drives",
                                   session.config.governance, status="expedite", phase="stepping")
    limit = session.config.expedite_max_files
    rows = [{"n": 1, "kind": "test", "files": list(test_paths),
             "behavior": f"reproduce the incident: {reason}"},
            {"n": 2, "kind": "code", "files": list(code_paths),
             "behavior": "minimum fix, with the test green"}]
    state.set_steps(rows)
    state.add_batch(1, list(test_paths), limit, True, me)
    state.add_batch(2, list(code_paths), limit, False, me)
    state.current_step = 1

    session.layout.task_dir(task_id).mkdir(parents=True, exist_ok=True)
    plan_text = _expedite_plan(task_id, reason, rows, session.config.governance)
    session.layout.plan(task_id).write_text(plan_text, encoding="utf-8")

    due = clock.stamp(clock.now() + _hours(session.config.expedite_review_hours))
    state.data["expedite"] = {"by": me, "at": clock.stamp(), "reason": reason,
                              "test_paths": list(test_paths), "paths": list(code_paths),
                              "review_due": due}
    state.record_approval(me, plan_mod.sha256(plan_text))
    state.add_event("expedite", me, note=reason)
    log.action_entry(session.layout.log(task_id), "expedite", me, body=reason)
    state.save()
    session.layout.local.mkdir(parents=True, exist_ok=True)
    session.layout.active_file.write_text(task_id + "\n", encoding="utf-8")

    sha, warnings = session.commit_task(
        state, "expedite", f"chore(pair): expedite {task_id}",
        extra_paths=[session.rel(session.layout.plan(task_id))])
    return Outcome([f"expedite {task_id} · phase stepping · review due {due}",
                    f"step 1 (test) {', '.join(test_paths)}",
                    f"step 2 (code) {', '.join(code_paths)}",
                    "evidence and CI rules are the normal ones: red on its own commit, then green "
                    "with 100% changed-line coverage"],
                   {"task": task_id, "review_due": due, "commit": sha}, warnings)


def _hours(count):
    import datetime
    return datetime.timedelta(hours=count)


def _expedite_plan(task_id, reason, rows, governance):
    table = "\n".join(f"| {row['n']} | {row['kind']} | "
                      + ", ".join(f"`{pattern}`" for pattern in row["files"])
                      + f" | {row['behavior']} |" for row in rows)
    return (f"# Task {task_id}: expedited incident\n"
            f"\U0001F3AF Goal: {reason}\n"
            f"\U0001F9ED Approach: reproduce with a test, then the minimum fix\n"
            f"\U0001F50E Explored: expedited — exploration happens in the review\n"
            f"\U0001F4DA Rules & lessons: TEST-001\n"
            f"\U0001F500 Alternatives: waiting for a normal task, rejected: this is an incident\n"
            f"⚠️ Risks: written under time pressure; the review is due within "
            f"expedite.review_hours\n"
            f"\U0001F465 Mode: agent-drives · Governance: {governance}\n\n"
            f"## Steps\n| # | Kind | Files | Behavior |\n|---|---|---|---|\n{table}\n\n"
            f"## Tests first\n- Scenarios: the incident, and the edge it exposed\n"
            f"- What could still slip through: anything the incident did not cover\n\n"
            f"## Dependencies\n\n## Waivers\n")


# -- lessons (SPEC 10.5) -------------------------------------------------------------------------

def lesson_propose(session, text, domain, state=None):
    if not (text or "").strip():
        raise UsageError('pair lesson propose needs the lesson: pair lesson propose "<text>" '
                         '--domain <domain>')
    if not re.match(r"^[a-z0-9-]+$", domain or ""):
        raise UsageError("--domain must be lowercase letters, digits and dashes")
    state = state or session.state()
    entry = state.add_lesson(domain, text.strip())
    me = session.me or state.owner
    state.add_event("lesson-propose", me, note=f"{domain}: {text.strip()}")
    log.action_entry(session.layout.log(state.task), "lesson-propose", me,
                     detail=f"{domain} #{entry['n']}", body=text.strip())
    state.save()
    sha, warnings = session.commit_task(state, "lesson-propose",
                                        f"chore(pair): propose lesson {entry['n']} for "
                                        f"{state.task}")
    return Outcome([f"lesson {entry['n']} proposed in {domain}: {text.strip()}",
                    f"the engineer accepts it with `pair lesson accept {entry['n']}`"],
                   {"lesson": entry["n"], "commit": sha}, warnings)


def lesson_decide(session, action, number, new_text=None, state=None):
    """`accept`, `edit` or `reject` one proposed lesson (human)."""
    if action not in ("accept", "edit", "reject"):
        raise UsageError(f"{action!r} is not accept, edit or reject")
    state = state or session.state()
    session.require_owner(state, f"lesson {action}")
    session.require_human(f"lesson-{action}", subject=state.task)
    entry = state.lesson(number)
    if entry is None:
        raise CheckFailed(f"{state.task} has no lesson {number} — `pair status` lists them")

    me = state.owner
    touched = []
    if action == "reject":
        entry["status"] = "rejected"
        lines = [f"lesson {number} rejected"]
    else:
        text = entry["text"]
        if action == "edit":
            if new_text is None:
                from pair import tty
                if not tty.available():
                    raise Refused(tty.NO_TERMINAL)
                with open("/dev/tty", "r+") as channel:
                    channel.write(f"Current: {text}\nNew text: ")
                    channel.flush()
                    new_text = channel.readline().strip()
            if not new_text:
                raise UsageError("an edited lesson needs text")
            text = new_text
            entry["text"] = text
        domain = lessons_mod.domain(session.layout, entry["domain"])
        existing = domain.with_text(text)
        if existing is not None:
            domain.confirm(existing.id, state.task)
            entry["lesson_id"] = existing.id
            lines = [f"lesson {number} matches {existing.id}; confirmed instead of duplicated"]
        else:
            lesson_id = (f"{entry['domain']}#{state.task}."
                         f"{domain.next_number(state.task)}")
            domain.add(lesson_id, text, f"step {state.current_step}", me)
            entry["lesson_id"] = lesson_id
            lines = [f"lesson {number} accepted as {lesson_id}"]
        domain.save()
        touched.append(session.rel(domain.path))
        entry["status"] = "edited" if action == "edit" else "accepted"

    state.add_event(f"lesson-{action}", me, note=f"lesson {number}")
    log.action_entry(session.layout.log(state.task), f"lesson-{action}", me,
                     detail=f"#{number}")
    state.save()
    sha, warnings = session.commit_task(state, f"lesson-{action}",
                                        f"docs(pair): lesson {number} {entry['status']}",
                                        extra_paths=touched)
    return Outcome(lines, {"lesson": number, "status": entry["status"], "commit": sha}, warnings)


def lesson_dispute(session, lesson_id, state=None):
    state = state or session.state()
    session.require_human("lesson-dispute", subject=state.task)
    found = lessons_mod.LESSON_ID.match(lesson_id or "")
    if not found:
        raise UsageError(f"{lesson_id!r} is not a lesson id (like billing#142-instalments.1)")
    domain = lessons_mod.domain(session.layout, found.group("domain"))
    if not domain.dispute(lesson_id):
        raise CheckFailed(f"{lesson_id} is not in pair/learnings/{found.group('domain')}.md, "
                          f"or is already disputed")
    domain.save()
    me = session.config.require_me()
    state.add_event("lesson-dispute", me, note=lesson_id)
    log.action_entry(session.layout.log(state.task), "lesson-dispute", me, detail=lesson_id)
    state.save()
    sha, warnings = session.commit_task(state, "lesson-dispute",
                                        f"docs(pair): dispute {lesson_id}",
                                        extra_paths=[session.rel(domain.path)])
    return Outcome([f"{lesson_id} marked disputed"], {"lesson_id": lesson_id, "commit": sha},
                   warnings)


# -- waivers (SPEC 10.6) -------------------------------------------------------------------------

def waive(session, rule_id, reason, scope_globs, expires, task_id=None):
    session.require_human("waive", subject=rule_id)
    me = session.config.require_me()
    rule = session.registry.by_id(rule_id)
    if rule is None:
        raise CheckFailed(f"{rule_id} is not a known rule — `pair find --rule {rule_id}` shows "
                          f"what is")
    if rule.tier == 0:
        raise Refused(f"{rule_id} is Tier 0 and cannot be waived. The route for a Tier 0 exception "
                      f"is an ADR in pair/rules/decisions/, or `pair expedite` for an incident.")
    if not (reason or "").strip():
        raise UsageError('pair waive needs --reason "<why>"')
    if not scope_globs:
        raise UsageError('pair waive needs --scope "<glob>"')
    if not clock.parse_date(expires or ""):
        raise UsageError("--expires must be a date like 2026-12-31")

    store = waivers_mod.Waivers.load(session.layout.waivers)
    already = store.history_count(session.root, rule_id)
    if already >= session.config.max_repeats:
        raise Refused(
            f"{rule_id} has been waived {already} time(s), and waivers.max_repeats is "
            f"{session.config.max_repeats}. The count comes from the file's history, so deleting a "
            f"waiver does not reset it. Fix the cause, or raise the rule with an ADR.")
    entry = {"rule": rule_id, "reason": reason.strip(), "scope": list(scope_globs),
             "granted_by": me, "granted_at": clock.today(), "expires": expires}
    if task_id:
        entry["task"] = task_id
    store.add(entry)

    paths_to_commit = [session.rel(session.layout.waivers)]
    state = None
    if task_id or session.active_id():
        try:
            state = session.state(task_id)
        except CheckFailed:
            state = None
    if state is not None:
        state.add_event("waive", me, note=f"{rule_id} until {expires}")
        log.action_entry(session.layout.log(state.task), "waive", me,
                         detail=f"{rule_id} until {expires}", body=reason.strip())
        state.save()
        sha, warnings = session.commit_task(state, "waive", f"chore(pair): waive {rule_id}",
                                            extra_paths=paths_to_commit)
    else:
        sha, warnings = commit.action_commit(session.root, paths_to_commit, "waive",
                                            session.config.governance,
                                            f"chore(pair): waive {rule_id}")
    return Outcome([f"{rule_id} waived until {expires} for {', '.join(scope_globs)}",
                    f"that is waiver {already + 1} of {session.config.max_repeats} for this rule"],
                   {"rule": rule_id, "commit": sha}, warnings)


def waive_remove(session, number):
    session.require_human("waive", subject="remove")
    store = waivers_mod.Waivers.load(session.layout.waivers)
    dropped = store.remove(number)
    sha, warnings = commit.action_commit(session.root, [session.rel(session.layout.waivers)],
                                        "waive", session.config.governance,
                                        f"chore(pair): remove waiver for {dropped['rule']}")
    return Outcome([f"removed the waiver for {dropped['rule']} (expired {dropped['expires']})",
                    "the repeat count is taken from git history and does not reset"],
                   {"rule": dropped["rule"], "commit": sha}, warnings)


# -- baselines (SPEC 15) -------------------------------------------------------------------------

def baseline(session, scope_name=None, lower=False, reason=None):
    session.require_human("baseline")
    me = session.config.require_me()
    if lower and not (reason or "").strip():
        raise UsageError('--lower needs --reason "<why>"')
    wanted = [session.scopes.by_name(scope_name)] if scope_name else list(session.scopes)
    if scope_name and wanted[0] is None:
        raise CheckFailed(f"there is no scope {scope_name!r}")
    baselines = session.baselines()
    lines = []
    changed = False
    for scope in wanted:
        if not scope.has("coverage"):
            lines.append(f"{scope.name}: no coverage command, skipped")
            continue
        env, xml_path = evidence.coverage_env(session.layout, scope)
        outcome = evidence.run(scope, "coverage", session.layout, extra_env=env)
        if not outcome.passed:
            lines.append(f"{scope.name}: coverage command failed ({outcome.code}), skipped")
            continue
        report = coverage_mod.Report.load(xml_path)
        if lower:
            baselines.lower(scope.name, report.line_rate, report.branch_rate, me, reason.strip())
            lines.append(f"{scope.name}: lowered to {report.line_rate}%/{report.branch_rate}% "
                         f"— {reason.strip()}")
            changed = True
        elif baselines.set_measured(scope.name, report.line_rate, report.branch_rate):
            entry = baselines.entry(scope.name)
            lines.append(f"{scope.name}: {entry['line']}%/{entry['branch']}%")
            changed = True
        else:
            entry = baselines.entry(scope.name)
            lines.append(f"{scope.name}: unchanged ({entry['line']}%/{entry['branch']}%)")
    if not changed:
        return Outcome(lines + ["nothing to commit"], {"changed": False})
    baselines.save()
    action = "baseline-lower" if lower else "baseline"
    subject_line = (f"chore(pair): lower coverage baseline — {reason.strip()}" if lower
                    else "chore(pair): raise coverage baselines")
    sha, warnings = commit.action_commit(session.root, [session.rel(session.layout.baseline)],
                                        action, session.config.governance, subject_line)
    return Outcome(lines, {"changed": True, "commit": sha}, warnings)


# -- export (SPEC 14.7) --------------------------------------------------------------------------

def export_walkthrough(session, task_id=None):
    state = session.state(task_id)
    path = session.layout.walkthrough(state.task)
    if not path.is_file():
        raise CheckFailed(f"{state.task} has no walkthrough yet")
    commits = gitcmd.find_commits(session.root, f"Pair-Task: {state.task}", "Pair-Action: ok")
    front = ["---", "source: pair", f"task: {state.task}", f"date: {clock.today()}",
             f"repo: {session.config.project_name}",
             "commits: " + ", ".join(sha[:8] for sha in commits), "---", ""]
    out = session.layout.outbox / f"{state.task}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(front) + path.read_text(encoding="utf-8"), encoding="utf-8")
    return Outcome([f"wrote {session.rel(out)}",
                    "ingest it with your wiki's own tooling — pair never writes to a source"],
                   {"path": session.rel(out)})
