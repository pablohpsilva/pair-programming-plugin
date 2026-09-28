"""`status`, `diff`, `report`, `export`, `lesson`, `doctor` — and the golden-file contract."""

import json

import pytest

from pair import gitcmd, state as state_mod
from engine_test_helpers import PLAN, WALKTHROUGH, full_task


# -- status, and the golden files ----------------------------------------------------------------

def test_status_with_no_task_points_at_pair_start(repo, cli, golden):
    code, out, err = cli.run("status")
    assert code == 0
    golden.check("status.no-task.txt", out)


def test_status_line_with_no_task(repo, cli, golden):
    golden.check("status.line.no-task.txt", cli.ok("status", "--line"))


def to_review(repo, cli):
    """Steps 1 and 2 validated, step 3 submitted: the phase `status` has the most to say about."""
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
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


def test_status_in_review_shows_the_evidence_and_who_is_waiting(repo, cli, golden):
    to_review(repo, cli)
    golden.check("status.review.txt", cli.ok("status"))


def test_status_in_closing(repo, cli, golden):
    to_review(repo, cli)
    cli.ok("ok")
    golden.check("status.closing.txt", cli.ok("status"))


def test_status_in_stepping_names_the_step_and_the_next_one(repo, cli, golden):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    golden.check("status.stepping.txt", cli.ok("status"))


def test_status_line_in_stepping(repo, cli, golden):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    golden.check("status.line.stepping.txt", cli.ok("status", "--line"))


def test_status_json_is_compared_whole(repo, cli, golden):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    code, out, err = cli.run("--json", "status")
    golden.check("status.stepping.json", out)


def test_the_session_start_injection_is_golden(repo, cli, golden):
    from pair import flow
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    state = state_mod.State.load(repo.layout, "142-instalments")
    golden.check("session-start.stepping.txt", flow.session_start_payload(state) + "\n")


def test_status_when_the_active_task_is_not_on_this_branch(repo, cli, golden):
    cli.ok("start", "142-instalments")
    repo.git("checkout", "-q", "main")
    golden.check("status.line.off-branch.txt", cli.ok("status", "--line"))


# -- diff ----------------------------------------------------------------------------------------

def test_diff_shows_an_untracked_step_file(repo, cli):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    out = cli.ok("diff")
    assert "+class InstalmentPlan:" in out


def test_diff_shows_a_tracked_change(repo, cli):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")
    cli.ok("ok")                                     # instalments.py is tracked from here on
    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py",
               "def test_x():\n    assert False\n")
    cli.ok("done")
    cli.ok("ok")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass  # edited\n")
    out = cli.ok("diff")
    assert "# edited" in out
    assert "+++ b/packages/billing/src/instalments.py" in out


def test_diff_in_closing_reports_that_nothing_is_pending(repo, cli):
    full_task(repo, cli, close=False)
    code, out, err = cli.run("diff")
    assert code == 0
    assert "no changes in packages/billing/src/instalments.py" in out


def test_diff_without_an_active_task_says_so(repo, cli):
    full_task(repo, cli)
    code, out, err = cli.run("diff")
    assert code == 1
    assert "no active task" in err


# -- report --------------------------------------------------------------------------------------

def test_report_counts_the_task_and_its_activity(repo, cli):
    full_task(repo, cli)
    code, data, err = cli.json("report")
    assert code == 0
    assert data["tasks"]["closed"] == 1
    assert data["rework_rate"] == 0.0
    assert data["overdue_expedites"] == 0
    assert data["coverage"]


def test_report_counts_rework_and_the_median_wait(repo, cli):
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass\n")
    cli.ok("done")
    cli.ok("rework", "use Decimal")
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass  # again\n")
    cli.ok("done")
    cli.ok("ok")
    code, data, err = cli.json("report")
    assert data["rework_rate"] == 1.0
    assert data["median_validation_wait_minutes"] is not None


def test_report_flags_an_overdue_expedite(repo, cli, monkeypatch):
    cli.ok("expedite", "900-outage", "--test-paths", "packages/billing/tests/**/*.py",
           "--paths", "packages/billing/src/**/*.py", "--reason", "double charge")
    monkeypatch.setenv("PAIR_NOW", "2026-10-05T10:00:00Z")
    code, data, err = cli.json("report")
    assert data["overdue_expedites"] == 1
    code, out, err = cli.run("doctor")
    assert code == 1
    assert "past its review deadline" in out


