"""The C-numbered acceptance tests of SPEC 22, in order."""

import json

import pytest

from pair import commit, gitcmd, state as state_mod

PLAN = """\
# Task 142-instalments: split an invoice into instalments
\U0001F3AF Goal: split an amount evenly (requirement: docs/req.md)
\U0001F9ED Approach: a small value object
\U0001F50E Explored: searched instalment → nothing reusable
\U0001F4DA Rules & lessons: TEST-001
\U0001F500 Alternatives: a service method, rejected as harder to test
⚠️ Risks: rounding
\U0001F465 Mode: agent-drives · Governance: 0.1

## Steps
| # | Kind | Files | Behavior |
|---|---|---|---|
| 1 | stub | `packages/billing/src/instalments.py` | InstalmentPlan signature |
| 2 | test | `packages/billing/tests/test_instalments.py` | splits evenly |
| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |

## Tests first
- Scenarios: happy, remainder, zero parts

## Dependencies

## Waivers
"""

WALKTHROUGH = """\
# 142-instalments

## What was built
An instalment plan value object.

## Where it fits
packages/billing, used by invoicing.

## Key decisions
Decimal, not float.

## Waivers used
none

## How to test it
python -m pytest packages/billing

## How to roll it back
pair revert 142-instalments

## Possibly stale knowledge
none

## Lessons
none
"""


def write_plan(repo, text=PLAN, task="142-instalments"):
    repo.write(f"pair/tasks/{task}/plan.md", text)


def start(repo, cli, task="142-instalments", mode=None):
    argv = ["start", task] + (["--mode", mode] if mode else [])
    cli.ok(*argv)
    return state_mod.State.load(repo.layout, task)


def approve(repo, cli, task="142-instalments", text=PLAN):
    write_plan(repo, text, task)
    cli.ok("approve")
    return state_mod.State.load(repo.layout, task)


# -- C1 ----------------------------------------------------------------------------------------

def test_c1_start_creates_the_branch_the_phase_and_a_commit(repo, cli):
    before = gitcmd.head(repo.root)
    state = start(repo, cli)
    assert state.phase == "planning"
    assert state.status == "active"
    assert state.owner == "@ana"
    assert gitcmd.current_branch(repo.root) == "pair/142-instalments"
    assert gitcmd.head(repo.root) != before
    trailers = commit.read_trailers(gitcmd.commit_message(repo.root, gitcmd.head(repo.root)))
    assert trailers["Pair-Action"] == "start"
    assert trailers["Pair-Task"] == "142-instalments"
    assert repo.layout.active_task() == "142-instalments"


def test_c1_start_refuses_a_dirty_tree_outside_the_task_folder(repo, cli):
    repo.write("packages/billing/src/money.py", "changed\n")
    code, out, err = cli.run("start", "142-instalments")
    assert code == 1
    assert "uncommitted changes outside pair/tasks/" in err


def test_c1_start_without_a_terminal_is_refused(repo, cli):
    code, out, err = cli.run("start", "142-instalments", answer=False)
    assert code == 3
    assert "not confirmed" in err


def test_c1_start_asks_for_the_task_id(repo, cli):
    cli.ok("start", "142-instalments")
    assert cli.questions[-1] == ("Type the task id to confirm `pair start`:", "142-instalments")


# -- C2 ----------------------------------------------------------------------------------------

def test_c2_approve_refuses_when_plan_check_fails(repo, cli):
    start(repo, cli)
    write_plan(repo, PLAN.replace("⚠️ Risks: rounding", ""))
    code, out, err = cli.run("approve")
    assert code == 1
    assert "plan-check does not pass" in err
    assert "Risks line is missing" in err
    assert state_mod.State.load(repo.layout, "142-instalments").phase == "planning"


def test_c2_approve_snapshots_the_steps_and_the_plan_hash(repo, cli):
    start(repo, cli)
    state = approve(repo, cli)
    assert state.phase == "stepping"
    assert [step.n for step in state.steps] == [1, 2, 3]
    assert state.approval["by"] == "@ana"
    assert state.step(1).approved_plan_sha256 == state.approval["plan_sha256"]
    assert state.current_step == 1


