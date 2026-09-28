# pair — module map for `engine/lib/pair/`

**This file is enforced, not prose.** `engine/tests/test_modules.py` reads the table below, walks
the AST of every module in `engine/lib/pair/`, and fails when:

1. a module file exists that this table does not list;
2. a module imports another `pair` module whose **layer is not strictly lower** than its own;
3. a listed module's layer is missing or not an integer.

A module listed here **may be absent** — the table is also the plan. Modules appear as the build
steps in SPEC §24 reach them.

Rule 2 is the whole contract: imports only ever point downwards, so the graph is acyclic by
construction and no test needs to hunt for cycles. Two modules in the same layer may **never**
import each other; if they need to, one of them belongs in a lower layer, or the shared part does.

Layer 0 holds the two modules every other one may need — `errors`, so anything can raise, and `globs`, because path matching reaches all the way down to `paths`. Neither imports any pair module, so nothing there can cycle.

Changing this table is a `doc` step like any other. Moving a module between layers is a design
decision: say why in the step report.

| Layer | Module | Responsibility | SPEC |
|---|---|---|---|
| 0 | `errors` | Exception types, one per exit code (§11: 1 check failed, 2 usage, 3 human-only refusal). Imports nothing. | §11 |
| 0 | `globs` | gitignore-style `**` matching. `fnmatch` does not implement `**`, and the file classes, batch grants, waiver scopes, protected paths and coverage exclusions all depend on it. At layer 0 because `paths` needs it and imports nothing else. | §8.1 |
| 1 | `paths` | Repo-root discovery, the `pair/` layout, protected-path globs, the pointer files. | §3, §4, §19.1 |
| 1 | `tomlio` | TOML read (`tomllib`) and write. The standard library has no writer, and `baseline.toml`, `waivers.toml` and `boundaries.toml` are all machine-written. Comments in a hand-edited file are preserved on rewrite. | §10.6, §10.7, §15.1 |
| 1 | `tty` | `confirm()` — the single channel for every human-only confirmation, named by §11.1 so that v2 can replace it without touching a command. | §11.1 |
| 1 | `clock` | `now()` as one seam, so evidence timestamps and golden output are reproducible in tests. | §22.1 |
| 1 | `redact` | Secret redaction applied to evidence summaries before they reach `log.md`. | §8.2, §13 `secrets` |
| 1 | `schema` | Hand-written stdlib validators: required keys, types, enums, floors. The shipped code never reads `engine/schemas/` (§3.4). | §5.2 |
| 1 | `gitcmd` | Thin `subprocess` wrapper over `git`. The only module that runs `git`. | — |
| 2 | `config` | Load and validate `config.toml` and `local/config.toml`, apply the floors from `defaults/config.toml`. | §5 |
| 2 | `rules` | The rule registry, tiers, and duplicate-ID detection across `defaults/rules.md`, `rules/overrides.md` and every scope `RULES.md`. | §6 |
| 3 | `scopes` | `scope.toml` loading and scope resolution by longest path prefix, including "no scope". | §8.4 |
| 3 | `files` | File classification in §8.1 order, first match wins. | §8.1 |
| 4 | `state` | `state.json` read and write. The only writer. | §7.2 |
| 4 | `plan` | `plan.md` parsing, plan-check, and the plan hash. | §10.1 |
| 4 | `log` | Append-only `log.md` entries, and detecting that an earlier entry changed. | §10.3 |
| 4 | `commit` | `git commit --only` with an explicit path list, the `Pair-*` trailers, and the refusal when another tracked path is staged. | §11.3 |
| 4 | `coverage` | Cobertura parsing, changed-line coverage, baselines and the ratchet. | §8.3, §15 |
| 4 | `boundaries` | The import graph: `boundaries.toml`, `import_patterns`, and module matching. | §10.7 |
| 4 | `lessons` | `learnings/<domain>.md`: the line grammar, and edits made in place so a merge keeps both branches' confirmations. | §10.5 |
| 4 | `waivers` | `rules/waivers.toml`: the grant shape, expiry, and the repeat count taken from the file's git history so deleting a line does not reset it. | §10.6 |
| 4 | `sources` | Knowledge-source detection, and turning a registration into a file list under its `include` / `exclude` globs. Below `index`, which consumes it. | §14.1, §14.2 |
| 5 | `evidence` | Running a scope's commands, capturing output, and deciding red / green / wrong-reason. | §8.2, §8.3 |
| 5 | `index` | Chunking and `local/index.json`. | §14.4 |
| 6 | `find` | BM25 scoring, boosts, staleness, and the `--rule` exact path. | §14.5 |
| 6 | `flow` | The phase machine: `start` through `close`, and every transition's preconditions. | §7.4 |
| 7 | `hook` | The three hook entry points and the decision tables. Writes `local/runs/hooks.jsonl`. | §12 |
| 7 | `check` | The CI gates. | §13 |
| 7 | `report` | Metrics. | §20 |
| 7 | `doctor` | Every consistency check, and the install advice. | §11.2, §11.4 |
| 7 | `init` | Interactive setup. | §11.4 |
| 7 | `upgrade` | Vendoring a new engine, format versions, and running migrations. | §18 |
| 8 | `cli` | Argument parsing, dispatch, `--json`, and mapping `errors` to exit codes. | §11 |

## Why the bottom of the stack looks like this

Four of the layer-1 modules exist only because of D2 (standard library only):

- `globs` — `**` is not in `fnmatch` (layer 0, since `paths` needs it);
- `tomlio` — `tomllib` reads and cannot write;
- `schema` — no `jsonschema` at runtime (§3.4);
- `gitcmd` — no `git` bindings.

They are the price of a dependency-free engine, and they are small and heavily tested for exactly
that reason. Each is the **only** module allowed to know its own trick: nothing outside `globs`
writes glob matching by hand, and nothing outside `gitcmd` calls `subprocess` with `git`.
