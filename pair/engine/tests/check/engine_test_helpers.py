"""Scripted histories the gate tests run against.

Built by driving the real CLI, so a gate is always checked against a history pair itself produced.
"""

from pair import state as state_mod

PLAN = """\
# Task 142-instalments: split an invoice into instalments
\U0001F3AF Goal: split an amount evenly (requirement: docs/req.md)
\U0001F9ED Approach: a small value object
\U0001F50E Explored: searched instalment → nothing reusable
\U0001F4DA Rules & lessons: TEST-001
\U0001F500 Alternatives: a service method, rejected as harder to test
⚠️ Risks: rounding
\U0001F465 Mode: agent-drives · Governance: 0.1

## Steps
| # | Kind | Files | Behavior |
|---|---|---|---|
| 1 | stub | `packages/billing/src/instalments.py` | InstalmentPlan signature |
| 2 | test | `packages/billing/tests/test_instalments.py` | splits evenly |
| 3 | code | `packages/billing/src/instalments.py` | minimum code to pass |

## Tests first
- Scenarios: happy, remainder, zero parts

## Dependencies

## Waivers
"""

WALKTHROUGH = """\
# 142-instalments

## What was built
An instalment plan value object.

## Where it fits
packages/billing, used by invoicing.

## Key decisions
Decimal, not float.

## Waivers used
none

## How to test it
python -m pytest packages/billing

## How to roll it back
pair revert 142-instalments

## Possibly stale knowledge
none

## Lessons
none
"""

STUB = "class InstalmentPlan:\n    pass\n"
TEST = "def test_splits_evenly():\n    assert False\n"
CODE = ("class InstalmentPlan:\n    def __init__(self, total):\n"
        "        self.total = total\n")


def full_task(repo, cli, close=True, task="142-instalments"):
    """start → approve → stub → test → code → close. Returns the base SHA to diff from."""
    from pair import gitcmd
    base = gitcmd.head(repo.root)
    cli.ok("start", task)
    repo.write(f"pair/tasks/{task}/plan.md", PLAN.replace("142-instalments", task))
    cli.ok("approve")

    repo.set_test_result(code=0, output="4 passed")
    repo.write("packages/billing/src/instalments.py", STUB)
    cli.ok("done")
    cli.ok("ok")

    repo.set_test_result(code=1, output="1 failed: AssertionError")
    repo.write("packages/billing/tests/test_instalments.py", TEST)
    cli.ok("done")
    cli.ok("ok")

    repo.set_coverage(hits=((1, 1), (2, 1), (3, 1)), filename="src/instalments.py")
    repo.write("packages/billing/src/instalments.py", CODE)
    cli.ok("done")
    cli.ok("ok")

    if close:
        repo.write(f"pair/tasks/{task}/walkthrough.md", WALKTHROUGH.replace("142-instalments", task))
        cli.ok("close")
    return base
