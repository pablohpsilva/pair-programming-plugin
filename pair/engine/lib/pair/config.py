"""`pair/config.toml`, `pair/local/config.toml` and the floors (SPEC 5).

Every command and the hook load this first. Validation is strict on purpose: an unknown key is an
error, not a warning, because a typo in a governance file otherwise leaves the engineer with a
default they never chose (SPEC 5.2, 5.4, G7).
"""

import pathlib

from pair import gitcmd, paths, schema, tomlio
from pair.errors import CheckFailed
from pair.schema import Bool, Int, ListOf, Num, Str, Table

SUPPORTED_FORMAT = 1

SOURCE_TYPES = ("pair", "docs", "adr", "llm-wiki", "markdown")
TRUST = ("high", "medium", "low")
DEFAULT_TRUST = {"pair": "high", "docs": "high", "adr": "high",
                 "llm-wiki": "medium", "markdown": "medium"}
FILE_CLASSES = ("tests", "migrations", "dependencies", "docs", "config")
HANDLE = r"^@[\w.-]+$"

LLM_WIKI_NEEDS_GLOBS = ("an llm-wiki source needs include and exclude globs — "
                        "pair does not guess a wiki's layout")

_GLOBS = ListOf(Str(allow_empty=False))

SOURCE = Table({
    "type": Str(choices=SOURCE_TYPES),
    "path": Str(allow_empty=False),
    "trust": Str(choices=TRUST),
    "include": _GLOBS,
    "exclude": _GLOBS,
}, required=("type", "path"))

CONFIG = Table({
    "format": Int(minimum=1),
    "engine": Str(pattern=r"^\d+\.\d+\.\d+$", describe="be a semver version like 0.1.0"),
    "governance": Str(pattern=r"^\d+\.\d+$", describe="look like 0.1"),
    "project": Table({"name": Str(), "default_branch": Str(allow_empty=False)}),
    "steps": Table({"max_files": Int(minimum=1),
                    "max_changed_lines": Int(minimum=1),
                    "batch_max_files": Int(minimum=1)}),
    "files": Table({name: _GLOBS for name in FILE_CLASSES}),
    "tests": Table({"wrong_reason_patterns": ListOf(Str(allow_empty=False))}),
    "coverage": Table({"target": Num(minimum=0, maximum=100),
                       "changed_lines": Num(minimum=0, maximum=100),
                       "ratchet_tolerance": Num(minimum=0)}),
    "protect": Table({"extra": _GLOBS}),
    "shell": Table({"ask_on_writes": Bool()}),
    "search": Table({"max_results": Int(minimum=1), "stale_days": Int(minimum=1)}),
    "learning": Table({"promote_after": Int(minimum=1), "review_unused_days": Int(minimum=1)}),
    "waivers": Table({"max_repeats": Int(minimum=0)}),
    "expedite": Table({"review_hours": Int(minimum=1), "max_files": Int(minimum=1)}),
    "sources": ListOf(SOURCE),
}, required=("format", "engine", "governance", "project"))

LOCAL = Table({
    "me": Str(pattern=HANDLE, describe="start with @, like @ana"),
    "sources": ListOf(SOURCE),
})

FLOOR = Table({"op": Str(choices=("eq", "min", "max")), "value": Num()}, required=("op", "value"))
DEFAULTS = Table(dict(CONFIG.fields, floors=Table(values=FLOOR)),
                 required=CONFIG.required)

_FLOOR_WORDS = {"eq": "must be exactly", "min": "must not be below", "max": "must not be above"}


def _dig(data, dotted):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _merge(base, extra):
    """`extra` over `base`, one level into each table. Lists replace, never append."""
    out = dict(base)
    for name, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(name), dict):
            out[name] = _merge(out[name], value)
        else:
            out[name] = value
    return out


class Source:
    def __init__(self, data, personal):
        self.type = data["type"]
        self.path = data["path"]
        self.trust = data.get("trust") or DEFAULT_TRUST.get(self.type, "medium")
        self.include = list(data.get("include") or [])
        self.exclude = list(data.get("exclude") or [])
        self.personal = personal

    def __repr__(self):
        return f"Source({self.type}, {self.path!r})"


