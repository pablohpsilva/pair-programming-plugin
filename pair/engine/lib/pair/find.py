"""`pair find` (SPEC 14.5): BM25 over the index, plus the exact `--rule` path."""

import math

from pair import clock, index as index_mod

K1 = 1.2
B = 0.75
HEADING_BOOST = 2.0
PAIR_BOOST = 1.5
HIGH_TRUST_BOOST = 1.2


class Hit:
    def __init__(self, chunk, score):
        self.chunk = chunk
        self.score = score

    @property
    def file(self):
        return self.chunk["file"]

    @property
    def heading(self):
        return self.chunk.get("heading") or ""

    @property
    def source_type(self):
        return self.chunk["source_type"]

    @property
    def updated(self):
        return self.chunk.get("updated") or _from_mtime(self.chunk.get("mtime"))

    def stale(self, stale_days, today=None):
        when = clock.parse_date(self.updated)
        now = clock.parse_date(today or clock.today())
        return bool(when and now and (now - when).days > stale_days)

    def render(self, stale_days, today=None):
        flag = " ⚠ stale?" if self.stale(stale_days, today) else ""
        where = f"{self.file}#{self.heading}" if self.heading else self.file
        head = f"[{self.source_type}{flag}] {where} (updated {self.updated or 'unknown'})"
        body = "\n".join(f"  {line}" for line in (self.chunk.get("preview") or "").splitlines())
        return head + ("\n" + body if body else "")

    def as_data(self):
        return {"source": self.source_type, "file": self.file, "heading": self.heading,
                "line": self.chunk.get("line"), "updated": self.updated,
                "score": round(self.score, 4), "preview": self.chunk.get("preview")}


def _from_mtime(mtime):
    if not mtime:
        return None
    import datetime
    return datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime("%Y-%m-%d")


def search(index, query, limit=5, source_type=None, scope=None):
    """The best `limit` chunks for `query`, scored with BM25 and the SPEC 14.5 boosts."""
    chunks = [entry for entry in index.chunks
              if (source_type is None or entry["source_type"] == source_type)
              and (scope is None or entry["file"].startswith(scope))]
    if not chunks:
        return []
    terms = index_mod.tokens(query)
    if not terms:
        return []
    total = len(chunks)
    lengths = [entry.get("length") or 1 for entry in chunks]
    average = sum(lengths) / total

    document_count = {}
    for term in set(terms):
        document_count[term] = sum(1 for entry in chunks if term in entry["terms"])

    hits = []
    for entry, length in zip(chunks, lengths):
        score = 0.0
        for term in terms:
            frequency = entry["terms"].get(term, 0)
            if not frequency:
                continue
            appearances = document_count[term] or 1
            idf = math.log(1 + (total - appearances + 0.5) / (appearances + 0.5))
            score += idf * (frequency * (K1 + 1)) / (
                frequency + K1 * (1 - B + B * length / (average or 1)))
        if score <= 0:
            continue
        heading = (entry.get("heading") or "").lower()
        if any(term in heading for term in terms):
            score *= HEADING_BOOST
        if entry["source_type"] == "pair":
            score *= PAIR_BOOST
        if entry.get("trust") == "high":
            score *= HIGH_TRUST_BOOST
        hits.append(Hit(entry, score))

    hits.sort(key=lambda hit: (-hit.score, hit.file, hit.chunk.get("line") or 0))
    return hits[:limit]


def by_rule(registry, rule_id):
    """SPEC 14.5: the rule's defining row, exactly, with no scoring."""
    rule = registry.by_id(rule_id)
    if rule is None:
        return None
    return rule


def log_query(layout, task_id, query, hits):
    """Append `{at, query, hits}` to `local/find_log/<task>.jsonl` — local, never committed."""
    if not task_id:
        return None
    import json
    path = layout.find_log / f"{task_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": clock.stamp(), "query": query,
              "hits": [{"file": hit.file, "heading": hit.heading, "source": hit.source_type}
                       for hit in hits]}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_log(layout, task_id):
    import json
    path = layout.find_log / f"{task_id}.jsonl"
    if not path.is_file():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return found
