"""C17 (init), C20 (upgrade), C32 (no vendor reference) and C37 (nothing outside the repo)."""

import json
import pathlib
import re
import subprocess

import pytest

from pair import check as check_mod, cli as cli_mod, flow, gitcmd, tomlio

ENGINE = pathlib.Path(__file__).resolve().parents[3] / "engine"


class Fresh:
    """A repository with no pair/ yet, so `init` has something real to do."""

    def __init__(self, root):
        self.root = root

    def git(self, *args, **kwargs):
        return gitcmd.run(self.root, *args, **kwargs)

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run(self, *argv, answer=True):
        import io
        out, err = io.StringIO(), io.StringIO()
        code = cli_mod.main([str(part) for part in argv], stdout=out, stderr=err,
                           confirm=lambda question, expect: answer, root=str(self.root))
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv, answer=True):
        code, out, err = self.run(*argv, answer=answer)
        assert code == 0, f"pair {' '.join(str(p) for p in argv)} exited {code}\n{out}\n{err}"
        return out


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-28T09:00:00Z")
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    root = tmp_path / "greenfield"
    root.mkdir()
    made = Fresh(root)
    made.git("init", "-q", "-b", "main", ".")
    made.git("config", "user.name", "Ana")
    made.git("config", "user.email", "ana@example.invalid")
    made.git("config", "commit.gpgsign", "false")
    made.write("packages/billing/pyproject.toml", '[project]\nname = "billing"\nversion = "0.1.0"\n')
    made.write("packages/billing/src/money.py", "def cents(x):\n    return int(x * 100)\n")
    made.write("packages/billing/tests/test_money.py",
               "from src.money import cents\n\n\ndef test_cents():\n    assert cents(1) == 100\n")
    made.write("packages/shared/pyproject.toml", '[project]\nname = "shared"\nversion = "0.1.0"\n')
    made.write("packages/shared/util.py", "def helper():\n    return 1\n")
    made.write("docs/architecture.md", "# Architecture\n\nBilling splits invoices.\n")
    made.write("README.md", "# greenfield\n")
    made.git("add", "-A")
    made.git("commit", "-q", "-m", "seed")
    return made


# -- C17 -----------------------------------------------------------------------------------------

def test_c17_init_creates_the_tree_and_is_idempotent(fresh):
    out = fresh.ok("init")
    assert "pair init in" in out

    for rel in ("pair/config.toml", "pair/README.md", "pair/.gitignore",
                "pair/scopes/_repo/scope.toml",
                "pair/scopes/packages/billing/scope.toml",
                "pair/scopes/packages/shared/scope.toml",
                "pair/rules/overrides.md", "pair/rules/boundaries.toml",
                "pair/rules/waivers.toml", "pair/rules/baseline.toml",
                ".github/workflows/pair.yml", ".github/CODEOWNERS",
                "githooks/commit-msg", ".claude/settings.json", "AGENTS.md"):
        assert (fresh.root / rel).is_file(), rel

    second = fresh.ok("init")
    assert "nothing to change" in second
    assert gitcmd.modified_tracked(fresh.root) == []


def test_c17_the_init_commit_passes_every_ci_gate(fresh):
    base = gitcmd.head(fresh.root)
    fresh.ok("init")
    session = flow.Session.open(str(fresh.root), confirm=lambda q, e: True)
    failures = check_mod.run(session, "all", base)
    assert failures == [], "\n".join(failure.render() for failure in failures)


def test_c17_init_detects_the_packages_and_pre_fills_the_commands(fresh):
    fresh.ok("init")
    scope = tomlio.load(fresh.root / "pair/scopes/packages/billing/scope.toml")
    assert scope["path"] == "packages/billing"
    assert scope["cwd"] == "packages/billing"
    assert "pytest" in scope["commands"]["test"]
    assert "PAIR_COVERAGE_XML" in scope["commands"]["coverage"]


def test_c17_init_registers_the_docs_source_it_found(fresh):
    fresh.ok("init")
    config = tomlio.load(fresh.root / "pair/config.toml")
    kinds = {entry["type"] for entry in config.get("sources", [])}
    assert "docs" in kinds


def test_c17_boundaries_record_the_edges_that_already_exist(fresh):
    fresh.write("packages/billing/src/money.py", "import shared\n\n\ndef cents(x):\n    return 1\n")
    fresh.git("add", "-A")
    fresh.git("commit", "-q", "-m", "billing uses shared")
    fresh.ok("init")
    text = (fresh.root / "pair/rules/boundaries.toml").read_text()
    data = tomlio.loads(text)
    assert data["modules"]["billing"]["may_depend_on"] == ["shared"]
    assert "observed 2026-09-28" in text


