"""The search index (`local/index.json`, SPEC 14.4).

Chunks are small and self-describing so that `pair find` can cite `[source] path#heading` with a
date without opening the file again. The index is never committed.
"""

import json
import re

from pair import clock, gitcmd, rules, sources

FORMAT = 1
MAX_LINES = 60
PREVIEW_LINES = 5
HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
# A token may contain `.`, `-` and `_` (so `TEST-001` and `foo.bar` survive) but never end
# with one, or every sentence would index "evenly." instead of "evenly".
WORD = re.compile(r"[a-z0-9](?:[a-z0-9_.-]*[a-z0-9])?")


def tokens(text):
    return WORD.findall((text or "").lower())


def term_frequencies(text):
    counts = {}
    for token in tokens(text):
        counts[token] = counts.get(token, 0) + 1
    return counts


def chunk(text):
    """Split Markdown at `#`–`###`. A section longer than 60 lines becomes several chunks."""
    lines = (text or "").splitlines()
    found = []
    heading = ""
    start = 1
    body = []

    def flush():
        if not body and not heading:
            return
        for offset in range(0, max(len(body), 1), MAX_LINES):
            piece = body[offset:offset + MAX_LINES]
            if not piece and offset:
                break
            found.append({"heading": heading, "line": start + offset, "lines": piece})

    for number, line in enumerate(lines, start=1):
        match = HEADING.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
            start = number
            body = []
            continue
        body.append(line)
    flush()
    return [entry for entry in found if entry["heading"] or "".join(entry["lines"]).strip()]


def chunks_for_file(path, display, resolved, root):
    text = path.read_text(encoding="utf-8", errors="replace")
    commit_sha = None
    updated = gitcmd.last_commit_date(root, display) if _inside(path, root) else None
    if updated:
        commit_sha = gitcmd.out(root, "log", "-1", "--format=%H", "--", display, check=False) or None
    try:
        mtime = int(path.stat().st_mtime)
    except OSError:
        mtime = 0
    found = []
    for piece in chunk(text):
        body = "\n".join(piece["lines"]).strip("\n")
        found.append({
            "source_type": resolved.type,
            "source_path": resolved.path,
            "trust": resolved.trust,
            "file": display,
            "heading": piece["heading"],
            "line": piece["line"],
            "mtime": mtime,
            "updated": updated,
            "git_commit": commit_sha,
            "rule_ids": rules.cited(piece["heading"] + "\n" + body),
            "terms": term_frequencies(piece["heading"] + " " + body),
            "length": len(tokens(body)) + len(tokens(piece["heading"])),
            "preview": "\n".join(piece["lines"][:PREVIEW_LINES]).rstrip(),
        })
    return found


def _inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class Index:
    def __init__(self, data):
        self.data = data

    @classmethod
    def empty(cls):
        return cls({"format": FORMAT, "built_at": None, "files": {}, "chunks": []})

    @classmethod
    def load(cls, path):
        if not path.is_file():
            return cls.empty()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls.empty()
        if data.get("format") != FORMAT:
            return cls.empty()
        return cls(data)

    @property
    def chunks(self):
        return self.data.get("chunks", [])

    @property
    def files(self):
        return self.data.setdefault("files", {})

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def stale_files(self, resolved_all):
        """The files whose mtime is newer than what the index holds (SPEC 14.4)."""
        stale = []
        for resolved in resolved_all:
            for path, display in resolved.files:
                try:
                    mtime = int(path.stat().st_mtime)
                except OSError:
                    continue
                if self.files.get(display) != mtime:
                    stale.append((resolved, path, display))
        return stale


def build(layout, config, previous=None, incremental=False):
    """Rebuild the index. `incremental` keeps chunks whose file has not changed."""
    resolved_all = sources.resolve_all(layout, config)
    index = Index.empty()
    keep = {}
    if incremental and previous is not None:
        fresh = {display for resolved in resolved_all for _, display in resolved.files}
        stale = {display for _, _, display in previous.stale_files(resolved_all)}
        for entry in previous.chunks:
            if entry["file"] in fresh and entry["file"] not in stale:
                keep.setdefault(entry["file"], []).append(entry)
        for display, mtime in previous.files.items():
            if display in keep:
                index.files[display] = mtime

    for resolved in resolved_all:
        for path, display in resolved.files:
            if display in keep:
                index.data["chunks"] += keep[display]
                continue
            index.data["chunks"] += chunks_for_file(path, display, resolved, layout.root)
            try:
                index.files[display] = int(path.stat().st_mtime)
            except OSError:
                index.files[display] = 0
    index.data["built_at"] = clock.stamp()
    index.data["sources"] = [{"type": each.type, "path": each.path, "files": len(each.files)}
                             for each in resolved_all]
    return index, resolved_all


def refresh(layout, config):
    """What `pair find` does first: rebuild only what changed (SPEC 14.4)."""
    previous = Index.load(layout.index_file)
    resolved_all = sources.resolve_all(layout, config)
    if previous.chunks and not previous.stale_files(resolved_all):
        return previous, resolved_all
    index, resolved_all = build(layout, config, previous=previous, incremental=True)
    index.save(layout.index_file)
    return index, resolved_all
