"""File classes and which kind of step may touch them (SPEC 8.1)."""

from pair import globs

CLASSES = ("tests", "migrations", "dependencies", "docs", "config", "code")

KINDS = ("stub", "test", "char", "code", "refactor", "doc", "config", "migration")

# The class each kind may write. `refactor` gains `tests` only through a batch grant with
# include_tests, which is why it is not listed here (SPEC 8.1).
KIND_CLASSES = {
    "stub": ("code",),
    "test": ("tests",),
    "char": ("tests",),
    "code": ("code",),
    "refactor": ("code",),
    "doc": ("docs",),
    "config": ("config", "dependencies"),
    "migration": ("migrations",),
}

# Which command each kind's evidence runs (SPEC 8.1). None means no command.
KIND_COMMAND = {
    "stub": "test",
    "test": "test",
    "char": "coverage",
    "code": "coverage",
    "refactor": "coverage",
    "doc": None,
    "config": "validate",
    "migration": "migrate_check",
}

# Kinds whose plan-check requires the scope command to be non-empty (SPEC 8.4).
KINDS_NEEDING_COMMANDS = ("stub", "test", "char", "code", "refactor")


def classify(rel_path, config):
    """The class of one file: the first `[files]` entry that matches, else `code` (SPEC 8.1)."""
    table = config.file_globs
    for name in ("tests", "migrations", "dependencies", "docs", "config"):
        if globs.match_any(rel_path, table.get(name, [])):
            return name
    return "code"


def allowed_for(kind, include_tests=False):
    """The classes a step of `kind` may write."""
    allowed = list(KIND_CLASSES.get(kind, ()))
    if kind == "refactor" and include_tests:
        allowed.append("tests")
    return tuple(allowed)


def is_allowed(kind, file_class, include_tests=False):
    return file_class in allowed_for(kind, include_tests)


def command_for(kind):
    return KIND_COMMAND.get(kind)
