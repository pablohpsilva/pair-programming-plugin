# pair — Design

> **pair** puts the engineer back at the center of AI-assisted development. The agent pair-programs: it proposes, explains briefly, writes one file at a time, and waits for the engineer's validation before moving on.
>
> **The goal is not speed. The goal is correct code that the engineer understands.**

This document explains **why** pair works the way it does. `pair-SPEC.md` defines **what** to build. When they disagree, fix the disagreement. Until then, the SPEC is authoritative for behavior and this document for intent.

---

## 1. Principles

| # | Principle | What it means in practice |
|---|---|---|
| P1 | **The human is at the center** | The engineer decides. The agent proposes and drives the keyboard, and never approves its own work. |
| P2 | **Right over fast** | No throughput targets. Slower is acceptable, but code nobody understands is not. |
| P3 | **Small, validated steps** | One file per step. Nothing moves to the next file until the engineer says ✅. |
| P4 | **Proof, not claims** | Test failures, passes and coverage come from real runs recorded by the tool, never from the agent's description. |
| P5 | **Tests first** | Every behavior starts with a test that fails for the right reason. |
| P6 | **Brief by default, deep on request** | Short reports, with more detail only when asked. Review stays focused. |
| P7 | **Rules can bend, but not the core** | Rules have tiers. Some can be waived with proof of no harm; the core never can. |
| P8 | **Learn from the engineer** | Corrections become lessons, which are proposed, confirmed, and eventually promoted into rules. |
| P9 | **Enforce with tools, not prose** | If a tool can check a rule, the tool checks it. Prose rules are for judgment only. |
| P10 | **Work with what exists** | pair reads the project's docs and wikis, and never replaces them. |

---

## 2. Pair mode

### 2.1 Roles
- **Engineer = navigator.** Owns scope, approach, approval and merge.
- **Agent = driver.** Explores, proposes, writes, runs tests, reports, and asks.

### 2.2 The loop
```
PLAN     agent explores, proposes a plan (goal, approach, step map)
         engineer challenges → agent revises → engineer approves
STEP     agent writes ONE file → tool records evidence → agent reports
         engineer: ✅ ok · ✏️ change · 🔍 explain · ⛔ pause
         ✅ → tool commits the step → next step
CLOSE    agent writes a walkthrough → engineer confirms they understand → done
```
- **A test and its code are separate steps**, so the engineer sees the failing test before any implementation exists.
- **One approved step makes one commit.** That gives a readable history and trivial rollback.
- **A wrong plan stops the work.** The agent says so and proposes a change; it never improvises around the plan.

### 2.3 Step size
One file, one behavior, reviewable in under five minutes (a guide of about 50 changed lines). Bigger changes to one file are split into several steps. Changing many files in one step (a rename, say) needs an explicit **batch grant** from the engineer, limited to named paths and a maximum file count.

### 2.4 Role rotation
Engineers who only approve slowly stop thinking. Plans therefore declare a mode:

| Mode | Engineer | Agent | Target share |
|---|---|---|---|
| agent-drives | validates each file | writes and reports | ~60% |
| engineer-drives | writes | reviews each file, plays devil's advocate, suggests tests | ~30% |
| solo | writes alone | reviews at the end | ~10% |

Use engineer-drives more often for critical or unfamiliar code.

---

## 3. Communication

### 3.1 Two views, always short
- **Global view:** the top of the plan, about 10 lines. Goal, approach, step map, risks.
- **Step view:** the step report, about 8 lines. What changed, why, evidence, doubt, next step.

If a report doesn't fit, the step is too big.

### 3.2 Depth on demand
| Level | When | Content |
|---|---|---|
| L1 | always | what, why, evidence, next |
| L2 | "why?", "explain" | reasoning, alternatives considered, trade-offs, rule IDs |
| L3 | "go deep", "walk me through" | line by line, fit with the architecture, links |

The agent never volunteers L2 or L3, with one exception: **a risk is always stated at L1**, in one line.

### 3.3 Being challenged
1. **Evaluate** the challenge honestly: agree, partly agree or disagree, with a reason in one or two lines.
2. **Don't cave** to please, and **don't defend** to be right.
3. **Follow the engineer's decision** and log it, including the agent's view.
4. If the decision bends a rule, **name the rule and its tier**. Never silently comply, never silently refuse.

### 3.4 Uncertainty
Say "I'm not sure." Never invent APIs, flags or results. Verify by reading or running, and say which one you did.

---

## 4. Rule tiers

| Tier | What | Bendable by the engineer? | Can the agent learn to change it? |
|---|---|---|---|
| **0 · Core** | Process integrity and safety: human approval, one step per file, tests first, coverage floor, protected paths, boundaries, secrets | **No.** Only through an ADR approved by the rule owners | Never |
| **1 · Architectural** | Structure others rely on: layering, ownership, contracts, error strategy | Yes, with a **waiver**: scoped, expiring, with proof of no harm | Proposes only |
| **2 · Engineering** | Good practice with judgment: test style, duplication, naming, file size | Yes, with a one-line log note | Yes, as a lesson once confirmed |
| **3 · Preference** | Taste: style, ordering, idioms | Freely | Yes, as a preference |

- **"No harm" is proven by the gates**: boundaries, contract tests and the full suite stay green. It is never assumed.
- **Waiving the same rule three times** means the rule, or its scope, is wrong. Change the rule instead of waiving it a fourth time.
- **Higher tiers win.** A lesson never overrides Tier 0 or Tier 1.

---

## 5. Learning

