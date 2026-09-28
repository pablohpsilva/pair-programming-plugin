import subprocess

import pytest

from pair import gitcmd
from pair.errors import CheckFailed


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    gitcmd.run(root, "init", "-q", "-b", "main", ".")
    gitcmd.run(root, "config", "user.name", "T")
    gitcmd.run(root, "config", "user.email", "t@example.invalid")
    (root / "a.py").write_text("one\ntwo\n")
    gitcmd.run(root, "add", "-A")
    gitcmd.run(root, "commit", "-q", "-m", "first")
    return root


def test_is_repo_and_head(repo, tmp_path):
    assert gitcmd.is_repo(repo)
    assert not gitcmd.is_repo(tmp_path)
    assert len(gitcmd.head(repo)) == 40
    assert gitcmd.current_branch(repo) == "main"


def test_a_failing_command_raises_with_the_stderr(repo):
    with pytest.raises(CheckFailed) as caught:
        gitcmd.run(repo, "rev-parse", "nope-not-a-ref")
    assert "git rev-parse nope-not-a-ref failed" in str(caught.value)
    assert caught.value.details


def test_status_reports_modified_and_untracked(repo):
    (repo / "a.py").write_text("one\nchanged\n")
    (repo / "new.py").write_text("x\n")
    codes = dict((path, code) for code, path in gitcmd.status_porcelain(repo))
    assert codes["a.py"] == "M"
    assert codes["new.py"] == "??"
    assert gitcmd.modified_tracked(repo) == ["a.py"]
    assert gitcmd.untracked(repo) == ["new.py"]


def test_modified_tracked_can_exclude_a_prefix(repo):
    (repo / "pair").mkdir()
    (repo / "pair" / "x").write_text("1")
    gitcmd.run(repo, "add", "-A")
    gitcmd.run(repo, "commit", "-q", "-m", "second")
    (repo / "pair" / "x").write_text("2")
    (repo / "a.py").write_text("changed\n")
    assert gitcmd.modified_tracked(repo, exclude_prefix="pair/") == ["a.py"]


def test_changed_lines_of_a_tracked_file(repo):
    (repo / "a.py").write_text("one\ntwo\nthree\nfour\n")
    assert gitcmd.changed_lines(repo, "a.py") == {3, 4}


def test_changed_lines_of_an_untracked_file_is_every_line(repo):
    (repo / "new.py").write_text("1\n2\n3\n")
    assert gitcmd.changed_lines(repo, "new.py") == {1, 2, 3}


def test_changed_lines_of_a_modified_middle_line(repo):
    (repo / "a.py").write_text("one\nCHANGED\n")
    assert gitcmd.changed_lines(repo, "a.py") == {2}


def test_is_tracked(repo):
    (repo / "new.py").write_text("x")
    assert gitcmd.is_tracked(repo, "a.py")
    assert not gitcmd.is_tracked(repo, "new.py")


def test_commit_only_commits_exactly_the_listed_paths(repo):
    (repo / "a.py").write_text("touched\n")
    (repo / "b.py").write_text("also touched\n")
    sha = gitcmd.commit_only(repo, "only a", ["a.py"])
    assert gitcmd.commit_files(repo, sha) == ["a.py"]
    assert gitcmd.modified_tracked(repo) == []
    assert gitcmd.untracked(repo) == ["b.py"]


def test_commit_only_refuses_when_no_listed_path_exists(repo):
    with pytest.raises(CheckFailed) as caught:
        gitcmd.commit_only(repo, "nothing", ["gone.py"])
    assert "nothing to commit" in str(caught.value)


def test_find_commits_matches_every_grep(repo):
    (repo / "a.py").write_text("x\n")
    gitcmd.commit_only(repo, "step\n\nPair-Task: t1\nPair-Step: 2\n", ["a.py"])
    (repo / "a.py").write_text("y\n")
    gitcmd.commit_only(repo, "step\n\nPair-Task: t1\nPair-Step: 3\n", ["a.py"])
    found = gitcmd.find_commits(repo, "Pair-Task: t1", "Pair-Step: 2")
    assert len(found) == 1
    assert "Pair-Step: 2" in gitcmd.commit_message(repo, found[0])


def test_commits_in_range_excludes_merges(repo):
    gitcmd.run(repo, "checkout", "-q", "-b", "side")
    (repo / "s.py").write_text("s\n")
    gitcmd.commit_only(repo, "side work", ["s.py"])
    gitcmd.run(repo, "checkout", "-q", "main")
    (repo / "m.py").write_text("m\n")
    gitcmd.commit_only(repo, "main work", ["m.py"])
    base = gitcmd.head(repo)
    gitcmd.run(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    shas = gitcmd.commits_in_range(repo, base, "HEAD")
    messages = [gitcmd.commit_message(repo, s).splitlines()[0] for s in shas]
    assert "merge side" not in messages


def test_revert_reports_a_conflict_without_resolving_it(repo):
    (repo / "a.py").write_text("v2\n")
    first = gitcmd.commit_only(repo, "v2", ["a.py"])
    (repo / "a.py").write_text("v3\n")
    gitcmd.commit_only(repo, "v3", ["a.py"])
    ok, output = gitcmd.revert(repo, first)
    assert not ok
    assert output
    gitcmd.run(repo, "revert", "--abort", check=False)


def test_show_returns_none_for_a_path_absent_at_that_revision(repo):
    assert gitcmd.show(repo, "HEAD", "a.py") == "one\ntwo\n"
    assert gitcmd.show(repo, "HEAD", "never.py") is None


def test_config_get_returns_none_when_unset(repo):
    assert gitcmd.config_get(repo, "core.hooksPath") is None
    gitcmd.run(repo, "config", "core.hooksPath", "githooks")
    assert gitcmd.config_get(repo, "core.hooksPath") == "githooks"


def test_last_commit_date_is_none_for_an_untracked_file(repo):
    (repo / "new.py").write_text("x")
    assert gitcmd.last_commit_date(repo, "a.py")
    assert gitcmd.last_commit_date(repo, "new.py") is None
