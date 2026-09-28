# Migrations

One file per layout version step, named `NNN_<name>.py`, exporting `migrate(layout)`.

Each one MUST be idempotent — `pair upgrade` may be interrupted and re-run — and each one MUST have
a test (SPEC 18). `NNN` is the `config.format` the migration brings the repository *to*.

There are none yet: format 1 is the first.
