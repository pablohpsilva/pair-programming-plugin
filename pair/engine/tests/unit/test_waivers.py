import pytest

from pair import waivers
from pair.errors import CheckFailed

ENTRY = {"rule": "PROJ-001", "reason": "legacy float API, wrapped at boundary",
         "scope": ["packages/legacy/**"], "granted_by": "@ana", "granted_at": "2026-09-27",
         "expires": "2026-12-31", "task": "142-instalments"}


@pytest.fixture
def loaded(repo):
    return waivers.Waivers.load(repo.layout.waivers), repo


def test_a_missing_file_is_empty(loaded):
    store, _ = loaded
    assert store.waivers == []
    assert store.expired() == []


def test_a_waiver_round_trips(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    assert [w.rule for w in store.waivers] == ["PROJ-001"]
    assert store.for_rule("PROJ-001")[0].scope == ["packages/legacy/**"]
    assert store.for_rule("PROJ-002") == []


def test_a_malformed_waiver_is_refused(loaded):
    store, _ = loaded
    with pytest.raises(CheckFailed) as caught:
        store.add(dict(ENTRY, expires="soon"))
    assert "look like 2026-12-31" in "\n".join(caught.value.details)


def test_a_missing_field_is_refused(loaded):
    store, _ = loaded
    broken = dict(ENTRY)
    del broken["reason"]
    with pytest.raises(CheckFailed):
        store.add(broken)


def test_expiry_is_compared_by_date(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    assert store.expired(today="2026-10-01") == []
    assert len(store.expired(today="2027-01-01")) == 1
    assert store.active(today="2027-01-01") == []


def test_expiry_on_the_day_itself_is_still_active(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    assert store.expired(today="2026-12-31") == []


def test_covering_matches_the_scope_globs(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    assert store.covering("PROJ-001", "packages/legacy/money.py", today="2026-10-01")
    assert store.covering("PROJ-001", "packages/billing/money.py", today="2026-10-01") is None
    assert store.covering("PROJ-002", "packages/legacy/money.py", today="2026-10-01") is None


def test_an_expired_waiver_covers_nothing(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    assert store.covering("PROJ-001", "packages/legacy/money.py", today="2027-01-01") is None


def test_adding_keeps_comments_in_the_file(loaded):
    store, repo = loaded
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("# hand-written note\n")
    store.add(dict(ENTRY))
    assert "# hand-written note" in store.path.read_text()


def test_remove_rewrites_the_file(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    store.add(dict(ENTRY, rule="PROJ-002"))
    dropped = store.remove(1)
    assert dropped["rule"] == "PROJ-001"
    assert [w.rule for w in store.waivers] == ["PROJ-002"]


def test_removing_the_last_waiver_leaves_a_readable_file(loaded):
    store, _ = loaded
    store.add(dict(ENTRY))
    store.remove(1)
    assert store.waivers == []
    assert waivers.Waivers.load(store.path).waivers == []


def test_removing_a_waiver_that_is_not_there(loaded):
    store, _ = loaded
    with pytest.raises(CheckFailed) as caught:
        store.remove(1)
    assert "there is no waiver 1" in str(caught.value)


def test_the_history_count_survives_a_deletion(loaded):
    store, repo = loaded
    store.add(dict(ENTRY))
    repo.commit_all("waive once")
    assert store.history_count(repo.root, "PROJ-001") == 1

    store.add(dict(ENTRY, reason="second grant", granted_at="2026-10-01"))
    repo.commit_all("waive twice")
    assert store.history_count(repo.root, "PROJ-001") == 2

    store.remove(1)
    repo.commit_all("delete the first")
    assert [w.reason for w in store.waivers] == ["second grant"]
    assert store.history_count(repo.root, "PROJ-001") == 2      # history remembers


def test_the_history_count_ignores_other_rules(loaded):
    store, repo = loaded
    store.add(dict(ENTRY))
    store.add(dict(ENTRY, rule="PROJ-009", reason="other"))
    repo.commit_all("two rules")
    assert store.history_count(repo.root, "PROJ-001") == 1
