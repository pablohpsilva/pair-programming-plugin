"""Knowledge sources: detection, and turning a registration into a list of files (SPEC 14).

pair never writes to a source except `pair` itself. `llm-wiki` is deliberately **not** detected by
folder name — the layout was never verified against a real checkout (T7), so every such source
carries its own `include`/`exclude` globs and the engineer confirms them (SPEC 14.2, D-T7).
"""

import os
import pathlib
import re

from pair import globs

TRUST_ORDER = {"high": 0, "medium": 1, "low": 2}
# SPEC 14.6: pair > docs/adr > markdown > llm-wiki.
PRECEDENCE = {"pair": 0, "docs": 1, "adr": 1, "markdown": 2, "llm-wiki": 3}

MARKDOWN_SUFFIXES = (".md", ".mdx", ".markdown")
DEFAULT_INCLUDE = ["**/*.md"]
WIKI_INCLUDE = ["wiki/**/*.md"]
WIKI_EXCLUDE = ["raw/**", "log/**", "audit/**", ".cache/**", "**/embeddings/**"]

ADR_FILE = re.compile(r"^\d{3,4}-.*\.md$")
DOC_FOLDERS = ("docs", "doc", "documentation")
ADR_FOLDERS = ("adr", "adrs", "decisions")

# SPEC 14.1: what the always-registered `pair` source reads.
PAIR_GLOBS = (
    "pair/rules/**",
    "pair/scopes/**/RULES.md",
    "pair/scopes/**/SUMMARY.md",
    "pair/knowledge/**",
    "pair/learnings/**",
)


class Resolved:
    """One registered source, with the files it actually covers."""

    def __init__(self, source, base, files):
        self.source = source
        self.base = base                   # the directory paths are shown relative to
        self.files = files                 # [(absolute path, display path)]

    @property
    def type(self):
        return self.source.type

    @property
    def trust(self):
        return self.source.trust

    @property
    def path(self):
        return self.source.path

    @property
    def empty(self):
        return not self.files

    def __repr__(self):
        return f"Resolved({self.type}, {len(self.files)} files)"


def expand(path, layout):
    """An absolute base for a registered path. `~` and absolute paths are personal-only (14.3)."""
    text = os.path.expanduser(str(path))
    candidate = pathlib.Path(text)
    return candidate if candidate.is_absolute() else layout.root / candidate


def resolve(source, layout):
    """The files a source covers (SPEC 14.1, 14.2). `exclude` always wins over `include`."""
    if source.type == "pair":
        return Resolved(source, layout.root, _pair_files(layout))

    raw = str(source.path)
    include = list(source.include)
    exclude = list(source.exclude)

    if _has_wildcard(raw):
        base = expand(_literal_prefix(raw), layout)
        include = include or [_relative_glob(raw)]
    else:
        base = expand(raw, layout)
        include = include or DEFAULT_INCLUDE

    found = []
    if base.is_dir():
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in MARKDOWN_SUFFIXES:
                continue
            rel = globs.normalise(path.relative_to(base))
            if exclude and globs.match_any(rel, exclude):
                continue
            if not globs.match_any(rel, include):
                continue
            found.append((path, _display(path, layout, base)))
    elif base.is_file():
        found.append((base, _display(base, layout, base.parent)))
    return Resolved(source, base, found)


def _pair_files(layout):
    """Walked and matched with pair's own globs, rather than pathlib's — `**` differs (SPEC 8.1)."""
    found = []
    if layout.pair_dir.is_dir():
        for path in sorted(layout.pair_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in MARKDOWN_SUFFIXES:
                continue
            rel = globs.normalise(path.relative_to(layout.root))
            if globs.match_any(rel, PAIR_GLOBS):
                found.append((path, rel))
    registry = layout.defaults / "rules.md"
    if registry.is_file():
        found.append((registry, globs.normalise(_safe_rel(registry, layout.root))))
    unique = {}
    for path, display in found:
        unique[str(path)] = (path, display)
    return [unique[key] for key in sorted(unique)]


def _safe_rel(path, root):
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _display(path, layout, base):
    try:
        return globs.normalise(path.relative_to(layout.root))
    except ValueError:
        return globs.normalise(path.relative_to(base))


def _has_wildcard(text):
    return bool(re.search(r"[*?\[]", text))


def _literal_prefix(pattern):
    parts = []
    for part in globs.normalise(pattern).split("/"):
        if _has_wildcard(part):
            break
        parts.append(part)
    return "/".join(parts) or "."


def _relative_glob(pattern):
    prefix = _literal_prefix(pattern)
    text = globs.normalise(pattern)
    if prefix and prefix != "." and text.startswith(prefix + "/"):
        return text[len(prefix) + 1:]
    return text


def resolve_all(layout, config):
    """Every source, the always-on `pair` one first, in precedence order (SPEC 14.6)."""
    registered = list(config.sources)
    if not any(source.type == "pair" for source in registered):
        registered.insert(0, config_source_for_pair())
    ordered = sorted(registered, key=lambda source: (PRECEDENCE.get(source.type, 9),
                                                     TRUST_ORDER.get(source.trust, 9)))
    return [resolve(source, layout) for source in ordered]


def config_source_for_pair():
    from pair.config import Source
    return Source({"type": "pair", "path": "pair/", "trust": "high"}, personal=False)


def empty_sources(resolved):
    """Sources whose globs match nothing — reported, never passed over (SPEC 14.2)."""
    return [each for each in resolved if each.empty]


# -- detection, for `pair init --sources` -------------------------------------------------------

def detect(root):
    """Proposed registrations for this repository. `llm-wiki` is never proposed (SPEC 14.2)."""
    found = []
    for name in DOC_FOLDERS:
        folder = root / name
        if folder.is_dir() and _has_markdown(folder):
            found.append({"type": "docs", "path": f"{name}/**/*.md", "trust": "high"})
            break
    docs_dir = _configured_docs_dir(root)
    if docs_dir and not any(entry["path"].startswith(docs_dir) for entry in found):
        found.append({"type": "docs", "path": f"{docs_dir}/**/*.md", "trust": "high"})
    for folder in sorted(root.rglob("*")):
        if not folder.is_dir() or folder.name not in ADR_FOLDERS:
            continue
        if any(ADR_FILE.match(child.name) for child in folder.iterdir() if child.is_file()):
            rel = globs.normalise(folder.relative_to(root))
            found.append({"type": "adr", "path": f"{rel}/**/*.md", "trust": "high"})
    readmes = [globs.normalise(path.relative_to(root))
               for path in sorted(root.rglob("README.md"))
               if "/node_modules/" not in str(path) and not str(path).startswith(str(root / "pair"))]
    if readmes:
        found.append({"type": "markdown", "path": "**/README.md", "trust": "medium",
                      "optional": True})
    return found


def wiki_defaults():
    """What `pair init --sources` offers for an llm-wiki: a suggestion, not a detection rule."""
    return {"type": "llm-wiki", "path": "", "trust": "medium",
            "include": list(WIKI_INCLUDE), "exclude": list(WIKI_EXCLUDE)}


def _has_markdown(folder):
    return any(path.suffix.lower() in MARKDOWN_SUFFIXES for path in folder.rglob("*")
               if path.is_file())


def _configured_docs_dir(root):
    mkdocs = root / "mkdocs.yml"
    if mkdocs.is_file():
        for line in mkdocs.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("docs_dir:"):
                return line.split(":", 1)[1].strip().strip("'\"").rstrip("/")
    for name in ("docusaurus.config.js", "docusaurus.config.ts", "docusaurus.config.mjs"):
        if (root / name).is_file():
            return "docs"
    return None
