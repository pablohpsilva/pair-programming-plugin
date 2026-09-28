"""Cobertura reports, changed-line coverage, baselines and the ratchet (SPEC 8.3, 15)."""

import re
import xml.etree.ElementTree as ElementTree

from pair import clock, schema, tomlio
from pair.errors import CheckFailed
from pair.schema import Num, Str, Table

# SPEC 13.1 COV-004: a pragma is only allowed in a file an approved exclusion covers.
PRAGMAS = (
    r"pragma:\s*no\s*cover",
    r"istanbul\s+ignore",
    r"c8\s+ignore",
    r"coverage:\s*ignore",
    r"#\[coverage\(off\)\]",
    r"@Generated",
)
PRAGMA = re.compile("|".join(PRAGMAS))

BASELINE = Table({"scopes": Table(values=Table({
    "line": Num(minimum=0, maximum=100),
    "branch": Num(minimum=0, maximum=100),
    "measured_at": Str(pattern=r"^\d{4}-\d{2}-\d{2}$", describe="look like 2026-09-27"),
    "lowered_by": Str(pattern=r"^@[\w.-]+$", describe="start with @"),
    "lowered_reason": Str(allow_empty=False),
}, required=("line", "branch", "measured_at")))})


class Report:
    """One Cobertura file: the root rates, and hit counts per file and line."""

    def __init__(self, line_rate, branch_rate, hits):
        self.line_rate = line_rate
        self.branch_rate = branch_rate
        self.hits = hits                    # {filename: {line number: hits}}

    @classmethod
    def parse(cls, text, what="the coverage report"):
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as problem:
            raise CheckFailed(f"{what} is not readable XML: {problem}") from problem
        if root.tag != "coverage":
            raise CheckFailed(f"{what} is not Cobertura XML (root element is <{root.tag}>)")
        hits = {}
        for element in root.iter("class"):
            name = element.get("filename")
            if not name:
                continue
            per_file = hits.setdefault(name, {})
            for line in element.iter("line"):
                try:
                    number = int(line.get("number"))
                    count = int(line.get("hits", "0"))
                except (TypeError, ValueError):
                    continue
                per_file[number] = max(count, per_file.get(number, 0))
        return cls(_rate(root.get("line-rate")), _rate(root.get("branch-rate")), hits)

    @classmethod
    def load(cls, path):
        try:
            return cls.parse(path.read_text(encoding="utf-8"), str(path))
        except (FileNotFoundError, NotADirectoryError) as problem:
            raise CheckFailed(
                f"no coverage report at {path}: the scope's `coverage` command must write "
                f"Cobertura XML to $PAIR_COVERAGE_XML (SPEC 8.3)"
            ) from problem

    def known_lines(self, filename):
        """The executable lines the report knows about for `filename`, matched by suffix.

        Cobertura paths are relative to the tool's source root, which is rarely the repo root, so a
        suffix match is what actually works across pytest-cov, coverage.py, jest and go tooling.
        """
        exact = self.hits.get(filename)
        if exact is not None:
            return exact
        for name, lines in self.hits.items():
            if filename.endswith(name) or name.endswith(filename):
                return lines
        return {}

    def covered(self, filename, numbers):
        """(covered, measurable) for `numbers` in `filename`, ignoring lines not in the report."""
        known = self.known_lines(filename)
        measurable = [number for number in numbers if number in known]
        covered = [number for number in measurable if known[number] > 0]
        return len(covered), len(measurable)


def _rate(value):
    try:
        return round(float(value) * 100, 2)
    except (TypeError, ValueError):
        return 0.0


def changed_lines_covered(report, changed):
    """The percentage of changed executable lines that are covered (SPEC 8.2).

    `changed` is {relative path: {line numbers}}. Returns (percentage, uncovered) where uncovered
    is {path: [lines]}. With nothing measurable the percentage is 100: a step that adds no
    executable line meets COV-002 trivially.
    """
    total = 0
    hit = 0
    uncovered = {}
    for path, numbers in sorted(changed.items()):
        covered, measurable = report.covered(path, numbers)
        total += measurable
        hit += covered
        if measurable > covered:
            known = report.known_lines(path)
            uncovered[path] = sorted(n for n in numbers if n in known and known[n] == 0)
    percentage = 100.0 if total == 0 else round(hit * 100.0 / total, 2)
    return percentage, uncovered


def find_pragmas(text):
    """Line numbers carrying a coverage-ignore pragma."""
    return [number for number, line in enumerate((text or "").splitlines(), start=1)
            if PRAGMA.search(line)]


class Baselines:
    """`rules/baseline.toml`: the best coverage recorded per scope (SPEC 15)."""

    def __init__(self, path, data):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path):
        data = tomlio.load_if_present(path, "pair/rules/baseline.toml")
        problems = schema.errors(data, BASELINE)
        if problems:
            raise CheckFailed("pair/rules/baseline.toml is invalid", problems)
        data.setdefault("scopes", {})
        return cls(path, data)

    @property
    def scopes(self):
        return self.data.setdefault("scopes", {})

    def entry(self, scope_name):
        return self.scopes.get(scope_name)

    def floor(self, scope_name, target, tolerance):
        """(line floor, branch floor) for a scope (SPEC 15.1).

        No entry: the target. Below the target: the baseline less the tolerance — coverage may not
        slip further. At or above: never below the target, and never more than the tolerance below
        the best value recorded.
        """
        entry = self.entry(scope_name)
        if entry is None:
            return float(target), float(target)
        return (_floor_value(entry["line"], target, tolerance),
                _floor_value(entry["branch"], target, tolerance))

    def raise_to(self, scope_name, line, branch, at=None):
        """Raise the entry when a measurement beats it. Returns True when anything changed.

        `pair ok` never *creates* an entry (SPEC 15.2): a scope without one must meet the target.
        """
        entry = self.entry(scope_name)
        if entry is None:
            return False
        changed = False
        if line > entry["line"]:
            entry["line"] = round(float(line), 2)
            changed = True
        if branch > entry["branch"]:
            entry["branch"] = round(float(branch), 2)
            changed = True
        if changed:
            entry["measured_at"] = at or clock.today()
        return changed

    def set_measured(self, scope_name, line, branch, at=None):
        """`pair baseline`: add a missing scope, or raise an existing one. Never lowers."""
        entry = self.entry(scope_name)
        if entry is None:
            self.scopes[scope_name] = {"line": round(float(line), 2),
                                       "branch": round(float(branch), 2),
                                       "measured_at": at or clock.today()}
            return True
        return self.raise_to(scope_name, line, branch, at=at)

    def lower(self, scope_name, line, branch, by, reason, at=None):
        """`pair baseline --lower`: the only way a value goes down (SPEC 15.2)."""
        self.scopes[scope_name] = {"line": round(float(line), 2),
                                   "branch": round(float(branch), 2),
                                   "measured_at": at or clock.today(),
                                   "lowered_by": by, "lowered_reason": reason}

    def save(self):
        tomlio.dump(self.path, {"scopes": dict(sorted(self.scopes.items()))},
                    header=["coverage baselines per scope (SPEC 15).",
                            "Raised by `pair ok` and `pair baseline`; lowered only by",
                            "`pair baseline --lower --reason \"<why>\"`."])
        return self.path


def _floor_value(baseline, target, tolerance):
    if baseline < target:
        return round(max(0.0, baseline - tolerance), 2)
    return round(max(float(target), baseline - tolerance), 2)
