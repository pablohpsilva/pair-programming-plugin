# Writing Tests — TEST-001…010

| ID | Rule | Tier |
|---|---|---|
| TEST-001 | Write the test **before** the code, as its own step, and see it **fail for the right reason**: the assertion fails, not an import error or typo | 0 |
| TEST-002 | Structure: Arrange–Act–Assert (unit) or Given–When–Then (BDD) | 2 |
| TEST-003 | One behavior per test; the name states the behavior | 2 |
| TEST-004 | Assert **outcomes**, not implementation details (no asserting private calls) | 2 |
| TEST-005 | Mock only what you don't own (network, clock, third parties); use real objects or fakes for your own code | 2 |
| TEST-006 | Deterministic: no real time, unseeded randomness, sleeps, or dependence on test order | 2 |
| TEST-007 | Build test data with builders or factories; no shared mutable fixtures | 2 |
| TEST-008 | Cover the happy path, **edge cases** (0, 1, max, empty, null, unicode) and **error paths** | 2 |
| TEST-009 | Unit tests are fast (< 100 ms each); slow tests are tagged and kept out of the inner loop | 2 |
| TEST-010 | A bug fix starts with a test that **reproduces the bug** | 2 |

## Self-check before showing a test step
- [ ] Which bug would slip through these tests? If I can name one, I add a test.
- [ ] If I deleted the implementation, would every new test fail?
- [ ] Did I run it, and does the failure message point at the missing behavior?

## Example (Python; the same shape in any language)
✅ Good
```python
def test_last_instalment_absorbs_rounding_remainder():
    plan = InstalmentPlan(total=Money("100.00"), parts=3)       # Arrange + Act
    assert [i.amount for i in plan.instalments] == [            # Assert outcome
        Money("33.33"), Money("33.33"), Money("33.34")]
```
❌ Bad
```python
def test_plan():                                   # name says nothing
    plan = InstalmentPlan(Money("100"), 3)
    plan._split = Mock()                           # mocks own code
    plan.build()
    plan._split.assert_called_once()               # asserts implementation
```

## BDD (Gherkin)
```gherkin
Feature: Instalment payments
  Scenario: Remainder goes to the last instalment
    Given an invoice of 100.00 EUR
    When the client pays in 3 instalments
    Then the instalments are 33.33, 33.33 and 33.34 EUR
```
The `.feature` file is written and **reviewed by the engineer before any step definition** exists.

## Step report evidence for a test step
```
🧪 Red: 1 new test fails with "AssertionError: expected [33.33, 33.33, 33.34]" (ran: task test)
```
