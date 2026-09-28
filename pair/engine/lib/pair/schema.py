"""Hand-written validators for every structured format pair reads.

This is what runs in production. `engine/schemas/` holds JSON Schemas saying the same thing, and
C39 asserts the two agree — but no shipped module may import `jsonschema` (D2, SPEC 19.2), so the
checking is here.

A spec is a tree of the small types below. `errors()` returns every problem, so one run reports the
whole file rather than the first mistake. Unknown keys are errors wherever the SPEC says they are
(5.2, 5.4); the message names the key and, when the raw text is supplied, its line.
"""

import re


class Invalid:
    """One problem, addressed by its dotted path."""

    def __init__(self, path, message):
        self.path = path
        self.message = message

    def render(self, text=None):
        where = self.path or "<root>"
        line = line_of(text, self.path) if text else None
        return f"{where}: {self.message}" + (f" (line {line})" if line else "")

    def __repr__(self):
        return f"Invalid({self.path!r}, {self.message!r})"


def line_of(text, dotted):
    """The 1-based line in `text` that defines `dotted`, or None.

    Good enough to point an engineer at the right line: the last path segment is looked for as a
    key or a table header, which is how every format pair reads is written.
    """
    if not text or not dotted:
        return None
    leaf = dotted.split(".")[-1]
    if leaf.isdigit():
        leaf = dotted.split(".")[-2] if len(dotted.split(".")) > 1 else leaf
    quoted = re.escape(leaf)
    key = re.compile(rf'(?:^|[\[.\s])(?:"{quoted}"|{quoted})\s*(?:=|\])')
    for number, line in enumerate(text.splitlines(), start=1):
        if key.search(line):
            return number
    return None


class Type:
    """Base: `check` yields Invalid for `value` at `path`."""

    def check(self, value, path):
        return []


class Bool(Type):
    def check(self, value, path):
        if not isinstance(value, bool):
            return [Invalid(path, f"must be true or false, got {_name(value)}")]
        return []


class Num(Type):
    """An integer or a float."""

    kinds = (int, float)
    label = "a number"

    def __init__(self, minimum=None, maximum=None, const=None):
        self.minimum = minimum
        self.maximum = maximum
        self.const = const

    def check(self, value, path):
        if isinstance(value, bool) or not isinstance(value, self.kinds):
            return [Invalid(path, f"must be {self.label}, got {_name(value)}")]
        if self.const is not None and value != self.const:
            return [Invalid(path, f"must be {self.const}")]
        if self.minimum is not None and value < self.minimum:
            return [Invalid(path, f"must be at least {self.minimum}, got {value}")]
        if self.maximum is not None and value > self.maximum:
            return [Invalid(path, f"must be at most {self.maximum}, got {value}")]
        return []


class Int(Num):
    kinds = (int,)
    label = "a whole number"


class Str(Type):
    def __init__(self, pattern=None, choices=None, allow_empty=True, describe=None):
        self.pattern = re.compile(pattern) if pattern else None
        self.choices = tuple(choices) if choices else None
        self.allow_empty = allow_empty
        self.describe = describe

    def check(self, value, path):
        if not isinstance(value, str):
            return [Invalid(path, f"must be text, got {_name(value)}")]
        if not self.allow_empty and not value:
            return [Invalid(path, "must not be empty")]
        if self.choices is not None and value not in self.choices:
            return [Invalid(path, f"must be one of {', '.join(self.choices)}, got {value!r}")]
        if value and self.pattern and not self.pattern.match(value):
            wanted = self.describe or f"match {self.pattern.pattern}"
            return [Invalid(path, f"must {wanted}, got {value!r}")]
        return []


class ListOf(Type):
    def __init__(self, item, min_items=0):
        self.item = item
        self.min_items = min_items

    def check(self, value, path):
        if not isinstance(value, list):
            return [Invalid(path, f"must be a list, got {_name(value)}")]
        if len(value) < self.min_items:
            return [Invalid(path, f"needs at least {self.min_items} entr"
                                  f"{'y' if self.min_items == 1 else 'ies'}")]
        found = []
        for index, entry in enumerate(value):
            found += self.item.check(entry, f"{path}.{index}" if path else str(index))
        return found


class Table(Type):
    def __init__(self, fields=None, required=(), allow_unknown=False, values=None):
        self.fields = dict(fields or {})
        self.required = tuple(required)
        self.allow_unknown = allow_unknown
        self.values = values                 # a type every value must satisfy, for open tables

    def check(self, value, path):
        if not isinstance(value, dict):
            return [Invalid(path, f"must be a table, got {_name(value)}")]
        found = []
        for name in self.required:
            if name not in value:
                found.append(Invalid(f"{path}.{name}" if path else name, "is required"))
        for name, entry in value.items():
            here = f"{path}.{name}" if path else str(name)
            if name in self.fields:
                found += self.fields[name].check(entry, here)
            elif self.values is not None:
                found += self.values.check(entry, here)
            elif not self.allow_unknown:
                found.append(Invalid(here, "is not a known key"))
        return found


class OneOf(Type):
    """Satisfies any of several types. Reports the problems of them all when none fits."""

    def __init__(self, *types):
        self.types = types

    def check(self, value, path):
        everything = []
        for kind in self.types:
            problems = kind.check(value, path)
            if not problems:
                return []
            everything += problems
        return everything


class Null(Type):
    def check(self, value, path):
        return [] if value is None else [Invalid(path, "must be empty")]


def _name(value):
    if value is None:
        return "nothing"
    return {bool: "true/false", int: "a whole number", float: "a number", str: "text",
            list: "a list", dict: "a table"}.get(type(value), type(value).__name__)


def errors(data, spec, text=None):
    """Every problem in `data`, rendered. `text` is the raw file, used to name line numbers."""
    return [problem.render(text) for problem in spec.check(data, "")]
