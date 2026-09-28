"""`pair init` (SPEC 11.4) and `pair upgrade` support for writing the tree.

Two constraints shape this module. It writes **nothing outside the repository** (D15, SPEC 4), and
outside `pair/` it writes only the five files SPEC 4 names — merging into `.claude/settings.json`
and `.github/CODEOWNERS` rather than rewriting them.
"""

import json
import pathlib

from pair import boundaries as boundaries_mod, clock, commit, files, gitcmd, globs, paths, sources, tomlio
from pair.errors import CheckFailed

MANIFESTS = {
    "package.json": "typescript",
    "pyproject.toml": "python",
    "setup.cfg": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
}
SKIP_DIRS = {".git", "node_modules", "pair", ".venv", "venv", "target", "dist", "build",
             "__pycache__", ".tox", ".mypy_cache", ".pytest_cache"}

MARKETPLACE = "pair-local"
PLUGIN_KEY = "pair@pair-local"


class Plan:
    """What `init` would write. Held first so the engineer sees the whole list before anything runs."""

    def __init__(self):
        self.writes = {}                # rel path -> text
        self.notes = []
        self.skipped = []

    def write(self, rel, text):
        self.writes[globs.normalise(rel)] = text

    def note(self, line):
        self.notes.append(line)

    def skip(self, rel, why):
        self.skipped.append(f"{rel}: {why}")

    @property
    def paths(self):
        return sorted(self.writes)

    def diff_against(self, root):
        """(new, changed, same) — what `init` on an existing pair/ would actually do."""
        new, changed, same = [], [], []
        for rel, text in sorted(self.writes.items()):
            path = root / rel
            if not path.exists():
                new.append(rel)
            elif path.read_text(encoding="utf-8") != text:
                changed.append(rel)
            else:
                same.append(rel)
        return new, changed, same


def detect_packages(root):
    """One proposed scope per package manifest (SPEC 11.4 step 1)."""
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name not in MANIFESTS:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        rel = globs.normalise(path.parent.relative_to(root))
        if rel in ("", "."):
            rel = ""
        found.append({"path": rel, "language": MANIFESTS[path.name], "manifest": path.name})
    unique = {}
    for entry in found:
        unique.setdefault(entry["path"], entry)
    return [unique[key] for key in sorted(unique)]


def scope_template(layout, language):
    path = layout.templates / f"scope.{language}.toml"
    if not path.is_file():
        path = _source_templates() / f"scope.{language}.toml"
    if not path.is_file():
        return {"path": "", "cwd": ".", "commands": {name: "" for name in
                                                     ("test", "coverage", "lint", "validate",
                                                      "migrate_check")}}
    return tomlio.load(path, str(path))


def _source_templates():
    return pathlib.Path(__file__).resolve().parents[2] / "templates"


def template_text(layout, name):
    path = layout.templates / name
    if not path.is_file():
        path = _source_templates() / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def build_plan(session, packages=None, source_entries=None, with_agents_md=True):
    """Everything `init` writes, assembled without touching the disk."""
    layout, config = session.layout, session.config
    plan = Plan()
    packages = packages if packages is not None else detect_packages(session.root)

    # -- pair/ ---------------------------------------------------------------------------------
    plan.write("pair/.gitignore", "local/\n")
    plan.write("pair/README.md", template_text(layout, "README.md"))
    plan.write("pair/config.toml", _config_text(session, source_entries))

    plan.write("pair/scopes/_repo/scope.toml", tomlio.dumps({
        "path": "", "cwd": ".", "module": "",
        "commands": {name: "" for name in ("test", "coverage", "lint", "validate",
                                           "migrate_check")}}))
    for package in packages:
        if not package["path"]:
            continue
        data = scope_template(layout, package["language"])
        data["path"] = package["path"]
        data["cwd"] = package["path"]
        data["module"] = package["path"].rsplit("/", 1)[-1]
        plan.write(f"pair/scopes/{package['path']}/scope.toml", tomlio.dumps(data))
        plan.write(f"pair/scopes/{package['path']}/RULES.md",
                   f"# {package['path']} — rules\n\nNo SCOPE rules yet.\n\n"
                   f"## Coverage exclusions\n\nNone.\n")

    plan.write("pair/rules/overrides.md",
               "# Project rules\n\nOnly the engine defines Tier 0. Project rules use `PROJ-` and "
               "tier 1-3.\n\n| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n")
    plan.write("pair/rules/boundaries.toml", _boundaries_text(session, packages))
    plan.write("pair/rules/waivers.toml",
               "# standing waivers (SPEC 10.6). Added by `pair waive`.\n")
    plan.write("pair/rules/baseline.toml",
               "# coverage baselines per scope (SPEC 15). Written by `pair baseline`.\n")
    plan.write("pair/knowledge/.gitkeep", "")
    plan.write("pair/learnings/preferences.md",
               "# Preferences\n\nTier 3 preferences, in the lesson format (SPEC 10.5).\n")
    plan.write("pair/reports/.gitkeep", "")

    # -- outside pair/, and only what SPEC 4 names ---------------------------------------------
    plan.write(".github/workflows/pair.yml", template_text(layout, "ci-github.yml"))
    plan.write(".github/CODEOWNERS", _codeowners(session))
    plan.write("githooks/commit-msg", template_text(layout, "commit-msg"))
    plan.write(".claude/settings.json", _settings(session))
    if with_agents_md:
        plan.write("AGENTS.md", template_text(layout, "AGENTS.md"))

    plan.note("a colleague who clones needs no install step for the plugin: "
              ".claude/settings.json declares it (SPEC 4)")
    plan.note("each clone does need one command: git config core.hooksPath githooks")
    plan.note("add the CLI to your own shell PATH if you want it there: "
              f"export PATH=\"{session.root}/pair/engine/bin:$PATH\" "
              "(the agent gets it from the plugin's bin/)")
    return plan


