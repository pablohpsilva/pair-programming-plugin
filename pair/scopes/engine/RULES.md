# engine — rules

| ID | Rule | Tier | Enforced by |
|---|---|---|---|
| SCOPE-001 | Every module of `engine/lib/pair/` is listed in `docs/MODULES.md` with a layer, and imports point strictly downwards | 1 | C38 |
| SCOPE-002 | A structured format gets its schema in `engine/schemas/` in the same step that first writes it | 1 | C39, review |
| SCOPE-003 | A test fixture is built by `build.sh`, never committed as a git repository | 2 | C40 |

## Coverage exclusions

None.
