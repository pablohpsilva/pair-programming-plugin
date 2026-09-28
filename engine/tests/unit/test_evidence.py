import pytest

from pair import evidence
from pair.errors import CheckFailed

STEP_TEST = {"n": 1, "kind": "test", "files": ["packages/billing/tests/test_money.py"],
             "behavior": "rounds half up"}
STEP_CODE = {"n": 2, "kind": "code", "files": ["packages/billing/src/money.py"],
             "behavior": "minimum code"}
STEP_STUB = {"n": 1, "kind": "stub", "files": ["packages/billing/src/thing.py"],
             "behavior": "signature"}


def gather(repo, st, step_number):
    return evidence.gather(repo.layout, repo.config, st, st.step(step_number), repo.billing,
                           repo.baselines)


# -- Run ------------------------------------------------------------------------------------

def test_a_command_runs_in_the_scope_cwd(repo):
    repo.set_commands(test="pwd")
    outcome = evidence.run(repo.billing, "test", repo.layout)
    assert outcome.passed
    assert outcome.output.strip().endswith("packages/billing")


def test_a_missing_command_is_refused(repo):
    with pytest.raises(CheckFailed) as caught:
        evidence.run(repo.billing, "validate", repo.layout)
    assert "has no `validate` command" in str(caught.value)


def test_the_summary_is_the_last_twenty_lines_redacted(repo):
    repo.write(".fixture/noisy.sh",
               "".join(f"echo {n}\n" for n in range(40))
               + "echo 'password = supersecretvalue123'\nexit 1\n")
    repo.set_commands(test="sh ../../.fixture/noisy.sh")
    outcome = evidence.run(repo.billing, "test", repo.layout)
    summary = outcome.summary()
    assert len(summary.splitlines()) == 20
    assert "supersecretvalue123" not in summary
    assert "‹redacted›" in summary


def test_a_timeout_is_reported_not_raised(repo):
    repo.set_commands(test="sleep 5")
    repo.set_timeout(1)
    outcome = evidence.run(repo.billing, "test", repo.layout)
    assert outcome.timed_out
    assert not outcome.passed
    assert "timed out" in outcome.output


def test_wrong_reason_patterns_are_matched(repo):
    repo.set_commands(test="echo ModuleNotFoundError; exit 1")
    outcome = evidence.run(repo.billing, "test", repo.layout)
    assert outcome.matches(["ImportError", "ModuleNotFoundError"]) == "ModuleNotFoundError"
    assert outcome.matches(["nothing"]) is None


# -- the file set ---------------------------------------------------------------------------

def test_without_a_grant_the_file_set_is_the_listed_file(repo):
    st = repo.task(steps=[STEP_TEST])
    assert evidence.file_set(repo.root, st, st.step(1), repo.config) == STEP_TEST["files"]


def test_with_a_grant_the_file_set_is_what_changed_inside_the_globs(repo):
    st = repo.task(steps=[dict(STEP_CODE, n=1, files=["packages/billing/src/**/*.py"])])
    st.add_batch(1, ["packages/billing/src/**/*.py"], 3, False, "@ana")
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return round(x * 100)\n")
    repo.write("packages/billing/src/extra.py", "x = 1\n")
    repo.write("packages/billing/notes.md", "outside the globs\n")
    found = evidence.file_set(repo.root, st, st.step(1), repo.config)
    assert found == ["packages/billing/src/extra.py", "packages/billing/src/money.py"]


def test_a_grant_with_nothing_changed_is_refused(repo):
    st = repo.task(steps=[dict(STEP_CODE, n=1, files=["packages/billing/src/**/*.py"])])
    st.add_batch(1, ["packages/billing/src/**/*.py"], 3, False, "@ana")
    with pytest.raises(CheckFailed) as caught:
        evidence.file_set(repo.root, st, st.step(1), repo.config)
    assert "nothing in" in str(caught.value)


def test_a_grant_exceeded_is_refused_and_lists_the_files(repo):
    st = repo.task(steps=[dict(STEP_CODE, n=1, files=["packages/billing/src/**/*.py"])])
    st.add_batch(1, ["packages/billing/src/**/*.py"], 1, False, "@ana")
    repo.write("packages/billing/src/a.py", "a = 1\n")
    repo.write("packages/billing/src/b.py", "b = 1\n")
    with pytest.raises(CheckFailed) as caught:
        evidence.file_set(repo.root, st, st.step(1), repo.config)
    assert "allows 1" in str(caught.value)
    assert len(caught.value.details) == 2


def test_hashes_record_a_deletion_literally(repo):
    (repo.root / "packages/billing/src/money.py").unlink()
    found = evidence.hashes(repo.root, ["packages/billing/src/money.py"])
    assert found["packages/billing/src/money.py"] == evidence.DELETED


def test_unchanged_reports_a_file_edited_after_done(repo):
    recorded = evidence.hashes(repo.root, ["packages/billing/src/money.py"])
    assert evidence.unchanged(repo.root, recorded) == []
    repo.write("packages/billing/src/money.py", "changed\n")
    assert evidence.unchanged(repo.root, recorded) == ["packages/billing/src/money.py"]


