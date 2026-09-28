"""gitignore-style glob matching.

`fnmatch` does not implement `**`, and the file classes (SPEC 8.1), batch grants (7.2), waiver
scopes (10.6), protected paths (19.1) and coverage exclusions (10.8) all need it. Standard library
only (D2), so it is written here once and nowhere else.

Semantics, chosen to match how the SPEC writes its patterns:

- a pattern is **anchored at the repository root** unless it begins with `**/`;
- `*` and `?` never cross a `/`; `[...]` is a character class;
- `**/x` matches `x` at any depth, including none;
- `x/**` matches everything strictly *under* `x`, not `x` itself;
- `a/**/b` matches `a/b` as well as `a/x/y/b`.

Paths are compared as POSIX, relative to the root, with no leading `./` or `/`.
"""

import re

_CACHE = {}


def normalise(path):
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _segment(seg):
    out = []
    i = 0
    while i < len(seg):
        ch = seg[i]
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            end = seg.find("]", i + 1)
            if end == -1:                       # an unclosed '[' is a literal bracket
                out.append(re.escape(ch))
            else:
                body = seg[i + 1:end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = end + 1
                continue
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


def compile(pattern):
    """The compiled regex for one pattern. Cached: the hook recompiles nothing per call."""
    key = pattern
    if key in _CACHE:
        return _CACHE[key]
    parts = normalise(pattern).split("/")
    out = []
    for i, seg in enumerate(parts):
        last = i == len(parts) - 1
        if seg == "**":
            if last:
                out.append(".+")                # x/** is everything under x
            else:
                out.append("(?:[^/]+/)*")       # zero or more whole segments
                continue
        else:
            out.append(_segment(seg))
        if not last:
            out.append("/")
    regex = re.compile("^" + "".join(out) + "$")
    _CACHE[key] = regex
    return regex


def match(path, pattern):
    return compile(pattern).match(normalise(path)) is not None


def match_any(path, patterns):
    """The first pattern that matches, or None. Returning the pattern lets callers explain why."""
    text = normalise(path)
    for pattern in patterns or ():
        if compile(pattern).match(text):
            return pattern
    return None
