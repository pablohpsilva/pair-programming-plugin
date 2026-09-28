import pytest

from pair import config, sources


def with_sources(repo, shared="", local=""):
    text = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", text + shared)
    if local:
        repo.write("pair/local/config.toml", local)
    return config.load(repo.layout)


def test_the_pair_source_is_always_registered(repo):
    repo.write("pair/knowledge/billing.md", "# Billing\n")
    resolved = sources.resolve_all(repo.layout, repo.config)
    assert resolved[0].type == "pair"
    assert any(display == "pair/knowledge/billing.md" for _, display in resolved[0].files)


def test_the_pair_source_reads_rules_learnings_and_scope_docs(repo):
    repo.write("pair/rules/overrides.md", "# Project rules\n")
    repo.write("pair/learnings/billing.md", "# Lessons\n")
    repo.write("pair/scopes/packages/billing/RULES.md", "# Scope rules\n")
    repo.write("pair/scopes/packages/billing/SUMMARY.md", "# What it does\n")
    found = [display for _, display in
             sources.resolve(sources.config_source_for_pair(), repo.layout).files]
    assert "pair/rules/overrides.md" in found
    assert "pair/learnings/billing.md" in found
    assert "pair/scopes/packages/billing/RULES.md" in found
    assert "pair/scopes/packages/billing/SUMMARY.md" in found


def test_a_docs_glob_source_resolves_its_files(repo):
    repo.write("docs/architecture/billing.md", "# Billing\n")
    repo.write("docs/notes.txt", "not markdown\n")
    cfg = with_sources(repo, '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n')
    resolved = [each for each in sources.resolve_all(repo.layout, cfg) if each.type == "docs"][0]
    assert [display for _, display in resolved.files] == ["docs/architecture/billing.md"]


def test_a_directory_source_defaults_to_every_markdown_file(repo):
    repo.write("handbook/a.md", "# A\n")
    repo.write("handbook/deep/b.md", "# B\n")
    cfg = with_sources(repo, '\n[[sources]]\ntype = "markdown"\npath = "handbook"\n')
    resolved = [each for each in sources.resolve_all(repo.layout, cfg) if each.type == "markdown"][0]
    assert sorted(display for _, display in resolved.files) == ["handbook/a.md", "handbook/deep/b.md"]


def test_an_llm_wiki_indexes_only_what_include_matches(repo, tmp_path):
    wiki = tmp_path / "wiki-checkout"
    (wiki / "wiki" / "billing").mkdir(parents=True)
    (wiki / "wiki" / "billing" / "rounding.md").write_text("# Rounding\n")
    (wiki / "raw").mkdir()
    (wiki / "raw" / "dump.md").write_text("# Raw source material\n")
    (wiki / "audit").mkdir()
    (wiki / "audit" / "trail.md").write_text("# Audit\n")
    cfg = with_sources(repo, local=(
        f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
        'include = ["wiki/**/*.md"]\nexclude = ["raw/**", "audit/**"]\n'))
    resolved = [each for each in sources.resolve_all(repo.layout, cfg)
                if each.type == "llm-wiki"][0]
    names = [display for _, display in resolved.files]
    assert names == ["wiki/billing/rounding.md"]
    assert not any("raw" in name for name in names)


def test_exclude_wins_over_include(repo, tmp_path):
    wiki = tmp_path / "w"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "wiki" / "keep.md").write_text("# Keep\n")
    (wiki / "wiki" / "drop.md").write_text("# Drop\n")
    cfg = with_sources(repo, local=(
        f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
        'include = ["wiki/**/*.md"]\nexclude = ["wiki/drop.md"]\n'))
    resolved = [each for each in sources.resolve_all(repo.layout, cfg)
                if each.type == "llm-wiki"][0]
    assert [display for _, display in resolved.files] == ["wiki/keep.md"]


