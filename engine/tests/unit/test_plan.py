import pytest

from pair import config, paths, plan as planmod, scopes, state

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
module = "billing"

[commands]
test = "pytest -q"
coverage = "pytest --cov"
"""

REPO = 'path = ""\ncwd = "."\n\n[commands]\ntest = ""\ncoverage = ""\n'

GOOD = """\
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
| 1 | stub | `packages/billing/src/instalment_plan.py` | InstalmentPlan signature |
| 2 | test | `packages/billing/tests/test_instalment_plan.py` | splits evenly |
| 3 | code | `packages/billing/src/instalment_plan.py` | minimum code to pass |

## Tests first
- Scenarios: happy, remainder, zero parts

## Dependencies
<!-- none -->

## Waivers
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T10:12:00Z")
    (tmp_path / "pair").mkdir()
    (tmp_path / "pair" / "config.toml").write_text(CONFIG)
    layout = paths.Layout(tmp_path)
    (layout.scopes_dir / "_repo").mkdir(parents=True)
    (layout.scopes_dir / "_repo" / "scope.toml").write_text(REPO)
    folder = layout.scopes_dir / "packages" / "billing"
    folder.mkdir(parents=True)
    (folder / "scope.toml").write_text(BILLING)
    cfg = config.load(layout)
    st = state.State.create(layout, "142-instalments", "@ana", "pair/142-instalments",
                            "agent-drives", "0.1")
    return layout, cfg, scopes.Scopes.load(layout, cfg), st


def check(repo, text, lesson_ids=()):
    layout, cfg, scope_set, st = repo
    return planmod.check(planmod.Plan(text), st, cfg, scope_set, lesson_ids)


# -- parsing -------------------------------------------------------------------------------

def test_a_good_plan_parses():
    parsed = planmod.Plan(GOOD)
    assert parsed.task == "142-instalments"
    assert parsed.title.endswith("instalments")
    assert parsed.headers["goal"].startswith("split an amount evenly")
    assert parsed.mode == "agent-drives"
    assert parsed.governance == "0.1"
    assert [row.n for row in parsed.rows] == [1, 2, 3]
    assert parsed.rows[0].files == ["packages/billing/src/instalment_plan.py"]
    assert parsed.rows[1].kind == "test"
    assert parsed.rows[2].behavior == "minimum code to pass"


def test_html_comments_are_stripped_before_checking():
    parsed = planmod.Plan(GOOD)
    assert "none" not in (parsed.section("Dependencies") or "")
    assert parsed.section("Dependencies") == ""


def test_the_header_separator_row_is_not_a_step():
    assert len(planmod.Plan(GOOD).rows) == 3


def test_lesson_refs_are_extracted():
    text = GOOD.replace("Rules & lessons: TEST-001",
                        "Rules & lessons: TEST-001, billing#142-instalments.1")
    assert planmod.Plan(text).lesson_refs == ["billing#142-instalments.1"]


def test_as_steps_is_sorted_and_shaped_for_state():
    rows = planmod.Plan(GOOD).as_steps()
    assert rows[0] == {"n": 1, "kind": "stub",
                       "files": ["packages/billing/src/instalment_plan.py"],
                       "behavior": "InstalmentPlan signature"}


def test_hashing_is_stable_and_content_addressed(tmp_path):
    path = tmp_path / "plan.md"
    path.write_text(GOOD)
    assert planmod.hash_file(path) == planmod.sha256(GOOD)
    assert planmod.hash_file(tmp_path / "gone.md") is None


def test_glob_prefix():
    assert planmod.glob_prefix("packages/billing/**/*.py") == "packages/billing"
    assert planmod.glob_prefix("**/*.py") == ""
    assert planmod.glob_prefix("a/b.py") == "a/b.py"


# -- plan-check ----------------------------------------------------------------------------

def test_a_good_plan_passes(repo):
    assert check(repo, GOOD) == []


def test_a_missing_header_line_is_reported(repo):
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith("⚠"))
    assert any("Risks line is missing" in p for p in check(repo, text))


def test_an_empty_header_line_is_reported(repo):
    text = GOOD.replace("⚠️ Risks: rounding", "⚠️ Risks:")
    assert any("Risks line is empty" in p for p in check(repo, text))


def test_a_mode_that_disagrees_with_the_task_is_reported(repo):
    text = GOOD.replace("Mode: agent-drives", "Mode: solo")
    problems = check(repo, text)
    assert any("Mode says 'solo'" in p and "pair mode solo" in p for p in problems)


