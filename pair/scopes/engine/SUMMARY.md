# engine

The engine is pair itself: a standard-library-only Python package (`lib/pair/`), one entry point
(`bin/pair`), the plugin that loads it into an agent session (`.claude-plugin/`, `hooks/`,
`skills/`), and the data it ships (`defaults/`, `templates/`, `schemas/`, `migrations/`).

`docs/MODULES.md` is the map, and it is enforced: every module carries a layer, and an import may
only point to a strictly lower one. Start there rather than here.

Two boundaries are worth knowing before changing anything:

- **Nothing shipped may import a third-party package** (D2). Four layer-1 modules exist only
  because of that rule — `globs`, `tomlio`, `schema` and `gitcmd` — and each is the only place
  allowed to know its own trick.
- **The engine writes nothing outside the repository** (D15). C37 runs the whole install flow with
  `$HOME` pointed at an empty directory and asserts it stays empty.
