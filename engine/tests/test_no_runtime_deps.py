"""The shipped engine imports the standard library only (D2, SPEC 19.2).

Checked by reading the code, not by importing it: an import guarded by a try/except, or reached
only on one platform, still breaks a colleague who installed nothing.
"""

import ast
import pathlib
import sys

DEV_ONLY = {"pytest", "coverage", "jsonschema", "_pytest"}
REPO = pathlib.Path(__file__).resolve().parents[2]
SHIPPED = [REPO / "engine" / "lib", REPO / "engine" / "bin"]


def top_level_imports(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            yield node.module.split(".")[0]


def shipped_files():
    for root in SHIPPED:
        if root.is_dir():
            yield from sorted(root.rglob("*.py"))
            for p in sorted(root.iterdir()):
                if p.is_file() and p.suffix == "" and p.read_bytes()[:2] == b"#!":
                    yield p


def test_shipped_code_imports_only_the_standard_library():
    allowed = set(sys.stdlib_module_names) | {"pair"}
    offenders = []
    for path in shipped_files():
        for name in top_level_imports(path):
            if name in DEV_ONLY or name not in allowed:
                offenders.append(f"{path.relative_to(REPO)}: imports {name!r}")
    assert not offenders, "\n".join(offenders)