def test_has_changes_sees_an_untracked_file_and_a_deletion(repo):
    assert not evidence.has_changes(repo.root, ["packages/billing/src/money.py"])
    repo.write("packages/billing/src/new.py", "x = 1\n")
    assert evidence.has_changes(repo.root, ["packages/billing/src/new.py"])
    (repo.root / "packages/billing/src/money.py").unlink()
    assert evidence.has_changes(repo.root, ["packages/billing/src/money.py"])


def test_changed_lines_skip_non_code_files(repo):
    repo.write("packages/billing/tests/test_money.py", "def test_x():\n    assert True\n")
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return 1\n")
    found = evidence.changed_lines(
        repo.root, ["packages/billing/tests/test_money.py", "packages/billing/src/money.py"],
        repo.config)
    assert list(found) == ["packages/billing/src/money.py"]


# -- per-kind decisions ---------------------------------------------------------------------

def test_a_test_step_that_fails_is_red(repo):
    repo.set_commands(test="echo '1 failed: AssertionError'; exit 1")
    repo.write("packages/billing/tests/test_money.py", "def test_x():\n    assert False\n")
    st = repo.task(steps=[STEP_TEST])
    record, warnings, outcome = gather(repo, st, 1)
    assert record["result"] == "red"
    assert "AssertionError" in record["summary"]
    assert record["files_sha256"]


def test_a_test_step_that_passes_is_refused(repo):
    repo.set_commands(test="echo '3 passed'; exit 0")
    repo.write("packages/billing/tests/test_money.py", "def test_x():\n    assert True\n")
    st = repo.task(steps=[STEP_TEST])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "proves nothing" in str(caught.value)
    assert "TEST-001" in str(caught.value)


def test_a_failure_for_the_wrong_reason_is_refused(repo):
    repo.set_commands(test="echo 'ImportError: no module named x'; exit 1")
    repo.write("packages/billing/tests/test_money.py", "import nope\n")
    st = repo.task(steps=[STEP_TEST])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "wrong reason" in str(caught.value)
    assert "ImportError" in str(caught.value)


def test_a_stub_step_passes_on_a_green_suite(repo):
    repo.set_commands(test="echo '3 passed'; exit 0")
    repo.write("packages/billing/src/thing.py", "def thing():\n    raise NotImplementedError\n")
    st = repo.task(steps=[STEP_STUB])
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"
    assert record["tests"] == "suite green"


def test_a_stub_step_passes_with_a_no_tests_exit_code(repo):
    repo.set_commands(test="echo 'no tests ran'; exit 5")
    repo.write("packages/billing/src/thing.py", "def thing():\n    raise NotImplementedError\n")
    st = repo.task(steps=[STEP_STUB])
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"
    assert record["tests"] == "no tests collected"


def test_a_stub_step_with_a_failing_suite_is_refused(repo):
    repo.set_commands(test="echo '1 failed'; exit 1")
    repo.write("packages/billing/src/thing.py", "x = 1\n")
    st = repo.task(steps=[STEP_STUB])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "stub step needs the suite green" in str(caught.value)


def test_a_code_step_records_rates_and_changed_line_coverage(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.962, branch=0.954, hits=((1, 1), (2, 1))))
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return round(x * 100)\n")
    st = repo.task(steps=[STEP_CODE], current=2)
    record, _, _ = gather(repo, st, 2)
    assert record["result"] == "green"
    assert record["scope_line"] == 96.2
    assert record["scope_branch"] == 95.4
    assert record["changed_lines_covered"] == 100.0
    assert record["floor_line"] == 95.0


def test_a_code_step_with_an_uncovered_changed_line_is_refused(repo):
    repo.set_commands(coverage=repo.cobertura(hits=((1, 1), (2, 0))))
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return round(x * 100)\n")
    st = repo.task(steps=[STEP_CODE], current=2)
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 2)
    assert "COV-002" in str(caught.value)
    assert "lines 2" in "\n".join(caught.value.details)


def test_a_code_step_below_the_floor_is_refused(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.80, branch=0.80, hits=((1, 1), (2, 1))))
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return round(x * 100)\n")
    st = repo.task(steps=[STEP_CODE], current=2)
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 2)
    assert "COV-001" in str(caught.value)


def test_a_failing_coverage_command_is_refused(repo):
    repo.set_commands(coverage="echo '1 failed'; exit 1")
    repo.write("packages/billing/src/money.py", "def cents(x):\n    return 1\n")
    st = repo.task(steps=[STEP_CODE], current=2)
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 2)
    assert "must be green for a code step" in str(caught.value)


def test_a_step_with_no_change_is_refused(repo):
    repo.set_commands(test="exit 1")
    st = repo.task(steps=[STEP_TEST])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "no changes in" in str(caught.value)
    assert "pair rework" in str(caught.value)


def test_a_long_step_only_warns(repo):
    repo.set_commands(coverage=repo.cobertura(hits=tuple((n, 1) for n in range(1, 80))))
    body = "".join(f"x{n} = {n}\n" for n in range(80))
    repo.write("packages/billing/src/money.py", body)
    st = repo.task(steps=[STEP_CODE], current=2)
    record, warnings, _ = gather(repo, st, 2)
    assert record["result"] == "green"
    assert any("changed lines, over the" in warning for warning in warnings)