def test_report_write_commits_the_file(repo, cli):
    full_task(repo, cli)
    out = cli.ok("report", "--write")
    assert "written to pair/reports/2026-09.md" in out
    text = (repo.layout.reports / "2026-09.md").read_text()
    assert text.startswith("# pair report")
    assert "## Audit notes" in text
    from pair import commit
    trailers = commit.read_trailers(gitcmd.commit_message(repo.root, gitcmd.head(repo.root)))
    assert trailers["Pair-Action"] == "report"


def test_report_write_needs_a_terminal(repo, cli):
    full_task(repo, cli)
    code, out, err = cli.run("report", "--write", answer=False)
    assert code == 3


def test_report_flags_a_zero_rework_task_with_five_steps(repo, cli):
    cli.ok("start", "142-instalments")
    longer = PLAN.replace(
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |",
        "| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |\n"
        "| 4 | doc | `docs/a.md` | explain |\n| 5 | doc | `docs/b.md` | explain more |")
    repo.write("pair/tasks/142-instalments/plan.md", longer)
    cli.ok("approve")
    code, data, err = cli.json("report")
    assert data["zero_rework_tasks"] == ["142-instalments"]


# -- export --------------------------------------------------------------------------------------

def test_export_walkthrough_writes_the_outbox_with_frontmatter(repo, cli):
    full_task(repo, cli)
    out = cli.ok("export", "walkthrough", "142-instalments")
    assert "pair/local/outbox/142-instalments.md" in out
    text = (repo.layout.outbox / "142-instalments.md").read_text()
    assert text.startswith("---\nsource: pair\ntask: 142-instalments\n")
    assert "date: 2026-09-27" in text
    assert "commits: " in text
    assert "## What was built" in text


def test_export_refuses_when_there_is_no_walkthrough(repo, cli):
    cli.ok("start", "142-instalments")
    code, out, err = cli.run("export", "walkthrough")
    assert code == 1
    assert "has no walkthrough yet" in err


# -- lessons -------------------------------------------------------------------------------------

def test_a_lesson_is_proposed_then_accepted_into_the_domain_file(repo, cli):
    full_task(repo, cli, close=False)
    cli.ok("lesson", "propose", "Money amounts use Decimal, never float.", "--domain", "billing")
    cli.ok("lesson", "accept", "1")
    text = (repo.layout.learnings / "billing.md").read_text()
    assert "billing#142-instalments.1" in text
    assert "Money amounts use Decimal, never float." in text
    assert "Source: step 3, @ana" in text
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.lesson(1)["status"] == "accepted"
    assert state.lesson(1)["lesson_id"] == "billing#142-instalments.1"


def test_accepting_the_same_text_twice_confirms_instead_of_duplicating(repo, cli):
    full_task(repo, cli, close=False)
    cli.ok("lesson", "propose", "Money uses Decimal.", "--domain", "billing")
    cli.ok("lesson", "accept", "1")
    cli.ok("lesson", "propose", "money uses decimal.", "--domain", "billing")
    out = cli.ok("lesson", "accept", "2")
    assert "confirmed instead of duplicated" in out
    text = (repo.layout.learnings / "billing.md").read_text()
    assert text.count("Source: step") == 1
    assert "  - confirmed: 142-instalments" in text


def test_a_lesson_can_be_edited_and_rejected(repo, cli):
    full_task(repo, cli, close=False)
    cli.ok("lesson", "propose", "Use floats.", "--domain", "billing")
    cli.ok("lesson", "edit", "1", "--text", "Use Decimal, never float.")
    text = (repo.layout.learnings / "billing.md").read_text()
    assert "Use Decimal, never float." in text
    assert "Use floats." not in text

    cli.ok("lesson", "propose", "Something else.", "--domain", "billing")
    cli.ok("lesson", "reject", "2")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.lesson(2)["status"] == "rejected"
    assert "Something else." not in (repo.layout.learnings / "billing.md").read_text()


def test_a_lesson_can_be_disputed(repo, cli):
    full_task(repo, cli, close=False)
    cli.ok("lesson", "propose", "Money uses Decimal.", "--domain", "billing")
    cli.ok("lesson", "accept", "1")
    cli.ok("lesson", "dispute", "billing#142-instalments.1")
    text = (repo.layout.learnings / "billing.md").read_text()
    assert "⚠️ disputed billing#142-instalments.1" in text