def test_c2_plan_check_alone_reports_every_problem(repo, cli):
    start(repo, cli)
    write_plan(repo, PLAN.replace("| 2 | test | `packages/billing/tests/test_instalments.py` | "
                                  "splits evenly |\n", ""))
    code, out, err = cli.run("plan-check")
    assert code == 1
    assert "must come before the first `code` step" in err


# -- C3, C4 ------------------------------------------------------------------------------------

def test_c3_done_on_a_test_step_that_passes_exits_one(repo, cli):
    start(repo, cli)
    approve(repo, cli)
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")                                       # step 1, the stub, is green
    cli.ok("ok")
    repo.write("packages/billing/tests/test_instalments.py", "def test_x():\n    assert True\n")
    code, out, err = cli.run("done")
    assert code == 1
    assert "proves nothing" in err
    assert state_mod.State.load(repo.layout, "142-instalments").phase == "stepping"


def test_c4_done_with_an_import_error_exits_one_for_the_wrong_reason(repo, cli):
    start(repo, cli)
    approve(repo, cli)
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")
    cli.ok("ok")
    repo.set_test_result(code=1, output="ImportError: cannot import name InstalmentPlan")
    repo.write("packages/billing/tests/test_instalments.py", "from nope import x\n")
    code, out, err = cli.run("done")
    assert code == 1
    assert "wrong reason" in err
    assert "ImportError" in err


# -- C5, C6, C7, C8, C9 -------------------------------------------------------------------------

def through_red(repo, cli):
    """Get to step 3 (code) with the test step validated."""
    start(repo, cli)
    approve(repo, cli)
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")
    cli.ok("ok")
    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py",
               "def test_splits_evenly():\n    assert False\n")
    cli.ok("done")
    cli.ok("ok")
    return state_mod.State.load(repo.layout, "142-instalments")


