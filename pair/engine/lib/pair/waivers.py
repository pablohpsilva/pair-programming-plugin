"""`rules/waivers.toml` (SPEC 10.6).

Two rules make this more than a file writer: Tier 0 can never be waived, and the repeat count is
taken from the file's **history**, so deleting a waiver does not reset it.
"""

from pair import clock, gitcmd, globs, schema, tomlio
from pair.errors import CheckFailed
from pair.schema import ListOf, Str, Table

WAIVER = Table({
    "rule": Str(pattern=r"^[A-Z]+-\d{3}$", describe="be a rule ID like PROJ-001"),
    "reason": Str(allow_empty=False),
    "scope": ListOf(Str(allow_empty=False), min_items=1),
    "granted_by": Str(pattern=r"^@[\w.-]+$", describe="start with @"),
    "granted_at": Str(pattern=r"^\d{4}-\d{2}-\d{2}$", describe="look like 2026-09-27"),
    "expires": Str(pattern=r"^\d{4}-\d{2}-\d{2}$", describe="look like 2026-12-31"),
    "task": Str(),
}, required=("rule", "reason", "scope", "granted_by", "granted_at", "expires"))

WAIVERS = Table({"waiver": ListOf(WAIVER)})


class Waiver:
    def __init__(self, data):
        self.data = data
        self.rule = data["rule"]
        self.reason = data["reason"]
        self.scope = list(data["scope"])
        self.granted_by = data["granted_by"]
        self.granted_at = data["granted_at"]
        self.expires = data["expires"]
        self.task = data.get("task", "")

    @property
    def identity(self):
        """What makes two waivers the same grant, for counting across history."""
        return (self.rule, self.reason, self.granted_at, self.expires)

    def expired(self, today=None):
        when = clock.parse_date(self.expires)
        now = clock.parse_date(today or clock.today())
        return bool(when and now and when < now)

    def covers(self, rel_path):
        return globs.match_any(rel_path, self.scope) is not None

    def __repr__(self):
        return f"Waiver({self.rule}, expires {self.expires})"


class Waivers:
    def __init__(self, path, data):
        self.path = path
        self.data = data
        self.waivers = [Waiver(entry) for entry in (data.get("waiver") or [])]

    @classmethod
    def load(cls, path):
        return cls(path, _read(path, "pair/rules/waivers.toml"))

    def for_rule(self, rule_id):
        return [waiver for waiver in self.waivers if waiver.rule == rule_id]

    def expired(self, today=None):
        return [waiver for waiver in self.waivers if waiver.expired(today)]

    def active(self, today=None):
        return [waiver for waiver in self.waivers if not waiver.expired(today)]

    def covering(self, rule_id, rel_path, today=None):
        for waiver in self.active(today):
            if waiver.rule == rule_id and waiver.covers(rel_path):
                return waiver
        return None

    def history_count(self, root, rule_id):
        """How many distinct waivers this rule has ever had (SPEC 10.6).

        Counted over every committed version of the file, so removing a line does not reset it.
        """
        rel = str(self.path.relative_to(root)) if str(self.path).startswith(str(root)) \
            else "pair/rules/waivers.toml"
        seen = {waiver.identity for waiver in self.for_rule(rule_id)}
        for sha in gitcmd.lines(root, "log", "--format=%H", "--all", "--", rel):
            text = gitcmd.show(root, sha, rel)
            if not text:
                continue
            try:
                data = tomlio.loads(text, rel)
            except CheckFailed:
                continue
            for entry in data.get("waiver") or []:
                if entry.get("rule") == rule_id:
                    seen.add((entry.get("rule"), entry.get("reason"), entry.get("granted_at"),
                              entry.get("expires")))
        return len(seen)

    def add(self, entry):
        problems = schema.errors({"waiver": [entry]}, WAIVERS)
        if problems:
            raise CheckFailed("that waiver is not well formed", problems)
        tomlio.append_array_of_tables(self.path, "waiver", entry)
        self.data = _read(self.path, "pair/rules/waivers.toml")
        self.waivers = [Waiver(each) for each in (self.data.get("waiver") or [])]
        return entry

    def remove(self, number):
        """Drop the n-th waiver (1-based) and rewrite the file."""
        entries = list(self.data.get("waiver") or [])
        if not 1 <= number <= len(entries):
            raise CheckFailed(f"there is no waiver {number} (the file has {len(entries)})")
        dropped = entries.pop(number - 1)
        tomlio.dump(self.path, {"waiver": entries} if entries else {},
                    header=["standing waivers (SPEC 10.6). Added by `pair waive`."])
        self.data = _read(self.path, "pair/rules/waivers.toml")
        self.waivers = [Waiver(each) for each in (self.data.get("waiver") or [])]
        return dropped


def _read(path, what):
    data = tomlio.load_if_present(path, what)
    problems = schema.errors(data, WAIVERS)
    if problems:
        raise CheckFailed(f"{what} is invalid", problems)
    return data
