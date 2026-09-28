"""A full task, driven through the CLI, for tests that only need the history it leaves."""

from engine_test_helpers import full_task as _full_task


def run_full_task(repo, cli, **kwargs):
    return _full_task(repo, cli, **kwargs)
