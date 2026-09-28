"""`log.md`: append-only entries (SPEC 10.3).

The CLI appends one entry per state change; the agent appends `report`, `decision`, `waive-t2` and
`note`. Nothing here rewrites an earlier entry — the CI `format` gate fails when one changes, and
this module gives that gate the comparison it needs.
"""

from pair import clock

HEADING = "### "

CLI_ACTIONS = (
    "start", "approve", "done", "ok", "rework", "reopen", "pause", "resume", "handoff", "abandon",
    "close", "grant-batch", "waive", "expedite", "lesson-propose", "lesson-accept", "lesson-edit",
    "lesson-reject", "lesson-dispute", "baseline", "baseline-lower", "revert", "mode", "report",
    "upgrade", "init",
)
AGENT_ACTIONS = ("report", "decision", "waive-t2", "note")


class Entry:
    def __init__(self, heading, body):
        self.heading = heading
        self.body = body

    @property
    def parts(self):
        return [part.strip() for part in self.heading[len(HEADING):].split("·")]

    @property
    def at(self):
        return self.parts[0] if self.parts else ""

    @property
    def action(self):
        """The action word of the entry, ignoring a `step <n>` segment."""
        for part in self.parts[1:]:
            if not part.startswith("step "):
                return part.split(" ")[0].strip("()")
        return ""

    @property
    def step(self):
        for part in self.parts[1:]:
            if part.startswith("step "):
                try:
                    return int(part.split(" ", 1)[1])
                except ValueError:
                    return None
        return None

    def text(self):
        return self.heading + ("\n" + self.body if self.body else "")

    def __repr__(self):
        return f"Entry({self.heading!r})"


def entries(text):
    """Parse a log into entries. Anything before the first heading is ignored."""
    found = []
    heading = None
    body = []
    for line in (text or "").splitlines():
        if line.startswith(HEADING):
            if heading is not None:
                found.append(Entry(heading, "\n".join(body).strip("\n")))
            heading = line.rstrip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        found.append(Entry(heading, "\n".join(body).strip("\n")))
    return found


def heading_for(parts):
    return HEADING + " · ".join(str(part) for part in parts if str(part))


def append(path, parts, body=None, at=None):
    """Append one entry. `parts` becomes `### <at> · <part> · <part>`."""
    entry = heading_for([at or clock.short(), *parts])
    text = entry + ("\n" + body.rstrip() if body else "") + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + text, encoding="utf-8")
    return entry


def action_entry(path, action, by, step=None, detail=None, body=None, at=None):
    """The CLI's own entry: `### <at> · [step n ·] <action>[ (detail)] · <by>`."""
    parts = []
    if step is not None:
        parts.append(f"step {step}")
    parts.append(f"{action} ({detail})" if detail else action)
    parts.append(by)
    return append(path, parts, body=body, at=at)


def appended_only(before, after):
    """True when `after` keeps every entry of `before` unchanged and only adds more (SPEC 10.3)."""
    old = [entry.text() for entry in entries(before)]
    new = [entry.text() for entry in entries(after)]
    return new[:len(old)] == old


def changed_entries(before, after):
    """The entries of `before` that `after` altered or dropped — what the `format` gate reports."""
    old = entries(before)
    new = entries(after)
    problems = []
    for index, entry in enumerate(old):
        if index >= len(new):
            problems.append(f"entry removed: {entry.heading}")
        elif new[index].text() != entry.text():
            problems.append(f"entry changed: {entry.heading}")
    return problems