def test_a_long_global_view_is_reported(repo):
    text = GOOD.replace("\U0001F9ED Approach: a small value object",
                        "\U0001F9ED Approach: a small value object\nextra\nextra\nextra\nextra\nextra")
    assert any("global view is" in p for p in check(repo, text))


def test_a_heading_naming_another_task_is_reported(repo):
    text = GOOD.replace("# Task 142-instalments:", "# Task 999-other:")
    assert any("the active task is" in p for p in check(repo, text))


def test_a_missing_steps_table_is_reported(repo):
    text = GOOD.split("## Steps")[0]
    assert any("no rows" in p for p in check(repo, text))


def test_repeated_step_numbers_are_reported(repo):
    text = GOOD.replace("| 3 | code |", "| 2 | code |")
    assert any("repeat" in p for p in check(repo, text))


def test_decreasing_step_numbers_are_reported(repo):
    text = GOOD.replace("| 1 | stub |", "| 9 | stub |")
    assert any("must increase" in p for p in check(repo, text))


def test_an_unknown_kind_is_reported(repo):
    text = GOOD.replace("| 1 | stub |", "| 1 | sketch |")
    assert any("'sketch' is not a kind" in p for p in check(repo, text))


def test_an_empty_behavior_cell_is_reported(repo):
    text = GOOD.replace("| InstalmentPlan signature |", "|  |")
    assert any("Behavior cell is empty" in p for p in check(repo, text))


def test_two_files_without_a_grant_are_reported_with_the_fix(repo):
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` |",
                        "| 3 | code | `packages/billing/src/instalment_plan.py`, "
                        "`packages/billing/src/other.py` |")
    problems = check(repo, text)
    assert any("one step is one file" in p and "grant-batch --step 3" in p for p in problems)


def test_a_granted_step_must_list_the_grant_globs(repo):
    layout, cfg, scope_set, st = repo
    st.add_batch(3, ["packages/billing/src/**/*.py"], 3, False, "@ana")
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` |",
                        "| 3 | code | `packages/billing/src/other.py` |")
    problems = planmod.check(planmod.Plan(text), st, cfg, scope_set)
    assert any("must list its globs" in p for p in problems)


def test_a_granted_step_listing_its_globs_passes(repo):
    layout, cfg, scope_set, st = repo
    st.add_batch(3, ["packages/billing/src/**/*.py"], 3, False, "@ana")
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` |",
                        "| 3 | code | `packages/billing/src/**/*.py` |")
    assert planmod.check(planmod.Plan(text), st, cfg, scope_set) == []


def test_a_protected_step_file_is_reported(repo):
    text = GOOD.replace("`packages/billing/tests/test_instalment_plan.py`", "`pair/config.toml`")
    assert any("protected path" in p for p in check(repo, text))


def test_a_file_in_no_scope_is_reported(repo):
    text = GOOD.replace("| 2 | test | `packages/billing/tests/test_instalment_plan.py` | "
                        "splits evenly |",
                        "| 2 | test | `pair/tasks/142-instalments/notes.md` | splits evenly |")
    assert any("belongs to no scope" in p or "protected" in p for p in check(repo, text))


def test_a_wrong_file_class_for_the_kind_is_reported(repo):
    text = GOOD.replace("| 2 | test | `packages/billing/tests/test_instalment_plan.py` |",
                        "| 2 | test | `packages/billing/src/other.py` |")
    assert any("is a code file, but a test step writes tests files" in p for p in check(repo, text))


def test_a_scope_without_the_needed_command_is_reported(repo):
    layout, cfg, scope_set, st = repo
    text = GOOD.replace("packages/billing/src/instalment_plan.py", "tools/script.py") \
               .replace("packages/billing/tests/test_instalment_plan.py", "tools/tests/test_s.py")
    assert any("has no `test` command" in p or "has no `coverage` command" in p
               for p in check(repo, text))


def test_code_without_a_preceding_test_is_reported(repo):
    text = GOOD.replace("| 2 | test | `packages/billing/tests/test_instalment_plan.py` | "
                        "splits evenly |\n", "")
    problems = check(repo, text)
    assert any("must come before the first `code` step" in p for p in problems)


def test_a_stub_without_a_later_code_step_on_the_same_file_is_reported(repo):
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` | "
                        "minimum code to pass |\n", "")
    assert any("stub with no later `code` step" in p for p in check(repo, text))


