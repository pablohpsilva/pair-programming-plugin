"""docs/MODULES.md is a contract: imports only ever point to a strictly lower layer.

The table is the plan as well as the map, so a listed module may be absent. A module that
exists and is *not* listed is a failure: that is how a module gets added without anyone
deciding which layer it belongs to.
"""

import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
MODULES_MD = REPO / "docs" / "MODULES.md"
PKG = REPO / "engine" / "lib" / "pair"

# "| 4 | `state` | … |" -> (4, "state"). Only rows whose first cell is an integer count, which
# skips the header, the separator and any other table in the file.
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([a-z_]+)`\s*\|")


def declared_layers():
    layers = {}
    for line in MODULES_MD.read_text().splitlines():
        m = ROW.match(line)
        if m:
            layer, name = int(m.group(1)), m.group(2)
            assert name not in layers, f"{name} is listed twice in MODULES.md"
            layers[name] = layer
    return layers


def internal_imports(path):
    """Every `pair` module imported by this file, however it is spelled."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "pair" and len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.level:                                  # from .x import y / from . import x
                if node.module:
                    found.add(node.module.split(".")[0])
                else:
                    found.update(a.name for a in node.names)
            elif node.module:
                parts = node.module.split(".")
                if parts[0] == "pair" and len(parts) > 1:
                    found.add(parts[1])
                    # from pair import state
                elif parts == ["pair"]:
                    found.update(a.name for a in node.names)
    return found


pytestmark = pytest.mark.skipif(
    not MODULES_MD.exists(),
    reason="MODULES.md is not vendored into a consuming repo (SPEC 3.4)",
)


def modules_on_disk():
    if not PKG.is_dir():
        return []
    return sorted(p for p in PKG.glob("*.py") if p.name != "__init__.py")


def test_every_module_on_disk_is_listed():
    listed = set(declared_layers())
    on_disk = {p.stem for p in modules_on_disk()}
    unlisted = sorted(on_disk - listed)
    assert not unlisted, (
        f"not in docs/MODULES.md: {unlisted}. Add a row with the layer it belongs to, "
        f"or move the code into a module that is already listed."
    )


def test_imports_point_strictly_downwards():
    layers = declared_layers()
    failures = []
    for path in modules_on_disk():
        mine = layers[path.stem]
        for other in sorted(internal_imports(path)):
            if other not in layers:
                failures.append(f"{path.stem} imports {other}, which is not in MODULES.md")
            elif layers[other] >= mine:
                failures.append(
                    f"{path.stem} (layer {mine}) imports {other} (layer {layers[other]}): "
                    f"an import must point to a strictly lower layer"
                )
    assert not failures, "\n".join(failures)


def test_the_table_itself_is_well_formed():
    layers = declared_layers()
    assert layers, "MODULES.md has no module rows — the regex or the table changed shape"
    assert min(layers.values()) == 0, "layer 0 must exist: nothing can be at the bottom otherwise"
    present = sorted(set(layers.values()))
    assert present == list(range(present[-1] + 1)), f"layers must be contiguous, got {present}"
