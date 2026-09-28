import pathlib

import pytest

from pair import paths


@pytest.fixture
def layout(tmp_path):
    (tmp_path / "pair").mkdir()
    (tmp_path / "pair" / "config.toml").write_text("format = 1\n")
    return paths.Layout(tmp_path)


@pytest.mark.parametrize("rel", [
    "pair/engine/lib/pair/cli.py", "pair/config.toml", "pair/rules/overrides.md",
    "pair/scopes/packages/billing/scope.toml", "pair/scopes/packages/billing/RULES.md",
    "pair/learnings/billing.md", "pair/local/active", "pair/tasks/142/state.json",
    ".github/workflows/pair.yml", "CODEOWNERS", "AGENTS.md", "CLAUDE.md",
    ".claude/settings.json", ".git/config", "pair/reports/2026-09.md",
])
def test_protected_paths(rel):
    assert paths.is_protected(rel), rel


@pytest.mark.parametrize("rel", [
    "pair/tasks/142/plan.md", "pair/tasks/142/log.md", "pair/tasks/142/walkthrough.md",
    "pair/knowledge/billing.md", "pair/scopes/packages/billing/SUMMARY.md",
    "packages/billing/src/x.py", "README.md",
])
def test_not_protected(rel):
    assert paths.is_protected(rel) is None, rel


def test_protect_extra_is_honoured():
    assert paths.is_protected("infra/main.tf", extra=["infra/**"]) == "infra/**"


def test_state_json_is_protected_only_one_level_down():
    assert paths.is_protected("pair/tasks/142/state.json")
    assert paths.is_protected("pair/tasks/142/nested/state.json") is None


def test_no_scope(layout):
    assert paths.has_no_scope("pair/config.toml")
    assert paths.has_no_scope("pair/tasks/142/plan.md")
    assert paths.has_no_scope("AGENTS.md")
    assert paths.has_no_scope(".claude/settings.json")
    assert not paths.has_no_scope("pair/knowledge/billing.md")
    assert not paths.has_no_scope("pair/scopes/packages/billing/SUMMARY.md")
    assert not paths.has_no_scope("packages/billing/src/x.py")


def test_scope_slug():
    assert paths.scope_slug("packages/billing") == "packages__billing"
    assert paths.scope_slug("") == "_repo"


def test_rel_resolves_dotdot_and_refuses_outside(layout):
    assert layout.rel(layout.root / "a" / ".." / "b.py") == "b.py"
    assert layout.rel("/etc/passwd") is None
    assert layout.rel("b.py") == "b.py"


def test_rel_follows_a_symlinked_directory_out_of_the_root(layout, tmp_path):
    outside = tmp_path.parent / "outside-the-root"
    outside.mkdir(exist_ok=True)
    (layout.root / "link").symlink_to(outside, target_is_directory=True)
    assert layout.rel(layout.root / "link" / "x.py") is None


def test_find_root_walks_up(layout, monkeypatch):
    deep = layout.root / "a" / "b"
    deep.mkdir(parents=True)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert paths.find_root(deep) == layout.root
    assert paths.find_root(pathlib.Path(layout.root).parent) is None


def test_find_root_prefers_the_declared_project_dir(layout, tmp_path, monkeypatch):
    other = tmp_path / "other"
    (other / "pair").mkdir(parents=True)
    (other / "pair" / "config.toml").write_text("")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(other))
    assert paths.find_root(layout.root) == other.resolve()


def test_declared_project_dir_is_ignored_when_it_is_not_a_pair_repo(layout, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nope"))
    assert paths.find_root(layout.root) == layout.root


def test_active_task_is_none_when_blank_or_missing(layout):
    assert layout.active_task() is None
    layout.local.mkdir(parents=True)
    layout.active_file.write_text("  \n")
    assert layout.active_task() is None
    layout.active_file.write_text("142-instalments\n")
    assert layout.active_task() == "142-instalments"
