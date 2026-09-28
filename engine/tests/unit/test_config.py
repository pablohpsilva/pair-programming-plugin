import pytest

from pair import config, paths
from pair.errors import CheckFailed

GOOD = """\
format = 1
engine = "0.1.0"
governance = "0.1"

[project]
name = "potato"
default_branch = "main"
"""


@pytest.fixture
def layout(tmp_path):
    (tmp_path / "pair").mkdir()
    (tmp_path / "pair" / "config.toml").write_text(GOOD)
    return paths.Layout(tmp_path)


def write(layout, text, local=None):
    layout.config.write_text(text)
    if local is not None:
        layout.local.mkdir(parents=True, exist_ok=True)
        layout.local_config.write_text(local)
    return config.load(layout)


def test_defaults_fill_in_what_the_project_omits(layout):
    loaded = config.load(layout)
    assert loaded.max_files == 1
    assert loaded.coverage_target == 95
    assert loaded.changed_lines_target == 100
    assert loaded.stale_days == 180
    assert loaded.ask_on_writes is True
    assert loaded.project_name == "potato"
    assert loaded.default_branch == "main"
    assert loaded.governance == "0.1"


def test_the_project_overrides_a_default(layout):
    loaded = write(layout, GOOD + "\n[search]\nstale_days = 30\n")
    assert loaded.stale_days == 30
    assert loaded.max_results == 5           # untouched keys keep the default


def test_file_globs_are_in_spec_order(layout):
    assert list(config.load(layout).file_globs) == list(config.FILE_CLASSES)


def test_an_unknown_key_is_an_error_naming_its_line(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD + "\n[search]\nmax_reslts = 5\n")
    message = "\n".join(caught.value.lines())
    assert "search.max_reslts: is not a known key" in message
    assert "line 10" in message


def test_a_wrong_type_is_an_error(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD.replace('format = 1', 'format = "one"'))
    assert "format: must be a whole number" in "\n".join(caught.value.lines())


def test_a_missing_required_key_is_an_error(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, 'format = 1\nengine = "0.1.0"\n')
    message = "\n".join(caught.value.lines())
    assert "governance: is required" in message
    assert "project: is required" in message


@pytest.mark.parametrize("snippet,expected", [
    ("[steps]\nmax_files = 2\n", "steps.max_files: must be exactly 1"),
    ("[steps]\nbatch_max_files = 80\n", "steps.batch_max_files: must not be above 50"),
    ("[coverage]\ntarget = 80\n", "coverage.target: must not be below 95"),
    ("[coverage]\nchanged_lines = 90\n", "coverage.changed_lines: must be exactly 100"),
    ("[coverage]\nratchet_tolerance = 2.5\n", "coverage.ratchet_tolerance: must not be above 1.0"),
    ("[expedite]\nreview_hours = 96\n", "expedite.review_hours: must not be above 72"),
    ("[expedite]\nmax_files = 40\n", "expedite.max_files: must not be above 20"),
    ("[waivers]\nmax_repeats = 9\n", "waivers.max_repeats: must not be above 3"),
])
def test_a_value_below_its_floor_is_refused(layout, snippet, expected):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD + "\n" + snippet)
    assert expected in "\n".join(caught.value.lines())


def test_a_stricter_value_than_the_floor_is_allowed(layout):
    loaded = write(layout, GOOD + "\n[coverage]\ntarget = 99\nratchet_tolerance = 0.0\n")
    assert loaded.coverage_target == 99
    assert loaded.ratchet_tolerance == 0.0


def test_a_too_new_format_says_upgrade_the_engine(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD.replace("format = 1", "format = 2"))
    assert "upgrade the engine" in str(caught.value)


def test_a_parse_error_names_the_file(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, "format = [\n")
    assert "pair/config.toml does not parse" in str(caught.value)


def test_an_unknown_key_in_the_local_config_is_an_error_too(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD, local='user = "@ana"\n')
    message = "\n".join(caught.value.lines())
    assert "pair/local/config.toml is invalid" in message
    assert "user: is not a known key" in message


def test_a_bad_handle_is_refused(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD, local='me = "ana"\n')
    assert "must start with @" in "\n".join(caught.value.lines())


def test_me_comes_from_the_local_config(layout):
    assert write(layout, GOOD, local='me = "@ana"\n').me == "@ana"


def test_me_falls_back_to_the_git_email(layout, monkeypatch):
    monkeypatch.setattr("pair.gitcmd.config_get", lambda root, name: "bob@example.invalid")
    assert config.load(layout).me == "@bob"


def test_require_me_explains_how_to_fix_it(layout, monkeypatch):
    monkeypatch.setattr("pair.gitcmd.config_get", lambda root, name: None)
    with pytest.raises(CheckFailed) as caught:
        config.load(layout).require_me()
    assert "pair/local/config.toml" in str(caught.value)


def test_sources_take_their_default_trust_from_the_type(layout):
    loaded = write(layout, GOOD + '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n')
    assert loaded.sources[0].trust == "high"
    assert loaded.sources[0].personal is False


def test_an_llm_wiki_source_without_globs_is_refused(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD, local='[[sources]]\ntype = "llm-wiki"\npath = "~/w"\n')
    assert config.LLM_WIKI_NEEDS_GLOBS in "\n".join(caught.value.lines())


def test_an_llm_wiki_source_with_only_include_is_refused(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD,
              local='[[sources]]\ntype = "llm-wiki"\npath = "~/w"\ninclude = ["wiki/**/*.md"]\n')
    assert config.LLM_WIKI_NEEDS_GLOBS in "\n".join(caught.value.lines())


def test_an_llm_wiki_source_with_both_globs_loads(layout):
    loaded = write(layout, GOOD, local=(
        '[[sources]]\ntype = "llm-wiki"\npath = "~/wikis/acme"\n'
        'include = ["wiki/**/*.md"]\nexclude = ["raw/**"]\n'))
    source = loaded.sources[-1]
    assert source.personal is True
    assert source.trust == "medium"
    assert source.exclude == ["raw/**"]


def test_a_shared_source_may_not_point_outside_the_repository(layout):
    with pytest.raises(CheckFailed) as caught:
        write(layout, GOOD + '\n[[sources]]\ntype = "docs"\npath = "~/elsewhere/**/*.md"\n')
    assert "must be inside the repository" in "\n".join(caught.value.lines())


def test_a_personal_source_may_point_outside(layout):
    loaded = write(layout, GOOD, local='[[sources]]\ntype = "markdown"\npath = "/abs/**/*.md"\n')
    assert loaded.sources[0].path == "/abs/**/*.md"


def test_protected_includes_protect_extra(layout):
    loaded = write(layout, GOOD + '\n[protect]\nextra = ["infra/**"]\n')
    assert loaded.protected("infra/main.tf") == "infra/**"
    assert loaded.protected("pair/config.toml")
    assert loaded.protected("src/x.py") is None


def test_a_missing_project_config_is_a_clear_failure(tmp_path):
    # find_root keys on pair/config.toml, so this is only reachable by passing a bad root.
    (tmp_path / "pair").mkdir()
    with pytest.raises(CheckFailed) as caught:
        config.load(paths.Layout(tmp_path))
    assert "pair/config.toml is missing" in str(caught.value)
