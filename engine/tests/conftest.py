"""Shared test machinery: an isolated HOME, and fixture repos built once per session.

The HOME isolation is not a convenience. SPEC 4 (D15) forbids any pair command from writing
outside the repository, and C37 asserts it; making every test run under an empty HOME means a
command that reaches for `~/.claude/` or a global git config fails in whichever test provoked it,
not only in C37.
"""

import os
import pathlib
import shlex
import shutil
import subprocess
import sys

import pytest


REPO = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ENGINE = REPO / "engine"

# The engine is not installed; it is vendored and run from bin/pair. Tests import it the same way.
if str(ENGINE / "lib") not in sys.path:
    sys.path.insert(0, str(ENGINE / "lib"))

from pair import (config as config_mod, coverage as coverage_mod, gitcmd,  # noqa: E402
                  paths, scopes, state, tomlio)


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


# --------------------------------------------------------------------------------------------
# A small pair repository in tmp_path, for every module that needs a real git tree.
# --------------------------------------------------------------------------------------------

CONFIG = """\
format = 1
engine = "0.1.0"
governance = "0.1"

[project]
name = "fixture"
default_branch = "main"
"""

REPO_SCOPE = 'path = ""\ncwd = "."\n\n[commands]\ntest = ""\ncoverage = ""\n'

COBERTURA = """\
<?xml version="1.0" ?>
<coverage line-rate="{line}" branch-rate="{branch}">
  <packages><package name="src"><classes>
    <class filename="{filename}" name="c"><lines>
{lines}
    </lines></class>
  </classes></package></packages>
</coverage>
"""


class Repo:
    """Everything a module under test needs: the tree, the config, the scopes, a task."""

    def __init__(self, root):
        self.root = root
        self.layout = paths.Layout(root)
        self._test_command = ""
        self._coverage_command = ""

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def git(self, *args, **kwargs):
        return gitcmd.run(self.root, *args, **kwargs)

    def commit_all(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return gitcmd.head(self.root)

    def set_commands(self, test="", coverage="", validate="", migrate_check="", timeout=60):
        """Rewrite the billing scope. Built through tomlio so any shell quoting survives."""
        self._test_command = test
        self._coverage_command = coverage
        self.write("pair/scopes/packages/billing/scope.toml", tomlio.dumps({
            "path": "packages/billing",
            "cwd": "packages/billing",
            "timeout_seconds": timeout,
            "no_tests_exit_codes": [5],
            "module": "billing",
            "commands": {"test": test, "coverage": coverage, "lint": "",
                         "validate": validate, "migrate_check": migrate_check},
        }))

    def cobertura(self, line=0.96, branch=0.95, hits=((1, 1), (2, 1)), name="cov",
                  filename="src/money.py"):
        """Stage a Cobertura file and return the one-line command that copies it into place.

        A copy, not a heredoc: the command has to survive being written into scope.toml.
        """
        body = "\n".join(f'      <line number="{n}" hits="{h}"/>' for n, h in hits)
        self.write(f".fixture/{name}.xml",
                   COBERTURA.format(line=line, branch=branch, lines=body,
                                    filename=filename))
        return f'cp ../../.fixture/{name}.xml "$PAIR_COVERAGE_XML"'

    def set_test_result(self, code=1, output="1 failed: AssertionError"):
        """Rewrite what the scope's `test` command does. The command itself never changes."""
        self.write(".fixture/test.sh", f"echo {shlex.quote(output)}\nexit {code}\n")
        return self

    def set_coverage(self, line=0.96, branch=0.95, hits=((1, 1), (2, 1)), code=0,
                     output="14 passed", filename="src/money.py"):
        """Rewrite what the scope's `coverage` command does: a staged report and an exit code."""
        copy = self.cobertura(line=line, branch=branch, hits=hits, filename=filename)
        self.write(".fixture/coverage.sh",
                   f"echo {shlex.quote(output)}\n{copy}\nexit {code}\n")
        return self

    def set_timeout(self, seconds):
        path = self.root / "pair/scopes/packages/billing/scope.toml"
        path.write_text(path.read_text().replace("timeout_seconds = 60",
                                                 f"timeout_seconds = {seconds}"))


    @property
    def config(self):
        return config_mod.load(self.layout)

    @property
    def scopes(self):
        return scopes.Scopes.load(self.layout, self.config)

    @property
    def billing(self):
        return self.scopes.by_name("packages/billing")

    @property
    def baselines(self):
        return coverage_mod.Baselines.load(self.layout.baseline)

    def task(self, task_id="142-instalments", mode="agent-drives", phase="stepping",
             steps=(), current=1):
        st = state.State.create(self.layout, task_id, "@ana", f"pair/{task_id}", mode, "0.1",
                                phase=phase)
        st.set_steps(list(steps))
        st.current_step = current
        st.save()
        self.layout.local.mkdir(parents=True, exist_ok=True)
        self.layout.active_file.write_text(task_id + "\n")
        return st


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T10:12:00Z")
    root = tmp_path / "work"
    root.mkdir()
    made = Repo(root)
    made.git("init", "-q", "-b", "main", ".")
    made.git("config", "user.name", "Ana")
    made.git("config", "user.email", "ana@example.invalid")
    made.git("config", "commit.gpgsign", "false")
    made.write(".gitignore", ".fixture/\n")
    made.write("pair/config.toml", CONFIG)
    made.write("pair/.gitignore", "local/\n")
    made.write("pair/scopes/_repo/scope.toml", REPO_SCOPE)
    # The billing scope's commands are two scripts the tests rewrite; the commands themselves are
    # fixed, so plan-check has something non-empty to accept from the start (SPEC 8.4).
    made.set_commands(test="sh ../../.fixture/test.sh", coverage="sh ../../.fixture/coverage.sh")
    made.set_test_result()
    made.set_coverage()
    made.write("packages/billing/src/__init__.py", "")
    made.write("packages/billing/src/money.py", "def cents(x):\n    return int(x * 100)\n")
    made.commit_all("seed")
    return made


class Cli:
    """Drives `pair.cli.main` in-process.

    In-process on purpose: the human-only commands need a real TTY (SPEC 11.1) and the engine must
    not ship a way round that, so the test replaces `tty.confirm` instead of the CLI offering an
    escape hatch. Commands that do not need a terminal are also exercised through `bin/pair` as a
    subprocess, in test_cli_subprocess.py.
    """

    def __init__(self, repo, answer=True):
        self.repo = repo
        self.answer = answer
        self.questions = []

    def confirm(self, question, expect="y"):
        self.questions.append((question, expect))
        return self.answer if isinstance(self.answer, bool) else self.answer(question, expect)

    def run(self, *argv, answer=None):
        """(exit code, stdout, stderr)."""
        from pair import cli
        import io
        was, self.answer = self.answer, self.answer if answer is None else answer
        out, err = io.StringIO(), io.StringIO()
        try:
            code = cli.main([str(part) for part in argv], stdout=out, stderr=err,
                            confirm=self.confirm, root=str(self.repo.root))
        finally:
            self.answer = was
        return code, out.getvalue(), err.getvalue()

    def json(self, *argv, answer=None):
        code, out, err = self.run("--json", *argv, answer=answer)
        import json as _json
        return code, _json.loads(out) if out.strip() else None, err

    def ok(self, *argv, answer=None):
        """Run and assert success, so a test's failure message names the command."""
        code, out, err = self.run(*argv, answer=answer)
        assert code == 0, f"pair {' '.join(str(p) for p in argv)} exited {code}\n{out}\n{err}"
        return out


@pytest.fixture
def cli(repo):
    return Cli(repo)
