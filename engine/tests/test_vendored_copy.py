"""`pair/engine/` is a vendored copy of `engine/` (SPEC 3.2).

The copy is what an agent session actually loads — `bin/` is on PATH from the **plugin root**, so
the `pair` an agent runs is `pair/engine/bin/pair`, never `engine/bin/pair` (SPEC 3.3). A drift
between the two means the tool being tested and the tool being used are different programs.

Refresh it with `pair upgrade --from .` at the end of a build step.
"""

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = REPO / "engine"
VENDORED = REPO / "pair" / "engine"

pytestmark = pytest.mark.skipif(not VENDORED.is_dir(),
                                reason="this repository has no vendored copy yet (SPEC 3.2)")

IGNORED = ("__pycache__", ".pytest_cache")


def files_under(root):
    found = {}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        found[str(path.relative_to(root))] = path
    return found


def test_the_vendored_copy_holds_the_same_files():
    source, vendored = files_under(SOURCE), files_under(VENDORED)
    missing = sorted(set(source) - set(vendored))
    extra = sorted(set(vendored) - set(source))
    assert not missing, ("the vendored copy is missing: " + ", ".join(missing[:10])
                         + " — run `pair upgrade --from .`")
    assert not extra, ("the vendored copy has files the source does not: " + ", ".join(extra[:10]))


def test_every_vendored_file_is_byte_for_byte_the_source():
    source, vendored = files_under(SOURCE), files_under(VENDORED)
    drifted = sorted(rel for rel in set(source) & set(vendored)
                     if source[rel].read_bytes() != vendored[rel].read_bytes())
    assert not drifted, ("the vendored copy has drifted: " + ", ".join(drifted[:10])
                         + " — run `pair upgrade --from .`")


def test_the_marketplace_manifest_sits_above_the_vendored_engine():
    """SPEC 3.3: the marketplace root is `pair/`, the path .claude/settings.json declares."""
    assert (VENDORED.parent / ".claude-plugin" / "marketplace.json").is_file()
    assert not (VENDORED / ".claude-plugin" / "marketplace.json").exists()
    assert (VENDORED / ".claude-plugin" / "plugin.json").is_file()
