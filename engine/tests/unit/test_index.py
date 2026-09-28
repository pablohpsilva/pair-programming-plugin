import pytest

from pair import config, index


def with_docs(repo, extra=""):
    text = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", text + '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n'
               + extra)
    return config.load(repo.layout)


def test_chunks_split_at_headings():
    text = "# One\nalpha\n\n## Two\nbeta\n\n### Three\ngamma\n"
    found = index.chunk(text)
    assert [entry["heading"] for entry in found] == ["One", "Two", "Three"]
    assert found[0]["line"] == 1
    assert found[1]["line"] == 4


def test_a_fourth_level_heading_does_not_split():
    found = index.chunk("# One\n#### Deep\nalpha\n")
    assert [entry["heading"] for entry in found] == ["One"]


def test_a_long_section_is_split_at_sixty_lines():
    text = "# One\n" + "".join(f"line {n}\n" for n in range(150))
    found = index.chunk(text)
    assert len(found) == 3
    assert [len(entry["lines"]) for entry in found] == [60, 60, 30]
    assert found[1]["line"] == 61


def test_content_before_the_first_heading_becomes_a_chunk():
    found = index.chunk("preamble\n\n# One\nalpha\n")
    assert found[0]["heading"] == ""
    assert "preamble" in "\n".join(found[0]["lines"])


def test_an_empty_document_yields_nothing():
    assert index.chunk("") == []
    assert index.chunk("\n\n") == []


def test_term_frequencies_are_lowercase_word_counts():
    assert index.term_frequencies("Money money DECIMAL") == {"money": 2, "decimal": 1}


def test_building_the_index_records_source_and_position(repo):
    repo.write("docs/billing.md", "# Instalments\nSplit the amount evenly.\n")
    built, resolved = index.build(repo.layout, with_docs(repo))
    entry = [chunk for chunk in built.chunks if chunk["file"] == "docs/billing.md"][0]
    assert entry["source_type"] == "docs"
    assert entry["heading"] == "Instalments"
    assert entry["trust"] == "high"
    assert entry["terms"]["evenly"] == 1
    assert entry["preview"].strip() == "Split the amount evenly."


def test_rule_ids_in_a_chunk_are_indexed(repo):
    repo.write("docs/rules.md", "# Testing\nFollow TEST-001 and COV-002.\n")
    built, _ = index.build(repo.layout, with_docs(repo))
    entry = [chunk for chunk in built.chunks if chunk["file"] == "docs/rules.md"][0]
    assert entry["rule_ids"] == ["COV-002", "TEST-001"]


def test_a_tracked_file_records_its_commit_date(repo):
    repo.write("docs/billing.md", "# Instalments\nalpha\n")
    repo.commit_all("add docs")
    built, _ = index.build(repo.layout, with_docs(repo))
    entry = [chunk for chunk in built.chunks if chunk["file"] == "docs/billing.md"][0]
    assert entry["updated"]
    assert entry["git_commit"]


def test_an_untracked_file_has_no_commit(repo):
    repo.write("docs/new.md", "# New\nalpha\n")
    built, _ = index.build(repo.layout, with_docs(repo))
    entry = [chunk for chunk in built.chunks if chunk["file"] == "docs/new.md"][0]
    assert entry["updated"] is None
    assert entry["git_commit"] is None
    assert entry["mtime"] > 0


def test_save_and_load_round_trip(repo):
    repo.write("docs/a.md", "# A\nalpha\n")
    built, _ = index.build(repo.layout, with_docs(repo))
    path = built.save(repo.layout.index_file)
    again = index.Index.load(path)
    assert len(again.chunks) == len(built.chunks)
    assert again.data["built_at"] == built.data["built_at"]


def test_a_broken_index_file_is_treated_as_empty(repo):
    repo.layout.index_file.parent.mkdir(parents=True, exist_ok=True)
    repo.layout.index_file.write_text("{not json")
    assert index.Index.load(repo.layout.index_file).chunks == []


def test_an_index_of_another_format_is_discarded(repo):
    repo.layout.index_file.parent.mkdir(parents=True, exist_ok=True)
    repo.layout.index_file.write_text('{"format": 99, "chunks": [{"file": "x"}]}')
    assert index.Index.load(repo.layout.index_file).chunks == []


def test_stale_files_are_detected_by_mtime(repo):
    repo.write("docs/a.md", "# A\nalpha\n")
    cfg = with_docs(repo)
    built, resolved = index.build(repo.layout, cfg)
    assert built.stale_files(resolved) == []
    import os
    path = repo.root / "docs/a.md"
    path.write_text("# A\nbeta\n")
    os.utime(path, (2000000000, 2000000000))
    assert [display for _, _, display in built.stale_files(resolved)] == ["docs/a.md"]


def test_an_incremental_rebuild_keeps_unchanged_chunks(repo):
    repo.write("docs/a.md", "# A\nalpha\n")
    repo.write("docs/b.md", "# B\nbeta\n")
    cfg = with_docs(repo)
    first, _ = index.build(repo.layout, cfg)
    first.save(repo.layout.index_file)

    import os
    path = repo.root / "docs/b.md"
    path.write_text("# B\ngamma delta\n")
    os.utime(path, (2000000000, 2000000000))

    second, _ = index.build(repo.layout, cfg, previous=first, incremental=True)
    a_chunk = [c for c in second.chunks if c["file"] == "docs/a.md"][0]
    b_chunk = [c for c in second.chunks if c["file"] == "docs/b.md"][0]
    assert a_chunk["terms"] == {"a": 1, "alpha": 1}
    assert "gamma" in b_chunk["terms"]


def test_a_removed_file_drops_out_of_the_index(repo):
    repo.write("docs/a.md", "# A\nalpha\n")
    repo.write("docs/b.md", "# B\nbeta\n")
    cfg = with_docs(repo)
    first, _ = index.build(repo.layout, cfg)
    (repo.root / "docs/b.md").unlink()
    second, _ = index.build(repo.layout, cfg, previous=first, incremental=True)
    assert {c["file"] for c in second.chunks} == {"docs/a.md"}


def test_refresh_writes_the_index_and_returns_it(repo):
    repo.write("docs/a.md", "# A\nalpha\n")
    cfg = with_docs(repo)
    built, resolved = index.refresh(repo.layout, cfg)
    assert repo.layout.index_file.is_file()
    assert built.chunks
    again, _ = index.refresh(repo.layout, cfg)
    assert again.data["built_at"] == built.data["built_at"]    # nothing changed, nothing rebuilt
