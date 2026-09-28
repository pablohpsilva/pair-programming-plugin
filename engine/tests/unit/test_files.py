import pytest

from pair import config, files, paths

CONFIG = """\
format = 1
engine = "0.1.0"
governance = "0.1"
[project]
name = "p"
default_branch = "main"
"""


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "pair").mkdir()
    (tmp_path / "pair" / "config.toml").write_text(CONFIG)
    return config.load(paths.Layout(tmp_path))


@pytest.mark.parametrize("rel,expected", [
    ("packages/billing/tests/test_money.py", "tests"),
    ("packages/billing/test_money.py", "tests"),
    ("src/money_test.go", "tests"),
    ("web/src/thing.test.ts", "tests"),
    ("web/src/thing.spec.tsx", "tests"),
    ("api/src/ThingTest.java", "tests"),
    ("features/checkout.feature", "tests"),
    ("db/migrations/001_init.sql", "migrations"),
    ("service/migrate/002.py", "migrations"),
    ("packages/billing/pyproject.toml", "dependencies"),
    ("package.json", "dependencies"),
    ("go.sum", "dependencies"),
    ("uv.lock", "dependencies"),
    ("docs/architecture.md", "docs"),
    ("README.txt", "docs"),
    ("ops/values.yaml", "config"),
    ("Dockerfile", "config"),
    ("Makefile", "config"),
    ("packages/billing/src/money.py", "code"),
    ("web/src/App.tsx", "code"),
])
def test_classification_follows_spec_order(cfg, rel, expected):
    assert files.classify(rel, cfg) == expected


def test_tests_win_over_config_when_both_match(cfg):
    # a JSON file inside tests/ is a test file: `tests` comes first in the order
    assert files.classify("packages/billing/tests/fixture.json", cfg) == "tests"


def test_migrations_win_over_code(cfg):
    assert files.classify("db/migrations/x.py", cfg) == "migrations"


def test_dependencies_win_over_config(cfg):
    # pyproject.toml matches both **/*.toml and **/pyproject.toml; dependencies is checked first
    assert files.classify("pyproject.toml", cfg) == "dependencies"


def test_a_project_may_override_the_globs(cfg):
    cfg.data["files"]["tests"] = ["spec/**"]
    assert files.classify("spec/a.py", cfg) == "tests"
    assert files.classify("packages/billing/tests/test_x.py", cfg) == "code"


@pytest.mark.parametrize("kind,allowed", [
    ("stub", "code"), ("test", "tests"), ("char", "tests"), ("code", "code"),
    ("refactor", "code"), ("doc", "docs"), ("config", "config"), ("migration", "migrations"),
])
def test_each_kind_allows_its_class(kind, allowed):
    assert files.is_allowed(kind, allowed)


def test_config_steps_also_allow_dependency_files():
    assert files.is_allowed("config", "dependencies")


def test_only_a_migration_step_may_touch_a_migration_file():
    for kind in files.KINDS:
        assert files.is_allowed(kind, "migrations") == (kind == "migration")


def test_a_refactor_takes_test_files_only_with_include_tests():
    assert not files.is_allowed("refactor", "tests")
    assert files.is_allowed("refactor", "tests", include_tests=True)
    assert files.is_allowed("refactor", "code", include_tests=True)


def test_include_tests_does_not_widen_another_kind():
    assert not files.is_allowed("code", "tests", include_tests=True)


def test_the_command_each_kind_runs():
    assert files.command_for("test") == "test"
    assert files.command_for("code") == "coverage"
    assert files.command_for("migration") == "migrate_check"
    assert files.command_for("doc") is None
