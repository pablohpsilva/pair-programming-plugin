"""`pair doctor` (SPEC 11.2): every consistency check, and the install advice (SPEC 4)."""

import os
import pathlib

from pair import (clock, files, flow, gitcmd, globs, lessons as lessons_mod,
                  sources as sources_mod, state as state_mod, waivers as waivers_mod)
from pair.errors import CheckFailed

HOOKS_PATH = "githooks"
CLOUD_FALLBACK = ("claude plugin marketplace add ./pair --scope local",
                  "claude plugin install pair@pair-local")


class Note:
    def __init__(self, level, message, fix=None):
        self.level = level                 # "error" | "warning" | "info"
        self.message = message
        self.fix = fix

    def render(self):
        mark = {"error": "✗", "warning": "!", "info": "·"}[self.level]
        text = f"{mark} {self.message}"
        return text + (f"\n    {self.fix}" if self.fix else "")

    def as_data(self):
        return {"level": self.level, "message": self.message, "fix": self.fix}


def error(message, fix=None):
    return Note("error", message, fix)


def warn(message, fix=None):
    return Note("warning", message, fix)


def info(message, fix=None):
    return Note("info", message, fix)


def run(session):
    """Every note, errors first. `pair doctor` exits 1 when any error is present."""
    notes = []
    notes += _config(session)
    notes += _rules(session)
    notes += _scopes(session)
    notes += _sources(session)
    notes += _lessons(session)
    notes += _waivers(session)
    notes += _tasks(session)
    notes += _summaries(session)
    notes += _session_start(session)
    notes += _install(session)
    order = {"error": 0, "warning": 1, "info": 2}
    return sorted(notes, key=lambda note: order[note.level])


def _config(session):
    # Loading the session already validated the config and the floors; say so, so a clean run is
    # informative rather than silent.
    return [info(f"config format {session.config.format}, engine {session.config.engine_version}, "
                 f"governance {session.config.governance}")]


def _rules(session):
    return [error(problem) for problem in session.registry.problems()]


def _scopes(session):
    notes = []
    if not len(session.scopes):
        return [error("no scopes are declared", "run `pair init` to create pair/scopes/")]
    if session.scopes.fallback is None:
        notes.append(error("there is no `_repo` fallback scope",
                           "create pair/scopes/_repo/scope.toml with path = \"\""))
    for scope in session.scopes:
        if scope.has("migrate_check"):
            continue
        holding = _migration_files(session, scope)
        if holding:
            notes.append(error(
                f"scope {scope.name} holds migration files ({', '.join(holding[:3])}) but its "
                f"`migrate_check` is empty, so they cannot change through pair",
                f"add a migrate_check command to pair/scopes/{scope.name}/scope.toml"))
    return notes


def _migration_files(session, scope):
    base = session.root / scope.path if scope.path else session.root
    if not base.is_dir():
        return []
    found = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = globs.normalise(path.relative_to(session.root))
        if rel.startswith("pair/") or rel.startswith(".git/"):
            continue
        if files.classify(rel, session.config) == "migrations" and \
                session.scopes.resolve(rel) is scope:
            found.append(rel)
    return found


def _sources(session):
    notes = []
    resolved = sources_mod.resolve_all(session.layout, session.config)
    for each in resolved:
        if each.empty:
            notes.append(warn(
                f"source {each.type} {each.path!r} matches no files",
                f"include/exclude are relative to the source's base ({each.base}), not to the "
                f"repository root. An empty source indexes nothing while looking healthy "
                f"(SPEC 14.2)"))
        else:
            notes.append(info(f"source {each.type} {each.path!r}: {len(each.files)} files"))
    stale = _stale_sources(session, resolved)
    if stale:
        notes.append(warn(f"{len(stale)} source file(s) older than "
                          f"{session.config.stale_days} days",
                          ", ".join(stale[:5])))
    return notes


def _stale_sources(session, resolved):
    found = []
    today = clock.parse_date(clock.today())
    for each in resolved:
        for path, display in each.files:
            when = gitcmd.last_commit_date(session.root, display) if \
                _inside(path, session.root) else None
            moment = clock.parse_date(when) if when else None
            if moment is None:
                continue
            if today and (today - moment).days > session.config.stale_days:
                found.append(display)
    return found


def _inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lessons(session):
    notes = []
    stale = lessons_mod.unused_since(session.layout, session.config.review_unused_days)
    if stale:
        notes.append(warn(f"{len(stale)} lesson(s) unused for more than "
                          f"{session.config.review_unused_days} days",
                          ", ".join(lesson.id for lesson in stale[:5])))
    candidates = lessons_mod.promotion_candidates(session.layout, session.config.promote_after)
    if candidates:
        notes.append(info(f"{len(candidates)} lesson(s) with at least "
                          f"{session.config.promote_after} confirmations: "
                          + ", ".join(lesson.id for lesson in candidates[:5])))
    return notes


def _waivers(session):
    store = waivers_mod.Waivers.load(session.layout.waivers)
    return [error(f"waiver {waiver.rule} expired on {waiver.expires}",
                  "remove it with `pair waive --remove <n>`")
            for waiver in store.expired()]


