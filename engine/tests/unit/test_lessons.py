import pytest

from pair import lessons, paths

PLAIN = ("- billing#142-instalments.1 — Money amounts use Decimal, never float. "
         "Source: step 2, @ana. Last used: 2026-09-27")
WITH_CONFIRMATIONS = PLAIN + "\n  - confirmed: 143-refunds 2026-09-28\n  - confirmed: 144-tax 2026-09-29"
DISPUTED = ("- ⚠️ disputed billing#142-instalments.1 — Money amounts use Decimal, "
            "never float. Source: step 2, @ana. Last used: 2026-09-27")
DUPLICATED = PLAIN + "\n  - confirmed: 143-refunds 2026-09-28\n  - confirmed: 143-refunds 2026-09-28"


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-10-01T09:00:00Z")
    (tmp_path / "pair" / "learnings").mkdir(parents=True)
    return paths.Layout(tmp_path)


def domain_with(layout, text, name="billing"):
    (layout.learnings / f"{name}.md").write_text(text + "\n")
    return lessons.domain(layout, name)


# -- the grammar, round-tripped (SPEC 10.5 names these four cases) --------------------------

@pytest.mark.parametrize("text", [PLAIN, WITH_CONFIRMATIONS, DISPUTED, DUPLICATED])
def test_round_trip_keeps_the_file_byte_for_byte(layout, text):
    loaded = domain_with(layout, text)
    assert loaded.render() == text + "\n"


def test_a_plain_lesson_parses_into_its_parts(layout):
    lesson = domain_with(layout, PLAIN).lessons[0]
    assert lesson.id == "billing#142-instalments.1"
    assert lesson.text == "Money amounts use Decimal, never float."
    assert lesson.source == "step 2"
    assert lesson.who == "@ana"
    assert lesson.date == "2026-09-27"
    assert lesson.disputed is False
    assert lesson.domain == "billing"


def test_confirmations_are_collected_in_order(layout):
    lesson = domain_with(layout, WITH_CONFIRMATIONS).lessons[0]
    assert lesson.confirmations == [("143-refunds", "2026-09-28"), ("144-tax", "2026-09-29")]
    assert lesson.confirmation_count == 2


def test_a_duplicate_confirmation_left_by_a_merge_counts_once(layout):
    lesson = domain_with(layout, DUPLICATED).lessons[0]
    assert len(lesson.confirmations) == 2
    assert lesson.confirmation_count == 1


def test_a_disputed_lesson_is_recognised(layout):
    lesson = domain_with(layout, DISPUTED).lessons[0]
    assert lesson.disputed is True
    assert lesson.id == "billing#142-instalments.1"


def test_prose_around_the_lessons_is_kept(layout):
    text = "# Billing lessons\n\nSome prose.\n\n" + PLAIN
    loaded = domain_with(layout, text)
    assert len(loaded.lessons) == 1
    assert loaded.render() == text + "\n"


def test_a_confirmation_after_prose_does_not_attach(layout):
    text = PLAIN + "\nsome prose\n  - confirmed: 143-refunds 2026-09-28"
    assert domain_with(layout, text).lessons[0].confirmations == []


def test_a_malformed_line_is_not_a_lesson(layout):
    assert domain_with(layout, "- billing#142.1 missing the dash separator").lessons == []


# -- edits -----------------------------------------------------------------------------------

def test_add_appends_a_well_formed_line(layout):
    loaded = domain_with(layout, "# Billing")
    loaded.add("billing#142-instalments.1", "Use Decimal.", "step 2", "@ana")
    assert len(loaded.lessons) == 1
    assert loaded.lessons[0].date == "2026-10-01"
    assert lessons.Domain(loaded.path, loaded.lines).lessons[0].text == "Use Decimal."


def test_confirm_inserts_a_sub_line_under_the_right_lesson(layout):
    loaded = domain_with(layout, WITH_CONFIRMATIONS)
    assert loaded.confirm("billing#142-instalments.1", "145-fx")
    assert loaded.lessons[0].confirmations[-1] == ("145-fx", "2026-10-01")
    assert loaded.render().splitlines()[3] == "  - confirmed: 145-fx 2026-10-01"


