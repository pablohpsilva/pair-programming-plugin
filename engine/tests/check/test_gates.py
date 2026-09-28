"""One failing and one passing history per gate, plus C27 and C33-C36 (SPEC 22)."""

import pytest

from pair import check as check_mod, commit, flow, gitcmd, state as state_mod
from engine_test_helpers import CODE, PLAN, STUB, TEST, WALKTHROUGH, full_task


def session(repo, cli):
    return flow.Session.open(str(repo.root), confirm=cli.confirm)


def gate(repo, cli, name, base, head="HEAD"):
    return check_mod.run(session(repo, cli), name, base, head)


def reasons(failures):
    return "\n".join(failure.render() for failure in failures)


# -- a clean task passes every gate (SPEC 22) ----------------------------------------------------

def test_a_full_clean_task_passes_all(repo, cli):
    base = full_task(repo, cli)
    failures = gate(repo, cli, "all", base)
    assert failures == [], reasons(failures)


def test_an_expedite_task_passes_all(repo, cli):
    base = gitcmd.head(repo.root)
    cli.ok("expedite", "900-outage", "--test-paths", "packages/billing/tests/**/*.py",
           "--paths", "packages/billing/src/**/*.py", "--reason", "invoices double-charge")
    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_outage.py", TEST)
    cli.ok("done")
    cli.ok("ok")
    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/outage.py")
    repo.write("packages/billing/src/outage.py", CODE)
    cli.ok("done")
    cli.ok("ok")
    failures = gate(repo, cli, "all", base)
    assert failures == [], reasons(failures)


# -- protected -----------------------------------------------------------------------------------

