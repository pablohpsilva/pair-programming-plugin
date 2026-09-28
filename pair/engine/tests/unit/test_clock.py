import datetime

from pair import clock


def test_now_is_utc_and_whole_seconds(monkeypatch):
    monkeypatch.delenv("PAIR_NOW", raising=False)
    moment = clock.now()
    assert moment.tzinfo == datetime.timezone.utc
    assert moment.microsecond == 0


def test_pair_now_freezes_the_clock(monkeypatch):
    monkeypatch.setenv("PAIR_NOW", "2026-09-27T10:40:00Z")
    assert clock.stamp() == "2026-09-27T10:40:00Z"
    assert clock.short() == "2026-09-27T10:40Z"
    assert clock.today() == "2026-09-27"


def test_parse_round_trips_a_stamp():
    assert clock.stamp(clock.parse("2026-09-27T10:40:00Z")) == "2026-09-27T10:40:00Z"


def test_parse_accepts_an_offset_form_and_assumes_utc():
    assert clock.parse("2026-09-27T10:40:00+00:00").hour == 10
    assert clock.parse("2026-09-27T10:40:00").tzinfo == datetime.timezone.utc


def test_parse_returns_none_for_nonsense():
    assert clock.parse("") is None
    assert clock.parse("not a time") is None
    assert clock.parse_date("2026-13-40") is None
    assert clock.parse_date(None) is None


def test_parse_date():
    assert clock.parse_date("2026-09-27").day == 27