def test_close_stamps_last_used_for_every_cited_lesson(repo, cli, monkeypatch):
    full_task(repo, cli, close=False)
    cli.ok("lesson", "propose", "Money uses Decimal.", "--domain", "billing")
    cli.ok("lesson", "accept", "1")
    cli.ok("reopen")
    repo.write("pair/tasks/142-instalments/plan.md",
               PLAN.replace("Rules & lessons: TEST-001",
                            "Rules & lessons: TEST-001, billing#142-instalments.1"))
    cli.ok("approve")
    monkeypatch.setenv("PAIR_NOW", "2026-10-15T09:00:00Z")
    repo.write("pair/tasks/142-instalments/walkthrough.md", WALKTHROUGH)
    cli.ok("close")
    text = (repo.layout.learnings / "billing.md").read_text()
    assert "Last used: 2026-10-15" in text


def test_a_lesson_needs_a_domain_and_text(repo, cli):
    cli.ok("start", "142-instalments")
    code, out, err = cli.run("lesson", "propose", "  ", "--domain", "billing")
    assert code == 2
    code, out, err = cli.run("lesson", "propose", "x", "--domain", "Not A Domain")
    assert code == 2


# -- doctor --------------------------------------------------------------------------------------

def test_doctor_is_clean_on_a_healthy_repository(repo, cli):
    repo.git("config", "core.hooksPath", "githooks")
    repo.write("githooks/commit-msg", "#!/bin/sh\nexit 0\n")
    repo.write(".claude/settings.json", "{}\n")
    repo.write("pair/knowledge/billing.md", "# Billing\n\nHow invoices work.\n")
    repo.commit_all("the pointer files and a knowledge note")
    code, out, err = cli.run("doctor")
    assert code == 0, out
    assert "— ok" in out


def test_doctor_reports_a_duplicate_rule_id_as_an_error(repo, cli):
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | one | 1 | review |\n| PROJ-001 | two | 2 | review |\n")
    code, out, err = cli.run("doctor")
    assert code == 1
    assert "is defined twice" in out


def test_doctor_names_the_missing_hooks_path_command(repo, cli):
    code, out, err = cli.run("doctor")
    assert "git config core.hooksPath githooks" in out
    assert "never --global" in out


def test_doctor_prints_the_cloud_fallback_when_the_plugin_is_not_declared(repo, cli):
    code, out, err = cli.run("doctor")
    assert "claude plugin marketplace add ./pair --scope local" in out


def test_doctor_reports_a_stale_summary(repo, cli, monkeypatch):
    repo.write("pair/scopes/packages/billing/SUMMARY.md", "# billing\n\nWhat it does.\n")
    import os
    old = dict(os.environ, GIT_AUTHOR_DATE="2020-01-01T00:00:00Z",
               GIT_COMMITTER_DATE="2020-01-01T00:00:00Z")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "an old summary", env=old)
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return round(x * 100)\n")
    repo.commit_all("newer code")
    code, out, err = cli.run("doctor")
    assert "changed on" in out


def test_doctor_lists_a_task_on_an_older_governance_version(repo, cli):
    cli.ok("start", "142-instalments")
    text = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", text.replace('governance = "0.1"', 'governance = "0.2"'))
    code, out, err = cli.run("doctor")
    assert "runs on governance 0.1" in out


# -- wrong-phase wording (SPEC 7.4) --------------------------------------------------------------

@pytest.mark.parametrize("command,argv", [
    ("approve", ("approve",)),
    ("done", ("done",)),
    ("ok", ("ok",)),
    ("rework", ("rework", "note")),
    ("close", ("close",)),
])
def test_a_transition_from_the_wrong_phase_names_the_phase_and_the_next_action(repo, cli, command,
                                                                              argv):
    cli.ok("start", "142-instalments")          # phase planning
    if command == "approve":
        pytest.skip("approve's from-phase is planning")
    code, out, err = cli.run(*argv)
    assert code == 1
    assert "planning" in err
    assert "waiting for:" in err


def test_reopen_refuses_from_planning(repo, cli):
    cli.ok("start", "142-instalments")
    code, out, err = cli.run("reopen")
    assert code == 1
    assert "needs phase stepping or review or closing" in err


def test_no_active_task_says_what_to_run(repo, cli):
    code, out, err = cli.run("done")
    assert code == 1
    assert "pair start <id>" in err
