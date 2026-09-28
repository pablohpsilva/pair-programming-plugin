import pytest

from pair import config, paths, scopes
from pair.errors import CheckFailed

CONFIG = """\
format = 1
engine = "0.1.0"
governance = "0.1"
[project]
name = "p"
default_branch = "main"
"""

BILLING = """\
path = "packages/billing"
cwd = "packages/billing"
timeout_seconds = 300
no_tests_exit_codes = [5]
module = "billing"

[commands]
test = "pytest -q"
coverage = "pytest --cov"
lint = ""
validate = ""
migrate_check = ""
"""

REPO = """\
path = ""
cwd = "."
module = ""

[commands]
test = ""
coverage = ""
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pair").mkdir()
    (tmp_path / "pair" / "config.toml").write_text(CONFIG)
    layout = paths.Layout(tmp_path)
    (layout.scopes_dir / "_repo").mkdir(parents=True)
    (layout.scopes_dir / "_repo" / "scope.toml").write_text(REPO)
    folder = layout.scopes_dir / "packages" / "billing"
    folder.mkdir(parents=True)
    (folder / "scope.toml").write_text(BILLING)
    return layout, config.load(layout)


def load(repo):
    layout, cfg = repo
    return scopes.Scopes.load(layout, cfg)


def test_scopes_load_with_their_commands(repo):
    found = load(repo)
    assert len(found) == 2
    billing = found.by_name("packages/billing")
    assert billing.command("test") == "pytest -q"
    assert billing.has("coverage")
    assert not billing.has("validate")
    assert billing.no_tests_exit_codes == [5]
    assert billing.module == "billing"
    assert billing.timeout_seconds == 300


def test_the_fallback_scope_is_found_by_either_name(repo):
    found = load(repo)
    assert found.fallback.path == ""
    assert found.by_name("_repo") is found.fallback
    assert found.by_name("") is found.fallback
    assert found.fallback.name == "_repo"
    assert found.fallback.slug == "_repo"


def test_the_longest_matching_path_wins(repo):
    layout, cfg = repo
    inner = layout.scopes_dir / "packages" / "billing" / "api"
    inner.mkdir(parents=True)
    (inner / "scope.toml").write_text(
        BILLING.replace('packages/billing"', 'packages/billing/api"').replace(
            'module = "billing"', 'module = "billing-api"'))
    found = scopes.Scopes.load(layout, cfg)
    assert found.resolve("packages/billing/api/src/x.py").path == "packages/billing/api"
    assert found.resolve("packages/billing/src/x.py").path == "packages/billing"


def test_an_unmatched_file_falls_back_to_repo(repo):
    assert load(repo).resolve("tools/script.py").path == ""


def test_a_prefix_only_matches_at_a_path_boundary(repo):
    assert load(repo).resolve("packages/billing-legacy/x.py").path == ""


def test_the_scope_folder_itself_resolves(repo):
    assert load(repo).resolve("packages/billing").path == "packages/billing"


def test_files_under_pair_have_no_scope(repo):
    found = load(repo)
    assert found.resolve("pair/config.toml") is None
    assert found.resolve("pair/tasks/142/plan.md") is None
    assert found.resolve("AGENTS.md") is None


def test_the_doc_exceptions_do_have_a_scope(repo):
    found = load(repo)
    assert found.resolve("pair/knowledge/billing.md") is not None
    assert found.resolve("pair/scopes/packages/billing/SUMMARY.md") is not None


def test_the_scope_target_defaults_to_the_project_target(repo):
    assert load(repo).by_name("packages/billing").target == 95


def test_a_scope_may_raise_its_target(repo):
    layout, cfg = repo
    path = layout.scopes_dir / "packages" / "billing" / "scope.toml"
    path.write_text(BILLING + "\n[coverage]\ntarget = 99\n")
    assert scopes.Scopes.load(layout, cfg).by_name("packages/billing").target == 99


def test_a_scope_may_not_lower_its_target(repo):
    layout, cfg = repo
    path = layout.scopes_dir / "packages" / "billing" / "scope.toml"
    path.write_text(BILLING + "\n[coverage]\ntarget = 80\n")
    with pytest.raises(CheckFailed) as caught:
        scopes.Scopes.load(layout, cfg)
    assert "may only raise it" in "\n".join(caught.value.details)


def test_a_declared_path_must_match_its_folder(repo):
    layout, cfg = repo
    path = layout.scopes_dir / "packages" / "billing" / "scope.toml"
    path.write_text(BILLING.replace('path = "packages/billing"', 'path = "packages/other"'))
    with pytest.raises(CheckFailed) as caught:
        scopes.Scopes.load(layout, cfg)
    assert "the folder says" in "\n".join(caught.value.details)


def test_an_unknown_key_in_a_scope_is_an_error(repo):
    layout, cfg = repo
    path = layout.scopes_dir / "packages" / "billing" / "scope.toml"
    path.write_text(BILLING + "\ntimeoutt = 5\n")
    with pytest.raises(CheckFailed) as caught:
        scopes.Scopes.load(layout, cfg)
    assert "timeoutt: is not a known key" in "\n".join(caught.value.details)


def test_resolve_all_returns_the_single_scope(repo):
    found = load(repo)
    scope, problem = found.resolve_all(["packages/billing/src/a.py", "packages/billing/src/b.py"])
    assert problem is None
    assert scope.path == "packages/billing"


def test_resolve_all_refuses_a_step_spanning_two_scopes(repo):
    scope, problem = load(repo).resolve_all(["packages/billing/src/a.py", "tools/b.py"])
    assert scope is None
    assert "spans more than one scope" in problem


def test_resolve_all_names_a_file_with_no_scope(repo):
    scope, problem = load(repo).resolve_all(["pair/config.toml"])
    assert scope is None
    assert "belongs to no scope: pair/config.toml" in problem


def test_resolve_all_on_nothing(repo):
    scope, problem = load(repo).resolve_all([])
    assert scope is None
    assert problem == "has no files"


def test_the_work_dir_is_the_scope_cwd(repo):
    layout, _ = repo
    assert load(repo).by_name("packages/billing").work_dir == layout.root / "packages/billing"
    assert load(repo).fallback.work_dir == layout.root / "."