def test_a_source_whose_globs_match_nothing_is_reported_as_empty(repo, tmp_path):
    wiki = tmp_path / "w"
    (wiki / "elsewhere").mkdir(parents=True)
    (wiki / "elsewhere" / "page.md").write_text("# Page\n")
    cfg = with_sources(repo, local=(
        f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
        'include = ["wiki/**/*.md"]\nexclude = ["raw/**"]\n'))
    repo.write("pair/knowledge/note.md", "# Note\n")     # so `pair` itself is not empty
    resolved = sources.resolve_all(repo.layout, cfg)
    empty = sources.empty_sources(resolved)
    assert [each.type for each in empty] == ["llm-wiki"]
    assert empty[0].path == str(wiki)


def test_sources_come_back_in_precedence_order(repo, tmp_path):
    repo.write("docs/a.md", "# A\n")
    repo.write("book/b.md", "# B\n")
    wiki = tmp_path / "w"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "wiki" / "c.md").write_text("# C\n")
    cfg = with_sources(
        repo,
        shared='\n[[sources]]\ntype = "markdown"\npath = "book/**/*.md"\n'
               '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n',
        local=f'[[sources]]\ntype = "llm-wiki"\npath = "{wiki}"\n'
              'include = ["wiki/**/*.md"]\nexclude = ["raw/**"]\n')
    assert [each.type for each in sources.resolve_all(repo.layout, cfg)] == \
        ["pair", "docs", "markdown", "llm-wiki"]


def test_a_home_relative_path_is_expanded(repo, monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / "notes").mkdir(parents=True)
    (home / "notes" / "a.md").write_text("# A\n")
    monkeypatch.setenv("HOME", str(home))
    cfg = with_sources(repo, local='[[sources]]\ntype = "markdown"\npath = "~/notes"\n')
    resolved = [each for each in sources.resolve_all(repo.layout, cfg)
                if each.type == "markdown"][0]
    assert [display for _, display in resolved.files] == ["a.md"]


# -- detection ------------------------------------------------------------------------------

def test_a_docs_folder_with_markdown_is_detected(repo):
    repo.write("docs/a.md", "# A\n")
    found = sources.detect(repo.root)
    assert {"type": "docs", "path": "docs/**/*.md", "trust": "high"} in found


def test_an_empty_docs_folder_is_not_detected(repo):
    (repo.root / "docs").mkdir()
    assert not any(entry["type"] == "docs" for entry in sources.detect(repo.root))


def test_mkdocs_points_at_the_docs_root(repo):
    repo.write("mkdocs.yml", "site_name: x\ndocs_dir: handbook\n")
    repo.write("handbook/a.md", "# A\n")
    found = sources.detect(repo.root)
    assert any(entry["path"] == "handbook/**/*.md" for entry in found)


def test_an_adr_folder_needs_numbered_files(repo):
    repo.write("docs/decisions/0001-use-pair.md", "# ADR\n")
    repo.write("docs/adrs/notes.md", "# not numbered\n")
    found = sources.detect(repo.root)
    adrs = [entry["path"] for entry in found if entry["type"] == "adr"]
    assert adrs == ["docs/decisions/**/*.md"]


def test_readmes_are_offered_as_one_optional_source(repo):
    repo.write("README.md", "# Root\n")
    repo.write("packages/billing/README.md", "# Billing\n")
    found = [entry for entry in sources.detect(repo.root) if entry["type"] == "markdown"]
    assert found == [{"type": "markdown", "path": "**/README.md", "trust": "medium",
                      "optional": True}]


def test_an_llm_wiki_is_never_detected(repo):
    repo.write("wiki/billing/rounding.md", "# Rounding\n")
    repo.write("raw/dump.md", "# Raw\n")
    assert not any(entry["type"] == "llm-wiki" for entry in sources.detect(repo.root))


def test_the_wiki_defaults_are_offered_for_the_engineer_to_confirm():
    offered = sources.wiki_defaults()
    assert offered["include"] == ["wiki/**/*.md"]
    assert "raw/**" in offered["exclude"]
    assert offered["path"] == ""