def test_protected_fails_on_a_hand_edit_of_a_protected_path(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | hand-written | 1 | review |\n")
    repo.commit_all("edit the rules by hand")
    failures = gate(repo, cli, "protected", base)
    assert failures
    assert "pair/rules/overrides.md is protected" in reasons(failures)
    assert "PAIR-006" in reasons(failures)


def test_c33_a_hand_edit_with_no_pair_action_trailer_fails_protected(repo, cli):
    """D6: with no agent identity to key on, the gate asks whether the *tool* made the change."""
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/overrides.md", "# changed by a human, outside `pair waive`\n")
    repo.commit_all("a perfectly well-meant hand edit")
    failures = gate(repo, cli, "protected", base)
    assert any(failure.rule == "PAIR-006" for failure in failures)


def test_protected_passes_for_the_action_that_owns_the_path(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | Money uses Decimal | 1 | review |\n")
    repo.commit_all("project rules")
    base = gitcmd.head(repo.root)
    cli.ok("waive", "PROJ-001", "--reason", "legacy", "--scope", "legacy/**",
           "--expires", "2027-01-01")
    failures = gate(repo, cli, "protected", base)
    assert failures == [], reasons(failures)


def test_protected_fails_when_an_ok_commit_lowers_a_baseline(repo, cli):
    repo.set_coverage(line=0.99, branch=0.99)
    cli.ok("baseline", "--scope", "packages/billing")
    base = gitcmd.head(repo.root)
    # Forge an ok commit that lowers the baseline.
    repo.write("pair/rules/baseline.toml",
               '[scopes."packages/billing"]\nline = 10.0\nbranch = 10.0\n'
               'measured_at = "2026-09-27"\n')
    repo.git("add", "pair/rules/baseline.toml")
    repo.git("commit", "-q", "-m", "feat(x): y\n\nPair-Action: ok\nPair-Governance: 0.1\n")
    failures = gate(repo, cli, "protected", base)
    assert "lowered a baseline" in reasons(failures)


# -- commits -------------------------------------------------------------------------------------

def test_commits_fails_when_a_plain_commit_changes_outside_files(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return 2\n")
    repo.commit_all("a change with no pair involvement")
    failures = gate(repo, cli, "commits", base)
    assert "without being a `Pair-Action: ok` commit" in reasons(failures)


def test_commits_fails_when_an_ok_commit_sweeps_in_another_file(repo, cli):
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")
    # Amend the ok commit so it also carries an unrelated file.
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return 3\n")
    repo.git("add", "packages/billing/src/money.py")
    repo.git("commit", "-q", "--amend", "--no-edit")
    failures = gate(repo, cli, "commits", base)
    assert "outside step 1's set" in reasons(failures)


def test_commits_fails_when_a_step_commits_two_files_without_a_grant(repo, cli):
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")
    # Forge a second file into the step's recorded set.
    state = state_mod.State.load(repo.layout, "142-instalments")
    state.step(1).evidence["committed_files"] = ["packages/billing/src/instalments.py",
                                                "packages/billing/src/money.py"]
    state.save()
    repo.git("add", "-A")
    repo.git("commit", "-q", "--amend", "--no-edit")
    failures = gate(repo, cli, "commits", base)
    assert "without a batch grant" in reasons(failures)


# -- approval ------------------------------------------------------------------------------------

def test_approval_fails_without_an_approve_ancestor(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/instalments.py", STUB)
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m",
             "feat(packages__billing): forged\n\nPair-Task: 142-instalments\n"
             "Pair-Action: ok\nPair-Step: 1\nPair-Kind: stub\nPair-Governance: 0.1\n")
    failures = gate(repo, cli, "approval", base)
    assert "no `Pair-Action: approve`" in reasons(failures)


def test_c36_approval_passes_across_a_reopen_and_re_approval(repo, cli):
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")
    first_hash = state_mod.State.load(repo.layout, "142-instalments").step(1)\
        .approved_plan_sha256

    cli.ok("reopen")
    longer = PLAN.replace("| 3 | code | `packages/billing/src/instalments.py` | "
                          "minimum code to pass |",
                          "| 3 | code | `packages/billing/src/instalments.py` | "
                          "minimum code to pass |\n"
                          "| 4 | doc | `docs/instalments.md` | explain it |")
    repo.write("pair/tasks/142-instalments/plan.md", longer)
    cli.ok("approve")
    state = state_mod.State.load(repo.layout, "142-instalments")
    assert state.step(1).approved_plan_sha256 == first_hash      # the ok'd step keeps its hash
    assert state.step(4).approved_plan_sha256 != first_hash

    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py", TEST)
    cli.ok("done")
    cli.ok("ok")

    failures = gate(repo, cli, "approval", base)
    assert failures == [], reasons(failures)


# -- red -----------------------------------------------------------------------------------------

def test_red_fails_when_the_test_step_commit_is_green(repo, cli):
    """The gate re-runs the suite at that commit, so a step recorded red must really have been."""
    repo.use_reproducible_test_command()
    repo.commit_all("a test command the gate can re-run")
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")
    repo.write("packages/billing/tests/test_instalments.py", TEST)
    cli.ok("done")
    cli.ok("ok")
    # Rewrite history so the committed test passes, while the evidence still says red.
    repo.write("packages/billing/tests/test_instalments.py",
               "def test_splits_evenly():\n    assert True\n")
    repo.git("add", "packages/billing/tests/test_instalments.py")
    repo.git("commit", "-q", "--amend", "--no-edit")
    failures = gate(repo, cli, "red", base)
    assert "was never red" in reasons(failures)


def test_red_passes_for_a_genuinely_red_step(repo, cli):
    repo.use_reproducible_test_command()
    repo.commit_all("a test command the gate can re-run")
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")
    repo.write("packages/billing/tests/test_instalments.py", TEST)
    cli.ok("done")
    cli.ok("ok")
    failures = gate(repo, cli, "red", base)
    assert failures == [], reasons(failures)


def test_c34_red_skips_cleanly_when_the_scope_test_command_is_empty(repo, cli):
    base = gitcmd.head(repo.root)
    cli.ok("start", "142-instalments")
    repo.write("pair/tasks/142-instalments/plan.md", PLAN)
    cli.ok("approve")
    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py", TEST)
    state = state_mod.State.load(repo.layout, "142-instalments")
    state.current_step = 2
    state.save()
    cli.ok("done")
    cli.ok("ok")
    repo.set_commands(test="", coverage="")                   # the command goes away afterwards
    repo.commit_all("drop the scope commands")
    failures = gate(repo, cli, "red", base)
    assert failures == [], reasons(failures)


# -- coverage ------------------------------------------------------------------------------------

def test_coverage_fails_below_the_floor(repo, cli):
    base = full_task(repo, cli, close=False)
    repo.set_coverage(line=0.10, branch=0.10, filename="src/instalments.py")
    repo.git("checkout", "--", ".") if False else None
    # Re-run the scope command so the report on disk is the poor one.
    from pair import evidence
    scope = repo.billing
    env, _ = evidence.coverage_env(repo.layout, scope)
    evidence.run(scope, "coverage", repo.layout, extra_env=env)
    failures = gate(repo, cli, "coverage", base)
    assert "below the floor" in reasons(failures)


def test_coverage_passes_when_the_report_is_good(repo, cli):
    base = full_task(repo, cli, close=False)
    from pair import evidence
    scope = repo.billing
    env, _ = evidence.coverage_env(repo.layout, scope)
    evidence.run(scope, "coverage", repo.layout, extra_env=env)
    failures = gate(repo, cli, "coverage", base)
    assert failures == [], reasons(failures)


def test_coverage_fails_when_a_baseline_decreases_outside_a_lower_commit(repo, cli):
    repo.set_coverage(line=0.99, branch=0.99)
    cli.ok("baseline", "--scope", "packages/billing")
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/baseline.toml",
               '[scopes."packages/billing"]\nline = 10.0\nbranch = 10.0\n'
               'measured_at = "2026-09-27"\n')
    repo.commit_all("quietly lower it")
    failures = gate(repo, cli, "coverage", base)
    assert "a baseline value decreased" in reasons(failures)


def test_c27_baseline_lower_passes_the_coverage_gate(repo, cli):
    repo.set_coverage(line=0.99, branch=0.99)
    cli.ok("baseline", "--scope", "packages/billing")
    base = gitcmd.head(repo.root)
    repo.set_coverage(line=0.50, branch=0.50)
    cli.ok("baseline", "--scope", "packages/billing", "--lower", "--reason",
           "deleted a well-tested module")
    failures = gate(repo, cli, "coverage", base)
    assert not [f for f in failures if f.rule == "COV-003"], reasons(failures)


def test_coverage_fails_on_a_new_pragma_with_no_exclusion(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py",
               "def cents(x):  # pragma: no cover\n    return int(x * 100)\n")
    repo.commit_all("add a pragma")
    failures = gate(repo, cli, "coverage", base)
    assert "coverage-ignore pragma was added" in reasons(failures)


def test_coverage_allows_a_pragma_in_an_excluded_file(repo, cli):
    repo.write("pair/scopes/packages/billing/RULES.md",
               "# rules\n\n## Coverage exclusions\n\n- `packages/billing/src/money.py`: "
               "thin wrapper over the payment SDK\n")
    repo.commit_all("approve an exclusion")
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py",
               "def cents(x):  # pragma: no cover\n    return int(x * 100)\n")
    repo.commit_all("add a pragma")
    failures = gate(repo, cli, "coverage", base)
    assert not [f for f in failures if f.rule == "COV-004"], reasons(failures)


# -- boundaries ----------------------------------------------------------------------------------

def test_boundaries_fails_on_a_disallowed_import(repo, cli):
    repo.write("pair/rules/boundaries.toml", """
[modules.billing]
path = "packages/billing"
import_names = ["billing"]
may_depend_on = []

[modules.shared]
path = "packages/shared"
import_names = ["shared"]
may_depend_on = []
""")
    repo.write("packages/shared/__init__.py", "")
    repo.commit_all("declare boundaries")
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py", "import shared\n\n\ndef cents(x):\n    return 1\n")
    repo.commit_all("cross the boundary")
    failures = gate(repo, cli, "boundaries", base)
    assert "billing imports shared" in reasons(failures)
    assert "ARCH-001" in reasons(failures)


def test_boundaries_passes_an_allowed_import(repo, cli):
    repo.write("pair/rules/boundaries.toml", """
[modules.billing]
path = "packages/billing"
import_names = ["billing"]
may_depend_on = ["shared"]

[modules.shared]
path = "packages/shared"
import_names = ["shared"]
may_depend_on = []
""")
    repo.write("packages/shared/__init__.py", "")
    repo.commit_all("declare boundaries")
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py", "import shared\n\n\ndef cents(x):\n    return 1\n")
    repo.commit_all("an allowed edge")
    assert gate(repo, cli, "boundaries", base) == []


def test_boundaries_is_silent_when_nothing_is_declared(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("packages/billing/src/money.py", "import anything\n")
    repo.commit_all("no boundaries configured")
    assert gate(repo, cli, "boundaries", base) == []


# -- secrets -------------------------------------------------------------------------------------

def test_secrets_fails_on_an_added_secret_under_pair(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/knowledge/notes.md", "the key is AKIAIOSFODNN7EXAMPLE\n")
    repo.commit_all("leak a key")
    failures = gate(repo, cli, "secrets", base)
    assert "aws-key-id" in reasons(failures)
    assert "SEC-001" in reasons(failures)


def test_secrets_ignores_the_same_text_outside_pair(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("docs/notes.md", "the key is AKIAIOSFODNN7EXAMPLE\n")
    repo.commit_all("a doc, not a pair file")
    assert gate(repo, cli, "secrets", base) == []


def test_secrets_passes_ordinary_pair_content(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/knowledge/notes.md", "# Billing\n\nRounding is half up.\n")
    repo.commit_all("a note")
    assert gate(repo, cli, "secrets", base) == []


# -- format --------------------------------------------------------------------------------------

def test_format_fails_on_an_unparseable_state_file(repo, cli):
    base = full_task(repo, cli)
    repo.write("pair/tasks/142-instalments/state.json", "{not json")
    failures = gate(repo, cli, "format", base)
    assert "does not parse" in reasons(failures)


def test_format_fails_when_an_earlier_log_entry_changed(repo, cli):
    base = full_task(repo, cli, close=False)
    path = repo.layout.log("142-instalments")
    path.write_text(path.read_text().replace("@ana", "@someone-else", 1))
    failures = gate(repo, cli, "format", base)
    assert "entry changed" in reasons(failures)


def test_format_fails_on_an_expired_waiver(repo, cli):
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | Money uses Decimal | 1 | review |\n")
    repo.commit_all("project rules")
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/waivers.toml",
               '[[waiver]]\nrule = "PROJ-001"\nreason = "legacy"\nscope = ["legacy/**"]\n'
               'granted_by = "@ana"\ngranted_at = "2020-01-01"\nexpires = "2020-12-31"\n')
    repo.commit_all("an expired waiver")
    failures = gate(repo, cli, "format", base)
    assert "expired on 2020-12-31" in reasons(failures)


def test_format_fails_on_a_duplicate_rule_id(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/rules/overrides.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| PROJ-001 | one | 1 | review |\n| PROJ-001 | two | 2 | review |\n")
    repo.commit_all("a duplicate")
    failures = gate(repo, cli, "format", base)
    assert "is defined twice" in reasons(failures)


def test_format_fails_on_a_malformed_lesson_line(repo, cli):
    base = gitcmd.head(repo.root)
    repo.write("pair/learnings/billing.md", "- billing#142.1 missing the separator\n")
    repo.commit_all("a bad lesson line")
    failures = gate(repo, cli, "format", base)
    assert "does not match the grammar" in reasons(failures)


def test_format_passes_a_clean_repository(repo, cli):
    base = full_task(repo, cli)
    failures = gate(repo, cli, "format", base)
    assert failures == [], reasons(failures)


# -- C27 revert, C35 merge commits ---------------------------------------------------------------

def test_c27_a_revert_commit_passes_the_commits_gate(repo, cli):
    full_task(repo, cli, close=False)
    base = gitcmd.head(repo.root)
    cli.ok("revert", "142-instalments", "--step", "3")
    failures = gate(repo, cli, "commits", base)
    assert failures == [], reasons(failures)
    # `revert` makes two commits: the inverse itself, then the task bookkeeping (SPEC 7.4).
    found = [commit.read_trailers(gitcmd.commit_message(repo.root, sha))
             for sha in gitcmd.lines(repo.root, "log", "--format=%H", f"{base}..HEAD")]
    assert [t["Pair-Action"] for t in found] == ["revert", "revert"]
    assert any(t.get("Pair-Reverts") for t in found)


def test_c27_a_forged_revert_that_is_not_the_inverse_fails(repo, cli):
    full_task(repo, cli, close=False)
    base = gitcmd.head(repo.root)
    reverted = gitcmd.find_commits(repo.root, "Pair-Task: 142-instalments", "Pair-Step: 3")[0]
    repo.write("packages/billing/src/instalments.py", "class InstalmentPlan:\n    pass  # not it\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m",
             f"revert: something\n\nPair-Task: 142-instalments\nPair-Action: revert\n"
             f"Pair-Reverts: {reverted}\nPair-Governance: 0.1\n")
    failures = gate(repo, cli, "commits", base)
    assert "is not the exact inverse" in reasons(failures)


def test_c35_a_range_containing_a_merge_commit_passes_all(repo, cli):
    base = full_task(repo, cli)
    repo.git("checkout", "-q", "main")
    repo.write("docs/on-main.md", "# Main moved on\n")
    repo.commit_all("main moves on")
    repo.git("checkout", "-q", "pair/142-instalments")
    repo.git("merge", "-q", "--no-ff", "-m", "merge main into the task branch", "main")
    # CI passes the PR's base, so the range starts at merge-base(main, head) — after main's own
    # commit, and excluding the merge itself (SPEC 13.1).
    failures = gate(repo, cli, "all", "main")
    assert failures == [], reasons(failures)


def test_an_unknown_gate_is_a_usage_error(repo, cli):
    from pair.errors import UsageError
    with pytest.raises(UsageError):
        gate(repo, cli, "frobnicate", gitcmd.head(repo.root))