class Config:
    """The effective configuration: defaults, then the project's file, plus the personal file."""

    def __init__(self, layout, data, local, defaults, floors):
        self.layout = layout
        self.data = data
        self.local = local
        self.defaults = defaults
        self.floors = floors

    # -- loading ---------------------------------------------------------------------------
    @classmethod
    def load(cls, layout):
        defaults_path = layout.defaults / "config.toml"
        if not defaults_path.is_file():
            defaults_path = _source_defaults()
        raw_defaults = tomlio.load(defaults_path, "engine/defaults/config.toml")
        floors = raw_defaults.pop("floors", {})
        problems = schema.errors(dict(raw_defaults, floors=floors), DEFAULTS)
        if problems:
            raise CheckFailed("engine/defaults/config.toml is invalid", problems)

        project_text = _read(layout.config)
        if project_text is None:
            raise CheckFailed(
                "pair/config.toml is missing: run `pair init`, or run pair from inside a repository "
                "that has a pair/ folder."
            )
        project = tomlio.loads(project_text, "pair/config.toml")
        problems = schema.errors(project, CONFIG, text=project_text)
        if problems:
            raise CheckFailed("pair/config.toml is invalid", problems)

        local_text = _read(layout.local_config)
        local = tomlio.loads(local_text, "pair/local/config.toml") if local_text is not None else {}
        problems = schema.errors(local, LOCAL, text=local_text)
        if problems:
            raise CheckFailed("pair/local/config.toml is invalid", problems)

        merged = _merge(raw_defaults, project)
        config = cls(layout, merged, local, raw_defaults, floors)
        config._check_format()
        config._check_floors(project)
        config._check_sources()
        return config

    def _check_format(self):
        if self.format > SUPPORTED_FORMAT:
            raise CheckFailed(
                f"pair/config.toml is format {self.format}, but this engine supports "
                f"{SUPPORTED_FORMAT}: upgrade the engine (pair upgrade)."
            )

    def _check_floors(self, project):
        """A project may only make a floor stricter (SPEC 5.3)."""
        problems = []
        for dotted, rule in sorted(self.floors.items()):
            value = _dig(project, dotted)
            if value is None:
                continue
            op, floor = rule["op"], rule["value"]
            if (op == "eq" and value != floor) or (op == "min" and value < floor) \
                    or (op == "max" and value > floor):
                problems.append(f"{dotted}: {_FLOOR_WORDS[op]} {floor}, got {value}")
        if problems:
            raise CheckFailed("pair/config.toml is looser than the floors (SPEC 5.3)", problems)

    def _check_sources(self):
        problems = []
        for source in self.sources:
            if source.type == "llm-wiki" and not (source.include and source.exclude):
                problems.append(f"{source.path}: {LLM_WIKI_NEEDS_GLOBS}")
            if not source.personal and _is_outside(source.path):
                problems.append(
                    f"{source.path}: a shared source path must be inside the repository — "
                    f"move it to pair/local/config.toml (SPEC 14.3)"
                )
        if problems:
            raise CheckFailed("a registered knowledge source is not usable", problems)

    # -- values ----------------------------------------------------------------------------
    @property
    def format(self):
        return self.data["format"]

    @property
    def engine_version(self):
        return self.data["engine"]

    @property
    def governance(self):
        return self.data["governance"]

    @property
    def default_branch(self):
        return self.data["project"]["default_branch"]

    @property
    def project_name(self):
        return self.data["project"].get("name") or self.layout.root.name

    def get(self, dotted, fallback=None):
        value = _dig(self.data, dotted)
        return fallback if value is None else value

    @property
    def max_files(self):
        return self.get("steps.max_files", 1)

    @property
    def max_changed_lines(self):
        return self.get("steps.max_changed_lines", 50)

    @property
    def batch_max_files(self):
        return self.get("steps.batch_max_files", 20)

    @property
    def coverage_target(self):
        return self.get("coverage.target", 95)

    @property
    def changed_lines_target(self):
        return self.get("coverage.changed_lines", 100)

    @property
    def ratchet_tolerance(self):
        return self.get("coverage.ratchet_tolerance", 0.5)

    @property
    def wrong_reason_patterns(self):
        return list(self.get("tests.wrong_reason_patterns", []))

    @property
    def file_globs(self):
        """{class: [glob]} in SPEC 8.1 order; the first match wins."""
        table = self.get("files", {})
        return {name: list(table.get(name, [])) for name in FILE_CLASSES}

    @property
    def protect_extra(self):
        return list(self.get("protect.extra", []))

    def protected(self, rel_path):
        return paths.is_protected(rel_path, self.protect_extra)

    @property
    def ask_on_writes(self):
        return bool(self.get("shell.ask_on_writes", True))

    @property
    def max_results(self):
        return self.get("search.max_results", 5)

    @property
    def stale_days(self):
        return self.get("search.stale_days", 180)

    @property
    def promote_after(self):
        return self.get("learning.promote_after", 3)

    @property
    def review_unused_days(self):
        return self.get("learning.review_unused_days", 90)

    @property
    def max_repeats(self):
        return self.get("waivers.max_repeats", 3)

    @property
    def expedite_review_hours(self):
        return self.get("expedite.review_hours", 24)

    @property
    def expedite_max_files(self):
        return self.get("expedite.max_files", 10)

    @property
    def sources(self):
        shared = [Source(entry, personal=False) for entry in self.get("sources", [])]
        personal = [Source(entry, personal=True) for entry in (self.local.get("sources") or [])]
        return shared + personal

    @property
    def me(self):
        """The engineer's handle: `local.me`, else derived from git's email (SPEC 5.4)."""
        stated = self.local.get("me")
        if stated:
            return stated
        email = gitcmd.config_get(self.layout.root, "user.email") or ""
        local_part = email.split("@")[0].strip()
        return f"@{local_part}" if local_part else None

    def require_me(self):
        handle = self.me
        if not handle:
            raise CheckFailed(
                "pair does not know who you are: set `me = \"@you\"` in pair/local/config.toml, "
                "or set git's user.email."
            )
        return handle


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None


def _is_outside(path):
    return path.startswith("~") or pathlib.PurePosixPath(path).is_absolute()


def _source_defaults():
    """While developing pair the engine runs from `engine/`, not `pair/engine/` (SPEC 3.2)."""
    return pathlib.Path(__file__).resolve().parents[2] / "defaults" / "config.toml"


def load(layout):
    return Config.load(layout)
