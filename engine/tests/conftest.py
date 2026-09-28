"""Shared test machinery: an isolated HOME, and fixture repos built once per session.

The HOME isolation is not a convenience. SPEC 4 (D15) forbids any pair command from writing
outside the repository, and C37 asserts it; making every test run under an empty HOME means a
command that reaches for `~/.claude/` or a global git config fails in whichever test provoked it,
not only in C37.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def isolated_home(tmp_path_factory):
    """Point HOME and git's global config at empty directories for the whole session."""
    home = tmp_path_factory.mktemp("home")
    empty_gitconfig = home / "gitconfig"
    empty_gitconfig.write_text("")
    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "GIT_CONFIG_GLOBAL": str(empty_gitconfig),
        "GIT_CONFIG_SYSTEM": str(empty_gitconfig),
        "CLAUDE_CONFIG_DIR": str(home / ".claude-unused"),
    }
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield home
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def _built_fixtures(tmp_path_factory, isolated_home):
    """name -> a pristine built tree. Built once; tests always get a copy."""
    root = tmp_path_factory.mktemp("fixtures")
    built = {}

    def build(name):
        if name not in built:
            script = FIXTURES / name / "build.sh"
            if not script.is_file():
                raise AssertionError(f"no fixture named {name!r} (looked for {script})")
            target = root / name
            subprocess.run([str(script), str(target)], check=True)
            built[name] = target
        return built[name]

    return build


@pytest.fixture
def fixture_repo(_built_fixtures, tmp_path):
    """Copy a built fixture into this test's tmp_path and return its path.

    Usage:  repo = fixture_repo("minimal-python")
    """

    def make(name):
        source = _built_fixtures(name)
        target = tmp_path / name
        shutil.copytree(source, target, symlinks=True)
        return target

    return make


@pytest.fixture
def fixture_names():
    return sorted(p.name for p in FIXTURES.iterdir() if (p / "build.sh").is_file())
