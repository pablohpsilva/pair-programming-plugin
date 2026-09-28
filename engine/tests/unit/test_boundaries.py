import pytest

from pair import boundaries
from pair.errors import CheckFailed

TOML = """\
[modules.shared]
path = "packages/shared"
import_names = ["shared", "@acme/shared"]
may_depend_on = []

[modules.billing]
path = "packages/billing"
import_names = ["billing", "@acme/billing"]
may_depend_on = ["shared"]
"""


@pytest.fixture
def loaded(tmp_path):
    path = tmp_path / "boundaries.toml"
    path.write_text(TOML)
    return boundaries.Boundaries.load(path), tmp_path


def test_modules_load_with_their_allowed_edges(loaded):
    graph, _ = loaded
    assert sorted(graph.modules) == ["billing", "shared"]
    assert graph.modules["billing"].may_depend_on == ["shared"]
    assert graph.configured


def test_a_missing_file_gives_an_empty_graph(tmp_path):
    graph = boundaries.Boundaries.load(tmp_path / "gone.toml")
    assert not graph.configured
    assert graph.violations(tmp_path, ["a.py"]) == []


def test_may_depend_on_naming_an_unknown_module_is_reported(tmp_path):
    path = tmp_path / "b.toml"
    path.write_text(TOML.replace('may_depend_on = ["shared"]', 'may_depend_on = ["nope"]'))
    with pytest.raises(CheckFailed) as caught:
        boundaries.Boundaries.load(path)
    assert "which is not a module" in "\n".join(caught.value.details)


def test_module_of_uses_the_longest_path(tmp_path):
    path = tmp_path / "b.toml"
    path.write_text(TOML + """
[modules.billing-api]
path = "packages/billing/api"
import_names = ["billing.api"]
may_depend_on = ["billing"]
""")
    graph = boundaries.Boundaries.load(path)
    assert graph.module_of("packages/billing/api/x.py").name == "billing-api"
    assert graph.module_of("packages/billing/x.py").name == "billing"
    assert graph.module_of("tools/x.py") is None


@pytest.mark.parametrize("suffix,source,expected", [
    (".py", "import billing\nfrom shared.money import x\n", ["billing", "shared.money"]),
    (".ts", "import a from '@acme/shared';\n", ["@acme/shared"]),
    (".ts", "const x = require(\"@acme/billing\")\n", ["@acme/billing"]),
    (".tsx", "import a from '@acme/shared';\n", ["@acme/shared"]),
    (".go", 'import "example.com/p/shared"\n', ["example.com/p/shared"]),
    (".java", "import static shared.Money;\n", ["shared.Money"]),
    (".rs", "use shared::money;\n", ["shared::money"]),
])
def test_imports_are_read_per_language(loaded, suffix, source, expected):
    graph, _ = loaded
    assert graph.imports_in(source, suffix) == sorted(expected)


def test_an_unknown_extension_yields_nothing(loaded):
    graph, _ = loaded
    assert graph.imports_in("anything", ".sql") == []


def test_a_name_matches_a_module_exactly_or_by_separator(loaded):
    graph, _ = loaded
    assert graph.match_import("shared").name == "shared"
    assert graph.match_import("shared/money").name == "shared"
    assert graph.match_import("shared.money").name == "shared"
    assert graph.match_import("shared::money").name == "shared"
    assert graph.match_import("@acme/shared").name == "shared"
    assert graph.match_import("sharedthing") is None
    assert graph.match_import("os") is None


def test_an_allowed_edge_is_no_violation(loaded):
    graph, root = loaded
    folder = root / "packages" / "billing"
    folder.mkdir(parents=True)
    (folder / "x.py").write_text("from shared.money import cents\n")
    assert graph.violations(root, ["packages/billing/x.py"]) == []


def test_a_disallowed_edge_is_reported(loaded):
    graph, root = loaded
    folder = root / "packages" / "shared"
    folder.mkdir(parents=True)
    (folder / "x.py").write_text("import billing\n")
    problems = graph.violations(root, ["packages/shared/x.py"])
    assert len(problems) == 1
    assert "shared imports billing" in problems[0]
    assert "ARCH-001" in problems[0]


def test_an_import_of_its_own_module_is_fine(loaded):
    graph, root = loaded
    folder = root / "packages" / "shared"
    folder.mkdir(parents=True)
    (folder / "x.py").write_text("from shared.money import cents\n")
    assert graph.violations(root, ["packages/shared/x.py"]) == []


def test_a_file_in_no_module_is_ignored(loaded):
    graph, root = loaded
    (root / "tools").mkdir()
    (root / "tools" / "x.py").write_text("import billing\n")
    assert graph.violations(root, ["tools/x.py"]) == []


def test_a_missing_file_is_skipped(loaded):
    graph, root = loaded
    assert graph.violations(root, ["packages/shared/gone.py"]) == []


def test_project_patterns_override_the_defaults(tmp_path):
    path = tmp_path / "b.toml"
    path.write_text(TOML + '\n[import_patterns]\n".py" = [\'^BRING (\\w+)\']\n')
    graph = boundaries.Boundaries.load(path)
    assert graph.imports_in("BRING shared\nimport billing\n", ".py") == ["shared"]


def test_observed_edges_are_collected(loaded):
    graph, root = loaded
    for name, source in (("shared", "import billing\n"), ("billing", "import shared\n")):
        folder = root / "packages" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "x.py").write_text(source)
    edges = graph.observed(root, ["packages/shared/x.py", "packages/billing/x.py"])
    assert edges == {"shared": {"billing"}, "billing": {"shared"}}


def test_cycles_are_found_and_reported_once():
    found = boundaries.cycles({"a": {"b"}, "b": {"a"}})
    assert len(found) == 1
    assert set(found[0]) == {"a", "b"}


def test_a_longer_cycle_is_found():
    found = boundaries.cycles({"a": {"b"}, "b": {"c"}, "c": {"a"}})
    assert len(found) == 1
    assert set(found[0]) == {"a", "b", "c"}


def test_an_acyclic_graph_has_no_cycles():
    assert boundaries.cycles({"a": {"b"}, "b": set()}) == []
