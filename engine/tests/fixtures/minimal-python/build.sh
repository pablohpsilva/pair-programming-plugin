#!/usr/bin/env bash
# Builds the minimal fixture repo: one python package, a hand-written pair/ tree, two commits.
# Usage: build.sh <target-dir>    (the directory must be empty or absent)
#
# Hand-written, not produced by `pair init`, on purpose: this fixture is what the CLI is tested
# against, so it must not depend on the code under test. See fixtures/README.md.
set -euo pipefail

target="${1:?usage: build.sh <target-dir>}"
if [[ -e "$target" && -n "$(ls -A "$target" 2>/dev/null)" ]]; then
  echo "build.sh: $target is not empty" >&2
  exit 1
fi
mkdir -p "$target"
cd "$target"

git init -q -b main .
git config user.name  "Fixture Engineer"
git config user.email "fixture@example.invalid"
git config commit.gpgsign false
git config core.hooksPath .git/hooks-unused

export GIT_AUTHOR_NAME="Fixture Engineer"  GIT_COMMITTER_NAME="Fixture Engineer"
export GIT_AUTHOR_EMAIL="fixture@example.invalid" GIT_COMMITTER_EMAIL="fixture@example.invalid"

mkdir -p packages/billing/src packages/billing/tests

cat > packages/billing/pyproject.toml <<'EOF'
[project]
name = "billing"
version = "0.1.0"
requires-python = ">=3.11"
EOF

cat > packages/billing/src/__init__.py <<'EOF'
EOF

cat > packages/billing/src/money.py <<'EOF'
def cents(amount: float) -> int:
    """Rounds half up, which is what the fixture's one test pins."""
    return int(amount * 100 + 0.5)
EOF

cat > packages/billing/tests/test_money.py <<'EOF'
from src.money import cents


def test_cents_rounds_half_up():
    assert cents(1.005) == 101
EOF

export GIT_AUTHOR_DATE="2026-01-05T09:00:00Z" GIT_COMMITTER_DATE="2026-01-05T09:00:00Z"
git add -A
git commit -q -m "feat(billing): cents conversion"

# ---- pair/ ---------------------------------------------------------------------------------
mkdir -p pair/rules/decisions pair/scopes/_repo pair/scopes/packages/billing pair/knowledge \
         pair/learnings pair/tasks pair/reports

cat > pair/.gitignore <<'EOF'
local/
EOF

cat > pair/README.md <<'EOF'
# pair

Fixture repository. See the SPEC for what belongs here.
EOF

cat > pair/config.toml <<'EOF'
format = 1
engine = "0.1.0"
governance = "0.1"

[project]
name = "fixture"
default_branch = "main"

[steps]
max_files = 1
max_changed_lines = 50
batch_max_files = 20

[coverage]
target = 95
changed_lines = 100
ratchet_tolerance = 0.5

[[sources]]
type = "docs"
path = "docs/**/*.md"
trust = "high"
include = ["docs/**/*.md"]
exclude = ["docs/archive/**"]
EOF

cat > pair/scopes/_repo/scope.toml <<'EOF'
path = ""
cwd = "."
module = ""

[commands]
test = ""
coverage = ""
lint = ""
validate = ""
migrate_check = ""
EOF

cat > pair/scopes/packages/billing/scope.toml <<'EOF'
path = "packages/billing"
cwd = "packages/billing"
timeout_seconds = 600
no_tests_exit_codes = [5]
module = "billing"

[commands]
test = "python -m pytest -q"
coverage = "python -m pytest -q --cov=src --cov-branch --cov-report=xml:$PAIR_COVERAGE_XML"
lint = ""
validate = ""
migrate_check = ""
EOF

cat > pair/scopes/packages/billing/RULES.md <<'EOF'
# packages/billing — rules

No SCOPE rules yet.

## Coverage exclusions

None.
EOF

cat > pair/rules/overrides.md <<'EOF'
# Project rules

| ID | Tier | Rule |
|---|---|---|
EOF

cat > pair/rules/boundaries.toml <<'EOF'
[modules.billing]
path = "packages/billing"
import_names = ["billing", "src"]
may_depend_on = []

[import_patterns]
".py" = ['^\s*import\s+([\w.]+)', '^\s*from\s+([\w.]+)\s+import']
EOF

cat > pair/rules/baseline.toml <<'EOF'
[scopes."packages/billing"]
line = 88.0
branch = 75.0
measured_at = "2026-01-05"
EOF

cat > pair/rules/waivers.toml <<'EOF'
EOF

export GIT_AUTHOR_DATE="2026-01-06T09:00:00Z" GIT_COMMITTER_DATE="2026-01-06T09:00:00Z"
git add -A
git commit -q -m "chore: set up pair"
