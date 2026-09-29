"""The single channel for a human confirmation (PAIR-005, SPEC 11.1).

Layer 1 of three. Both checks are needed: `isatty` says nothing about the *controlling* terminal,
and a process with piped stdio can normally still reach the engineer's screen through `/dev/tty`.
Verified in build step 0 (T4): the agent's Bash tool has no TTY on any stream and cannot open
`/dev/tty` at all, so this is enforcement rather than a speed bump.

Named by the SPEC as `tty.confirm` so that v2 can replace the channel without touching a command
(SPEC 25).
"""

import sys

from pair.errors import Refused

NO_TERMINAL = (
    "this command is for a human at a terminal (PAIR-005). "
    "Ask the engineer to run it, or run it yourself in your own shell."
)


def available():
    """True when a real controlling terminal can be reached."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except (ValueError, AttributeError):
        return False
    try:
        with open("/dev/tty"):
            return True
    except OSError:
        return False


def confirm(question, expect="y"):
    """Ask on `/dev/tty` and return True only when the answer is exactly `expect`.

    Raises `Refused` (exit 3) when there is no controlling terminal. `expect` is the task id for
    most commands and `y` for `init`, `upgrade` and `baseline` (SPEC 11.1).
    """
    if not available():
        raise Refused(NO_TERMINAL)
    # Two one-way handles, never `r+`: an update mode builds a BufferedRandom, and CPython refuses
    # to build one on a terminal that does not report itself seekable. That is not exotic — it is
    # a plain `io.UnsupportedOperation` traceback on the engineer's own machine, in the one channel
    # every human-only command depends on.
    try:
        with open("/dev/tty", "w") as out, open("/dev/tty", "r") as incoming:
            out.write(f"{question} ")
            out.flush()
            answer = incoming.readline()
    except OSError as problem:
        raise Refused(f"{NO_TERMINAL} (/dev/tty could not be opened: {problem})") from problem
    return answer.strip() == expect
