"""`pair upgrade` and the format migrations (SPEC 18)."""

import pathlib
import runpy
import re
import shutil
import subprocess
import tempfile

from pair import clock, commit, config as config_mod, gitcmd, globs, state as state_mod, tomlio
from pair.errors import CheckFailed, UsageError

MIGRATION = re.compile(r"^(\d{3})_([a-z0-9_-]+)\.py$")
ENGINE_FILES = ("VERSION", ".claude-plugin", "skills", "hooks", "bin", "lib", "defaults",
                "schemas", "templates", "migrations")


def fetch(source, into):
    """Put the new engine in `into`. `source` is a path, or a git URL with an optional `@tag`."""
    target = pathlib.Path(into)
    if "://" in source or source.startswith("git@"):
        url, _, tag = source.partition("@") if source.count("@") == 1 and "://" in source \
            else (source, "", "")
        args = ["git", "clone", "--depth", "1"]
        if tag:
            args += ["--branch", tag]
        args += [url, str(target)]
        done = subprocess.run(args, capture_output=True, text=True)
        if done.returncode != 0:
            raise CheckFailed(f"cannot fetch {source}", (done.stderr or "").splitlines()[:5])
        return _engine_root(target)
    origin = pathlib.Path(source).expanduser().resolve()
    if not origin.is_dir():
        raise CheckFailed(f"{source} is not a directory")
    found = _engine_root(origin)
    shutil.copytree(found, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    return target


def _engine_root(folder):
    """The engine inside a checkout: `engine/` while developing pair, else the folder itself."""
    for candidate in (folder / "engine", folder / "pair" / "engine", folder):
        if (candidate / "VERSION").is_file() or (candidate / "lib" / "pair").is_dir():
            return candidate
    raise CheckFailed(f"{folder} does not look like a pair engine (no VERSION, no lib/pair)")


def version_of(engine_dir):
    path = pathlib.Path(engine_dir) / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "unknown"


def diff(session, new_engine):
    """A readable summary of what replacing the engine changes."""
    current = session.layout.engine
    added, removed, changed = [], [], []
    old_files = _relative_files(current)
    new_files = _relative_files(new_engine)
    for rel in sorted(new_files - old_files):
        added.append(rel)
    for rel in sorted(old_files - new_files):
        removed.append(rel)
    for rel in sorted(old_files & new_files):
        if (current / rel).read_bytes() != (new_engine / rel).read_bytes():
            changed.append(rel)
    return {"added": added, "removed": removed, "changed": changed,
            "from": version_of(current), "to": version_of(new_engine)}


def _relative_files(folder):
    if not folder.is_dir():
        return set()
    found = set()
    for path in folder.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            found.add(globs.normalise(path.relative_to(folder)))
    return found


def replace(session, new_engine):
    target = session.layout.engine
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(new_engine, target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    return target


def migrations(engine_dir):
    """`NNN_<name>.py` in order (SPEC 18)."""
    folder = pathlib.Path(engine_dir) / "migrations"
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.iterdir()):
        match = MIGRATION.match(path.name)
        if match:
            found.append((int(match.group(1)), match.group(2), path))
    return sorted(found)


def pending(engine_dir, current_format, target_format):
    return [entry for entry in migrations(engine_dir)
            if current_format < entry[0] <= target_format]


def run_migrations(layout, engine_dir, current_format, target_format):
    """Run each migration in order. Each one MUST be idempotent (SPEC 18).

    Takes the layout rather than a session: after a format bump the config is, by design, no longer
    loadable by the engine that wrote it.
    """
    applied = []
    for number, name, path in pending(engine_dir, current_format, target_format):
        namespace = runpy.run_path(str(path))
        migrate = namespace.get("migrate")
        if not callable(migrate):
            raise CheckFailed(f"{path.name} has no `migrate(layout)` function")
        migrate(layout)
        applied.append(f"{number:03d}_{name}")
    return applied


def target_format(engine_dir):
    """The layout version the new engine supports, read from its own code."""
    path = pathlib.Path(engine_dir) / "lib" / "pair" / "config.py"
    if path.is_file():
        match = re.search(r"^SUPPORTED_FORMAT\s*=\s*(\d+)", path.read_text(encoding="utf-8"),
                          re.M)
        if match:
            return int(match.group(1))
    return config_mod.SUPPORTED_FORMAT


def stamp_config(session, engine_version, new_format):
    """Update `config.engine` and `config.format` in place, keeping comments."""
    path = session.layout.config
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^engine\s*=\s*".*"$', f'engine = "{engine_version}"', text, count=1,
                  flags=re.M)
    text = re.sub(r"^format\s*=\s*\d+$", f"format = {new_format}", text, count=1, flags=re.M)
    path.write_text(text, encoding="utf-8")
    return path


def stamp_states(session, new_format):
    """Migrations update both format numbers (SPEC 18)."""
    touched = []
    for task_id in state_mod.find_tasks(session.layout):
        path = session.layout.state(task_id)
        try:
            state = state_mod.State.load(session.layout, task_id)
        except CheckFailed:
            continue
        if state.data["format"] != new_format:
            state.data["format"] = new_format
            state.save()
            touched.append(globs.normalise(path.relative_to(session.root)))
    return touched


def temporary_folder():
    return tempfile.mkdtemp(prefix="pair-upgrade-")
