"""One exception per exit code (SPEC 11).

0 ok · 1 a check failed or a precondition wasn't met · 2 usage · 3 human-only or owner-only refusal.
"""


class PairError(Exception):
    """Base for every failure the CLI reports. `exit_code` is what `pair` returns."""

    exit_code = 1

    def __init__(self, message, details=()):
        super().__init__(message)
        self.message = message
        self.details = list(details)

    def lines(self):
        return [self.message, *self.details]


class CheckFailed(PairError):
    """A check failed, or a precondition wasn't met."""

    exit_code = 1


class UsageError(PairError):
    """The command was called wrongly."""

    exit_code = 2


class Refused(PairError):
    """Human-only or owner-only: the caller may not do this (PAIR-005)."""

    exit_code = 3
