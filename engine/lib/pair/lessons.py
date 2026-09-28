"""`learnings/<domain>.md` (SPEC 10.5).

The grammar is matched exactly, and edits are made **in place**: `pair close` rewrites only the
`Last used` date, and a dispute only adds a prefix. Anything else in the file — prose, headings, a
colleague's notes — survives untouched, which also means two branches merging keeps both sets of
confirmations.
"""

import re

from pair import clock

DISPUTED = "⚠️ disputed "

LESSON = re.compile(
    r"^- (?P<disputed>⚠️ disputed )?(?P<id>[a-z0-9-]+#[a-z0-9-]+\.\d+) — "
    r"(?P<text>.+?) Source: (?P<source>.+?), (?P<who>@[\w.-]+)\. "
    r"Last used: (?P<date>\d{4}-\d{2}-\d{2})$"
)
CONFIRMED = re.compile(r"^  - confirmed: (?P<task>[a-z0-9-]+) (?P<date>\d{4}-\d{2}-\d{2})$")
LESSON_ID = re.compile(r"^(?P<domain>[a-z0-9-]+)#(?P<task>[a-z0-9-]+)\.(?P<n>\d+)$")


class Lesson:
    def __init__(self, match, index):
        self.id = match.group("id")
        self.text = match.group("text")
        self.source = match.group("source")
        self.who = match.group("who")
        self.date = match.group("date")
        self.disputed = bool(match.group("disputed"))
        self.index = index                  # the line this lesson sits on
        self.confirmations = []             # [(task, date)], in file order

    @property
    def domain(self):
        found = LESSON_ID.match(self.id)
        return found.group("domain") if found else None

    @property
    def confirmation_count(self):
        """Distinct confirming tasks. A merge can leave the same line twice (SPEC 10.5)."""
        return len({task for task, _ in self.confirmations})

    def render(self):
        prefix = DISPUTED if self.disputed else ""
        return (f"- {prefix}{self.id} — {self.text} Source: {self.source}, {self.who}. "
                f"Last used: {self.date}")

    def __repr__(self):
        return f"Lesson({self.id})"


def format_lesson(lesson_id, text, source, who, date=None, disputed=False):
    prefix = DISPUTED if disputed else ""
    return (f"- {prefix}{lesson_id} — {text} Source: {source}, {who}. "
            f"Last used: {date or clock.today()}")


class Domain:
    """One `learnings/<domain>.md`, held as its lines so edits stay surgical."""

    def __init__(self, path, lines):
        self.path = path
        self.lines = lines
        self.lessons = []
        self._parse()

    @classmethod
    def load(cls, path):
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        return cls(path, text.splitlines())

    def _parse(self):
        current = None
        for index, line in enumerate(self.lines):
            found = LESSON.match(line)
            if found:
                current = Lesson(found, index)
                self.lessons.append(current)
                continue
            confirmed = CONFIRMED.match(line)
            if confirmed and current is not None:
                current.confirmations.append((confirmed.group("task"), confirmed.group("date")))
                continue
            if line.strip() and not line.startswith("  "):
                current = None

    @property
    def name(self):
        return self.path.stem

    def by_id(self, lesson_id):
        for lesson in self.lessons:
            if lesson.id == lesson_id:
                return lesson
        return None

    def with_text(self, text):
        """A lesson with the same text, case-insensitively — `accept` confirms instead of adding."""
        wanted = (text or "").strip().lower()
        for lesson in self.lessons:
            if lesson.text.strip().lower() == wanted:
                return lesson
        return None

    def next_number(self, task_id):
        used = []
        for lesson in self.lessons:
            found = LESSON_ID.match(lesson.id)
            if found and found.group("task") == task_id:
                used.append(int(found.group("n")))
        return max(used, default=0) + 1

    # -- edits -----------------------------------------------------------------------------
    def add(self, lesson_id, text, source, who, date=None):
        self.lines.append(format_lesson(lesson_id, text, source, who, date))
        self._reparse()
        return lesson_id

    def confirm(self, lesson_id, task_id, date=None):
        lesson = self.by_id(lesson_id)
        if lesson is None:
            return False
        line = f"  - confirmed: {task_id} {date or clock.today()}"
        at = lesson.index + 1 + len(lesson.confirmations)
        self.lines.insert(at, line)
        self._reparse()
        return True

    def set_last_used(self, lesson_id, date=None):
        """Rewrite only the date, in place (SPEC 10.5)."""
        lesson = self.by_id(lesson_id)
        if lesson is None:
            return False
        lesson.date = date or clock.today()
        self.lines[lesson.index] = lesson.render()
        self._reparse()
        return True

    def dispute(self, lesson_id):
        lesson = self.by_id(lesson_id)
        if lesson is None or lesson.disputed:
            return False
        lesson.disputed = True
        self.lines[lesson.index] = lesson.render()
        self._reparse()
        return True

    def _reparse(self):
        self.lessons = []
        self._parse()

    def render(self):
        return "\n".join(self.lines).rstrip("\n") + "\n" if self.lines else ""

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.render(), encoding="utf-8")
        return self.path


def domains(layout):
    folder = layout.learnings
    if not folder.is_dir():
        return []
    return [Domain.load(path) for path in sorted(folder.glob("*.md"))]


def domain(layout, name):
    return Domain.load(layout.learnings / f"{name}.md")


def all_lessons(layout):
    found = []
    for each in domains(layout):
        found += each.lessons
    return found


def ids(layout):
    return sorted(lesson.id for lesson in all_lessons(layout))


def promotion_candidates(layout, promote_after):
    return [lesson for lesson in all_lessons(layout)
            if lesson.confirmation_count >= promote_after]


def unused_since(layout, days, today=None):
    """Lessons whose `Last used` is older than `days` (SPEC 10.5, `pair doctor`)."""
    now = clock.parse_date(today or clock.today())
    stale = []
    for lesson in all_lessons(layout):
        when = clock.parse_date(lesson.date)
        if when is None or now is None:
            continue
        if (now - when).days > days:
            stale.append(lesson)
    return stale
