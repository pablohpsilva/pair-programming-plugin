"""Every fixture keeps the contract in fixtures/README.md."""

import json
import pathlib
import subprocess
import tomllib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "engine" / "schemas"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"

NAMES = sorted(p.name for p in FIXTURES.iterdir() if (p / "build.sh").is_file())


def test_there_is_at_least_one_fixture():
    assert NAMES, "engine/tests/fixtures/ holds no build.sh"


@pytest.mark.parametrize("name", NAMES)
def test_no_fixture_commits_a_git_repo(name):
    committed = subprocess.run(
        ["git", "ls-files", "-z", str((FIXTURES / name).relative_to(REPO))],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    nested = [p for p in committed if "/.git/" in p or p.endswith("/.git")]
    assert not nested, f"{name} has a committed git repo: {nested} (fixtures/README.md)"


@pytest.mark.parametrize("name", NAMES)
def test_build_sh_is_executable(name):
    assert (FIXTURES / name / "build.sh").stat().st_mode & 0o111, "build.sh must be executable"


@pytest.mark.parametrize("name", NAMES)
def test_build_refuses_a_non_empty_target(name, tmp_path):
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "something").write_text("in the way")
    done = subprocess.run([str(FIXTURES / name / "build.sh"), str(target)], capture_output=True)
    assert done.returncode != 0, "build.sh must refuse a non-empty target"


@pytest.mark.parametrize("name", NAMES)
def test_the_built_repo_is_a_git_repo_with_history(fixture_repo, name):
    repo = fixture_repo(name)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert len(head) == 40
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                            capture_output=True, text=True, check=True).stdout
    assert status == "", f"a fresh fixture must have a clean tree, got:\n{status}"


@pytest.mark.parametrize("name", NAMES)
def test_a_fixture_pair_config_validates(fixture_repo, name):
    jsonschema = pytest.importorskip("jsonschema", reason="see engine/requirements-dev.txt")
    from referencing import Registry, Resource

    repo = fixture_repo(name)
    config = repo / "pair" / "config.toml"
    if not config.is_file():
        pytest.skip(f"{name} has no pair/config.toml")

    registry = Registry().with_resources(
        (json.loads(p.read_text())["$id"], Resource.from_contents(json.loads(p.read_text())))
        for p in sorted(SCHEMAS.glob("*.schema.json"))
    )
    schema = json.loads((SCHEMAS / "config.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema, registry=registry)
    errors = sorted(validator.iter_errors(tomllib.loads(config.read_text())),
                    key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    )
