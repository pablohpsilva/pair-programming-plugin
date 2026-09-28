# `engine/schemas/`

JSON Schemas (draft 2020-12) for pair's machine-readable formats.

## What they are for

**Tests, not the CLI.** The shipped engine imports the standard library only (D2, §19.2), so it
validates with the hand-written checks in `engine/lib/pair/schema.py`. `jsonschema` is a test
dependency in `engine/requirements-dev.txt` and is never imported by shipped code.

These schemas exist so that the hand-written checks have something independent to be wrong
against. `engine/tests/test_schemas.py` does two things:

1. **Spec agreement.** For each schema, it extracts the literal example from the SPEC section named
   in the schema's `x-spec` field and asserts the example validates. A format that changes in the
   spec and not here fails immediately.
2. **Agreement with the CLI.** For each fixture and golden file that is one of these formats, it
   asserts `jsonschema` and `pair.schema` reach the **same** verdict — both accept or both reject.
   A divergence is a bug in `schema.py`, which is the module that actually runs in production.

Test 1 cannot run in a consuming repo, because `docs/pair-SPEC.md` is not vendored. It skips when
the spec is absent. Test 2 runs everywhere.

## TOML

A schema describes the **parsed** document — what `tomllib.load` returns — not the file's text. So
`[[waiver]]` is an array under the key `waiver`, and `[scopes."packages/billing"]` is a nested
object. Nothing here validates TOML syntax; `tomllib` does that, and a parse failure is the CI
`format` gate's business (§13).

## Adding one

Every structured format listed in §3.4 MUST have a schema here, added by the build step that first
writes that format. Each file is named `<format>.schema.json` and carries:

- `$id`: `https://pair.invalid/schemas/<format>.schema.json`
- `x-spec`: the SPEC section holding the authoritative example, e.g. `"7.2"`
- `additionalProperties: false` wherever the spec says an unknown key is an error (§5.2)

Floors that are a fixed bound (§5.3) are encoded as `const`, `minimum` or `maximum`. Floors that
compare two configured values — a scope `coverage.target` that may only be ≥ the project's — are
not expressible here and live in `schema.py` alone.
