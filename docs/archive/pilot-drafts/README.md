# Monorepo — Governance Pilot

This repo is built **the right way, not the fast way**. Every change is written in pair mode between an engineer and an AI agent:
- the agent proposes a plan;
- the engineer challenges and approves it;
- the agent writes **one file at a time** and waits for validation before moving on.

## Start here
| You are… | Read |
|---|---|
| An AI agent | [`AGENTS.md`](AGENTS.md), then [`governance/INDEX.md`](governance/INDEX.md) |
| An engineer | [`governance/PAIRING.md`](governance/PAIRING.md) and [`governance/COMMUNICATION.md`](governance/COMMUNICATION.md) |
| Looking for a rule | [`governance/INDEX.md`](governance/INDEX.md): every rule, its ID, owner and how it's enforced |

## Layout
```
AGENTS.md              Agent entry point
governance/            Rules (tiers, pairing, communication, testing, templates)
architecture/          boundaries.yaml: which module may depend on which
learnings/             What agents learned from engineers (reviewed, versioned)
.pairing/<task-id>/    Plan, log and state of each paired task
.claude/               Agent harness settings + the pairing gate hook
.github/workflows/     CI gates
tooling/gates.py       CI gate implementations (scope, step commits, red-first, boundaries, protected paths)
Taskfile.yml           Uniform commands for every language
```

## Uniform commands
Every package, in any language, answers to the same commands (see `Taskfile.yml`):
`task lint` · `task test` · `task coverage` · `task check`

## Starting a task
1. The engineer confirms the task is ready: a requirement, acceptance criteria and a domain.
2. The engineer runs `echo <task-id> > .pairing/ACTIVE`. Only a human does this.
3. The agent writes `.pairing/<task-id>/plan.md` from `governance/templates/plan.template.md`.
4. The engineer challenges the plan, then ticks the approval line **by hand**.
5. Pair mode begins: one file per step, each one validated.

## Pilot status
This is the **pilot set** (governance v0.1). Files are added only when a real problem calls for them; see the rules changelog in `governance/INDEX.md`.
