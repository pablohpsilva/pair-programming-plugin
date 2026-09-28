"""globs: gitignore-style ** matching. fnmatch has no **, hence this module (D2)."""

import pytest

from pair import globs


@pytest.mark.parametrize("pattern,path", [
    ("**/test_*.py", "test_x.py"),
    ("**/test_*.py", "a/b/test_x.py"),
    ("**/tests/**", "tests/x.py"),
    ("**/tests/**", "a/tests/b/x.py"),
    ("packages/billing/**/*.py", "packages/billing/src/x.py"),
    ("packages/billing/**/*.py", "packages/billing/x.py"),
    ("pair/engine/**", "pair/engine/lib/pair/cli.py"),
    ("**/*.test.[jt]s", "a/b/thing.test.ts"),
    ("**/*.test.[jt]s", "a/b/thing.test.js"),
    ("**/build.gradle*", "app/build.gradle.kts"),
    ("docs/**/*.md", "docs/a/b.md"),
    ("*.md", "README.md"),
    ("**", "anything/at/all.py"),
    ("a/**/b", "a/b"),
    ("a/**/b", "a/x/y/b"),
])
def test_matches(pattern, path):
    assert globs.match(path, pattern), f"{pattern!r} should match {path!r}"


@pytest.mark.parametrize("pattern,path", [
    ("**/test_*.py", "a/b/spec_x.py"),
    ("**/tests/**", "tests"),                       # the directory itself, not a file under it
    ("packages/billing/**/*.py", "packages/other/x.py"),
    ("pair/engine/**", "pair/engine"),
    ("pair/engine/**", "pair/config.toml"),
    ("**/*.test.[jt]s", "a/thing.test.py"),
    ("docs/**/*.md", "src/a.md"),
    ("*.md", "docs/a.md"),                          # a bare pattern is anchored at the root
    ("a/**/b", "a/b/c"),
    ("src/*.py", "src/a/b.py"),                     # one star never crosses a separator
])
def test_does_not_match(pattern, path):
    assert not globs.match(path, pattern), f"{pattern!r} should not match {path!r}"


def test_match_any_reports_the_pattern_that_matched():
    assert globs.match_any("a/tests/x.py", ["**/*.go", "**/tests/**"]) == "**/tests/**"
    assert globs.match_any("src/x.py", ["**/*.go", "**/tests/**"]) is None


def test_a_backslash_in_a_pattern_is_literal_not_an_escape():
    assert globs.match("a+b.py", "a+b.py")
    assert not globs.match("axb.py", "a+b.py")


def test_leading_slash_and_dot_slash_are_normalised():
    assert globs.match("src/x.py", "/src/x.py")
    assert globs.match("src/x.py", "./src/x.py")
