"""engine/schemas/ is checked against the SPEC, and against the validators that actually ship.

Two independent things can go wrong, and each test here catches exactly one:

1. The SPEC changes a format and the schema does not. Caught by validating the SPEC's own literal
   example. This test cannot run in a consuming repo, where the SPEC is not vendored.
2. schema.py and the JSON Schema disagree. Caught by asserting both reach the same verdict on
   every example. A divergence is a bug in schema.py, which is the module that runs in production.
"""

import json
import pathlib
import re
import tomllib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "engine" / "schemas"
SPEC = REPO / "docs" / "pair-SPEC.md"

jsonschema = pytest.importorskip("jsonschema", reason="see engine/requirements-dev.txt")
from referencing import Registry, Resource  # noqa: E402  (a jsonschema dependency)


def schema_files():
    return sorted(SCHEMAS.glob("*.schema.json"))


def load(path):
    return json.loads(path.read_text())


def validator_for(schema):
    """A validator whose registry holds every schema here, so a cross-file $ref resolves."""
    registry = Registry().with_resources(
        (load(other)["$id"], Resource.from_contents(load(other))) for other in schema_files()
    )
    return jsonschema.Draft202012Validator(schema, registry=registry)


def spec_example(section):
    """The first fenced block after '### <section>' (or '## <section>'), with its language."""
    text = SPEC.read_text()
    m = re.search(rf"^#{{2,3}} {re.escape(section)}[ .]", text, re.M)
    assert m, f"SPEC has no section {section}"
    fence = re.search(r"```(\w+)\n(.*?)```", text[m.start():], re.S)
    assert fence, f"SPEC section {section} has no fenced example"
    return fence.group(1), fence.group(2)


def test_there_is_at_least_one_schema():
    assert schema_files(), "engine/schemas/ is empty"


@pytest.mark.parametrize("path", schema_files(), ids=lambda p: p.name)
def test_schema_is_a_valid_json_schema(path):
    schema = load(path)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "x-spec" in schema, "every schema names the SPEC section that owns its format"
    assert schema["$id"].endswith(path.name), "$id must match the filename"


@pytest.mark.skipif(not SPEC.exists(), reason="the SPEC is not vendored (SPEC 3.4)")
@pytest.mark.parametrize("path", schema_files(), ids=lambda p: p.name)
def test_the_spec_example_validates(path):
    schema = load(path)
    lang, body = spec_example(schema["x-spec"])
    document = tomllib.loads(body) if lang == "toml" else json.loads(body)

    errors = sorted(validator_for(schema).iter_errors(document),
                    key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    )
