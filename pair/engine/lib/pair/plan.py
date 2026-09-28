"""`plan.md`: parse it, and check it (SPEC 10.1, 10.1.1).

plan-check is the gate the engineer's approval rests on, so every rule below reports rather than
raises: an engineer fixing a plan wants the whole list, not the first line that broke.
"""

import hashlib
import re

from pair import files, globs, paths
from pair.errors import CheckFailed

HEADERS = (
    ("goal", "\U0001F3AF", "Goal"),
    ("approach", "\U0001F9ED", "Approach"),
    ("explored", "\U0001F50E", "Explored"),
    ("rules", "\U0001F4DA", "Rules & lessons"),
    ("alternatives", "\U0001F500", "Alternatives"),
    ("risks", "⚠️", "Risks"),
    ("people", "\U0001F465", "Mode"),
)
GLOBAL_VIEW_LIMIT = 12
LESSON_REF = re.compile(r"\b[a-z0-9-]+#[a-z0-9-]+\.\d+\b")
BACKTICKED = re.compile(r"`([^`]+)`")
COMMENT = re.compile(r"<!--.*?-->", re.S)
WILDCARD = re.compile(r"[*?\[]")


def strip_comments(text):
    return COMMENT.sub("", text or "")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path):
    try:
        return sha256(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError):
        return None


def glob_prefix(pattern):
    """The literal directory part of a glob — `packages/billing` for `packages/billing/**/*.py`."""
    text = globs.normalise(pattern)
    parts = []
    for part in text.split("/"):
        if WILDCARD.search(part):
            break
        parts.append(part)
    return "/".join(parts)


class Row:
    def __init__(self, n, kind, files_listed, behavior, line):
        self.n = n
        self.kind = kind
        self.files = list(files_listed)
        self.behavior = behavior
        self.line = line

    def as_step(self):
        return {"n": self.n, "kind": self.kind, "files": self.files, "behavior": self.behavior}

    def __repr__(self):
        return f"Row({self.n}, {self.kind}, {self.files})"


class Plan:
    def __init__(self, text):
        self.raw = text
        self.text = strip_comments(text)
        self.title = None
        self.task = None
        self.headers = {}
        self.rows = []
        self.sections = {}
        self.global_view_lines = 0
        self.table_problems = []
        self._parse()

    # -- parsing ---------------------------------------------------------------------------
    def _parse(self):
        lines = self.text.splitlines()
        section = None
        body = []
        before_steps = []
        seen_steps = False
        for line in lines:
            if line.startswith("# ") and self.title is None:
                self.title = line[2:].strip()
                match = re.match(r"Task\s+([a-z0-9][a-z0-9-]*)\s*:\s*(.*)$", self.title)
                if match:
                    self.task = match.group(1)
                before_steps.append(line)
                continue
            if line.startswith("## "):
                if section is not None:
                    self.sections[section] = "\n".join(body).strip()
                section = line[3:].strip()
                body = []
                if section.lower() == "steps":
                    seen_steps = True
                continue
            if not seen_steps:
                before_steps.append(line)
            if section is None:
                self._header_line(line)
            else:
                body.append(line)
        if section is not None:
            self.sections[section] = "\n".join(body).strip()
        self.global_view_lines = len([entry for entry in before_steps if entry.strip()])
        self._parse_steps()

    def _header_line(self, line):
        stripped = line.strip()
        for key, emoji, label in HEADERS:
            if stripped.startswith(emoji):
                rest = stripped[len(emoji):].strip()
                if rest.startswith(label + ":"):
                    rest = rest[len(label) + 1:].strip()
                elif rest.startswith(":"):
                    rest = rest[1:].strip()
                self.headers[key] = rest
                return

    def _parse_steps(self):
        body = self.sections.get("Steps")
        if body is None:
            for name, content in self.sections.items():
                if name.lower() == "steps":
                    body = content
                    break
        if not body:
            return
        for number, line in enumerate(body.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) < 4:
                continue
            if not cells[0].isdigit():
                if cells[0].lower() in ("#", "") or set(cells[0]) <= set("-: "):
                    continue
                self.table_problems.append(
                    f"step row {number}: `#` must be a number, got {cells[0]!r}")
                continue
            listed = BACKTICKED.findall(cells[2])
            if not listed and cells[2]:
                listed = [part.strip() for part in cells[2].split(",") if part.strip()]
            self.rows.append(Row(int(cells[0]), cells[1], listed, cells[3], number))

    @property
    def mode(self):
        """The mode from the 👥 line: `agent-drives · Governance: 0.1`."""
        value = self.headers.get("people", "")
        return value.split("·")[0].strip()

    @property
    def governance(self):
        match = re.search(r"Governance:\s*([\d.]+)", self.headers.get("people", ""))
        return match.group(1) if match else None

    @property
    def lesson_refs(self):
        return sorted(set(LESSON_REF.findall(self.headers.get("rules", ""))))

    def section(self, name):
        for key, value in self.sections.items():
            if key.lower() == name.lower():
                return value
        return None

    def as_steps(self):
        return [row.as_step() for row in sorted(self.rows, key=lambda row: row.n)]


