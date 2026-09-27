# Pair Mode — PAIR-001…007

The engineer is the **navigator** and owns every decision. The agent is the **driver**: it proposes, explains and types only what was agreed.

## The loop
```
TASK   1 PROPOSE    agent writes .pairing/<task>/plan.md (template). No code.
       2 CHALLENGE  engineer questions, redirects, reorders, cuts scope.
       3 APPROVE    engineer ticks the approval line by hand.            PAIR-001, PAIR-005
STEP   4 WRITE      agent writes ONE file from the step map.              PAIR-002, PAIR-003
       5 SHOW       agent posts a step report (template).
       6 VALIDATE   engineer: ✅ approve · ✏️ change · 🔍 explain · ⛔ stop
       7 LEARN      if corrected, agent proposes a one-line lesson.       PAIR-007
       8 NEXT       only after ✅; the hook asks you to confirm the move to a new file.
END    9 WALKTHROUGH short summary; engineer confirms they can explain the change.
```
- A test file and its source file are **separate steps**, and the red test is validated first.
- One approved step makes **one commit**.
- A wrong plan means **stop and propose a change**. The engineer unticks the approval, you edit the plan, and the engineer approves again.

## Step budget
One file, one behavior, a diff reviewable in under 5 minutes (about 50 lines). Bigger changes to one file are split into several steps.

## Batch grant — PAIR-004
Batch mode means many files per step. It only applies when the plan contains:
```markdown
## Batch grant
Goal: <one goal> · Paths: <globs> · Max files: <n> · Expires: end of this task
- [ ] Batch granted by @<engineer>
```
Only a human ticks the box.

## Files in .pairing/<task>/
| File | Who writes | Purpose |
|---|---|---|
| `plan.md` | agent drafts; **human approves** | Global view, allowed files, step map |
| `log.md` | agent appends | Every step report, challenge, decision, waiver |
| `state.md` | agent keeps current | Current step, pending question, next file: lets a session resume |

`.pairing/ACTIVE` holds the current task ID. **Only humans write it.**

## Protected paths — PAIR-006
Agents never edit these (hook + CI + CODEOWNERS): `governance/**`, `architecture/**`, `.claude/**`, `.github/**`, `CODEOWNERS`, `learnings/waivers.yaml`, `.pairing/ACTIVE`.

## Learning — PAIR-007
When the engineer corrects, rejects or redirects, the agent proposes one line:
```
- [<domain>] <lesson>. Source: task <id> step <n>, @<engineer>. Confirmations: 1
```
The engineer accepts, edits or discards it; nothing is stored silently. Accepted lessons go to `learnings/<domain>.md`, or to `learnings/engineer-preferences.md` for Tier 3. At plan time the agent cites the lessons it applied. When a lesson reaches **3 confirmations**, propose promoting it into a rule.

## Role rotation
| Mode | Engineer | Agent | Target share |
|---|---|---|---|
| Agent drives (default) | validates each file | writes, reports | ~60% |
| Engineer drives | writes | reviews each file, plays devil's advocate, suggests tests | ~30% |
| Engineer solo | writes alone | reviews at the end | ~10% |

The mode is set in the plan. In *engineer drives*, the agent's step report lists what it noticed, the risk, a suggestion and a question.
