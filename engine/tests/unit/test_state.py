import json

import pytest

from pair import paths, state
from pair.errors import CheckFailed

pytestmark = pytest.mark.usefixtures("frozen_clock")


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T10:12:00Z")


@pytest.fixture
def layout(tmp_path):
    (tmp_path / "pair").mkdir()
    return paths.Layout(tmp_path)


@pytest.fixture
def fresh(layout):
    return state.State.create(layout, "142-instalments", "@ana", "pair/142-instalments",
                              "agent-drives", "0.1")


def test_create_writes_every_required_field(fresh):
    assert fresh.data["format"] == state.FORMAT
    assert fresh.phase == "planning"
    assert fresh.status == "active"
    assert fresh.created_at == "2026-09-27T10:12:00Z"
    assert fresh.current_step == 0
    assert fresh.is_open


def test_save_and_load_round_trip(fresh, layout):
    path = fresh.save()
    assert path == layout.state("142-instalments")
    again = state.State.load(layout, "142-instalments")
    assert again.data == fresh.data


def test_the_saved_file_is_indented_json_ending_in_a_newline(fresh):
    text = fresh.save().read_text()
    assert text.startswith("{\n  ")
    assert text.endswith("}\n")
    json.loads(text)


def test_loading_a_missing_task_says_so(layout):
    with pytest.raises(CheckFailed) as caught:
        state.State.load(layout, "nope")
    assert "does not exist on this branch" in str(caught.value)


def test_a_broken_file_names_the_problem(layout):
    layout.task_dir("t").mkdir(parents=True)
    layout.state("t").write_text("{nope")
    with pytest.raises(CheckFailed) as caught:
        state.State.load(layout, "t")
    assert "does not parse" in str(caught.value)


def test_an_invalid_field_is_reported(layout):
    with pytest.raises(CheckFailed) as caught:
        state.State.loads(layout, json.dumps({"format": 1, "task": "t", "owner": "ana",
                                              "branch": "b", "mode": "nope", "status": "active",
                                              "phase": "planning", "governance": "0.1",
                                              "created_at": "x", "current_step": 0, "steps": []}))
    message = "\n".join(caught.value.lines())
    assert "owner: must start with @" in message
    assert "mode: must be one of" in message


def test_a_too_new_format_says_upgrade_the_engine(layout, fresh):
    fresh.data["format"] = 99
    with pytest.raises(CheckFailed) as caught:
        state.State.loads(layout, fresh.dumps())
    assert "upgrade the engine" in str(caught.value)


def test_save_refuses_to_write_an_invalid_state(fresh):
    fresh.data["phase"] = "nonsense"
    with pytest.raises(CheckFailed) as caught:
        fresh.save()
    assert "refusing to write" in str(caught.value)


def test_set_steps_snapshots_plan_rows(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a_test.py"], "behavior": "x"},
                     {"n": 2, "kind": "code", "files": ["a.py"], "behavior": "y"}])
    assert [s.n for s in fresh.steps] == [1, 2]
    assert fresh.step(1).status == "pending"
    assert fresh.step(2).kind == "code"
    assert fresh.total_steps == 2


def test_set_steps_keeps_an_ok_step_and_its_evidence(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a_test.py"], "behavior": "x"}])
    fresh.step(1).status = "ok"
    fresh.step(1).evidence = {"result": "red", "summary": "1 failed"}
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a_test.py"], "behavior": "x"},
                     {"n": 2, "kind": "code", "files": ["a.py"], "behavior": "y"}])
    assert fresh.step(1).status == "ok"
    assert fresh.step(1).evidence["summary"] == "1 failed"
    assert fresh.step(2).status == "pending"


