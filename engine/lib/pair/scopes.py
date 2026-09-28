"""Scopes: where a step's commands come from, and which file belongs to which (SPEC 8.4)."""

from pair import paths, schema, tomlio
from pair.errors import CheckFailed
from pair.schema import Int, ListOf, Num, Str, Table

REPO_SCOPE = "_repo"
COMMANDS = ("test", "coverage", "lint", "validate", "migrate_check")

SCOPE = Table({
    "path": Str(),
    "cwd": Str(),
    "timeout_seconds": Int(minimum=1),
    "no_tests_exit_codes": ListOf(Int()),
    "module": Str(),
    "commands": Table({name: Str() for name in COMMANDS}),
    "coverage": Table({"target": Num(minimum=0, maximum=100)}),
}, required=("path", "commands"))


class Scope:
    def __init__(self, layout, folder, data, config):
        self.layout = layout
        self.folder = folder                      # pair/scopes/<...>
        self.data = data
        self.path = data["path"]
        self.cwd = data.get("cwd") or (self.path or ".")
        self.timeout_seconds = data.get("timeout_seconds", 600)
        self.no_tests_exit_codes = list(data.get("no_tests_exit_codes") or [])
        self.module = data.get("module") or ""
        self.commands = {name: (data.get("commands", {}).get(name) or "") for name in COMMANDS}
        self._target = (data.get("coverage") or {}).get("target")
        self._config_target = config.coverage_target

    @property
    def name(self):
        return self.path or REPO_SCOPE

    @property
    def slug(self):
        return paths.scope_slug(self.path)

    @property
    def target(self):
        return self._target if self._target is not None else self._config_target

    @property
    def work_dir(self):
        return self.layout.root / self.cwd

    @property
    def rules_md(self):
        return self.folder / "RULES.md"

    @property
    def summary_md(self):
        return self.folder / "SUMMARY.md"

    def command(self, name):
        return self.commands.get(name, "")

    def has(self, name):
        return bool(self.command(name))

    def __repr__(self):
        return f"Scope({self.name!r})"


class Scopes:
    def __init__(self, scopes):
        # Longest path first, so `resolve` can return the first match (SPEC 8.4).
        self.scopes = sorted(scopes, key=lambda s: len(s.path), reverse=True)

    @classmethod
    def load(cls, layout, config):
        found = []
        problems = []
        root = layout.scopes_dir
        if root.is_dir():
            for path in sorted(root.rglob("scope.toml")):
                rel = str(path.relative_to(layout.root))
                text = path.read_text(encoding="utf-8")
                data = tomlio.loads(text, rel)
                issues = schema.errors(data, SCOPE, text=text)
                if issues:
                    problems += [f"{rel}: {issue}" for issue in issues]
                    continue
                folder = path.parent
                declared = data["path"]
                expected = str(folder.relative_to(root)).replace("\\", "/")
                if expected == REPO_SCOPE:
                    expected = ""
                if declared != expected:
                    problems.append(
                        f"{rel}: path is {declared!r} but the folder says {expected!r} — "
                        f"they must match (SPEC 8.4)"
                    )
                    continue
                scope = Scope(layout, folder, data, config)
                if scope._target is not None and scope._target < config.coverage_target:
                    problems.append(
                        f"{rel}: coverage.target {scope._target} is below the project's "
                        f"{config.coverage_target}; a scope may only raise it (SPEC 8.4)"
                    )
                    continue
                found.append(scope)
        if problems:
            raise CheckFailed("a scope is not usable", problems)
        return cls(found)

    def __iter__(self):
        return iter(self.scopes)

    def __len__(self):
        return len(self.scopes)

    @property
    def fallback(self):
        for scope in self.scopes:
            if scope.path == "":
                return scope
        return None

    def by_name(self, name):
        wanted = "" if name in ("", REPO_SCOPE) else name
        for scope in self.scopes:
            if scope.path == wanted:
                return scope
        return None

    def resolve(self, rel_path):
        """The scope owning `rel_path`, or None when the file belongs to no scope (SPEC 8.4)."""
        text = rel_path.replace("\\", "/")
        if paths.has_no_scope(text):
            return None
        for scope in self.scopes:
            if scope.path and (text == scope.path or text.startswith(scope.path + "/")):
                return scope
        return self.fallback

    def resolve_all(self, rel_paths):
        """(the one scope, None) or (None, an explanation) — a step must resolve to one scope."""
        found = {}
        missing = []
        for rel in rel_paths:
            scope = self.resolve(rel)
            if scope is None:
                missing.append(rel)
            else:
                found.setdefault(scope.name, scope)
        if missing:
            return None, f"belongs to no scope: {', '.join(sorted(missing))} (SPEC 8.4)"
        if len(found) > 1:
            return None, ("spans more than one scope: " + ", ".join(sorted(found)) +
                          " — split the step (SPEC 8.2)")
        if not found:
            return None, "has no files"
        return next(iter(found.values())), None
