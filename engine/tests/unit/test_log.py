import pytest

from pair import log

SAMPLE = """\
### 2026-09-27T10:40Z · approve · @ana
### 2026-09-27T10:52Z · step 1 · done (red) · 1 failed: AssertionError
### 2026-09-27T10:53Z · step 1 · report
\U0001F4CD Step 1/3 (test)
✅ pair ok
### 2026-09-27T10:55Z · step 1 · ok · @ana
"""


@pytest.fixture
def path(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T11:00:00Z")
    return tmp_path / "log.md"


def test_entries_are_split_at_headings():
    found = log.entries(SAMPLE)
    assert len(found) == 4
    assert found[0].at == "2026-09-27T10:40Z"
    assert found[0].action == "approve"
    assert found[2].body.startswith("\U0001F4CD Step 1/3")


def test_a_step_number_is_read_from_the_heading():
    found = log.entries(SAMPLE)
    assert found[0].step is None
    assert found[1].step == 1
    assert found[1].action == "done"


def test_prose_before_the_first_heading_is_ignored():
    assert len(log.entries("# Log\n\nsome prose\n" + SAMPLE)) == 4


def test_an_empty_log_has_no_entries():
    assert log.entries("") == []
    assert log.entries(None) == []


def test_append_creates_the_file_and_stamps_the_time(path):
    log.append(path, ["approve", "@ana"])
    assert path.read_text() == "### 2026-09-27T11:00Z · approve · @ana\n"


def test_append_adds_a_body(path):
    log.append(path, ["step 1", "report"], body="\U0001F4CD Step 1/3\n")
    assert path.read_text().endswith("\U0001F4CD Step 1/3\n")
    assert len(log.entries(path.read_text())) == 1


def test_append_keeps_earlier_entries(path):
    log.append(path, ["approve", "@ana"])
    log.append(path, ["step 1", "done (red)"])
    assert len(log.entries(path.read_text())) == 2


def test_append_fixes_a_missing_final_newline(path):
    path.write_text("### 2026-09-27T10:00Z · start · @ana")
    log.append(path, ["approve", "@ana"])
    assert len(log.entries(path.read_text())) == 2


def test_action_entry_shapes_the_heading(path):
    entry = log.action_entry(path, "done", "@ana", step=2, detail="green")
    assert entry == "### 2026-09-27T11:00Z · step 2 · done (green) · @ana"


def test_action_entry_without_a_step(path):
    assert log.action_entry(path, "pause", "@ana") == \
        "### 2026-09-27T11:00Z · pause · @ana"


def test_appended_only_accepts_an_addition():
    assert log.appended_only(SAMPLE, SAMPLE + "### 2026-09-27T11:00Z · pause · @ana\n")


def test_appended_only_rejects_a_changed_entry():
    tampered = SAMPLE.replace("approve · @ana", "approve · @bob")
    assert not log.appended_only(SAMPLE, tampered)


def test_appended_only_rejects_a_removed_entry():
    shorter = "\n".join(SAMPLE.splitlines()[1:])
    assert not log.appended_only(SAMPLE, shorter)


def test_appended_only_rejects_a_changed_body():
    tampered = SAMPLE.replace("✅ pair ok", "✅ nothing to see")
    assert not log.appended_only(SAMPLE, tampered)


def test_changed_entries_names_what_changed():
    tampered = SAMPLE.replace("approve · @ana", "approve · @bob")
    problems = log.changed_entries(SAMPLE, tampered)
    assert problems == ["entry changed: ### 2026-09-27T10:40Z · approve · @ana"]


def test_changed_entries_names_a_removal():
    problems = log.changed_entries(SAMPLE, "")
    assert len(problems) == 4
    assert all(p.startswith("entry removed") for p in problems)


def test_every_action_the_cli_writes_is_listed():
    for action in ("start", "approve", "done", "ok", "rework", "reopen", "pause", "resume",
                   "handoff", "abandon", "close", "grant-batch", "waive", "expedite",
                   "lesson-propose", "lesson-accept", "lesson-edit", "lesson-reject",
                   "lesson-dispute"):
        assert action in log.CLI_ACTIONS, action
