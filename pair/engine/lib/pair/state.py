"""`state.json`: read, validate, write. The only module that writes it (SPEC 3.1, 7.2).

Commit SHAs are never stored; a step's commit is found by its trailers (SPEC 7.2).
"""

import json

from pair import clock, schema
from pair.errors import CheckFailed
from pair.schema import Bool, Int, ListOf, Null, Num, OneOf, Str, Table

FORMAT = 1
SUPPORTED_FORMAT = 1

STATUSES = ("active", "paused", "expedite", "closed", "abandoned")
PHASES = ("planning", "stepping", "review", "closing", "done")
MODES = ("agent-drives", "engineer-drives", "solo")
STEP_STATUSES = ("pending", "submitted", "ok")
RESULTS = ("red", "green")
KINDS = ("stub", "test", "char", "code", "refactor", "doc", "config", "migration")
LESSON_STATUSES = ("proposed", "accepted", "edited", "rejected", "disputed")

TASK_ID = r"^[a-z0-9][a-z0-9-]{1,39}$"
HANDLE = r"^@[\w.-]+$"

_HANDLE = Str(pattern=HANDLE, describe="start with @, like @ana")
_PATHS = ListOf(Str(allow_empty=False))

EVIDENCE = Table({
    "result": Str(choices=RESULTS),
    "summary": Str(),
    "at": Str(),
    "tests": Str(),
    "note": Str(),
    "changed_lines_covered": Num(minimum=0, maximum=100),
    "scope_line": Num(minimum=0, maximum=100),
    "scope_branch": Num(minimum=0, maximum=100),
    "floor_line": Num(minimum=0, maximum=100),
    "floor_branch": Num(minimum=0, maximum=100),
    "committed_files": _PATHS,
    "files_sha256": Table(values=Str(allow_empty=False)),
}, required=("result",))

STEP = Table({
    "n": Int(minimum=1),
    "kind": Str(choices=KINDS),
    "files": _PATHS,
    "behavior": Str(),
    "status": Str(choices=STEP_STATUSES),
    "approved_plan_sha256": Str(),
    "evidence": OneOf(Null(), EVIDENCE),
}, required=("n", "kind", "files", "behavior", "status"))

BATCH = Table({
    "step": Int(minimum=1),
    "paths": _PATHS,
    "max_files": Int(minimum=1),
    "include_tests": Bool(),
    "by": _HANDLE,
    "at": Str(),
}, required=("step", "paths", "max_files", "by", "at"))

STATE = Table({
    "format": Int(minimum=1),
    "task": Str(pattern=TASK_ID, describe="be lowercase letters, digits and dashes"),
    "owner": _HANDLE,
    "branch": Str(),
    "mode": Str(choices=MODES),
    "status": Str(choices=STATUSES),
    "phase": Str(choices=PHASES),
    "governance": Str(),
    "created_at": Str(),
    "approval": OneOf(Null(), Table({"by": _HANDLE, "at": Str(), "plan_sha256": Str()},
                                    required=("by", "at", "plan_sha256"))),
    "batches": ListOf(BATCH),
    "expedite": OneOf(Null(), Table({
        "by": _HANDLE, "at": Str(), "reason": Str(allow_empty=False),
        "test_paths": _PATHS, "paths": _PATHS, "review_due": Str(),
    }, required=("by", "at", "reason", "test_paths", "paths"))),
    "current_step": Int(minimum=0),
    "steps": ListOf(STEP),
    "lessons": ListOf(Table({
        "n": Int(minimum=1), "domain": Str(allow_empty=False), "text": Str(allow_empty=False),
        "status": Str(choices=LESSON_STATUSES), "lesson_id": Str(),
    }, required=("n", "domain", "text", "status"))),
    "lessons_used": ListOf(Str(allow_empty=False)),
    "events": ListOf(Table({"at": Str(), "by": _HANDLE, "action": Str(allow_empty=False),
                            "note": Str()}, required=("at", "by", "action"))),
}, required=("format", "task", "owner", "branch", "mode", "status", "phase", "governance",
             "created_at", "current_step", "steps"))