def _config_text(session, source_entries):
    data = {
        "format": session.config.format,
        "engine": session.config.engine_version,
        "governance": session.config.governance,
        "project": {"name": session.root.name,
                    "default_branch": gitcmd.current_branch(session.root) or "main"},
    }
    text = tomlio.dumps(data)
    if source_entries:
        text += "\n" + tomlio.dumps({"sources": list(source_entries)})
    return text


def _boundaries_text(session, packages):
    """Step 3: propose the dependencies that already exist, each marked as observed."""
    modules = {}
    for package in packages:
        if not package["path"]:
            continue
        name = package["path"].rsplit("/", 1)[-1]
        modules[name] = {"path": package["path"],
                         "import_names": [name, package["path"]],
                         "may_depend_on": []}
    if not modules:
        return ("# module dependency rules (SPEC 10.7). `pair init` found no packages to propose.\n"
                "\n[modules]\n")
    graph = boundaries_mod.Boundaries({name: boundaries_mod.Module(name, entry)
                                       for name, entry in modules.items()},
                                      dict(boundaries_mod.DEFAULT_PATTERNS))
    code = []
    for path in sorted(session.root.rglob("*")):
        if not path.is_file():
            continue
        rel = globs.normalise(path.relative_to(session.root))
        if any(part in SKIP_DIRS for part in rel.split("/")[:-1]):
            continue
        code.append(rel)
    observed = graph.observed(session.root, code)
    for name, targets in observed.items():
        modules[name]["may_depend_on"] = sorted(targets)
    comments = {f"modules.{name}.may_depend_on": f"observed {clock.today()}"
                for name in observed}
    cycles = boundaries_mod.cycles(observed)
    header = ["module dependency rules (SPEC 10.7).",
              "Edges below were observed in the code, not chosen. Remove any the team wants to",
              "forbid, and fix the code through tasks (SPEC 15.3)."]
    for cycle in cycles:
        header.append("WARNING cycle: " + " -> ".join(cycle))
    return ("".join(f"# {line}\n" for line in header) + "\n"
            + tomlio.dumps({"modules": modules}, comments))


def _codeowners(session):
    """Appends pair's two lines; never rewrites an existing one (SPEC 4)."""
    path = session.root / ".github" / "CODEOWNERS"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = existing.splitlines()
    have = {line.split()[0] for line in lines if line.strip() and not line.startswith("#")}
    added = []
    for owned in ("/pair/", "/.github/"):
        if owned not in have:
            added.append(f"{owned} @OWNERS")
    if not added:
        return existing if existing.endswith("\n") or not existing else existing + "\n"
    body = existing.rstrip("\n")
    prefix = (body + "\n\n") if body else ""
    return (prefix + "# pair: these paths are the engineer's (SPEC 19.1)\n"
            + "\n".join(added) + "\n")


def _settings(session):
    """Merges exactly two keys into `.claude/settings.json`; touches nothing else (SPEC 4)."""
    path = session.root / ".claude" / "settings.json"
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as problem:
            raise CheckFailed(f".claude/settings.json does not parse ({problem}); fix it before "
                              f"running init") from problem
        if not isinstance(data, dict):
            raise CheckFailed(".claude/settings.json is not an object")
    marketplaces = data.setdefault("extraKnownMarketplaces", {})
    marketplaces[MARKETPLACE] = {"source": {"source": "directory", "path": "./pair"}}
    enabled = data.setdefault("enabledPlugins", {})
    enabled[PLUGIN_KEY] = True
    return json.dumps(data, indent=2) + "\n"


def apply(session, plan):
    """Write the plan. Every path is inside the repository; nothing else is touched (D15)."""
    written = []
    for rel in plan.paths:
        target = session.root / rel
        if session.layout.rel(target) is None:
            raise CheckFailed(f"refusing to write outside the repository: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(plan.writes[rel], encoding="utf-8")
        if rel.endswith("commit-msg"):
            target.chmod(0o755)
        written.append(rel)
    return written


def commit_init(session, written):
    return commit.action_commit(session.root, written, "init", session.config.governance,
                               f"chore(pair): set up pair in {session.root.name}")