def test_c17_settings_json_declares_the_plugin_with_a_relative_path(fresh):
    fresh.ok("init")
    data = json.loads((fresh.root / ".claude/settings.json").read_text())
    assert data["extraKnownMarketplaces"]["pair-local"]["source"]["path"] == "./pair"
    assert data["enabledPlugins"]["pair@pair-local"] is True


def test_c17_init_merges_into_an_existing_settings_file(fresh):
    fresh.write(".claude/settings.json", json.dumps({"model": "something", "enabledPlugins":
                                                     {"other@market": True}}))
    fresh.git("add", "-A")
    fresh.git("commit", "-q", "-m", "existing settings")
    fresh.ok("init")
    data = json.loads((fresh.root / ".claude/settings.json").read_text())
    assert data["model"] == "something"
    assert data["enabledPlugins"]["other@market"] is True
    assert data["enabledPlugins"]["pair@pair-local"] is True


def test_c17_init_never_writes_settings_local_json(fresh):
    fresh.ok("init")
    assert not (fresh.root / ".claude/settings.local.json").exists()


def test_c17_init_appends_codeowners_without_rewriting_it(fresh):
    fresh.write(".github/CODEOWNERS", "/src/ @someone\n")
    fresh.git("add", "-A")
    fresh.git("commit", "-q", "-m", "existing owners")
    fresh.ok("init")
    text = (fresh.root / ".github/CODEOWNERS").read_text()
    assert text.startswith("/src/ @someone\n")
    assert "/pair/" in text
    assert "/.github/" in text


def test_c17_init_writes_nothing_else_outside_pair(fresh):
    before = set(gitcmd.lines(fresh.root, "ls-files"))
    fresh.ok("init")
    after = set(gitcmd.lines(fresh.root, "ls-files"))
    added_outside = {rel for rel in after - before if not rel.startswith("pair/")}
    assert added_outside == {".github/workflows/pair.yml", ".github/CODEOWNERS",
                             "githooks/commit-msg", ".claude/settings.json", "AGENTS.md"}


def test_c17_init_refuses_outside_a_git_repository(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out, err = Fresh(plain).run("init")
    assert code == 1
    assert "not a git repository" in err


def test_c17_init_prints_both_activation_costs(fresh):
    out = fresh.ok("init")
    assert "no install step" in out
    assert "git config core.hooksPath githooks" in out


def test_the_committed_commit_msg_hook_refuses_ai_attribution(fresh):
    fresh.ok("init")
    fresh.git("config", "core.hooksPath", "githooks")
    fresh.write("notes.txt", "x\n")
    fresh.git("add", "notes.txt")
    done = fresh.git("commit", "-m",
                     "feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n", check=False)
    assert done.returncode != 0
    assert "authorship is the engineer's" in (done.stdout + done.stderr)

    done = fresh.git("commit", "-m", "feat: x\n\nCo-Authored-By: Bob <bob@example.invalid>\n",
                     check=False)
    assert done.returncode == 0


# -- C20 -----------------------------------------------------------------------------------------

def make_engine(folder, version="0.2.0", supported=3):
    """A minimal engine to upgrade to, with two migrations that record the order they ran in."""
    engine = folder / "engine"
    (engine / "lib" / "pair").mkdir(parents=True)
    (engine / "VERSION").write_text(version + "\n")
    (engine / "lib" / "pair" / "config.py").write_text(
        f"SUPPORTED_FORMAT = {supported}\n")
    (engine / "defaults").mkdir()
    (engine / "defaults" / "config.toml").write_text(
        (ENGINE / "defaults" / "config.toml").read_text())
    (engine / "defaults" / "rules.md").write_text((ENGINE / "defaults" / "rules.md").read_text())
    migrations = engine / "migrations"
    migrations.mkdir()
    for number, name in ((2, "second"), (3, "third")):
        (migrations / f"{number:03d}_{name}.py").write_text(
            "def migrate(layout):\n"
            "    path = layout.pair_dir / 'migration-order.txt'\n"
            f"    line = '{number:03d}_{name}\\n'\n"
            "    existing = path.read_text() if path.is_file() else ''\n"
            "    if line not in existing:\n"
            "        path.write_text(existing + line)\n")
    return engine


def test_c20_upgrade_runs_migrations_in_order(repo, cli, tmp_path):
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source)
    cli.ok("upgrade", "--from", str(source))

    order = (repo.root / "pair" / "migration-order.txt").read_text().splitlines()
    assert order == ["002_second", "003_third"]
    assert (repo.layout.engine / "VERSION").read_text().strip() == "0.2.0"
    config = tomlio.load(repo.layout.config)
    assert config["engine"] == "0.2.0"
    assert config["format"] == 3


def test_c20_migrations_are_idempotent(repo, cli, tmp_path):
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source)
    cli.ok("upgrade", "--from", str(source))
    # No session: after the bump the config is deliberately unreadable by the old engine.
    from pair import paths, upgrade as upgrade_mod
    layout = paths.Layout(repo.root)
    upgrade_mod.run_migrations(layout, layout.engine, 1, 3)
    order = (repo.root / "pair" / "migration-order.txt").read_text().splitlines()
    assert order == ["002_second", "003_third"]


