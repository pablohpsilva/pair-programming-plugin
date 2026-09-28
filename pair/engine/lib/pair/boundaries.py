"""The import graph: `rules/boundaries.toml` and the ARCH-001 gate (SPEC 10.7, 13.1)."""

import pathlib
import re

from pair import schema, tomlio
from pair.errors import CheckFailed
from pair.schema import ListOf, Str, Table

MODULE = Table({
    "path": Str(allow_empty=False),
    "import_names": ListOf(Str(allow_empty=False), min_items=1),
    "may_depend_on": ListOf(Str(allow_empty=False)),
}, required=("path", "import_names", "may_depend_on"))

BOUNDARIES = Table({
    "modules": Table(values=MODULE),
    "import_patterns": Table(values=ListOf(Str(allow_empty=False), min_items=1)),
})

DEFAULT_PATTERNS = {
    ".py": [r"^\s*import\s+([\w.]+)", r"^\s*from\s+([\w.]+)\s+import"],
    ".ts": [r"""from\s+['"]([^'"]+)['"]""", r"""require\(\s*['"]([^'"]+)['"]\s*\)"""],
    ".go": [r'^\s*(?:import\s+)?(?:\w+\s+)?"([^"]+)"'],
    ".java": [r"^\s*import\s+(?:static\s+)?([\w.]+)"],
    ".rs": [r"^\s*use\s+([\w:]+)"],
}
# The same patterns serve the sibling extensions of each language.
ALIASES = {".tsx": ".ts", ".js": ".ts", ".jsx": ".ts", ".mts": ".ts", ".cts": ".ts", ".kt": ".java"}

SEPARATORS = ("/", ".", "::")


class Module:
    def __init__(self, name, data):
        self.name = name
        self.path = data["path"]
        self.import_names = list(data["import_names"])
        self.may_depend_on = list(data["may_depend_on"])

    def owns(self, rel_path):
        return rel_path == self.path or rel_path.startswith(self.path + "/")

    def __repr__(self):
        return f"Module({self.name!r})"


class Boundaries:
    def __init__(self, modules, patterns):
        self.modules = modules                     # {name: Module}
        self.patterns = patterns

    @classmethod
    def load(cls, path):
        data = tomlio.load_if_present(path, "pair/rules/boundaries.toml")
        problems = schema.errors(data, BOUNDARIES)
        if problems:
            raise CheckFailed("pair/rules/boundaries.toml is invalid", problems)
        modules = {name: Module(name, entry) for name, entry in (data.get("modules") or {}).items()}
        unknown = []
        for module in modules.values():
            for wanted in module.may_depend_on:
                if wanted not in modules:
                    unknown.append(f"modules.{module.name}.may_depend_on names {wanted!r}, "
                                   f"which is not a module")
        if unknown:
            raise CheckFailed("pair/rules/boundaries.toml is inconsistent", unknown)
        patterns = dict(DEFAULT_PATTERNS)
        patterns.update(data.get("import_patterns") or {})
        return cls(modules, patterns)

    @property
    def configured(self):
        return bool(self.modules)

    def module_of(self, rel_path):
        """The module owning `rel_path` — the longest matching `path` wins."""
        best = None
        for module in self.modules.values():
            if module.owns(rel_path) and (best is None or len(module.path) > len(best.path)):
                best = module
        return best

    def patterns_for(self, suffix):
        key = ALIASES.get(suffix, suffix)
        return [re.compile(pattern, re.M) for pattern in self.patterns.get(key, [])]

    def imports_in(self, text, suffix):
        """Every imported name in `text`, from group 1 of each configured pattern."""
        found = set()
        for regex in self.patterns_for(suffix):
            for match in regex.finditer(text or ""):
                if match.group(1):
                    found.add(match.group(1))
        return sorted(found)

    def match_import(self, name):
        """The module an imported name refers to, or None (SPEC 10.7)."""
        for module in self.modules.values():
            for candidate in module.import_names:
                if name == candidate:
                    return module
                for separator in SEPARATORS:
                    if name.startswith(candidate + separator):
                        return module
        return None

    def violations(self, root, rel_paths):
        """Every disallowed edge in `rel_paths` as a readable line (ARCH-001)."""
        found = []
        for rel in sorted(rel_paths):
            owner = self.module_of(rel)
            if owner is None:
                continue
            suffix = pathlib.PurePosixPath(rel).suffix
            if not self.patterns_for(suffix):
                continue
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in self.imports_in(text, suffix):
                target = self.match_import(name)
                if target is None or target.name == owner.name:
                    continue
                if target.name not in owner.may_depend_on:
                    found.append(
                        f"{rel}: {owner.name} imports {target.name} ({name}), which is not in "
                        f"its may_depend_on (ARCH-001)")
        return found

    def observed(self, root, rel_paths):
        """{module: {module}} — every edge actually present. `pair init` proposes from this."""
        edges = {}
        for rel in sorted(rel_paths):
            owner = self.module_of(rel)
            if owner is None:
                continue
            suffix = pathlib.PurePosixPath(rel).suffix
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in self.imports_in(text, suffix):
                target = self.match_import(name)
                if target is not None and target.name != owner.name:
                    edges.setdefault(owner.name, set()).add(target.name)
        return edges


def cycles(edges):
    """Every cycle in `{name: {name}}`, as a list of names. `pair init` prints these as warnings."""
    found = []
    seen = set()

    def walk(node, trail):
        if node in trail:
            cycle = trail[trail.index(node):] + [node]
            key = tuple(sorted(set(cycle)))
            if key not in seen:
                seen.add(key)
                found.append(cycle)
            return
        for target in sorted(edges.get(node, ())):
            walk(target, trail + [node])

    for start in sorted(edges):
        walk(start, [])
    return found
