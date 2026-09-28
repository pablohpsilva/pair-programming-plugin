"""The one place time enters the engine.

Every timestamp pair writes comes from here, so tests and golden files are reproducible
(SPEC 22.1). `PAIR_NOW` freezes it, which is how a test drives the CLI as a subprocess without
reaching inside it; nothing else in the engine reads the environment for behaviour.
"""

import datetime
import os

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def now():
    frozen = os.environ.get("PAIR_NOW")
    if frozen:
        return datetime.datetime.strptime(frozen, _FORMAT).replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def stamp(moment=None):
    """`2026-09-27T10:40:00Z` — what state.json and log.md record."""
    return (moment or now()).strftime(_FORMAT)


def short(moment=None):
    """`2026-09-27T10:40Z` — the log heading and the SessionStart line (SPEC 12.3)."""
    return (moment or now()).strftime("%Y-%m-%dT%H:%MZ")


def today(moment=None):
    """`2026-09-27` — lesson dates, waiver dates, baseline `measured_at`."""
    return (moment or now()).strftime("%Y-%m-%d")


def parse(text):
    """A stamp written by `stamp()` back to a datetime, or None when it is unreadable."""
    if not text:
        return None
    try:
        return datetime.datetime.strptime(text, _FORMAT).replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def parse_date(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
    except (ValueError, TypeError):
        return None
