"""Secret patterns, used twice: to redact evidence, and as the CI `secrets` gate (SPEC 13.1).

One list, so a pattern added for the gate also starts redacting logs.
"""

import re

MASK = "‹redacted›"

#                 name,          pattern,                                     keep the label?
_SPECS = (
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", False),
    ("aws-key-id", r"AKIA[0-9A-Z]{16}", False),
    ("github-token", r"gh[pousr]_[A-Za-z0-9]{36,}", False),
    ("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}", False),
    ("assignment", r"(?i)(secret|token|password|api[_-]?key)(\s*[:=]\s*)['\"]?[^\s'\"]{12,}", True),
)

PATTERNS = tuple((name, re.compile(pattern), labelled) for name, pattern, labelled in _SPECS)


def findall(text):
    """Every (name, matched text) in `text`. The gate reports; the redactor rewrites."""
    hits = []
    for name, regex, _ in PATTERNS:
        for match in regex.finditer(text or ""):
            hits.append((name, match.group(0)))
    return hits


def redact(text):
    """`text` with every secret replaced by the mask.

    An assignment keeps its label — `password = <mask>` is far more useful in a log than a bare
    mask, and the label was never the secret.
    """
    out = text or ""
    for _, regex, labelled in PATTERNS:
        if labelled:
            out = regex.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", out)
        else:
            out = regex.sub(MASK, out)
    return out
