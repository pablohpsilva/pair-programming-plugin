"""The repository layout: where the root is, what is protected, what belongs to no scope.

Every other module asks this one for a path. Nothing else joins `pair/` onto a root by hand.
"""

import os
import pathlib

from pair import globs

PAIR = "pair"

# SPEC 19.1. `protect.extra` from the config is appended by config.protected_globs().
PROTECTED = (
    "pair/engine/**",
    "pair/config.toml",
    "pair/README.md",
    "pair/.gitignore",
    "pair/rules/**",
    "pair/scopes/**/scope.toml",
    "pair/scopes/**/RULES.md",
    "pair/learnings/**",
    "pair/reports/**",
    "pair/local/**",
    "pair/tasks/*/state.json",
    ".github/**",
    "CODEOWNERS",
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/**",
    ".git/**",
)

# SPEC 4: the only files pair creates outside pair/. They belong to no scope (SPEC 8.4).
POINTER_FILES = (
    ".github/workflows/pair.yml",
    ".github/CODEOWNERS",
    "AGENTS.md",
    ".claude/settings.json",
    "githooks/commit-msg",
)

# SPEC 8.4: files under pair/ have no scope, except these, which may be `doc` steps.
DOC_EXCEPTIONS = (
    "pair/knowledge/**",
    "pair/scopes/**/SUMMARY.md",
)


class Layout:
    """Absolute paths derived from one repository root."""

    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()

    # -- the pair tree ---------------------------------------------------------------------
    @property
    def pair_dir(self):
        return self.root / PAIR

    @property
    def config(self):
        return self.pair_dir / "config.toml"

    @property
    def engine(self):
        return self.pair_dir / "engine"

    @property
    def defaults(self):
        return self.engine / "defaults"

    @property
    def templates(self):
        return self.engine / "templates"

    @property
    def rules_dir(self):
        return self.pair_dir / "rules"

    @property
    def overrides(self):
        return self.rules_dir / "overrides.md"

    @property
    def boundaries(self):
        return self.rules_dir / "boundaries.toml"

    @property
    def baseline(self):
        return self.rules_dir / "baseline.toml"

    @property
    def waivers(self):
        return self.rules_dir / "waivers.toml"

    @property
    def scopes_dir(self):
        return self.pair_dir / "scopes"

    @property
    def learnings(self):
        return self.pair_dir / "learnings"

    @property
    def knowledge(self):
        return self.pair_dir / "knowledge"

    @property
    def tasks_dir(self):
        return self.pair_dir / "tasks"

    @property
    def reports(self):
        return self.pair_dir / "reports"

    # -- local/, never committed ----------------------------------------------------------
    @property
    def local(self):
        return self.pair_dir / "local"

    @property
    def local_config(self):
        return self.local / "config.toml"

    @property
    def active_file(self):
        return self.local / "active"

    @property
    def index_file(self):
        return self.local / "index.json"

    @property
    def coverage_dir(self):
        return self.local / "coverage"

    @property
    def runs(self):
        return self.local / "runs"

    @property
    def find_log(self):
        return self.local / "find_log"

    @property
    def outbox(self):
        return self.local / "outbox"

    @property
    def hooks_log(self):
        return self.runs / "hooks.jsonl"

    # -- one task -------------------------------------------------------------------------
    def task_dir(self, task_id):
        return self.tasks_dir / task_id

    def plan(self, task_id):
        return self.task_dir(task_id) / "plan.md"

    def log(self, task_id):
        return self.task_dir(task_id) / "log.md"

    def state(self, task_id):
        return self.task_dir(task_id) / "state.json"

    def walkthrough(self, task_id):
        return self.task_dir(task_id) / "walkthrough.md"

    def run_log(self, task_id, step):
        return self.runs / task_id / f"{step}.log"

    def coverage_xml(self, scope_path):
        return self.coverage_dir / f"{scope_slug(scope_path)}.xml"

    # -- relative paths -------------------------------------------------------------------
    def rel(self, path):
        """`path` relative to the root as a POSIX string, or None when it is outside.

        Symlinks and `..` are resolved first, so neither can smuggle a path past a check.
        """
        try:
            resolved = pathlib.Path(path)
            if not resolved.is_absolute():
                resolved = self.root / resolved
            resolved = _resolve_existing(resolved)
            return globs.normalise(resolved.relative_to(self.root))
        except ValueError:
            return None

    def contains(self, path):
        return self.rel(path) is not None

    def active_task(self):
        """The task id in local/active, or None. A blank or missing file means none."""
        try:
            name = self.active_file.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, NotADirectoryError):
            return None
        return name or None


def _resolve_existing(path):
    """Resolve symlinks without requiring the path to exist (a step file may be new)."""
    return pathlib.Path(os.path.normpath(str(path.parent.resolve()))) / path.name


def scope_slug(scope_path):
    """SPEC 8.3: the scope path with `/` replaced by `__`; `_repo` for the fallback scope."""
    return scope_path.replace("/", "__") if scope_path else "_repo"


def find_root(start=None):
    """The nearest ancestor holding `pair/config.toml`, or None.

    `$CLAUDE_PROJECT_DIR` wins when it is itself a pair repo (SPEC 12.2), because the hook runs
    with a cwd that may be anywhere under the root.
    """
    declared = os.environ.get("CLAUDE_PROJECT_DIR")
    if declared and (pathlib.Path(declared) / PAIR / "config.toml").is_file():
        return pathlib.Path(declared).resolve()
    here = pathlib.Path(start or os.getcwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / PAIR / "config.toml").is_file():
            return candidate
    return None


def is_protected(rel_path, extra=()):
    """The pattern that protects `rel_path`, or None (SPEC 19.1)."""
    return globs.match_any(rel_path, list(PROTECTED) + list(extra or ()))


def is_pointer_file(rel_path):
    return globs.normalise(rel_path) in POINTER_FILES


def has_no_scope(rel_path):
    """SPEC 8.4: files under pair/ and the pointer files belong to no scope.

    The two `doc` exceptions do have a scope for the purpose of being step files.
    """
    text = globs.normalise(rel_path)
    if globs.match_any(text, DOC_EXCEPTIONS):
        return False
    return text == PAIR or text.startswith(PAIR + "/") or is_pointer_file(text)