def test_c20_upgrade_stamps_every_task_state(repo, cli, tmp_path):
    cli.ok("start", "142-instalments")
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source)
    cli.ok("upgrade", "--from", str(source))
    data = json.loads(repo.layout.state("142-instalments").read_text())
    assert data["format"] == 3


def test_c20_upgrade_commits_with_the_action_trailer(repo, cli, tmp_path):
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source)
    cli.ok("upgrade", "--from", str(source))
    from pair import commit
    trailers = commit.read_trailers(gitcmd.commit_message(repo.root, gitcmd.head(repo.root)))
    assert trailers["Pair-Action"] == "upgrade"


def test_a_too_new_format_stops_every_command(repo, cli, tmp_path):
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source, version="0.9.0", supported=9)
    cli.ok("upgrade", "--from", str(source))
    # Now downgrade the engine's own SUPPORTED_FORMAT by running the old code against it.
    code, out, err = cli.run("status")
    assert code == 1
    assert "upgrade the engine" in err


def test_upgrade_refuses_a_folder_that_is_not_an_engine(repo, cli, tmp_path):
    empty = tmp_path / "not-an-engine"
    empty.mkdir()
    code, out, err = cli.run("upgrade", "--from", str(empty))
    assert code == 1
    assert "does not look like a pair engine" in err


# -- C32 -----------------------------------------------------------------------------------------

VENDORS = re.compile(r"(?i)\b(claude|anthropic|copilot|chatgpt|openai|gemini|codeium|devin)\b")


def test_c32_no_template_or_default_names_a_vendor():
    offenders = []
    for folder in (ENGINE / "templates", ENGINE / "defaults"):
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if VENDORS.search(line) and "commit-msg" not in path.name:
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "\n".join(offenders)


def test_c32_nothing_the_cli_generates_names_a_vendor(fresh):
    fresh.ok("init")
    fresh.git("config", "core.hooksPath", "githooks")
    generated = [rel for rel in gitcmd.lines(fresh.root, "ls-files")
                 if rel.startswith("pair/") or rel in (".github/workflows/pair.yml", "AGENTS.md",
                                                       ".github/CODEOWNERS")]
    offenders = []
    for rel in generated:
        for number, line in enumerate((fresh.root / rel).read_text().splitlines(), 1):
            if VENDORS.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    assert offenders == [], "\n".join(offenders)


def test_c32_no_commit_message_pair_writes_names_a_vendor(repo, cli):
    from engine_helpers import run_full_task
    run_full_task(repo, cli)
    for sha in gitcmd.lines(repo.root, "log", "--format=%H"):
        message = gitcmd.commit_message(repo.root, sha)
        assert not VENDORS.search(message), message


# -- C37 -----------------------------------------------------------------------------------------

def test_c37_no_command_writes_outside_the_repository(fresh, tmp_path, monkeypatch):
    """`$HOME` points at an empty directory; it must still be empty afterwards (D15)."""
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    gitconfig = tmp_path / "global-gitconfig"
    gitconfig.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))

    fresh.ok("init")
    fresh.run("doctor")
    fresh.ok("baseline")
    source = tmp_path / "newer"
    source.mkdir()
    make_engine(source)
    fresh.ok("upgrade", "--from", str(source))

    assert list(home.iterdir()) == [], f"HOME was written to: {list(home.iterdir())}"
    assert gitconfig.read_text() == "", "the global git config was written to"


def test_c37_no_argument_list_uses_user_scope_or_global_git_config():
    """Read the shipped code: the forms SPEC 4 forbids must not be there to be run (D15).

    `--scope` is one of pair's own flags, so the check is narrow: `--global` as its own argument,
    and a user-scoped install anywhere.
    """
    global_flag = re.compile(r'[\'"]--global[\'"]')
    user_scope = re.compile(r'--scope[\s\'",]+user')
    offenders = []
    for path in sorted((ENGINE / "lib").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if global_flag.search(line) or user_scope.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "\n".join(offenders)


def test_c37_nothing_pair_writes_resolves_outside_the_root(fresh):
    """`init.apply` refuses any path that leaves the repository."""
    from pair import init as init_mod
    session = flow.Session.open(str(fresh.root), confirm=lambda q, e: True) \
        if (fresh.root / "pair/config.toml").is_file() else None
    fresh.ok("init")
    session = flow.Session.open(str(fresh.root), confirm=lambda q, e: True)
    plan = init_mod.Plan()
    plan.write("../escaped.txt", "nope")
    from pair.errors import CheckFailed
    with pytest.raises(CheckFailed) as caught:
        init_mod.apply(session, plan)
    assert "outside the repository" in str(caught.value)
