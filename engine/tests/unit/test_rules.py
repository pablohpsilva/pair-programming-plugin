import pytest

from pair import paths, rules
from pair.errors import CheckFailed

ENGINE = """\
| ID | Rule | Tier | Enforced by |
|---|---|---|---|
| PAIR-001 | No edits without an approved plan | 0 | hook |
| TEST-007 | Build test data with builders or factories; no shared mutable fixtures | 2 | review |
"""


@pytest.fixture
def layout(tmp_path):
    (tmp_path / "pair" / "engine" / "defaults").mkdir(parents=True)
    (tmp_path / "pair" / "engine" / "defaults" / "rules.md").write_text(ENGINE)
    (tmp_path / "pair" / "rules").mkdir(parents=True)
    (tmp_path / "pair" / "config.toml").write_text("")
    return paths.Layout(tmp_path)


def test_rows_are_parsed_with_tier_and_text():
    found = rules.parse_table(ENGINE, "engine/defaults/rules.md")
    assert [r.id for r in found] == ["PAIR-001", "TEST-007"]
    assert found[0].tier == 0
    assert found[1].text.startswith("Build test data")
    assert found[1].enforced_by == "review"


def test_the_raw_row_is_kept_verbatim_for_find_rule():
    found = rules.parse_table(ENGINE, "s")
    assert found[1].raw == ("| TEST-007 | Build test data with builders or factories; "
                            "no shared mutable fixtures | 2 | review |")


def test_header_separator_and_prose_rows_are_skipped():
    text = ENGINE + "\n| not a rule | x | 2 | y |\nsome prose\n"
    assert len(rules.parse_table(text, "s")) == 2


def test_a_non_numeric_tier_is_an_error():
    with pytest.raises(CheckFailed) as caught:
        rules.parse_table("| PROJ-001 | x | high | review |", "pair/rules/overrides.md")
    assert "tier must be a number" in str(caught.value)


def test_a_tier_outside_0_to_3_is_an_error():
    with pytest.raises(CheckFailed) as caught:
        rules.parse_table("| PROJ-001 | x | 7 | review |", "s")
    assert "tier must be 0-3" in str(caught.value)


def test_the_registry_loads_engine_project_and_scope_rules(layout):
    layout.overrides.write_text("| PROJ-001 | Money uses Decimal | 1 | review |\n")
    scope = layout.scopes_dir / "packages" / "billing"
    scope.mkdir(parents=True)
    (scope / "RULES.md").write_text("| SCOPE-001 | No floats at the edge | 2 | review |\n")
    registry = rules.Registry.load(layout).require_valid()
    assert registry.ids() == ["PAIR-001", "TEST-007", "PROJ-001", "SCOPE-001"]
    assert registry.tier("PROJ-001") == 1


def test_a_duplicate_id_anywhere_is_reported(layout):
    layout.overrides.write_text("| PROJ-001 | a | 1 | review |\n")
    scope = layout.scopes_dir / "a"
    scope.mkdir(parents=True)
    (scope / "RULES.md").write_text("| PROJ-001 | b | 2 | review |\n")
    problems = rules.Registry.load(layout).problems()
    assert any("PROJ-001 is defined twice" in p for p in problems)


def test_two_scopes_cannot_share_a_scope_id(layout):
    for name in ("a", "b"):
        folder = layout.scopes_dir / name
        folder.mkdir(parents=True)
        (folder / "RULES.md").write_text("| SCOPE-001 | x | 2 | review |\n")
    problems = rules.Registry.load(layout).problems()
    assert any("SCOPE-001 is defined twice" in p for p in problems)


def test_only_the_engine_may_define_tier_0(layout):
    layout.overrides.write_text("| PROJ-001 | sneaky | 0 | review |\n")
    problems = rules.Registry.load(layout).problems()
    assert any("only the engine defines Tier 0" in p for p in problems)


def test_a_project_rule_must_use_the_proj_prefix(layout):
    layout.overrides.write_text("| SCOPE-001 | wrong place | 1 | review |\n")
    problems = rules.Registry.load(layout).problems()
    assert any("must use the PROJ- prefix" in p for p in problems)


def test_a_scope_rule_must_use_the_scope_prefix(layout):
    folder = layout.scopes_dir / "a"
    folder.mkdir(parents=True)
    (folder / "RULES.md").write_text("| PROJ-009 | wrong place | 1 | review |\n")
    problems = rules.Registry.load(layout).problems()
    assert any("must use the SCOPE- prefix" in p for p in problems)


def test_require_valid_raises_with_every_problem(layout):
    layout.overrides.write_text("| PROJ-001 | a | 0 | review |\n| SCOPE-002 | b | 1 | review |\n")
    with pytest.raises(CheckFailed) as caught:
        rules.Registry.load(layout).require_valid()
    assert len(caught.value.details) == 2


def test_by_id_returns_none_for_an_unknown_rule(layout):
    assert rules.Registry.load(layout).by_id("NOPE-999") is None


def test_cited_finds_every_rule_id_in_prose():
    assert rules.cited("follows TEST-001 and COV-002, see TEST-001") == ["COV-002", "TEST-001"]
    assert rules.cited(None) == []