def test_rule_8a_rejects_test_then_stub(repo):
    text = GOOD.replace(
        "| 3 | code | `packages/billing/src/instalment_plan.py` | minimum code to pass |",
        "| 3 | stub | `packages/billing/src/other.py` | another signature |\n"
        "| 4 | code | `packages/billing/src/other.py` | pass |")
    problems = check(repo, text)
    assert any("the next non-doc step must be `code`" in p for p in problems)


def test_rule_8a_rejects_test_then_test(repo):
    text = GOOD.replace(
        "| 3 | code | `packages/billing/src/instalment_plan.py` | minimum code to pass |",
        "| 3 | test | `packages/billing/tests/test_other.py` | another case |\n"
        "| 4 | code | `packages/billing/src/instalment_plan.py` | pass |")
    problems = check(repo, text)
    assert any("left a test red" in p for p in problems)


def test_rule_8a_allows_a_doc_step_between_test_and_code(repo):
    text = GOOD.replace(
        "| 3 | code | `packages/billing/src/instalment_plan.py` | minimum code to pass |",
        "| 3 | doc | `docs/note.md` | explain |\n"
        "| 4 | code | `packages/billing/src/instalment_plan.py` | pass |")
    assert check(repo, text) == []


def test_a_test_step_with_nothing_after_it_is_reported(repo):
    text = GOOD.replace("| 1 | stub | `packages/billing/src/instalment_plan.py` | "
                        "InstalmentPlan signature |\n", "") \
               .replace("| 3 | code | `packages/billing/src/instalment_plan.py` | "
                        "minimum code to pass |\n", "")
    assert any("no `code` step after it" in p for p in check(repo, text))


def test_a_dependency_file_needs_the_dependencies_section(repo):
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` | "
                        "minimum code to pass |",
                        "| 3 | code | `packages/billing/src/instalment_plan.py` | pass |\n"
                        "| 4 | config | `packages/billing/pyproject.toml` | add a dependency |")
    assert any("`## Dependencies` section is required" in p for p in check(repo, text))


def test_a_dependency_file_with_a_filled_section_passes(repo):
    text = GOOD.replace("| 3 | code | `packages/billing/src/instalment_plan.py` | "
                        "minimum code to pass |",
                        "| 3 | code | `packages/billing/src/instalment_plan.py` | pass |\n"
                        "| 4 | config | `packages/billing/pyproject.toml` | add a dependency |") \
               .replace("## Dependencies\n<!-- none -->",
                        "## Dependencies\n- attrs 23.2: value objects; alternatives: dataclasses")
    assert check(repo, text) == []


def test_a_validated_step_may_not_change(repo):
    layout, cfg, scope_set, st = repo
    st.set_steps(planmod.Plan(GOOD).as_steps())
    st.step(1).status = "ok"
    text = GOOD.replace("| 1 | stub | `packages/billing/src/instalment_plan.py` | "
                        "InstalmentPlan signature |",
                        "| 1 | stub | `packages/billing/src/instalment_plan.py` | changed |")
    problems = planmod.check(planmod.Plan(text), st, cfg, scope_set)
    assert any("already validated, so its row may not change" in p for p in problems)


def test_a_validated_step_missing_from_the_plan_is_reported(repo):
    layout, cfg, scope_set, st = repo
    st.set_steps(planmod.Plan(GOOD).as_steps())
    st.step(2).status = "ok"
    text = GOOD.replace("| 2 | test | `packages/billing/tests/test_instalment_plan.py` | "
                        "splits evenly |\n", "")
    problems = planmod.check(planmod.Plan(text), st, cfg, scope_set)
    assert any("missing from the plan" in p for p in problems)


def test_an_unknown_lesson_id_is_reported(repo):
    text = GOOD.replace("Rules & lessons: TEST-001",
                        "Rules & lessons: billing#142-instalments.1")
    assert any("does not exist in pair/learnings/" in p for p in check(repo, text))


def test_a_known_lesson_id_passes(repo):
    text = GOOD.replace("Rules & lessons: TEST-001",
                        "Rules & lessons: billing#142-instalments.1")
    assert check(repo, text, lesson_ids=["billing#142-instalments.1"]) == []


def test_a_step_row_with_a_non_numeric_number_is_reported(repo):
    text = GOOD.replace("| 1 | stub |", "| one | stub |")
    assert any("must be a number" in p for p in check(repo, text))


def test_a_step_with_no_backticked_file_is_reported(repo):
    text = GOOD.replace("| 1 | stub | `packages/billing/src/instalment_plan.py` |",
                        "| 1 | stub |  |")
    assert any("no file is listed" in p for p in check(repo, text))
