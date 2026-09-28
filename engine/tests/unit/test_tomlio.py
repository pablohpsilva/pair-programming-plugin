import tomllib

import pytest

from pair import tomlio
from pair.errors import CheckFailed


def round_trip(data):
    return tomllib.loads(tomlio.dumps(data))


def test_scalars_and_lists_round_trip():
    data = {"format": 1, "engine": "0.1.0", "rate": 96.2, "on": True,
            "paths": ["a/**", "b/*.py"], "codes": [5]}
    assert round_trip(data) == data


def test_nested_tables_round_trip():
    data = {"project": {"name": "potato"}, "coverage": {"target": 95, "changed_lines": 100}}
    assert round_trip(data) == data


def test_a_key_needing_quotes_round_trips():
    data = {"scopes": {"packages/billing": {"line": 71.4, "branch": 63.0}}}
    assert round_trip(data) == data
    assert '["scopes"."packages/billing"]' in tomlio.dumps(data) or \
           '[scopes."packages/billing"]' in tomlio.dumps(data)


def test_an_array_of_tables_round_trips():
    data = {"waiver": [{"rule": "PROJ-001", "scope": ["a/**"]},
                       {"rule": "PROJ-002", "scope": ["b/**"]}]}
    assert round_trip(data) == data


def test_a_regex_with_backslashes_survives():
    data = {"import_patterns": {".py": [r"^\s*import\s+([\w.]+)"]}}
    assert round_trip(data) == data


def test_a_string_with_a_quote_and_a_backslash_survives():
    data = {"patterns": [r"""from\s+['"]([^'"]+)['"]"""]}
    assert round_trip(data) == data


def test_comments_are_emitted_and_ignored_by_the_parser():
    text = tomlio.dumps({"modules": {"billing": {"may_depend_on": []}}},
                        comments={"modules.billing.may_depend_on": "observed 2026-09-27"})
    assert "# observed 2026-09-27" in text
    assert tomllib.loads(text) == {"modules": {"billing": {"may_depend_on": []}}}


def test_append_keeps_everything_already_in_the_file(tmp_path):
    path = tmp_path / "waivers.toml"
    path.write_text("# hand-written, keep me\n\n[[waiver]]\nrule = \"PROJ-001\"\n")
    tomlio.append_array_of_tables(path, "waiver", {"rule": "PROJ-002"})
    text = path.read_text()
    assert "# hand-written, keep me" in text
    assert [w["rule"] for w in tomllib.loads(text)["waiver"]] == ["PROJ-001", "PROJ-002"]


def test_append_to_a_missing_file_creates_it(tmp_path):
    path = tmp_path / "nested" / "waivers.toml"
    tomlio.append_array_of_tables(path, "waiver", {"rule": "PROJ-001"})
    assert tomllib.loads(path.read_text())["waiver"][0]["rule"] == "PROJ-001"


def test_dump_writes_a_header(tmp_path):
    path = tmp_path / "boundaries.toml"
    tomlio.dump(path, {"modules": {}}, header=["written by pair init"])
    assert path.read_text().startswith("# written by pair init\n")


def test_a_parse_error_names_the_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("nope = [\n")
    with pytest.raises(CheckFailed) as caught:
        tomlio.load(path, "pair/config.toml")
    assert "pair/config.toml" in str(caught.value)
    assert "does not parse" in str(caught.value)


def test_a_missing_file_is_a_check_failure(tmp_path):
    with pytest.raises(CheckFailed) as caught:
        tomlio.load(tmp_path / "gone.toml", "pair/config.toml")
    assert "is missing" in str(caught.value)


def test_load_if_present_returns_empty_for_a_missing_file(tmp_path):
    assert tomlio.load_if_present(tmp_path / "gone.toml") == {}


def test_an_unwritable_type_is_refused():
    with pytest.raises(CheckFailed):
        tomlio.dumps({"when": object()})
