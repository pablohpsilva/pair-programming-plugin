"""Every commit pair makes (SPEC 11.3).

Three rules live here and nowhere else: explicit paths only, the `Pair-*` trailers, and authorship
by the engineer with **no** co-author trailer and no vendor reference (D6).
"""

from pair import gitcmd
from pair.errors import CheckFailed

# SPEC 11.3: the conventional-commit type each kind uses.
TYPES = {
    "stub": "feat", "code": "feat", "migration": "feat",
    "test": "test", "char": "test",
    "refactor": "refactor", "doc": "docs", "config": "chore",
}


def type_for(kind, plan_title=""):
    """`fix` when the plan's title starts with "Fix", else the kind's own type."""
    base = TYPES.get(kind, "chore")
    if base == "feat" and (plan_title or "").strip().lower().startswith("fix"):
        return "fix"
    return base


def subject(kind, scope_slug, behavior, plan_title=""):
    return f"{type_for(kind, plan_title)}({scope_slug}): {behavior}"


def message(subject_line, trailers):
    """The subject, a blank line, then the trailers in the order given."""
    lines = [subject_line, ""]
    for name, value in trailers:
        if value is None or value == "":
            continue
        lines.append(f"{name}: {value}")
    return "\n".join(lines) + "\n"


def trailers_for(action, governance, task=None, step=None, kind=None, approved_by=None,
                 reverts=None, extra=()):
    found = []
    if task:
        found.append(("Pair-Task", task))
    found.append(("Pair-Action", action))
    if step is not None:
        found.append(("Pair-Step", step))
    if kind:
        found.append(("Pair-Kind", kind))
    if approved_by:
        found.append(("Pair-Approved-By", approved_by))
    if reverts:
        found.append(("Pair-Reverts", reverts))
    found += list(extra)
    found.append(("Pair-Governance", governance))
    return found


def check_index(root, rel_paths):
    """Refuse when another **tracked** path is staged; report untracked extras as a warning.

    SPEC 11.3: pair never sweeps a stray change into a step's commit. Untracked files are left
    alone, because pair never touches the index outside its own commits (SPEC 8.2).
    """
    listed = set(rel_paths)
    intruders = sorted(path for path in gitcmd.staged(root) if path not in listed)
    if intruders:
        raise CheckFailed(
            "another tracked file is staged, so this commit would not be only the step's files "
            "(PAIR-003)",
            [*intruders, "unstage them with `git restore --staged <path>` and run this again"],
        )
    warnings = []
    extras = [path for path in gitcmd.untracked(root) if path not in listed]
    if extras:
        warnings.append("untracked files left alone: " + ", ".join(sorted(extras)[:10]))
    return warnings


def make(root, rel_paths, subject_line, trailers):
    """Commit exactly `rel_paths`. Returns (sha, warnings)."""
    warnings = check_index(root, rel_paths)
    sha = gitcmd.commit_only(root, message(subject_line, trailers), rel_paths)
    return sha, warnings


def action_commit(root, rel_paths, action, governance, subject_line, task=None, step=None,
                  kind=None, approved_by=None, reverts=None, extra=()):
    """The usual shape: a subject plus the standard trailers for `action`."""
    trailers = trailers_for(action, governance, task=task, step=step, kind=kind,
                            approved_by=approved_by, reverts=reverts, extra=extra)
    return make(root, rel_paths, subject_line, trailers)


def read_trailers(message_text):
    """{name: value} for the `Pair-*` trailers of a commit message. Later wins."""
    found = {}
    for line in (message_text or "").splitlines():
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.strip()
        if name.startswith("Pair-"):
            found[name] = value.strip()
    return found