def test_steps_are_sorted_by_number(fresh):
    fresh.set_steps([{"n": 3, "kind": "code", "files": ["c.py"], "behavior": ""},
                     {"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""}])
    assert [s.n for s in fresh.steps] == [1, 3]


def test_next_pending_skips_ok_steps(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""},
                     {"n": 2, "kind": "code", "files": ["b.py"], "behavior": ""},
                     {"n": 3, "kind": "doc", "files": ["c.md"], "behavior": ""}])
    fresh.step(1).status = "ok"
    fresh.step(2).status = "ok"
    assert fresh.next_pending().n == 3
    assert fresh.first_unfinished().n == 3
    fresh.step(3).status = "ok"
    assert fresh.next_pending() is None
    assert fresh.first_unfinished() is None


def test_next_pending_can_start_after_a_given_step(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""},
                     {"n": 2, "kind": "code", "files": ["b.py"], "behavior": ""}])
    assert fresh.next_pending(after=1).n == 2


def test_record_approval_stamps_every_unfinished_step(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""},
                     {"n": 2, "kind": "code", "files": ["b.py"], "behavior": ""}])
    fresh.step(1).status = "ok"
    fresh.step(1).data["approved_plan_sha256"] = "old"
    fresh.record_approval("@ana", "new")
    assert fresh.approval == {"by": "@ana", "at": "2026-09-27T10:12:00Z", "plan_sha256": "new"}
    assert fresh.step(1).approved_plan_sha256 == "old"        # an ok step is never restamped
    assert fresh.step(2).approved_plan_sha256 == "new"


def test_clear_approval_resets_only_unfinished_steps(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""},
                     {"n": 2, "kind": "code", "files": ["b.py"], "behavior": ""}])
    fresh.step(1).status = "ok"
    fresh.step(1).evidence = {"result": "red"}
    fresh.step(2).status = "submitted"
    fresh.step(2).evidence = {"result": "green"}
    fresh.clear_approval()
    assert fresh.approval is None
    assert fresh.step(1).status == "ok" and fresh.step(1).evidence
    assert fresh.step(2).status == "pending" and fresh.step(2).evidence is None


def test_a_batch_grant_is_stored_per_step_and_replaces_an_earlier_one(fresh):
    fresh.add_batch(2, ["a/**"], 6, True, "@ana")
    fresh.add_batch(2, ["b/**"], 3, False, "@ana")
    assert len(fresh.batches) == 1
    grant = fresh.batch_for(2)
    assert grant["paths"] == ["b/**"] and grant["max_files"] == 3
    assert grant["include_tests"] is False
    assert fresh.batch_for(1) is None


def test_lessons_are_numbered_from_one(fresh):
    assert fresh.add_lesson("billing", "use Decimal")["n"] == 1
    assert fresh.add_lesson("billing", "and round half up")["n"] == 2
    assert fresh.lesson(2)["text"] == "and round half up"
    assert fresh.lesson(9) is None


def test_events_are_appended_with_who_and_when(fresh):
    fresh.add_event("approve", "@ana")
    fresh.add_event("rework", "@ana", note="use Decimal")
    assert [e["action"] for e in fresh.events] == ["approve", "rework"]
    assert fresh.events[0]["at"] == "2026-09-27T10:12:00Z"
    assert fresh.events[1]["note"] == "use Decimal"
    assert "note" not in fresh.events[0]


def test_is_open_covers_active_and_expedite(fresh):
    for status, expected in [("active", True), ("expedite", True), ("paused", False),
                             ("closed", False), ("abandoned", False)]:
        fresh.status = status
        assert fresh.is_open is expected, status


def test_find_tasks_lists_only_folders_with_a_state_file(layout, fresh):
    fresh.save()
    layout.task_dir("empty-one").mkdir(parents=True)
    assert state.find_tasks(layout) == ["142-instalments"]


def test_find_tasks_is_empty_without_a_tasks_folder(layout):
    assert state.find_tasks(layout) == []


def test_an_evidence_result_outside_the_spec_is_refused(fresh):
    fresh.set_steps([{"n": 1, "kind": "test", "files": ["a.py"], "behavior": ""}])
    fresh.step(1).evidence = {"result": "purple"}
    with pytest.raises(CheckFailed):
        fresh.save()