def load(path):
    try:
        return Plan(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, NotADirectoryError) as problem:
        raise CheckFailed(f"{path} does not exist — the plan has not been written yet") from problem


def check(plan, state, config, scope_set, lesson_ids=()):
    """Every problem with `plan`, in SPEC 10.1.1 order. An empty list means plan-check passes."""
    problems = []
    problems += _headers(plan, state)
    problems += plan.table_problems
    problems += _table(plan)
    rows = sorted(plan.rows, key=lambda row: row.n)
    for row in rows:
        problems += _row_files(row, plan, state, config, scope_set)
    problems += _sequence(rows)
    problems += _dependencies(rows, plan, config, scope_set)
    problems += _locked_steps(rows, state)
    problems += _lessons(plan, lesson_ids)
    return problems


def _headers(plan, state):
    problems = []
    if plan.title is None:
        problems.append("the plan needs a `# Task <id>: <title>` heading (10.1)")
    elif state is not None and plan.task and plan.task != state.task:
        problems.append(f"the heading names task {plan.task!r}, but the active task is "
                        f"{state.task!r}")
    for key, emoji, label in HEADERS:
        if key not in plan.headers:
            problems.append(f"the {emoji} {label} line is missing (10.1)")
        elif not plan.headers[key]:
            problems.append(f"the {emoji} {label} line is empty (10.1)")
    if state is not None and plan.mode and plan.mode != state.mode:
        problems.append(f"\U0001F465 Mode says {plan.mode!r}, but the task's mode is "
                        f"{state.mode!r} — run `pair mode {plan.mode}` or fix the plan")
    if plan.global_view_lines > GLOBAL_VIEW_LIMIT:
        problems.append(f"the global view is {plan.global_view_lines} lines; keep it to "
                        f"{GLOBAL_VIEW_LIMIT} or fewer (COMM-001)")
    return problems


def _table(plan):
    problems = []
    if not plan.rows:
        problems.append("the `## Steps` table has no rows (10.1)")
        return problems
    numbers = [row.n for row in plan.rows]
    if len(set(numbers)) != len(numbers):
        problems.append(f"step numbers repeat: {sorted(numbers)}")
    if numbers != sorted(numbers):
        problems.append(f"step numbers must increase: {numbers}")
    for row in plan.rows:
        if row.kind not in files.KINDS:
            problems.append(f"step {row.n}: {row.kind!r} is not a kind "
                            f"({', '.join(files.KINDS)})")
        if not row.behavior:
            problems.append(f"step {row.n}: the Behavior cell is empty")
    return problems


def _row_files(row, plan, state, config, scope_set):
    problems = []
    grant = state.batch_for(row.n) if state is not None else None
    if not row.files:
        problems.append(f"step {row.n}: no file is listed — put the path in backticks (10.1.1/3)")
        return problems
    if grant is None:
        if len(row.files) > 1:
            problems.append(
                f"step {row.n}: lists {len(row.files)} files; one step is one file (PAIR-004) — "
                f"ask the engineer for `pair grant-batch --step {row.n} --paths \"<glob>\" "
                f"--max-files <n>`")
            return problems
    else:
        if sorted(row.files) != sorted(grant["paths"]):
            problems.append(
                f"step {row.n}: has a batch grant, so the Files cell must list its globs "
                f"({', '.join(grant['paths'])})")
    include_tests = bool(grant and grant.get("include_tests"))
    for listed in row.files:
        problems += _one_path(row, listed, config, scope_set, include_tests)
    if row.kind in files.KINDS_NEEDING_COMMANDS:
        scope = _scope_of(row, scope_set)
        if scope is not None:
            needed = files.command_for(row.kind)
            if needed and not scope.has(needed):
                problems.append(
                    f"step {row.n}: scope {scope.name} has no `{needed}` command, which a "
                    f"{row.kind} step needs (8.4) — add it to "
                    f"pair/scopes/{scope.name}/scope.toml")
    scope, trouble = scope_set.resolve_all([glob_prefix(f) or f for f in row.files])
    if trouble and len(row.files) > 1:
        problems.append(f"step {row.n}: {trouble}")
    return problems


