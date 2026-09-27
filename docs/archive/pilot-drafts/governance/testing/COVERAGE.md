# Coverage — COV-001…004

| ID | Rule | Tier | Enforced by |
|---|---|---|---|
| COV-001 | ≥ **95%** line **and** branch coverage per package | 0 | each package's `task coverage` fails below 95% |
| COV-002 | **100%** of changed lines covered in every PR | 0 | CI `diff-cover --fail-under=100` |
| COV-003 | Coverage never decreases (ratchet) | 0 | pilot: reviewer checks the CI report; tool later |
| COV-004 | Every exclusion has a reason and a human approver | 0 | pilot: reviewer; tool later |

## Package contract
Every package's `task coverage` must:
1. run all tests with **branch** coverage on;
2. **fail** below 95% line or branch;
3. write a Cobertura report to `<package>/coverage/coverage.xml`. CI merges these reports for the diff check.

## Per-language commands
| Language | Command in the package Taskfile |
|---|---|
| Python | `pytest --cov=src --cov-branch --cov-fail-under=95 --cov-report=xml:coverage/coverage.xml` |
| TypeScript | vitest: `coverage: { provider: 'v8', reporter: ['cobertura'], reportsDirectory: 'coverage', thresholds: { lines: 95, branches: 95 } }` |
| Go | `go test -coverprofile=c.out -covermode=atomic ./...` then `gocover-cobertura < c.out > coverage/coverage.xml`, plus a threshold script |
| Java/Kotlin | JaCoCo `check` rule with `LINE` and `BRANCH` minimum `0.95`, XML report converted to Cobertura |
| Rust | `cargo llvm-cov --branch --fail-under-lines 95 --cobertura --output-path coverage/coverage.xml` |

## Exclusions (COV-004)
Allowed only for generated code, trivial wiring (`main`) and third-party shims. An inline pragma (`# pragma: no cover`, `/* istanbul ignore */`, …) needs a line in the package's `RULES.md`:
```
Excluded: <path or symbol> — <reason> — approved by @<engineer> <date>
```
Agents may **propose** an exclusion in a step report; they never add one on their own.

## Coverage is not proof
High coverage shows that code **ran**, not that it was **checked**. Pair it with the self-check in `WRITING-TESTS.md`. Mutation testing (≥ 80%) arrives after the pilot.
