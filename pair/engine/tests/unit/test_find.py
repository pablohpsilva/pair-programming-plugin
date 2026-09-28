import pytest

from pair import config, find, index, rules

DOCS = {
    "docs/billing.md": "# Instalments\nSplit the amount evenly across parts.\n",
    "docs/rounding.md": "# Rounding\nMoney amounts round half up, never down.\n",
    "docs/unrelated.md": "# Deployment\nThe service deploys on merge.\n",
}


def build(repo, extra=""):
    for path, text in DOCS.items():
        repo.write(path, text)
    base = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml",
               base + '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n' + extra)
    cfg = config.load(repo.layout)
    built, _ = index.build(repo.layout, cfg)
    return built, cfg


def test_a_query_finds_the_right_document(repo):
    built, _ = build(repo)
    hits = find.search(built, "instalments evenly")
    assert hits
    assert hits[0].file == "docs/billing.md"


def test_an_unrelated_query_finds_nothing(repo):
    built, _ = build(repo)
    assert find.search(built, "kubernetes helm") == []


def test_an_empty_query_finds_nothing(repo):
    built, _ = build(repo)
    assert find.search(built, "") == []


def test_a_heading_match_outranks_a_body_match(repo):
    repo.write("docs/a.md", "# Rounding\nnothing much here\n")
    repo.write("docs/b.md", "# Other\nrounding rounding rounding rounding\n")
    base = (repo.root / "pair/config.toml").read_text()
    repo.write("pair/config.toml", base + '\n[[sources]]\ntype = "docs"\npath = "docs/**/*.md"\n')
    cfg = config.load(repo.layout)
    built, _ = index.build(repo.layout, cfg)
    hits = find.search(built, "rounding")
    assert hits[0].file == "docs/a.md"


def test_the_pair_source_is_boosted_over_docs(repo):
    repo.write("pair/knowledge/rounding.md", "# Rounding\nMoney amounts round half up.\n")
    built, _ = build(repo)
    hits = find.search(built, "rounding half up")
    assert hits[0].source_type == "pair"


def test_results_can_be_limited(repo):
    built, _ = build(repo)
    assert len(find.search(built, "the", limit=1)) <= 1


def test_results_can_be_filtered_by_source_type(repo):
    repo.write("pair/knowledge/rounding.md", "# Rounding\nhalf up\n")
    built, _ = build(repo)
    hits = find.search(built, "rounding", source_type="docs")
    assert hits and all(hit.source_type == "docs" for hit in hits)


def test_results_can_be_filtered_by_scope(repo):
    built, _ = build(repo)
    assert find.search(built, "instalments", scope="packages/") == []
    assert find.search(built, "instalments", scope="docs/")


def test_the_rendered_hit_matches_the_spec_shape(repo):
    build(repo)
    repo.commit_all("docs")
    built, cfg = build(repo)
    hit = find.search(built, "instalments")[0]
    rendered = hit.render(stale_days=180, today="2026-09-28")
    assert rendered.startswith("[docs] docs/billing.md#Instalments (updated ")
    assert "\n  Split the amount evenly across parts." in rendered


def test_a_stale_file_is_flagged(repo):
    build(repo)
    repo.commit_all("docs")
    built, _ = build(repo)
    hit = find.search(built, "instalments")[0]
    assert "⚠ stale?" in hit.render(stale_days=1, today="2030-01-01")
    assert "⚠ stale?" not in hit.render(stale_days=3650, today="2026-09-28")


def test_a_hit_serialises_for_json(repo):
    built, _ = build(repo)
    data = find.search(built, "instalments")[0].as_data()
    assert data["file"] == "docs/billing.md"
    assert data["heading"] == "Instalments"
    assert isinstance(data["score"], float)


def test_find_rule_returns_the_exact_row(repo):
    repo.write("pair/engine/defaults/rules.md",
               "| ID | Rule | Tier | Enforced by |\n|---|---|---|---|\n"
               "| TEST-007 | Build test data with builders or factories; no shared mutable "
               "fixtures | 2 | review |\n")
    registry = rules.Registry.load(repo.layout)
    rule = find.by_rule(registry, "TEST-007")
    assert rule.raw == ("| TEST-007 | Build test data with builders or factories; no shared "
                        "mutable fixtures | 2 | review |")
    assert find.by_rule(registry, "NOPE-001") is None


def test_queries_are_logged_per_task(repo):
    built, _ = build(repo)
    hits = find.search(built, "instalments")
    path = find.log_query(repo.layout, "142-instalments", "instalments", hits)
    assert path.is_file()
    entries = find.read_log(repo.layout, "142-instalments")
    assert entries[0]["query"] == "instalments"
    assert entries[0]["hits"][0]["file"] == "docs/billing.md"


def test_nothing_is_logged_without_an_active_task(repo):
    built, _ = build(repo)
    assert find.log_query(repo.layout, None, "q", []) is None
    assert find.read_log(repo.layout, "142-instalments") == []


def test_a_broken_log_line_is_skipped(repo):
    path = repo.layout.find_log / "t.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"query": "a"}\nnot json\n\n')
    assert find.read_log(repo.layout, "t") == [{"query": "a"}]
