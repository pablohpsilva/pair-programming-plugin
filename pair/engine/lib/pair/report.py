"""`pair report` (SPEC 20): metrics from `tasks/*/state.json` and `log.md`."""

import statistics

from pair import clock, coverage as coverage_mod, lessons as lessons_mod, log as log_mod, state as state_mod, waivers as waivers_mod

DEFAULT_DAYS = 30
ZERO_REWORK_STEPS = 5


class Report:
    def __init__(self, since, data, lines):
        self.since = since
        self.data = data
        self.lines = lines

    def render(self):
        return "\n".join(self.lines)


def build(session, since=None):
    layout = session.layout
    since_date = since or _default_since()
    tasks = []
    for task_id in state_mod.find_tasks(layout):
        try:
            state = state_mod.State.load(layout, task_id)
        except Exception:
            continue
        if not _in_window(state, since_date):
            continue
        tasks.append(state)

    entries = {state.task: _entries(layout, state.task) for state in tasks}
    counts = {"closed": 0, "abandoned": 0, "expedite": 0, "active": 0, "paused": 0}
    for state in tasks:
        counts[state.status] = counts.get(state.status, 0) + 1

    waits = []
    reworks = explains = reopens = oks = 0
    zero_rework = []
    for state in tasks:
        own = entries[state.task]
        waits += _validation_waits(own)
        own_reworks = sum(1 for entry in own if entry.action == "rework")
        own_oks = sum(1 for entry in own if entry.action == "ok")
        reworks += own_reworks
        oks += own_oks
        explains += sum(1 for entry in own
                        if entry.action == "note" or "note: explain" in entry.heading)
        reopens += sum(1 for entry in own if entry.action == "reopen")
        if state.total_steps >= ZERO_REWORK_STEPS and own_reworks == 0:
            zero_rework.append(state.task)

    store = waivers_mod.Waivers.load(layout.waivers)
    per_rule = {}
    for waiver in store.waivers:
        per_rule[waiver.rule] = per_rule.get(waiver.rule, 0) + 1

    lesson_counts = {"proposed": 0, "accepted": 0, "rejected": 0, "disputed": 0}
    for state in tasks:
        for lesson in state.lessons:
            lesson_counts[lesson["status"]] = lesson_counts.get(lesson["status"], 0) + 1
    candidates = lessons_mod.promotion_candidates(layout, session.config.promote_after)

    baselines = coverage_mod.Baselines.load(layout.baseline)
    per_scope = []
    for scope in session.scopes:
        entry = baselines.entry(scope.name)
        per_scope.append({"scope": scope.name, "baseline": entry, "target": scope.target,
                          "last": _last_measured(tasks, scope.name)})

    overdue = [state.task for state in tasks if _overdue(state)]

    data = {
        "since": since_date,
        "tasks": counts,
        "median_validation_wait_minutes": round(statistics.median(waits), 1) if waits else None,
        "rework_rate": round(reworks / oks, 3) if oks else None,
        "explain_requests": explains,
        "plan_reopenings": round(reopens / len(tasks), 3) if tasks else None,
        "waivers": {"active": len(store.active()), "expired": len(store.expired()),
                    "per_rule": per_rule},
        "lessons": dict(lesson_counts, promotion_candidates=[c.id for c in candidates]),
        "coverage": per_scope,
        "overdue_expedites": len(overdue),
        "zero_rework_tasks": zero_rework,
    }
    return Report(since_date, data, _render(data))


def _render(data):
    lines = [f"pair report · since {data['since']}", ""]
    counts = data["tasks"]
    lines.append("Tasks: " + ", ".join(f"{name} {number}" for name, number in sorted(counts.items())
                                       if number))
    wait = data["median_validation_wait_minutes"]
    lines.append(f"Median validation wait: {wait if wait is not None else 'n/a'} min")
    lines.append(f"Rework rate: {data['rework_rate'] if data['rework_rate'] is not None else 'n/a'}")
    lines.append(f"Explain requests: {data['explain_requests']}")
    lines.append(f"Plan reopenings per task: "
                 f"{data['plan_reopenings'] if data['plan_reopenings'] is not None else 'n/a'}")
    waivers = data["waivers"]
    lines.append(f"Waivers: {waivers['active']} active, {waivers['expired']} expired"
                 + (" · " + ", ".join(f"{rule} ×{count}"
                                           for rule, count in sorted(waivers["per_rule"].items()))
                    if waivers["per_rule"] else ""))
    lessons = data["lessons"]
    lines.append(f"Lessons: " + ", ".join(f"{name} {lessons.get(name, 0)}"
                                          for name in ("proposed", "accepted", "rejected",
                                                       "disputed")))
    if lessons["promotion_candidates"]:
        lines.append("  promotion candidates: " + ", ".join(lessons["promotion_candidates"]))
    lines.append("Coverage:")
    for entry in data["coverage"]:
        baseline = entry["baseline"]
        shown = f"{baseline['line']}%/{baseline['branch']}%" if baseline else "no baseline"
        lines.append(f"  {entry['scope']}: last {entry['last'] or 'n/a'} · baseline {shown} "
                     f"· target {entry['target']}")
    lines.append(f"Overdue expedites: {data['overdue_expedites']}")
    if data["zero_rework_tasks"]:
        lines.append("Zero-rework flag (≥ 5 steps, no rework): "
                     + ", ".join(data["zero_rework_tasks"]))
    lines.append("")
    lines.append("## Audit notes")
    lines.append("")
    return lines


def _default_since():
    import datetime
    return (clock.now() - datetime.timedelta(days=DEFAULT_DAYS)).strftime("%Y-%m-%d")


def _in_window(state, since_date):
    created = clock.parse(state.created_at)
    boundary = clock.parse_date(since_date)
    if created is None or boundary is None:
        return True
    if created >= boundary:
        return True
    return state.is_open or state.status == "paused"


def _entries(layout, task_id):
    path = layout.log(task_id)
    if not path.is_file():
        return []
    return log_mod.entries(path.read_text(encoding="utf-8"))


def _validation_waits(entries):
    """Minutes from each `done` entry to the `ok` entry for the same step."""
    waits = []
    pending = {}
    for entry in entries:
        when = clock.parse(entry.at) or clock.parse(entry.at + ":00Z")
        if when is None:
            continue
        if entry.action == "done":
            pending[entry.step] = when
        elif entry.action == "ok" and entry.step in pending:
            waits.append((when - pending.pop(entry.step)).total_seconds() / 60.0)
    return waits


def _last_measured(tasks, scope_name):
    best = None
    for state in tasks:
        for step in state.steps:
            record = step.evidence or {}
            if record.get("scope_line") is not None:
                best = record["scope_line"]
    return best


def _overdue(state):
    record = state.expedite
    if not record or not record.get("review_due"):
        return False
    due = clock.parse(record["review_due"])
    return bool(due and clock.now() > due)


def write(session, report):
    """`--write` saves `pair/reports/YYYY-MM.md` with an empty Audit notes section (SPEC 20)."""
    path = session.layout.reports / f"{clock.today()[:7]}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# pair report\n\n" + report.render().rstrip() + "\n", encoding="utf-8")
    return path
