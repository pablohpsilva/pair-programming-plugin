import pytest

from pair import tty
from pair.errors import Refused


def test_no_terminal_means_refused(monkeypatch):
    monkeypatch.setattr(tty, "available", lambda: False)
    with pytest.raises(Refused) as caught:
        tty.confirm("type the task id")
    assert caught.value.exit_code == 3
    assert "human at a terminal" in str(caught.value)


def test_available_is_false_under_pytest_because_there_is_no_tty():
    # The suite runs with captured stdio, which is exactly the agent's situation (T4).
    assert tty.available() is False


def test_confirm_compares_the_answer_exactly(monkeypatch):
    monkeypatch.setattr(tty, "available", lambda: True)
    answers = iter(["142-instalments", "no"])

    class FakeChannel:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def write(self, _):
            pass

        def flush(self):
            pass

        def readline(self):
            return next(answers) + "\n"

    monkeypatch.setattr("builtins.open", lambda *a, **k: FakeChannel())
    assert tty.confirm("id?", expect="142-instalments") is True
    assert tty.confirm("id?", expect="142-instalments") is False
