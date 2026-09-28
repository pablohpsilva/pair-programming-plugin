import pytest

from pair import commit, gitcmd
from pair.errors import CheckFailed


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    gitcmd.run(root, "init", "-q", "-b", "main", ".")
    gitcmd.run(root, "config", "user.name", "Ana")
    gitcmd.run(root, "config", "user.email", "ana@example.invalid")
    (root / "seed.txt").write_text("seed\n")
    gitcmd.run(root, "add", "-A")
    gitcmd.run(root, "commit", "-q", "-m", "seed")
    return root


def test_commit_types_by_kind():
    assert commit.type_for("stub") == "feat"
    assert commit.type_for("code") == "feat"
    assert commit.type_for("migration") == "feat"
    assert commit.type_for("test") == "test"
    assert commit.type_for("char") == "test"
    assert commit.type_for("refactor") == "refactor"
    assert commit.type_for("doc") == "docs"
    assert commit.type_for("config") == "chore"


def test_a_plan_titled_fix_makes_it_a_fix():
    assert commit.type_for("code", "Fix rounding of instalments") == "fix"
    assert commit.type_for("test", "Fix rounding") == "test"      # only feat becomes fix


def test_the_subject_names_the_scope_slug_and_behavior():
    assert commit.subject("code", "packages__billing", "splits evenly") == \
        "feat(packages__billing): splits evenly"


def test_the_message_is_a_subject_a_blank_line_and_trailers():
    text = commit.message("feat(b): x", [("Pair-Task", "142"), ("Pair-Step", 3)])
    assert text == "feat(b): x\n\nPair-Task: 142\nPair-Step: 3\n"


def test_empty_trailer_values_are_dropped():
    text = commit.message("s", [("Pair-Task", ""), ("Pair-Action", "ok"), ("Pair-Kind", None)])
    assert text == "s\n\nPair-Action: ok\n"


def test_trailers_for_ok_are_in_spec_order():
    found = commit.trailers_for("ok", "0.1", task="142", step=3, kind="code", approved_by="@ana")
    assert [name for name, _ in found] == [
        "Pair-Task", "Pair-Action", "Pair-Step", "Pair-Kind", "Pair-Approved-By",
        "Pair-Governance"]


def test_no_attribution_trailer_is_ever_added():
    text = commit.message("feat(b): x", commit.trailers_for("ok", "0.1", task="t", step=1,
                                                            kind="code", approved_by="@ana"))
    lowered = text.lower()
    assert "co-authored-by" not in lowered
    assert "generated" not in lowered


def test_read_trailers_picks_up_only_pair_keys():
    text = "feat(b): x\n\nPair-Task: 142\nSigned-off-by: Ana\nPair-Step: 3\n"
    assert commit.read_trailers(text) == {"Pair-Task": "142", "Pair-Step": "3"}


def test_read_trailers_of_an_empty_message():
    assert commit.read_trailers("") == {}
    assert commit.read_trailers(None) == {}


def test_make_commits_only_the_listed_paths(repo):
    (repo / "a.py").write_text("a\n")
    (repo / "b.py").write_text("b\n")
    gitcmd.run(repo, "add", "a.py", "b.py")
    gitcmd.run(repo, "commit", "-q", "-m", "both")
    (repo / "a.py").write_text("a2\n")
    (repo / "b.py").write_text("b2\n")
    sha, warnings = commit.make(repo, ["a.py"], "feat(x): a", [("Pair-Action", "ok")])
    assert gitcmd.commit_files(repo, sha) == ["a.py"]
    assert warnings == []


def test_make_refuses_when_another_tracked_file_is_staged(repo):
    (repo / "a.py").write_text("a\n")
    (repo / "b.py").write_text("b\n")
    gitcmd.run(repo, "add", "-A")
    gitcmd.run(repo, "commit", "-q", "-m", "both")
    (repo / "a.py").write_text("a2\n")
    (repo / "b.py").write_text("b2\n")
    gitcmd.run(repo, "add", "b.py")
    with pytest.raises(CheckFailed) as caught:
        commit.make(repo, ["a.py"], "feat(x): a", [("Pair-Action", "ok")])
    message = "\n".join(caught.value.lines())
    assert "another tracked file is staged" in message
    assert "b.py" in message
    assert "git restore --staged" in message


def test_untracked_extras_are_a_warning_not_a_refusal(repo):
    (repo / "a.py").write_text("a\n")
    (repo / "junk.log").write_text("noise\n")
    sha, warnings = commit.make(repo, ["a.py"], "feat(x): a", [("Pair-Action", "ok")])
    assert gitcmd.commit_files(repo, sha) == ["a.py"]
    assert warnings and "junk.log" in warnings[0]


def test_action_commit_writes_the_trailers(repo):
    (repo / "a.py").write_text("a\n")
    sha, _ = commit.action_commit(repo, ["a.py"], "ok", "0.1", "feat(x): a", task="142", step=2,
                                  kind="code", approved_by="@ana")
    trailers = commit.read_trailers(gitcmd.commit_message(repo, sha))
    assert trailers == {"Pair-Task": "142", "Pair-Action": "ok", "Pair-Step": "2",
                        "Pair-Kind": "code", "Pair-Approved-By": "@ana",
                        "Pair-Governance": "0.1"}


def test_the_commit_is_authored_by_the_engineer(repo):
    (repo / "a.py").write_text("a\n")
    sha, _ = commit.action_commit(repo, ["a.py"], "ok", "0.1", "feat(x): a", task="142")
    author = gitcmd.out(repo, "log", "-1", "--format=%an <%ae>", sha)
    assert author == "Ana <ana@example.invalid>"
