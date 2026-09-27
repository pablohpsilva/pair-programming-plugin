"""Shared parsing for the pairing gate hook and the CI gates.

Pure standard library, so the hook runs anywhere Python 3.8+ exists.
Protected path: humans maintain this file.
"""
from __future__ import annotations

import re
from pathlib import Path

PROTECTED = [
    "governance/**",
    "architecture/**",
    ".claude/**",
    ".github/**",
    "CODEOWNERS",
    "tooling/**",
    "learnings/waivers.yaml",
    ".pairing/ACTIVE",
]

# A ticked approval or grant, e.g. "- [x] Approved by @ana" / "- [x] Batch granted by @ana".
TICK_RE = re.compile(r"^\s*[-*]\s*\[[xX]\].*\b(approved|granted)\b", re.I | re.M)
APPROVAL_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*Approved by @([\w.-]+)", re.I | re.M)
BATCH_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*Batch granted by @([\w.-]+)", re.I | re.M)
WAIVER_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*Waiver granted by @([\w.-]+)", re.I | re.M)

TEST_FILE_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|features)/"
    r"|(^|/)test_[^/]+\.py$|_test\.(py|go)$"
    r"|\.(test|spec)\.[jt]sx?$|(Test|Tests|Spec)\.(java|kt)$|\.feature$"
)


def glob_to_regex(pattern: str) -> re.Pattern:
    """Glob with ** support: '**' spans directories, '*' and '?' stay inside one."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def matches(path: str, globs: list[str]) -> bool:
    path = path.lstrip("./") if path.startswith("./") else path
    return any(glob_to_regex(g).match(path) for g in globs)


def is_protected(path: str) -> bool:
    return matches(path, PROTECTED)


def is_test_file(path: str) -> bool:
    return bool(TEST_FILE_RE.search(path))


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def section(text: str, heading: str) -> str:
    """Body of a '## heading' section (until the next '## ')."""
    text = _strip_comments(text)
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def _backticked(body: str) -> list[str]:
    return [p.strip() for p in re.findall(r"`([^`]+)`", body) if p.strip()]


def parse_plan(text: str) -> dict:
    approval = APPROVAL_RE.search(section(text, "Approval"))
    batch_body = section(text, "Batch grant")
    batch = BATCH_RE.search(batch_body)
    paths_line = re.search(r"Paths:\s*(.+?)(?:·|$)", batch_body, re.M)
    max_line = re.search(r"Max files:\s*(\d+)", batch_body)
    batch_paths = []
    if paths_line:
        raw = paths_line.group(1)
        batch_paths = _backticked(raw) or [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]
    return {
        "approved": bool(approval),
        "approver": approval.group(1) if approval else None,
        "allowed": _backticked(section(text, "Allowed files")),
        "batch": {
            "granted": bool(batch),
            "paths": batch_paths,
            "max_files": int(max_line.group(1)) if max_line else 0,
        },
    }


def read_active(root: Path) -> str | None:
    f = root / ".pairing" / "ACTIVE"
    if not f.is_file():
        return None
    task = f.read_text().strip()
    return task if re.fullmatch(r"[\w.-]+", task or "") else None
