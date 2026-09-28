# pair

This folder holds how this repository pairs with an agent. The engineer decides; the agent proposes
and writes one file per validated step.

## Start here

```
pair status          # where the current task stands, and whose turn it is
pair start <id>      # begin a task (human only)
```

`pair doctor` checks this setup and prints anything missing.

## What is where

| Path | What it is |
|---|---|
| `config.toml` | project settings and floors |
| `rules/` | project rules, module boundaries, coverage baselines, waivers, ADRs |
| `scopes/` | per-package commands and rules, mirroring the repository layout |
| `knowledge/`, `learnings/` | team notes and accumulated lessons |
| `tasks/<id>/` | one task: plan, log, state, walkthrough |
| `engine/` | the tool itself — replaced by `pair upgrade`, never edited by hand |
| `local/` | this engineer's machine only, not committed |

## The flow

`planning → stepping → review → closing → done`. One approved step is one commit. Every step shows
its evidence before the engineer validates it.
