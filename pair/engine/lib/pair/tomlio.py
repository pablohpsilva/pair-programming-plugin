"""TOML in and out.

`tomllib` reads and cannot write, and D2 allows no dependency, so the writer lives here. It is
deliberately small: pair writes `baseline.toml`, `waivers.toml`, `boundaries.toml` and, at `init`,
`config.toml` and each `scope.toml` — all of them shapes this module emits, and none of them needing
the general case.

Two write styles, because ownership differs (SPEC 3.1):

- `append_array_of_tables` adds one `[[waiver]]` block and leaves the rest of the file byte for byte
  as the engineer left it, comments included;
- `dump` rewrites a whole file, and is used only where pair owns the content outright.
"""

import tomllib

from pair.errors import CheckFailed

_BARE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def loads(text, what="TOML"):
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as problem:
        raise CheckFailed(f"{what} does not parse: {problem}") from problem


def load(path, what=None):
    label = what or str(path)
    try:
        return loads(path.read_text(encoding="utf-8"), label)
    except FileNotFoundError as problem:
        raise CheckFailed(f"{label} is missing") from problem


def load_if_present(path, what=None):
    if not path.is_file():
        return {}
    return load(path, what)


def key(name):
    """A table or value key, quoted only when it has to be."""
    text = str(name)
    if text and all(ch in _BARE for ch in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def value(item):
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, (int, float)):
        return repr(item)
    if isinstance(item, str):
        if "'" not in item and "\\" in item:
            return "'" + item + "'"          # a regex reads better as a literal string
        return '"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(item, (list, tuple)):
        return "[" + ", ".join(value(each) for each in item) + "]"
    raise CheckFailed(f"cannot write {type(item).__name__} to TOML")


def _is_table(item):
    return isinstance(item, dict)


def _is_table_array(item):
    return isinstance(item, (list, tuple)) and item and all(_is_table(each) for each in item)


def dumps(data, comments=None):
    """TOML text for `data`. `comments` maps a dotted key path to a trailing comment."""
    comments = comments or {}
    lines = []
    _emit(data, [], lines, comments)
    return "\n".join(lines).strip("\n") + "\n"


def _emit(table, prefix, lines, comments):
    scalars = [(k, v) for k, v in table.items() if not _is_table(v) and not _is_table_array(v)]
    tables = [(k, v) for k, v in table.items() if _is_table(v)]
    arrays = [(k, v) for k, v in table.items() if _is_table_array(v)]

    for name, item in scalars:
        path = ".".join(prefix + [str(name)])
        note = comments.get(path)
        lines.append(f"{key(name)} = {value(item)}" + (f"    # {note}" if note else ""))

    for name, item in tables:
        here = prefix + [str(name)]
        if lines and lines[-1] != "":
            lines.append("")
        note = comments.get(".".join(here))
        header = "[" + ".".join(key(part) for part in here) + "]"
        lines.append(header + (f"    # {note}" if note else ""))
        _emit(item, here, lines, comments)

    for name, entries in arrays:
        here = prefix + [str(name)]
        for entry in entries:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("[[" + ".".join(key(part) for part in here) + "]]")
            _emit(entry, here, lines, comments)


def dump(path, data, header=None, comments=None):
    """Rewrite `path` entirely. `header` is comment lines kept at the top."""
    text = ""
    if header:
        text += "".join(f"# {line}\n" for line in header) + "\n"
    text += dumps(data, comments)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_array_of_tables(path, name, entry, comments=None):
    """Append one `[[name]]` block, leaving everything already in the file untouched."""
    body = dumps({name: [entry]}, comments)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    separator = "\n" if existing.strip() else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing + separator + body, encoding="utf-8")
