"""The rule registry (SPEC 6): the engine's rules, the project's, and each scope's.

One table format everywhere, one namespace for IDs. `pair find --rule <ID>` returns the row this
module kept verbatim, which is why the raw line is stored and not reassembled (C18).
"""

import re

from pair.errors import CheckFailed

ID = re.compile(r"^[A-Z]+-\d{3}$")
ANY_ID = re.compile(r"\b[A-Z]+-\d{3}\b")
ENGINE_PREFIXES = ("PAIR", "COMM", "TEST", "COV", "ARCH", "SEC", "KNOW")
TIERS = (0, 1, 2, 3)


class Rule:
    def __init__(self, rule_id, text, tier, enforced_by, source, line, raw):
        self.id = rule_id
        self.text = text
        self.tier = tier
        self.enforced_by = enforced_by
        self.source = source            # a repo-relative path, for messages
        self.line = line
        self.raw = raw                  # the row exactly as written (C18)

    @property
    def prefix(self):
        return self.id.split("-")[0]

    def __repr__(self):
        return f"Rule({self.id}, tier {self.tier})"


def parse_table(text, source):
    """Every rule row in a Markdown document. Header and separator rows are skipped."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4 or not ID.match(cells[0]):
            continue
        try:
            tier = int(cells[2])
        except ValueError:
            raise CheckFailed(f"{source}:{number}: tier must be a number, got {cells[2]!r}")
        if tier not in TIERS:
            raise CheckFailed(f"{source}:{number}: tier must be 0-3, got {tier}")
        found.append(Rule(cells[0], cells[1], tier, cells[3], source, number, stripped))
    return found


class Registry:
    def __init__(self, rules):
        self.rules = list(rules)

    @classmethod
    def load(cls, layout):
        found = []
        found += _read(_registry_path(layout), "engine/defaults/rules.md")
        found += _read(layout.overrides, "pair/rules/overrides.md")
        if layout.scopes_dir.is_dir():
            for path in sorted(layout.scopes_dir.rglob("RULES.md")):
                found += _read(path, str(path.relative_to(layout.root)))
        return cls(found)

    def by_id(self, rule_id):
        for rule in self.rules:
            if rule.id == rule_id:
                return rule
        return None

    def ids(self):
        return [rule.id for rule in self.rules]

    def tier(self, rule_id):
        rule = self.by_id(rule_id)
        return None if rule is None else rule.tier

    def problems(self):
        """Every registry error: duplicate IDs, a wrong prefix, a project-defined Tier 0."""
        found = []
        seen = {}
        for rule in self.rules:
            if rule.id in seen:
                first = seen[rule.id]
                found.append(
                    f"{rule.id} is defined twice: {first.source}:{first.line} and "
                    f"{rule.source}:{rule.line} — rule IDs are unique across the repository (6.2)"
                )
            else:
                seen[rule.id] = rule

            engine = rule.source.endswith("engine/defaults/rules.md")
            if engine:
                if rule.prefix not in ENGINE_PREFIXES:
                    found.append(f"{rule.source}:{rule.line}: {rule.id} is not an engine prefix")
                continue
            if rule.tier == 0:
                found.append(
                    f"{rule.source}:{rule.line}: {rule.id} is Tier 0, but only the engine defines "
                    f"Tier 0 (6.2) — use tier 1-3"
                )
            wanted = "PROJ" if rule.source.endswith("rules/overrides.md") else "SCOPE"
            if rule.prefix != wanted:
                found.append(
                    f"{rule.source}:{rule.line}: {rule.id} must use the {wanted}- prefix (6.2)"
                )
        return found

    def require_valid(self):
        problems = self.problems()
        if problems:
            raise CheckFailed("the rule registry is inconsistent", problems)
        return self


def _registry_path(layout):
    """The vendored registry, or the engine source while developing pair (SPEC 3.2)."""
    vendored = layout.defaults / "rules.md"
    if vendored.is_file():
        return vendored
    import pathlib as _pathlib
    return _pathlib.Path(__file__).resolve().parents[2] / "defaults" / "rules.md"


def _read(path, source):
    if not path.is_file():
        return []
    return parse_table(path.read_text(encoding="utf-8"), source)


def cited(text):
    """Every rule ID mentioned in `text` — used to index chunks (SPEC 14.4)."""
    return sorted(set(ANY_ID.findall(text or "")))