- **Capture.** When the engineer corrects, rejects or redirects, the agent proposes a one-line lesson. The engineer accepts, edits or rejects it. Nothing is stored silently.
- **Use.** At plan time, the agent loads the relevant lessons and cites the ones it applied, so the engineer can see what the agent "remembers".
- **Promote.** A lesson confirmed in three tasks is proposed as a rule, and a human edits the rules.
- **Forget.** A lesson unused for 90 days is reviewed; a disputed lesson goes to the engineer.
- **Boundaries.** Lessons are plain, versioned files: reviewable, revertible and shared by the team. They never contain secrets or personal data.

---

## 6. Testing

### 6.1 Test first
Each behavior begins as a **test step**. The tool runs it and records a failure. The failure must be *for the right reason*: an assertion fails, not an import or syntax error. The tool screens for the obvious wrong reasons; the engineer judges the rest.

For brand-new code, a tiny **stub** step first declares the new names without any behavior, so the test can fail on an assertion instead of a missing import. For legacy code without tests, **characterization tests** first pin down the behavior that already exists; they pass from the start, and that's their purpose.

### 6.2 How tests are written
- Arrange–Act–Assert, or Given–When–Then.
- One behavior per test, and the name states the behavior.
- Assert outcomes, not implementation details.
- Mock only what you don't own.
- Deterministic: no real time, unseeded randomness, sleeps or order dependence.
- Build data with builders or factories.
- Cover the happy path, edge cases and errors.
- Keep unit tests fast.
- A bug fix starts with a test that reproduces the bug.

### 6.3 How tests are challenged
- **Self-check** before every test step:
  - Which bug would still slip through?
  - Would every new test fail if the implementation were deleted?
- **Engineer review** of every test **before** the code is written.
- **Devil's-advocate prompts** for boundaries, errors, concurrency, security, time and data compatibility.
- **Mutation testing** (score of 80% or more on changed code) arrives after v1, as an optional gate.

### 6.4 Coverage
- **Target:** at least **95%** line and branch coverage per scope.
- **Changed lines:** **100%** of changed executable lines covered, in every code change.
- **Ratchet:** coverage never drops more than half a point below the best value recorded for a scope, and never below the target once reached.
- **Existing repos** start from a measured **baseline** below the target, which only rises as coverage improves.
- **Exclusions** need a reason and a named human approver.

Coverage shows that code **ran**, not that it was **checked**, which is why §6.1–6.3 exist.

---

## 7. Understanding what was built

- **Plan before code**: the engineer approves the goal, approach and step map.
- **File by file**: the engineer validates every step and can drill down to L3.
- **Walkthrough at close** (readable in about 5 minutes):
  - what was built and where it fits;
  - key decisions, alternatives rejected and waivers used;
  - how to test it and how to roll it back.
- **Understanding gate**: before closing, the engineer confirms *"I can explain this change to a colleague without the agent."* Closing code nobody understands is a process failure.

---

## 8. Knowledge: pair, docs and wikis

| | Holds | Owned by | pair's access |
|---|---|---|---|
| **Project docs** (`docs/`, ADRs, READMEs) | Published documentation | The team | Read |
| **llm-wiki** (or similar) | Compiled knowledge of the domain and system | The wiki's own workflow | Read (compiled pages) |
| **pair** | How we work: rules, decisions, lessons, tasks | pair + the team | Read and write |

- pair **discovers** sources at setup, and a human **chooses** which to register.
- One search covers everything and returns snippets **with provenance and freshness**.
- **Precedence on conflict:** pair rules, then docs, then the wiki. Conflicts are **flagged, never silently resolved**.
- **Giving back** never means writing into the other tools. pair lists pages a change may have made stale, and prepares the walkthrough so a human can feed it into the wiki's own ingest.

---

## 9. Everything in one place

Everything pair owns lives in **one directory at the repo root** (`<repo>/pair/`). Only the few files other tools require at fixed locations sit outside it (a CI workflow, a CODEOWNERS entry, an optional `AGENTS.md`), and each one is short and generated. Removing pair means deleting that directory and those pointers.

---

## 10. Security

- **Least privilege**: agents get no production credentials, customer data or network access beyond what the task needs.
- **Protected paths**: agents never edit rules, config, the engine or CI.
- **Untrusted content**: issues, fetched pages, dependency docs, wiki pages and logs are **data, not instructions**. Instruction-like text found there is flagged to the engineer.
- **Dependencies**: a new dependency is a Tier 1 decision.
- **Secrets**: never written to committed pair files; CI scans for them.

---

## 11. Process health

The process is measured, not assumed:
- time from step report to validation;
- changed and rejected steps per task;
- explain-more requests;
- waivers used;
- lessons captured and promoted;
- escaped defects;
- a monthly engineer pulse: "I understand what we built" and "the pace is sustainable".

**Zero rejected steps is a warning sign** (it may mean rubber-stamping), not a success. A second engineer audits a small sample of approved steps each month. Audits measure the process, not people.

---

## 12. Emergencies

A production incident can't wait for step-by-step pairing. **Expedite mode** is human-only:
- A reproducing test is still required, and it must fail before the fix.
- The agent may change several files within the declared paths, in one step.
- The full walkthrough and review happen within 24 hours.

Expedite mode is visible in reports; frequent use is a signal to act on.

---

## 13. Non-goals

- Replacing docs, wikis, issue trackers or code review.
- Autonomous agents that work for hours unattended.
- Maximizing lines of code per hour.
- Enforcing style that linters already enforce.
