import pytest

from pair import coverage
from pair.errors import CheckFailed

XML = """\
<?xml version="1.0" ?>
<coverage line-rate="0.962" branch-rate="0.954" version="1.9">
  <packages>
    <package name="src">
      <classes>
        <class filename="src/money.py" name="money">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="1"/>
            <line number="5" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def test_the_root_rates_are_read_as_percentages():
    report = coverage.Report.parse(XML)
    assert report.line_rate == 96.2
    assert report.branch_rate == 95.4


def test_per_line_hits_are_read():
    report = coverage.Report.parse(XML)
    assert report.known_lines("src/money.py") == {1: 1, 2: 1, 5: 0}


def test_a_report_path_is_matched_by_suffix():
    report = coverage.Report.parse(XML)
    assert report.known_lines("packages/billing/src/money.py") == {1: 1, 2: 1, 5: 0}
    assert report.known_lines("other/file.py") == {}


def test_missing_rates_are_zero():
    report = coverage.Report.parse('<coverage><packages/></coverage>')
    assert report.line_rate == 0.0
    assert report.branch_rate == 0.0


def test_broken_xml_is_reported():
    with pytest.raises(CheckFailed) as caught:
        coverage.Report.parse("<coverage", "the report")
    assert "not readable XML" in str(caught.value)


def test_xml_that_is_not_cobertura_is_reported():
    with pytest.raises(CheckFailed) as caught:
        coverage.Report.parse("<testsuite/>", "the report")
    assert "not Cobertura XML" in str(caught.value)


def test_a_missing_report_explains_what_the_command_must_write(tmp_path):
    with pytest.raises(CheckFailed) as caught:
        coverage.Report.load(tmp_path / "gone.xml")
    assert "PAIR_COVERAGE_XML" in str(caught.value)


def test_changed_lines_ignore_lines_the_report_does_not_know():
    report = coverage.Report.parse(XML)
    percentage, uncovered = coverage.changed_lines_covered(report, {"src/money.py": {1, 2, 99}})
    assert percentage == 100.0
    assert uncovered == {}


def test_an_uncovered_changed_line_is_reported():
    report = coverage.Report.parse(XML)
    percentage, uncovered = coverage.changed_lines_covered(report, {"src/money.py": {1, 2, 5}})
    assert percentage == 66.67
    assert uncovered == {"src/money.py": [5]}


def test_a_step_with_no_measurable_line_is_fully_covered():
    report = coverage.Report.parse(XML)
    assert coverage.changed_lines_covered(report, {"docs/a.md": {1, 2}}) == (100.0, {})
    assert coverage.changed_lines_covered(report, {}) == (100.0, {})


def test_pragmas_are_found_by_line():
    text = "a = 1\nb = 2  # pragma: no cover\n/* istanbul ignore next */\n@Generated\n"
    assert coverage.find_pragmas(text) == [2, 3, 4]
    assert coverage.find_pragmas("") == []


# -- baselines and the floor formula -------------------------------------------------------

@pytest.fixture
def baselines(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T10:00:00Z")
    return coverage.Baselines.load(tmp_path / "baseline.toml")


def test_no_entry_means_the_floor_is_the_target(baselines):
    assert baselines.floor("packages/billing", 95, 0.5) == (95.0, 95.0)


def test_a_baseline_below_the_target_gives_baseline_minus_tolerance(baselines):
    baselines.scopes["b"] = {"line": 71.4, "branch": 63.0, "measured_at": "2026-01-01"}
    assert baselines.floor("b", 95, 0.5) == (70.9, 62.5)


def test_a_baseline_above_the_target_never_falls_below_the_target(baselines):
    baselines.scopes["b"] = {"line": 95.2, "branch": 99.0, "measured_at": "2026-01-01"}
    assert baselines.floor("b", 95, 0.5) == (95.0, 98.5)


def test_a_baseline_exactly_at_the_target_holds_the_target(baselines):
    baselines.scopes["b"] = {"line": 95.0, "branch": 95.0, "measured_at": "2026-01-01"}
    assert baselines.floor("b", 95, 0.5) == (95.0, 95.0)


def test_a_tolerance_of_zero_pins_the_baseline(baselines):
    baselines.scopes["b"] = {"line": 71.4, "branch": 63.0, "measured_at": "2026-01-01"}
    assert baselines.floor("b", 95, 0.0) == (71.4, 63.0)


def test_a_floor_never_goes_below_zero(baselines):
    baselines.scopes["b"] = {"line": 0.2, "branch": 0.0, "measured_at": "2026-01-01"}
    assert baselines.floor("b", 95, 1.0) == (0.0, 0.0)


def test_raise_to_only_raises_and_restamps(baselines):
    baselines.scopes["b"] = {"line": 71.4, "branch": 63.0, "measured_at": "2026-01-01"}
    assert baselines.raise_to("b", 80.0, 60.0) is True
    assert baselines.scopes["b"]["line"] == 80.0
    assert baselines.scopes["b"]["branch"] == 63.0          # a lower branch value is ignored
    assert baselines.scopes["b"]["measured_at"] == "2026-09-27"


def test_raise_to_reports_no_change_when_nothing_improves(baselines):
    baselines.scopes["b"] = {"line": 71.4, "branch": 63.0, "measured_at": "2026-01-01"}
    assert baselines.raise_to("b", 71.4, 63.0) is False
    assert baselines.scopes["b"]["measured_at"] == "2026-01-01"


def test_pair_ok_never_creates_an_entry(baselines):
    assert baselines.raise_to("brand-new", 99.0, 99.0) is False
    assert baselines.entry("brand-new") is None


def test_pair_baseline_adds_a_missing_scope(baselines):
    assert baselines.set_measured("brand-new", 88.0, 77.0) is True
    assert baselines.entry("brand-new") == {"line": 88.0, "branch": 77.0,
                                           "measured_at": "2026-09-27"}


def test_pair_baseline_never_lowers(baselines):
    baselines.set_measured("b", 88.0, 77.0)
    assert baselines.set_measured("b", 50.0, 50.0) is False
    assert baselines.entry("b")["line"] == 88.0


def test_lower_records_who_and_why(baselines):
    baselines.set_measured("b", 88.0, 77.0)
    baselines.lower("b", 50.0, 40.0, "@ana", "deleted a well-tested module")
    entry = baselines.entry("b")
    assert entry["line"] == 50.0
    assert entry["lowered_by"] == "@ana"
    assert entry["lowered_reason"] == "deleted a well-tested module"


def test_save_and_load_round_trip(baselines):
    baselines.set_measured("packages/billing", 71.4, 63.0)
    path = baselines.save()
    assert path.read_text().startswith("# coverage baselines")
    again = coverage.Baselines.load(path)
    assert again.entry("packages/billing") == {"line": 71.4, "branch": 63.0,
                                              "measured_at": "2026-09-27"}


def test_an_invalid_baseline_file_is_reported(tmp_path):
    path = tmp_path / "baseline.toml"
    path.write_text('[scopes."b"]\nline = 71.4\n')
    with pytest.raises(CheckFailed) as caught:
        coverage.Baselines.load(path)
    assert "branch: is required" in "\n".join(caught.value.details)