def _tasks(session):
    notes = []
    for task_id in state_mod.find_tasks(session.layout):
        try:
            state = state_mod.State.load(session.layout, task_id)
        except CheckFailed as problem:
            notes.append(error(f"{task_id}: {problem.message}"))
            continue
        if state.is_open and state.governance != session.config.governance:
            notes.append(warn(f"{task_id} runs on governance {state.governance}, the repo is on "
                              f"{session.config.governance}",
                              "that is allowed mid-task; it is recorded in every commit"))
        if state.expedite and state.expedite.get("review_due"):
            due = clock.parse(state.expedite["review_due"])
            if due and clock.now() > due:
                notes.append(error(f"{task_id} is an expedite past its review deadline "
                                   f"({state.expedite['review_due']})",
                                   "review it, or close the task"))
    active = session.layout.active_task()
    if active and not session.layout.state(active).is_file():
        notes.append(warn(f"local/active names {active}, which is not on this branch",
                          f"run `pair resume {active}` on its branch, or `pair start <id>`"))
    return notes


def _summaries(session):
    """A SUMMARY.md last committed before the newest code change in its scope is stale (11.2)."""
    notes = []
    for scope in session.scopes:
        summary = scope.summary_md
        if not summary.is_file():
            continue
        rel = globs.normalise(summary.relative_to(session.root))
        summary_date = gitcmd.last_commit_date(session.root, rel)
        if not summary_date:
            continue
        newest = None
        base = session.root / scope.path if scope.path else session.root
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            candidate = globs.normalise(path.relative_to(session.root))
            if candidate.startswith("pair/") or files.classify(candidate, session.config) != "code":
                continue
            when = gitcmd.last_commit_date(session.root, candidate)
            if when and (newest is None or when > newest):
                newest = when
        if newest and newest > summary_date:
            notes.append(warn(f"{rel} was last updated {summary_date}, but code in "
                              f"{scope.name} changed on {newest}",
                              "plan a `doc` step to refresh it"))
    return notes


def _session_start(session):
    """SPEC 12.3: the assembled payload must stay under 1 800 bytes, with headroom."""
    state = None
    active = session.layout.active_task()
    if active and session.layout.state(active).is_file():
        try:
            state = state_mod.State.load(session.layout, active)
        except CheckFailed:
            state = None
    text = flow.session_start_payload(state)
    size = len(text.encode("utf-8"))
    notes = []
    if size > flow.DOCTOR_LIMIT:
        notes.append(error(f"the SessionStart injection is {size} bytes, over the "
                           f"{flow.DOCTOR_LIMIT}-byte limit",
                           "shorten it: only the first ~2 KB reaches the model (SPEC 12.3)"))
    first = text.splitlines()[0] if text else ""
    if not first.startswith("pair @ ") or "supersedes any earlier pair: block" not in first:
        notes.append(error("the SessionStart first line is missing its timestamp or its "
                           "supersedes clause",
                           "injections accumulate, so each block must say it replaces the last "
                           "(SPEC 12.3)"))
    else:
        notes.append(info(f"SessionStart injection {size} bytes of {flow.DOCTOR_LIMIT}"))
    return notes


def _install(session):
    """The activation costs of SPEC 4, and nothing outside the repository is touched (D15)."""
    notes = []
    configured = gitcmd.config_get(session.root, "core.hooksPath")
    hook_file = session.root / HOOKS_PATH / "commit-msg"
    if configured == HOOKS_PATH:
        notes.append(info(f"core.hooksPath is {HOOKS_PATH} · commit-msg "
                          f"{'present' if hook_file.is_file() else 'MISSING'}"))
    elif configured:
        notes.append(warn(f"core.hooksPath is {configured!r}, not {HOOKS_PATH!r}",
                          f"git takes one hooks directory. Chain pair's check into "
                          f"{configured}/commit-msg rather than overwriting it."))
    else:
        notes.append(error("core.hooksPath is unset, so githooks/commit-msg is inert in this clone",
                           "run: git config core.hooksPath githooks    (repository-local, never "
                           "--global)"))

    settings = session.root / ".claude" / "settings.json"
    if settings.is_file():
        notes.append(info(".claude/settings.json declares the plugin; a colleague who clones needs "
                          "no install step"))
    else:
        notes.append(warn(".claude/settings.json does not declare the plugin",
                          "run `pair init` to add it, or in a cloud session, where the "
                          "workspace-trust dialog never appears: "
                          + " then ".join(f"`{line}`" for line in CLOUD_FALLBACK)))

    cache = pathlib.Path(os.path.expanduser("~/.claude/plugins"))
    notes.append(info(f"host CLI plugin cache {'present' if cache.is_dir() else 'absent'} at "
                      f"~/.claude/plugins — pair never writes there (SPEC 4)"))
    return notes


def worst(notes):
    if any(note.level == "error" for note in notes):
        return "error"
    if any(note.level == "warning" for note in notes):
        return "warning"
    return "ok"