def test_confirm_on_an_unknown_lesson_reports_false(layout):
    assert domain_with(layout, PLAIN).confirm("billing#nope.9", "t") is False


def test_set_last_used_rewrites_only_the_date(layout):
    loaded = domain_with(layout, WITH_CONFIRMATIONS)
    before = loaded.render().splitlines()
    loaded.set_last_used("billing#142-instalments.1", "2026-10-01")
    after = loaded.render().splitlines()
    assert after[0].endswith("Last used: 2026-10-01")
    assert after[1:] == before[1:]
    assert after[0].replace("2026-10-01", "2026-09-27") == before[0]


def test_dispute_prefixes_the_line_and_is_idempotent(layout):
    loaded = domain_with(layout, PLAIN)
    assert loaded.dispute("billing#142-instalments.1") is True
    assert loaded.render().startswith("- ⚠️ disputed billing#142-instalments.1")
    assert loaded.dispute("billing#142-instalments.1") is False


def test_a_disputed_lesson_still_takes_a_confirmation(layout):
    loaded = domain_with(layout, DISPUTED)
    assert loaded.confirm("billing#142-instalments.1", "145-fx")
    assert loaded.lessons[0].disputed


def test_with_text_matches_case_insensitively(layout):
    loaded = domain_with(layout, PLAIN)
    assert loaded.with_text("money amounts use decimal, never float.").id.endswith(".1")
    assert loaded.with_text("something else") is None


def test_next_number_continues_per_task(layout):
    loaded = domain_with(layout, PLAIN)
    assert loaded.next_number("142-instalments") == 2
    assert loaded.next_number("999-other") == 1


def test_save_writes_the_rendered_file(layout):
    loaded = domain_with(layout, PLAIN)
    loaded.add("billing#142-instalments.2", "Round half up.", "step 4", "@ana")
    path = loaded.save()
    assert len(lessons.Domain.load(path).lessons) == 2


def test_saving_a_new_domain_creates_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-10-01T09:00:00Z")
    (tmp_path / "pair").mkdir()
    layout = paths.Layout(tmp_path)
    loaded = lessons.domain(layout, "fresh")
    loaded.add("fresh#1-a.1", "A lesson.", "step 1", "@ana")
    assert loaded.save().is_file()


# -- across domains --------------------------------------------------------------------------

def test_ids_and_all_lessons_span_every_domain(layout):
    domain_with(layout, PLAIN, "billing")
    domain_with(layout, PLAIN.replace("billing#142-instalments.1", "web#9-x.1"), "web")
    assert lessons.ids(layout) == ["billing#142-instalments.1", "web#9-x.1"]
    assert len(lessons.all_lessons(layout)) == 2


def test_no_learnings_folder_yields_nothing(tmp_path):
    (tmp_path / "pair").mkdir()
    assert lessons.ids(paths.Layout(tmp_path)) == []
    assert lessons.domains(paths.Layout(tmp_path)) == []


def test_promotion_candidates_need_distinct_tasks(layout):
    domain_with(layout, WITH_CONFIRMATIONS)
    assert len(lessons.promotion_candidates(layout, 2)) == 1
    assert lessons.promotion_candidates(layout, 3) == []


def test_a_duplicated_confirmation_does_not_promote(layout):
    domain_with(layout, DUPLICATED)
    assert lessons.promotion_candidates(layout, 2) == []


def test_unused_since_finds_a_stale_lesson(layout):
    domain_with(layout, PLAIN)
    assert len(lessons.unused_since(layout, 1, today="2026-12-01")) == 1
    assert lessons.unused_since(layout, 365, today="2026-12-01") == []


def test_format_lesson_matches_the_grammar(layout):
    line = lessons.format_lesson("billing#1-a.1", "Text here.", "step 1", "@ana", "2026-01-01")
    assert lessons.LESSON.match(line)