def test_c5_done_on_a_code_step_records_evidence_and_counts_every_new_line(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(line=0.97, branch=0.96, hits=((1, 1), (2, 1), (3, 1)),
                      filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    state = state_mod.State.load(repo.layout, "142-instalments")
    record = state.step(3).evidence
    assert record["result"] == "green"
    assert record["changed_lines_covered"] == 100.0
    assert record["scope_line"] == 97.0
    assert state.phase == "review"


def test_c5_an_untracked_file_counts_all_its_executable_lines(repo, cli):
    start(repo, cli)
    plan = PLAN.replace("| 1 | stub | `packages/billing/src/instalments.py` | "
                        "InstalmentPlan signature |\n", "")
    plan = plan.replace("| 2 | test |", "| 1 | test |").replace("| 3 | code |", "| 2 | code |")
    approve(repo, cli, text=plan)
    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py",
               "def test_splits_evenly():\n    assert False\n")
    cli.ok("done")
    cli.ok("ok")
    # instalments.py has never been committed: every line is a changed line.
    repo.set_coverage(hits=((1, 1), (2, 0)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py", "a = 1\nb = 2\n")
    code, out, err = cli.run("done")
    assert code == 1
    assert "lines 2" in err


def test_c6_ok_after_editing_the_file_refuses(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    code, out, err = cli.run("ok")
    assert code == 1
    assert "changed after `pair done`" in err
    assert "run `pair done` again" in err


def test_c7_ok_commits_exactly_the_file_set_state_and_log_with_the_trailers(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("ok")
    sha = gitcmd.head(repo.root)
    assert sorted(gitcmd.commit_files(repo.root, sha)) == [
        "packages/billing/src/instalments.py",
        "pair/tasks/142-instalments/log.md",
        "pair/tasks/142-instalments/state.json",
    ]
    message = gitcmd.commit_message(repo.root, sha)
    assert message.splitlines()[0] == "feat(packages__billing): minimum code to pass"
    trailers = commit.read_trailers(message)
    assert trailers == {"Pair-Task": "142-instalments", "Pair-Action": "ok", "Pair-Step": "3",
                        "Pair-Kind": "code", "Pair-Approved-By": "@ana",
                        "Pair-Governance": "0.1"}
    assert "co-authored-by" not in message.lower()


def test_c8_ok_without_a_tty_exits_three(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    code, out, err = cli.run("ok", answer=False)
    assert code == 3


def test_c8_ok_through_a_real_subprocess_has_no_tty(repo, cli):
    """The real thing: no fake confirm, so layer 1 of PAIR-005 is what refuses."""
    import subprocess
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    binary = str(pytest.importorskip("pathlib").Path(__file__).resolve().parents[3]
                 / "engine" / "bin" / "pair")
    done = subprocess.run([binary, "ok"], cwd=str(repo.root), capture_output=True, text=True)
    assert done.returncode == 3
    assert "human at a terminal" in done.stderr


def test_c9_ok_by_a_non_owner_exits_three(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    repo.write("pair/local/config.toml", 'me = "@bob"\n')
    code, out, err = cli.run("ok")
    assert code == 3
    assert "@ana" in err
    assert "pair handoff" in err


# -- C10, C11, C12, C13 -------------------------------------------------------------------------

def test_c10_rework_returns_to_stepping_and_clears_the_evidence(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("rework", "use Decimal, not float")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.phase == "stepping"
    assert state.step(3).status == "pending"
    assert state.step(3).evidence is None
    assert "use Decimal" in repo.layout.log("142-instalments").read_text()


def test_c11_reopen_keeps_validated_steps_locked_and_continues_the_numbering(repo, cli):
    through_red(repo, cli)
    cli.ok("reopen")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.phase == "planning"
    assert state.approval is None
    assert [step.status for step in state.steps] == ["ok", "ok", "pending"]

    # A validated row may not change...
    write_plan(repo, PLAN.replace("| 1 | stub | `packages/billing/src/instalments.py` | "
                                  "InstalmentPlan signature |",
                                  "| 1 | stub | `packages/billing/src/instalments.py` | changed |"))
    code, out, err = cli.run("approve")
    assert code == 1
    assert "already validated, so its row may not change" in err

    # ...and new steps continue the numbering.
    longer = PLAN.replace("| 3 | code | `packages/billing/src/instalments.py` | "
                          "minimum code to pass |",
                          "| 3 | code | `packages/billing/src/instalments.py` | "
                          "minimum code to pass |\n"
                          "| 4 | doc | `docs/instalments.md` | explain it |")
    state = approve(repo, cli, text=longer)
    assert [step.n for step in state.steps] == [1, 2, 3, 4]
    assert state.step(1).status == "ok"
    assert state.current_step == 3


def test_c12_reopen_from_closing_works(repo, cli):
    state = through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("ok")
    assert state_mod.State.load(repo.layout, "142-instalments").phase == "closing"
    cli.ok("reopen")
    assert state_mod.State.load(repo.layout, "142-instalments").phase == "planning"


def test_c13_close_refuses_a_walkthrough_with_a_missing_or_empty_section(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("ok")

    code, out, err = cli.run("close")
    assert code == 1
    assert "has not been written yet" in err

    repo.write("pair/tasks/142-instalments/walkthrough.md",
               WALKTHROUGH.replace("## Lessons\nnone\n", "## Lessons\n"))
    code, out, err = cli.run("close")
    assert code == 1
    assert "`## Lessons` is empty" in err

    repo.write("pair/tasks/142-instalments/walkthrough.md",
               WALKTHROUGH.replace("## How to roll it back\npair revert 142-instalments\n\n", ""))
    code, out, err = cli.run("close")
    assert code == 1
    assert "`## How to roll it back` is missing" in err

    repo.write("pair/tasks/142-instalments/walkthrough.md", WALKTHROUGH)
    cli.ok("close")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert (state.phase, state.status) == ("done", "closed")
    assert repo.layout.active_task() is None


def test_c13_close_refuses_when_the_understanding_check_is_answered_no(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("ok")
    repo.write("pair/tasks/142-instalments/walkthrough.md", WALKTHROUGH)

    def answer(question, expect):
        return "explain this change" not in question
    code, out, err = cli.run("close", answer=answer)
    assert code == 3
    assert "understanding check" in err


# -- C14 ---------------------------------------------------------------------------------------

def test_c14_a_config_below_a_floor_exits_one(repo, cli):
    text = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", text + "\n[coverage]\ntarget = 80\n")
    code, out, err = cli.run("status")
    assert code == 1
    assert "coverage.target: must not be below 95" in err


def test_c14_every_floor_is_enforced_through_the_cli(repo, cli):
    text = (repo.root / "pair/config.toml").read_text()
    for snippet, expected in (
        ("[steps]\nmax_files = 2\n", "steps.max_files: must be exactly 1"),
        ("[expedite]\nreview_hours = 96\n", "expedite.review_hours: must not be above 72"),
        ("[waivers]\nmax_repeats = 9\n", "waivers.max_repeats: must not be above 3"),
    ):
        repo.write("pair/config.toml", text + "\n" + snippet)
        code, out, err = cli.run("doctor")
        assert code == 1
        assert expected in err


# -- C28 ---------------------------------------------------------------------------------------

def test_c28_pause_rework_and_lesson_propose_commit_only_the_task_bookkeeping(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")

    for argv in (("rework", "use Decimal"),
                 ("lesson", "propose", "Money uses Decimal", "--domain", "billing"),
                 ("pause",)):
        cli.ok(*argv)
        files = gitcmd.commit_files(repo.root, gitcmd.head(repo.root))
        assert files == ["pair/tasks/142-instalments/log.md",
                         "pair/tasks/142-instalments/state.json"], argv

    # and a new task afterwards still starts, once the reworked file is resolved
    repo.git("checkout", "--", "packages/billing/src/instalments.py")
    cli.ok("start", "143-refunds")
    assert state_mod.State.load(repo.layout, "143-refunds").phase == "planning"


# -- C24 ---------------------------------------------------------------------------------------

def test_c24_handoff_moves_the_owner_and_the_old_owner_loses_ok(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("handoff", "@bob")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert (state.owner, state.status) == ("@bob", "paused")

    # @ana cannot resume it either: the task is @bob's now.
    code, out, err = cli.run("resume", "142-instalments")
    assert code == 3
    assert "@bob" in err

    repo.write("pair/local/config.toml", 'me = "@bob"\n')
    cli.ok("resume", "142-instalments")

    # Now the task is active again, so the owner check is what refuses @ana.
    repo.write("pair/local/config.toml", 'me = "@ana"\n')
    code, out, err = cli.run("ok")
    assert code == 3
    assert "@bob" in err
    assert "pair handoff @ana" in err

    repo.write("pair/local/config.toml", 'me = "@bob"\n')
    cli.ok("ok")
    assert state_mod.State.load(repo.layout, "142-instalments").step(3).status == "ok"


# -- C25 ---------------------------------------------------------------------------------------

def test_c25_ok_refuses_a_staged_intruder_but_not_untracked_artifacts(repo, cli):
    through_red(repo, cli)
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")

    repo.write("packages/billing/src/money.py", "def cents(x):\n    return 1\n")
    repo.git("add", "packages/billing/src/money.py")
    code, out, err = cli.run("ok")
    assert code == 1
    assert "another tracked file is staged" in err
    assert "packages/billing/src/money.py" in err

    repo.git("restore", "--staged", "packages/billing/src/money.py")
    repo.git("checkout", "--", "packages/billing/src/money.py")
    repo.write("packages/billing/.coverage-artifact", "noise\n")
    code, out, err = cli.run("ok")
    assert code == 0
    assert "untracked files left alone" in err


# -- C26 ---------------------------------------------------------------------------------------

def test_c26_plan_check_rejects_test_then_stub_and_test_then_test(repo, cli):
    start(repo, cli)
    write_plan(repo, PLAN.replace(
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |",
        "| 3 | stub | `packages/billing/src/other.py` | another signature |\n"
        "| 4 | code | `packages/billing/src/other.py` | pass |"))
    code, out, err = cli.run("plan-check")
    assert code == 1
    assert "the next non-doc step must be `code`" in err

    write_plan(repo, PLAN.replace(
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |",
        "| 3 | test | `packages/billing/tests/test_other.py` | another case |\n"
        "| 4 | code | `packages/billing/src/instalments.py` | pass |"))
    code, out, err = cli.run("plan-check")
    assert code == 1
    assert "left a test red" in err


# -- C29 ---------------------------------------------------------------------------------------

def test_c29_a_stub_in_a_brand_new_scope_passes_with_exit_code_5(repo, cli):
    start(repo, cli)
    approve(repo, cli)
    repo.set_test_result(code=5, output="no tests ran")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        ...\n")
    cli.ok("done")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.step(1).evidence["result"] == "green"
    assert state.step(1).evidence["tests"] == "no tests collected"


# -- C21 ---------------------------------------------------------------------------------------

def test_c21_stub_then_test_then_code_passes_end_to_end(repo, cli):
    start(repo, cli)
    approve(repo, cli)

    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")
    cli.ok("ok")

    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py",
               "def test_splits_evenly():\n    assert False\n")
    cli.ok("done")
    cli.ok("ok")

    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py",
               "class InstalmentPlan:\n    def __init__(self, total):\n        self.total = total\n")
    cli.ok("done")
    cli.ok("ok")

    repo.write("pair/tasks/142-instalments/walkthrough.md", WALKTHROUGH)
    cli.ok("close")

    state = state_mod.State.load(repo.layout, "142-instalments")
    assert [step.status for step in state.steps] == ["ok", "ok", "ok"]
    assert (state.phase, state.status) == ("done", "closed")
    kinds = []
    for sha in gitcmd.lines(repo.root, "log", "--format=%H"):
        trailers = commit.read_trailers(gitcmd.commit_message(repo.root, sha))
        if trailers.get("Pair-Action") == "ok":
            kinds.append(trailers.get("Pair-Kind"))
    assert kinds == ["code", "test", "stub"]              # newest first


# -- C23 ---------------------------------------------------------------------------------------

def test_c23_a_batch_granted_refactor_across_three_files_commits_exactly_those(repo, cli):
    for name in ("a", "b"):
        repo.write(f"packages/billing/src/{name}.py", f"def {name}():\n    return 1\n")
    repo.write("packages/billing/tests/test_ab.py", "def test_ab():\n    assert True\n")
    repo.commit_all("seed the refactor targets")

    start(repo, cli)
    plan = PLAN.replace(
        "| 1 | stub | `packages/billing/src/instalments.py` | InstalmentPlan signature |\n"
        "| 2 | test | `packages/billing/tests/test_instalments.py` | splits evenly |\n"
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |",
        "| 1 | refactor | `packages/billing/**/*.py` | rename for clarity |")
    write_plan(repo, plan)
    cli.ok("grant-batch", "--step", "1", "--paths", "packages/billing/**/*.py",
           "--max-files", "3", "--include-tests")
    approve(repo, cli, text=plan)

    repo.set_coverage(hits=((1, 1), (2, 1)))
    repo.write("packages/billing/src/a.py", "def alpha():\n    return 1\n")
    repo.write("packages/billing/src/b.py", "def beta():\n    return 1\n")
    repo.write("packages/billing/tests/test_ab.py", "def test_alpha():\n    assert True\n")
    cli.ok("done")
    cli.ok("ok")
    files = gitcmd.commit_files(repo.root, gitcmd.head(repo.root))
    assert sorted(files) == [
        "packages/billing/src/a.py", "packages/billing/src/b.py",
        "packages/billing/tests/test_ab.py",
        "pair/tasks/142-instalments/log.md", "pair/tasks/142-instalments/state.json"]


# -- C15 ---------------------------------------------------------------------------------------

def test_c15_waive_refuses_tier_zero_and_stops_at_max_repeats(repo, cli):
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | Money uses Decimal | 1 | review |\n")
    repo.commit_all("project rules")

    code, out, err = cli.run("waive", "TEST-001", "--reason", "legacy", "--scope", "legacy/**",
                             "--expires", "2027-01-01")
    assert code == 3
    assert "Tier 0 and cannot be waived" in err

    for number in range(3):
        cli.ok("waive", "PROJ-001", "--reason", f"grant {number}", "--scope", "legacy/**",
               "--expires", "2027-01-01")

    code, out, err = cli.run("waive", "PROJ-001", "--reason", "one more", "--scope", "legacy/**",
                             "--expires", "2027-01-01")
    assert code == 3
    assert "max_repeats" in err

    cli.ok("waive", "--remove", "1")
    code, out, err = cli.run("waive", "PROJ-001", "--reason", "after deleting", "--scope",
                             "legacy/**", "--expires", "2027-01-01")
    assert code == 3
    assert "does not reset" in err


# -- C16 ---------------------------------------------------------------------------------------

def test_c16_baseline_never_lowers_and_the_floor_formula_holds(repo, cli):
    repo.set_coverage(line=0.714, branch=0.63)
    cli.ok("baseline", "--scope", "packages/billing")
    entry = repo.baselines.entry("packages/billing")
    assert (entry["line"], entry["branch"]) == (71.4, 63.0)

    repo.set_coverage(line=0.50, branch=0.40)
    out = cli.ok("baseline", "--scope", "packages/billing")
    assert "unchanged" in out
    assert repo.baselines.entry("packages/billing")["line"] == 71.4

    cases = [(71.4, 63.0, 95, 0.5, (70.9, 62.5)),
             (95.2, 99.0, 95, 0.5, (95.0, 98.5)),
             (None, None, 95, 0.5, (95.0, 95.0))]
    for line, branch, target, tolerance, expected in cases:
        baselines = repo.baselines
        if line is None:
            baselines.scopes.pop("packages/billing", None)
        else:
            baselines.scopes["packages/billing"] = {"line": line, "branch": branch,
                                                    "measured_at": "2026-01-01"}
        assert baselines.floor("packages/billing", target, tolerance) == expected


def test_c16_baseline_lower_needs_a_reason_and_records_it(repo, cli):
    repo.set_coverage(line=0.90, branch=0.90)
    cli.ok("baseline", "--scope", "packages/billing")
    code, out, err = cli.run("baseline", "--scope", "packages/billing", "--lower")
    assert code == 2
    assert "--reason" in err
    repo.set_coverage(line=0.50, branch=0.50)
    cli.ok("baseline", "--scope", "packages/billing", "--lower", "--reason",
           "deleted a well-tested module")
    entry = repo.baselines.entry("packages/billing")
    assert entry["line"] == 50.0
    assert entry["lowered_reason"] == "deleted a well-tested module"
    trailers = commit.read_trailers(gitcmd.commit_message(repo.root, gitcmd.head(repo.root)))
    assert trailers["Pair-Action"] == "baseline-lower"


# -- C22 ---------------------------------------------------------------------------------------

def char_plan(repo):
    return PLAN.replace(
        "| 1 | stub | `packages/billing/src/instalments.py` | InstalmentPlan signature |\n"
        "| 2 | test | `packages/billing/tests/test_instalments.py` | splits evenly |\n"
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |",
        "| 1 | char | `packages/billing/tests/test_legacy.py` | pins existing rounding |")


def test_c22_a_char_step_needs_a_baseline_then_must_buy_coverage(repo, cli):
    start(repo, cli)
    approve(repo, cli, text=char_plan(repo))
    repo.set_coverage(line=0.80, branch=0.70)
    repo.write("packages/billing/tests/test_legacy.py", "def test_legacy():\n    assert True\n")

    code, out, err = cli.run("done")
    assert code == 1
    assert "pair baseline --scope packages/billing" in err

    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    cli.ok("done")
    assert state_mod.State.load(repo.layout, "142-instalments").step(1).evidence["result"] == "green"


def test_c22_a_char_step_without_a_gain_fails_then_passes_with_the_escape_line(repo, cli):
    start(repo, cli)
    approve(repo, cli, text=char_plan(repo))
    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    repo.set_coverage(line=0.714, branch=0.63)
    repo.write("packages/billing/tests/test_legacy.py", "def test_legacy():\n    assert True\n")

    code, out, err = cli.run("done")
    assert code == 1
    assert "coverage did not rise" in err

    note = "⚠️ no coverage gain: already covered by an integration test"
    log_path = repo.layout.log("142-instalments")
    log_path.write_text(log_path.read_text()
                        + f"### 2026-09-27T12:00Z · step 1 · report\n{note}\n")
    cli.ok("done")
    record = state_mod.State.load(repo.layout, "142-instalments").step(1).evidence
    assert record["note"] == note


# -- C30 ---------------------------------------------------------------------------------------

def test_c30_an_expedite_tasks_test_step_accepts_the_matched_test_files(repo, cli):
    cli.ok("expedite", "900-outage", "--test-paths", "packages/billing/tests/**/*.py",
           "--paths", "packages/billing/src/**/*.py", "--reason", "invoices double-charge")
    state = state_mod.State.load(repo.layout, "900-outage")
    assert (state.status, state.phase) == ("expedite", "stepping")
    assert state.expedite["reason"] == "invoices double-charge"
    assert state.approval is not None
    assert state.batch_for(1)["include_tests"] is True

    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_outage.py",
               "def test_double_charge():\n    assert False\n")
    cli.ok("done")
    assert state_mod.State.load(repo.layout, "900-outage").step(1).evidence["result"] == "red"


def test_c30_an_expedite_spanning_two_scopes_is_refused(repo, cli):
    code, out, err = cli.run("expedite", "900-outage", "--test-paths",
                             "packages/billing/tests/**/*.py,tools/**/*.py",
                             "--paths", "packages/billing/src/**/*.py",
                             "--reason", "double charge")
    assert code == 1
    assert "split the incident into separate tasks" in err


# -- C18, C19 ----------------------------------------------------------------------------------

def test_c18_find_rule_returns_the_exact_row(repo, cli):
    code, data, err = cli.json("find", "--rule", "TEST-007")
    assert code == 0
    assert data["row"] == ("| TEST-007 | Build test data with builders or factories; no shared "
                          "mutable fixtures | 2 | review |")
    assert data["tier"] == 2


def test_c19_an_llm_wiki_indexes_only_its_configured_globs(repo, cli, tmp_path):
    wiki = tmp_path / "wiki-checkout"
    (wiki / "published" / "billing").mkdir(parents=True)
    (wiki / "published" / "billing" / "rounding.md").write_text("# Rounding\nhalf up\n")
    (wiki / "source-material").mkdir()
    (wiki / "source-material" / "dump.md").write_text("# Rounding\nraw notes\n")
    # Deliberately not `wiki/` and `raw/`: the globs are configured, never guessed (SPEC 14.2).
    repo.write("pair/local/config.toml",
               f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
               'include = ["published/**/*.md"]\nexclude = ["source-material/**"]\n')
    code, data, err = cli.json("index")
    assert code == 0
    code, data, err = cli.json("find", "rounding")
    files = {hit["file"] for hit in data["hits"]}
    assert "published/billing/rounding.md" in files
    assert not any("source-material" in name for name in files)


def test_c19_a_source_matching_nothing_is_reported_as_empty(repo, cli, tmp_path):
    wiki = tmp_path / "w"
    (wiki / "elsewhere").mkdir(parents=True)
    (wiki / "elsewhere" / "a.md").write_text("# A\n")
    repo.write("pair/local/config.toml",
               f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
               'include = ["published/**/*.md"]\nexclude = ["raw/**"]\n')
    out = cli.ok("index")
    assert "(empty)" in out
    code, out, err = cli.run("doctor")
    assert "matches no files" in out


def test_c19_a_stale_source_is_flagged(repo, cli):
    repo.write("docs/old.md", "# Old\nancient knowledge\n")
    repo.git("add", "-A")
    import os
    old_date = dict(os.environ, GIT_AUTHOR_DATE="2020-01-01T00:00:00Z",
                    GIT_COMMITTER_DATE="2020-01-01T00:00:00Z")
    repo.git("commit", "-q", "-m", "old docs", env=old_date)
    text = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", text + '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n')
    code, out, err = cli.run("doctor")
    assert "older than" in out