def _one_path(row, listed, config, scope_set, include_tests):
    problems = []
    rel = globs.normalise(listed)
    protected = config.protected(glob_prefix(rel) or rel) or config.protected(rel)
    if protected:
        problems.append(f"step {row.n}: `{rel}` is a protected path ({protected}) — "
                        f"agents never edit it (PAIR-006)")
        return problems
    if WILDCARD.search(rel):
        # A glob's class cannot be decided here; the hook checks each real file at write time (F14).
        prefix = glob_prefix(rel)
        if prefix and paths.has_no_scope(prefix):
            problems.append(f"step {row.n}: `{rel}` is under pair/, which belongs to no scope (8.4)")
        return problems
    if scope_set.resolve(rel) is None:
        problems.append(f"step {row.n}: `{rel}` belongs to no scope, so it cannot be a step file "
                        f"(8.4)")
        return problems
    file_class = files.classify(rel, config)
    if not files.is_allowed(row.kind, file_class, include_tests):
        allowed = ", ".join(files.allowed_for(row.kind, include_tests))
        problems.append(f"step {row.n}: `{rel}` is a {file_class} file, but a {row.kind} step "
                        f"writes {allowed} files (8.1)")
    return problems


def _scope_of(row, scope_set):
    for listed in row.files:
        candidate = glob_prefix(listed) or listed
        scope = scope_set.resolve(candidate)
        if scope is not None:
            return scope
    return None


def _sequence(rows):
    """Rules 7, 8 and 8a: red before green, a stub always gets its code step."""
    problems = []
    kinds = [row.kind for row in rows]
    if "code" in kinds:
        first_code = kinds.index("code")
        if "test" not in kinds[:first_code]:
            problems.append("a `test` step must come before the first `code` step (10.1.1/7)")

    for index, row in enumerate(rows):
        if row.kind != "stub":
            continue
        later = [other for other in rows[index + 1:]
                 if other.kind == "code" and _covers(other.files, row.files)]
        if not later:
            problems.append(
                f"step {row.n} is a stub with no later `code` step on {', '.join(row.files)} "
                f"(10.1.1/8)")

    for index, row in enumerate(rows):
        if row.kind != "test":
            continue
        following = [other for other in rows[index + 1:] if other.kind != "doc"]
        if not following:
            problems.append(f"step {row.n} is a `test` step with no `code` step after it — "
                            f"a red test must be cleared (10.1.1/8a)")
        elif following[0].kind != "code":
            problems.append(
                f"step {following[0].n} is a `{following[0].kind}` step, but step {row.n} left a "
                f"test red: the next non-doc step must be `code` (10.1.1/8a)")
    return problems


def _covers(candidate_files, wanted):
    """True when every `wanted` path is listed by, or matched by a glob in, `candidate_files`.

    A batch-granted `code` step lists globs, so a stub's file is covered without being named.
    """
    for target in wanted:
        if target in candidate_files:
            continue
        if any(globs.match(target, pattern) for pattern in candidate_files):
            continue
        return False
    return True


def _dependencies(rows, plan, config, scope_set):
    section = plan.section("Dependencies")
    touching = []
    for row in rows:
        for listed in row.files:
            rel = globs.normalise(listed)
            if WILDCARD.search(rel):
                continue
            if files.classify(rel, config) == "dependencies":
                touching.append((row.n, rel))
    if touching and not section:
        names = ", ".join(f"step {n} (`{rel}`)" for n, rel in touching)
        return [f"{names} touches a dependency file, so the `## Dependencies` section is "
                f"required (SEC-003)"]
    return []


def _locked_steps(rows, state):
    if state is None:
        return []
    problems = []
    by_number = {row.n: row for row in rows}
    for step in state.steps:
        if not step.is_ok:
            continue
        row = by_number.get(step.n)
        if row is None:
            problems.append(f"step {step.n} is already validated but is missing from the plan — "
                            f"validated steps are locked (7.5)")
            continue
        if row.kind != step.kind or sorted(row.files) != sorted(step.files) \
                or row.behavior != step.behavior:
            problems.append(f"step {step.n} is already validated, so its row may not change "
                            f"(7.5) — it was: {step.kind} `{', '.join(step.files)}` "
                            f"{step.behavior}")
    return problems


def _lessons(plan, lesson_ids):
    known = set(lesson_ids or ())
    return [f"lesson {ref} is cited but does not exist in pair/learnings/ (10.1.1/11)"
            for ref in plan.lesson_refs if ref not in known]