# -- char steps -----------------------------------------------------------------------------

def char_task(repo):
    step = {"n": 1, "kind": "char", "files": ["packages/billing/tests/test_legacy.py"],
            "behavior": "pins existing rounding"}
    repo.write("packages/billing/tests/test_legacy.py", "def test_legacy():\n    assert True\n")
    return repo.task(steps=[step])


def test_a_char_step_without_a_baseline_says_run_pair_baseline(repo):
    repo.set_commands(coverage=repo.cobertura())
    st = char_task(repo)
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "pair baseline --scope packages/billing" in str(caught.value)


def test_a_char_step_passes_when_coverage_rises(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.80, branch=0.70))
    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    st = char_task(repo)
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"
    assert "note" not in record


def test_a_char_step_fails_when_coverage_does_not_rise(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.714, branch=0.63))
    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    st = char_task(repo)
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "coverage did not rise" in str(caught.value)
    assert evidence.NO_GAIN in str(caught.value)


def test_a_char_step_passes_with_the_escape_line_recorded_verbatim(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.714, branch=0.63))
    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    st = char_task(repo)
    note = f"{evidence.NO_GAIN} the behaviour was already covered by an integration test"
    repo.write(f"pair/tasks/{st.task}/log.md",
               f"### 2026-09-27T10:00Z · step 1 · report\n{note}\n")
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"
    assert record["note"] == note


def test_the_escape_line_must_belong_to_this_step(repo):
    repo.set_commands(coverage=repo.cobertura(line=0.714, branch=0.63))
    baselines = repo.baselines
    baselines.set_measured("packages/billing", 71.4, 63.0)
    baselines.save()
    st = char_task(repo)
    repo.write(f"pair/tasks/{st.task}/log.md",
               f"### 2026-09-27T10:00Z · step 9 · report\n{evidence.NO_GAIN} elsewhere\n")
    with pytest.raises(CheckFailed):
        gather(repo, st, 1)


# -- doc, config and migration steps --------------------------------------------------------

def test_a_doc_step_checks_relative_links(repo):
    repo.write("docs/a.md", "see [other](./b.md)\n")
    st = repo.task(steps=[{"n": 1, "kind": "doc", "files": ["docs/a.md"], "behavior": "explain"}])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "`./b.md` does not resolve" in "\n".join(caught.value.details)
    repo.write("docs/b.md", "here\n")
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"


def test_external_and_anchor_links_are_not_checked(repo):
    repo.write("docs/a.md", "[x](https://example.invalid) [y](#section) [z](mailto:a@b.c)\n")
    st = repo.task(steps=[{"n": 1, "kind": "doc", "files": ["docs/a.md"], "behavior": "explain"}])
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"


def test_a_config_step_without_a_validate_command_records_no_automated_check(repo):
    repo.write("ops/values.yaml", "a: 1\n")
    st = repo.task(steps=[{"n": 1, "kind": "config", "files": ["ops/values.yaml"],
                           "behavior": "tune"}])
    record, _, _ = evidence.gather(repo.layout, repo.config, st, st.step(1),
                                  repo.scopes.fallback, repo.baselines)
    assert record["summary"] == "no automated check"


def test_a_config_step_runs_validate_when_there_is_one(repo):
    repo.set_commands(validate="echo 'schema ok'")
    repo.write("packages/billing/settings.yaml", "a: 1\n")
    st = repo.task(steps=[{"n": 1, "kind": "config", "files": ["packages/billing/settings.yaml"],
                           "behavior": "tune"}])
    record, _, _ = gather(repo, st, 1)
    assert "schema ok" in record["summary"]


def test_a_migration_step_needs_a_migrate_check(repo):
    repo.write("packages/billing/migrations/001.sql", "SELECT 1;\n")
    st = repo.task(steps=[{"n": 1, "kind": "migration",
                           "files": ["packages/billing/migrations/001.sql"], "behavior": "add"}])
    with pytest.raises(CheckFailed) as caught:
        gather(repo, st, 1)
    assert "no `migrate_check` command" in str(caught.value)


def test_a_migration_step_passes_when_migrate_check_passes(repo):
    repo.set_commands(migrate_check="echo 'up and down ok'")
    repo.write("packages/billing/migrations/001.sql", "SELECT 1;\n")
    st = repo.task(steps=[{"n": 1, "kind": "migration",
                           "files": ["packages/billing/migrations/001.sql"], "behavior": "add"}])
    record, _, _ = gather(repo, st, 1)
    assert record["result"] == "green"
    assert "up and down ok" in record["summary"]


def test_the_run_log_holds_the_full_output(repo):
    repo.set_commands(test="echo line; exit 1")
    outcome = evidence.run(repo.billing, "test", repo.layout)
    path = evidence.run_log(repo.layout, "142-instalments", 1, outcome)
    assert path.read_text().startswith("$ echo line; exit 1\n[exit 1]")
    assert evidence.run_log(repo.layout, "t", 1, None) is None