class Step:
    """A view on one entry of `state.steps`. Writes go through the parent state."""

    def __init__(self, data):
        self.data = data

    n = property(lambda self: self.data["n"])
    kind = property(lambda self: self.data["kind"])
    behavior = property(lambda self: self.data.get("behavior", ""))

    @property
    def files(self):
        return list(self.data.get("files") or [])

    @property
    def status(self):
        return self.data.get("status", "pending")

    @status.setter
    def status(self, value):
        self.data["status"] = value

    @property
    def evidence(self):
        return self.data.get("evidence")

    @evidence.setter
    def evidence(self, value):
        if value is None:
            self.data.pop("evidence", None)
        else:
            self.data["evidence"] = value

    @property
    def approved_plan_sha256(self):
        return self.data.get("approved_plan_sha256")

    @property
    def is_ok(self):
        return self.status == "ok"

    def __repr__(self):
        return f"Step({self.n}, {self.kind}, {self.status})"


class State:
    def __init__(self, layout, data):
        self.layout = layout
        self.data = data

    # -- loading and saving ----------------------------------------------------------------
    @classmethod
    def load(cls, layout, task_id):
        path = layout.state(task_id)
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError) as problem:
            raise CheckFailed(
                f"no task {task_id}: pair/tasks/{task_id}/state.json does not exist on this branch"
            ) from problem
        return cls.loads(layout, text, f"pair/tasks/{task_id}/state.json")

    @classmethod
    def loads(cls, layout, text, what="state.json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as problem:
            raise CheckFailed(f"{what} does not parse: {problem}") from problem
        problems = schema.errors(data, STATE)
        if problems:
            raise CheckFailed(f"{what} is invalid", problems)
        if data["format"] > SUPPORTED_FORMAT:
            raise CheckFailed(
                f"{what} is format {data['format']}, but this engine supports {SUPPORTED_FORMAT}: "
                f"upgrade the engine (pair upgrade)."
            )
        return cls(layout, data)

    @classmethod
    def create(cls, layout, task_id, owner, branch, mode, governance, status="active",
               phase="planning"):
        return cls(layout, {
            "format": FORMAT,
            "task": task_id,
            "owner": owner,
            "branch": branch,
            "mode": mode,
            "status": status,
            "phase": phase,
            "governance": governance,
            "created_at": clock.stamp(),
            "approval": None,
            "batches": [],
            "expedite": None,
            "current_step": 0,
            "steps": [],
            "lessons": [],
            "lessons_used": [],
            "events": [],
        })

    def dumps(self):
        return json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"

    def save(self):
        problems = schema.errors(self.data, STATE)
        if problems:                                      # never write a state pair can't read back
            raise CheckFailed("refusing to write an invalid state.json", problems)
        path = self.layout.state(self.task)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(), encoding="utf-8")
        return path

    # -- fields ----------------------------------------------------------------------------
    task = property(lambda self: self.data["task"])
    owner = property(lambda self: self.data["owner"])
    branch = property(lambda self: self.data["branch"])
    governance = property(lambda self: self.data["governance"])
    created_at = property(lambda self: self.data["created_at"])

    @property
    def mode(self):
        return self.data["mode"]

    @mode.setter
    def mode(self, value):
        self.data["mode"] = value

    @property
    def status(self):
        return self.data["status"]

    @status.setter
    def status(self, value):
        self.data["status"] = value

    @property
    def phase(self):
        return self.data["phase"]

    @phase.setter
    def phase(self, value):
        self.data["phase"] = value

    @property
    def approval(self):
        return self.data.get("approval")

    @property
    def expedite(self):
        return self.data.get("expedite")

    @property
    def current_step(self):
        return self.data["current_step"]

    @current_step.setter
    def current_step(self, value):
        self.data["current_step"] = value

    @property
    def is_open(self):
        """An active or expedite task: the only states the hook lets an agent write in (F4)."""
        return self.status in ("active", "expedite")

    # -- steps -----------------------------------------------------------------------------
    @property
    def steps(self):
        return [Step(entry) for entry in self.data["steps"]]

    def step(self, n):
        for step in self.steps:
            if step.n == n:
                return step
        return None

    @property
    def current(self):
        return self.step(self.current_step)

    @property
    def total_steps(self):
        return len(self.data["steps"])

    def next_pending(self, after=0):
        for step in sorted(self.steps, key=lambda s: s.n):
            if step.n > after and step.status != "ok":
                return step
        return None

    def first_unfinished(self):
        for step in sorted(self.steps, key=lambda s: s.n):
            if step.status != "ok":
                return step
        return None

    def set_steps(self, rows):
        """Snapshot plan rows into state, keeping every `ok` step untouched (SPEC 7.5)."""
        kept = {step.n: step.data for step in self.steps if step.is_ok}
        out = []
        for row in rows:
            if row["n"] in kept:
                out.append(kept[row["n"]])
                continue
            out.append({"n": row["n"], "kind": row["kind"], "files": list(row["files"]),
                        "behavior": row.get("behavior", ""), "status": "pending"})
        self.data["steps"] = sorted(out, key=lambda entry: entry["n"])

    # -- grants ----------------------------------------------------------------------------
    @property
    def batches(self):
        return list(self.data.get("batches") or [])

    def batch_for(self, n):
        for grant in self.batches:
            if grant["step"] == n:
                return grant
        return None

    def add_batch(self, n, paths, max_files, include_tests, by):
        self.data.setdefault("batches", [])
        self.data["batches"] = [g for g in self.batches if g["step"] != n]
        self.data["batches"].append({"step": n, "paths": list(paths), "max_files": max_files,
                                     "include_tests": bool(include_tests), "by": by,
                                     "at": clock.stamp()})
        self.data["batches"].sort(key=lambda grant: grant["step"])

    # -- lessons and events ----------------------------------------------------------------
    @property
    def lessons(self):
        return list(self.data.get("lessons") or [])

    def add_lesson(self, domain, text):
        self.data.setdefault("lessons", [])
        n = max([entry["n"] for entry in self.lessons], default=0) + 1
        entry = {"n": n, "domain": domain, "text": text, "status": "proposed"}
        self.data["lessons"].append(entry)
        return entry

    def lesson(self, n):
        for entry in self.lessons:
            if entry["n"] == n:
                return entry
        return None

    @property
    def lessons_used(self):
        return list(self.data.get("lessons_used") or [])

    @lessons_used.setter
    def lessons_used(self, value):
        self.data["lessons_used"] = list(value)

    @property
    def events(self):
        return list(self.data.get("events") or [])

    def add_event(self, action, by, note=None):
        self.data.setdefault("events", [])
        entry = {"at": clock.stamp(), "by": by, "action": action}
        if note:
            entry["note"] = note
        self.data["events"].append(entry)
        return entry

    # -- approval --------------------------------------------------------------------------
    def record_approval(self, by, plan_sha256):
        self.data["approval"] = {"by": by, "at": clock.stamp(), "plan_sha256": plan_sha256}
        for step in self.steps:
            if not step.is_ok:
                step.data["approved_plan_sha256"] = plan_sha256

    def clear_approval(self):
        self.data["approval"] = None
        for step in self.steps:
            if not step.is_ok:
                step.evidence = None
                step.status = "pending"

    def __repr__(self):
        return f"State({self.task}, {self.phase}, {self.status})"


def find_tasks(layout):
    """Every task id with a state file on this branch, oldest id first."""
    if not layout.tasks_dir.is_dir():
        return []
    return sorted(p.name for p in layout.tasks_dir.iterdir() if (p / "state.json").is_file())
