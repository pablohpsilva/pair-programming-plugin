"""Running a step's evidence and deciding what it proves (SPEC 8.1, 8.2, 8.3).

`pair done` is the only caller. Everything here is deliberately explicit about *why* a step failed,
because the message goes to the agent and has to name the next action (SPEC 12.4).
"""

import hashlib
import os
import pathlib
import re
import subprocess

from pair import clock, coverage as coverage_mod, files, gitcmd, globs, log, redact
from pair.errors import CheckFailed

SUMMARY_LINES = 20
DELETED = "deleted"
NO_GAIN = "⚠️ no coverage gain:"
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class Run:
    """One command invocation."""

    def __init__(self, command, code, output, timed_out=False):
        self.command = command
        self.code = code
        self.output = output
        self.timed_out = timed_out

    @property
    def passed(self):
        return self.code == 0

    def summary(self):
        """The last 20 lines, redacted — what goes in `log.md` (SPEC 8.2)."""
        lines = redact.redact(self.output).rstrip().splitlines()
        return "\n".join(lines[-SUMMARY_LINES:])

    def matches(self, patterns):
        """The first wrong-reason pattern the output matches, or None (TEST-001)."""
        for pattern in patterns or ():
            try:
                if re.search(pattern, self.output):
                    return pattern
            except re.error:
                if pattern in self.output:
                    return pattern
        return None


def headline(outcome):
    """The command's own last line of output, which is where a test runner puts its count."""
    lines = [line.strip() for line in (outcome.summary() or "").splitlines() if line.strip()]
    return lines[-1][:80] if lines else ""


def run(scope, command_name, layout, extra_env=None):
    command = scope.command(command_name)
    if not command:
        raise CheckFailed(f"scope {scope.name} has no `{command_name}` command (SPEC 8.4)")
    env = dict(os.environ)
    env.update(extra_env or {})
    try:
        done = subprocess.run(command, shell=True, cwd=str(scope.work_dir), capture_output=True,
                              text=True, timeout=scope.timeout_seconds, env=env)
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or "") + (expired.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        return Run(command, 124, output + f"\n[timed out after {scope.timeout_seconds}s]",
                   timed_out=True)
    return Run(command, done.returncode, done.stdout + done.stderr)


def coverage_env(layout, scope):
    path = layout.coverage_xml(scope.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return {"PAIR_COVERAGE_XML": str(path)}, path


# -- the step's file set -----------------------------------------------------------------------

def file_set(root, state, step, config):
    """The paths this step's evidence covers (SPEC 8.2).

    Without a grant it is exactly the listed file. With one it is whatever the worktree actually
    changed inside the grant's globs, which is how a batch step stays honest about its size.
    """
    grant = state.batch_for(step.n)
    if grant is None:
        return list(step.files)
    found = []
    for code, path in gitcmd.status_porcelain(root):
        if globs.match_any(path, grant["paths"]):
            found.append(path)
    found = sorted(set(found))
    if not found:
        raise CheckFailed(
            f"step {step.n} has a batch grant but nothing in {', '.join(grant['paths'])} changed — "
            f"write the step, or `pair rework \"<note>\"` if the plan is wrong")
    if len(found) > grant["max_files"]:
        raise CheckFailed(
            f"step {step.n} changed {len(found)} files, but its grant allows "
            f"{grant['max_files']} (PAIR-004)", found)
    return found


def hashes(root, rel_paths):
    """SHA-256 per path; a deleted file records the literal `deleted` (SPEC 8.2)."""
    found = {}
    for rel in rel_paths:
        path = root / rel
        if not path.exists():
            found[rel] = DELETED
            continue
        found[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def unchanged(root, recorded):
    """The paths whose hash no longer matches — why `pair ok` refuses (SPEC 8.2)."""
    current = hashes(root, list(recorded))
    return sorted(rel for rel, digest in recorded.items() if current.get(rel) != digest)


def has_changes(root, rel_paths):
    """True when at least one path in the set actually differs from HEAD (SPEC 7.4)."""
    for rel in rel_paths:
        exists = (root / rel).exists()
        tracked = gitcmd.is_tracked(root, rel)
        if not exists:
            if tracked:
                return True                              # the step deleted a tracked file
            continue                                     # never written: not a change
        if not tracked:
            return True                                  # a new, untracked file
        if gitcmd.changed_lines(root, rel):
            return True
    return False


def changed_lines(root, rel_paths, config, exclusions=()):
    """{path: {line numbers}} for code files only (SPEC 8.2)."""
    found = {}
    for rel in rel_paths:
        if files.classify(rel, config) != "code":
            continue
        if globs.match_any(rel, exclusions):
            continue
        numbers = gitcmd.changed_lines(root, rel)
        if numbers:
            found[rel] = numbers
    return found


# -- the per-kind decision ---------------------------------------------------------------------

def gather(layout, config, state, step, scope, baselines):
    """Run the evidence for `step` and return its record, or raise CheckFailed with the reason."""
    kind = step.kind
    paths_in_step = file_set(layout.root, state, step, config)
    if not has_changes(layout.root, paths_in_step):
        raise CheckFailed(
            f"no changes in {', '.join(paths_in_step)} — write the step, or "
            f"`pair rework \"<note>\"` if the plan is wrong")

    record = {"at": clock.stamp(), "committed_files": paths_in_step,
              "files_sha256": hashes(layout.root, paths_in_step)}
    warnings = []

    changed = changed_lines(layout.root, paths_in_step, config)
    total_changed = sum(len(numbers) for numbers in changed.values())
    if total_changed > config.max_changed_lines:
        warnings.append(f"{total_changed} changed lines, over the "
                        f"{config.max_changed_lines}-line guide (steps.max_changed_lines)")

    if kind == "doc":
        problems = broken_links(layout.root, paths_in_step)
        if problems:
            raise CheckFailed("a relative link does not resolve", problems)
        record.update(result="green", summary="links resolve", tests="no test command for a doc step")
        return record, warnings, None

    if kind == "config":
        return _config_step(layout, scope, record, warnings)

    if kind == "migration":
        if not scope.has("migrate_check"):
            raise CheckFailed(
                f"scope {scope.name} has no `migrate_check` command, so a migration step cannot be "
                f"validated (SPEC 8.1) — add one to pair/scopes/{scope.name}/scope.toml, or ask "
                f"the engineer for `pair expedite` or a waiver")
        outcome = run(scope, "migrate_check", layout)
        if not outcome.passed:
            raise CheckFailed(f"`{outcome.command}` failed ({outcome.code})",
                              outcome.summary().splitlines())
        record.update(result="green", summary=outcome.summary(), tests="migrate_check passed")
        return record, warnings, outcome

    if kind in ("stub", "test"):
        return _test_step(layout, config, scope, step, record, warnings)

    return _coverage_step(layout, config, state, scope, step, record, warnings, changed, baselines)


def _config_step(layout, scope, record, warnings):
    if not scope.has("validate"):
        record.update(result="green", summary="no automated check",
                      tests="scope has no `validate` command")
        return record, warnings, None
    outcome = run(scope, "validate", layout)
    if not outcome.passed:
        raise CheckFailed(f"`{outcome.command}` failed ({outcome.code})",
                          outcome.summary().splitlines())
    record.update(result="green", summary=outcome.summary(), tests="validate passed")
    return record, warnings, outcome


def _test_step(layout, config, scope, step, record, warnings):
    outcome = run(scope, "test", layout)
    wrong = outcome.matches(config.wrong_reason_patterns)
    if wrong:
        raise CheckFailed(
            f"the suite failed for the wrong reason (matched {wrong!r}) — fix the step's file so "
            f"the test fails on its assertion, not on an import or syntax error (TEST-001)",
            outcome.summary().splitlines())

    if step.kind == "stub":
        if not (outcome.passed or outcome.code in scope.no_tests_exit_codes):
            raise CheckFailed(
                f"a stub step needs the suite green (or a `no_tests_exit_codes` code), but "
                f"`{outcome.command}` exited {outcome.code} — a stub adds signatures only",
                outcome.summary().splitlines())
        note = "no tests collected" if outcome.code else "suite green"
        record.update(result="green", summary=outcome.summary(), tests=note)
        return record, warnings, outcome

    if outcome.passed:
        raise CheckFailed(
            "the new test passes, so it proves nothing (TEST-001) — make it fail first, then run "
            "`pair done` again", outcome.summary().splitlines())
    record.update(result="red", summary=outcome.summary(),
                  tests=f"failed as intended (exit {outcome.code})")
    return record, warnings, outcome


def _coverage_step(layout, config, state, scope, step, record, warnings, changed, baselines):
    env, xml_path = coverage_env(layout, scope)
    outcome = run(scope, "coverage", layout, extra_env=env)
    wrong = outcome.matches(config.wrong_reason_patterns)
    if not outcome.passed:
        hint = (f" (matched {wrong!r} — that is an import or syntax error, not a failing "
                f"assertion)" if wrong else "")
        raise CheckFailed(
            f"`{outcome.command}` failed ({outcome.code}){hint} — the whole scope suite must be "
            f"green for a {step.kind} step", outcome.summary().splitlines())

    report = coverage_mod.Report.load(xml_path)
    record["scope_line"] = report.line_rate
    record["scope_branch"] = report.branch_rate
    floor_line, floor_branch = baselines.floor(scope.name, scope.target, config.ratchet_tolerance)
    record["floor_line"] = floor_line
    record["floor_branch"] = floor_branch

    if step.kind == "char":
        _char_gain(layout, state, step, scope, report, baselines, record)
    else:
        percentage, uncovered = coverage_mod.changed_lines_covered(report, changed)
        record["changed_lines_covered"] = percentage
        if percentage < config.changed_lines_target:
            detail = [f"{path}: lines {', '.join(str(n) for n in numbers)}"
                      for path, numbers in sorted(uncovered.items())]
            raise CheckFailed(
                f"{percentage}% of changed lines are covered; {config.changed_lines_target}% is "
                f"required (COV-002) — add a test for these lines", detail)

    if report.line_rate < floor_line or report.branch_rate < floor_branch:
        raise CheckFailed(
            f"scope coverage {report.line_rate}% line / {report.branch_rate}% branch is below the "
            f"floor {floor_line}/{floor_branch} (COV-001)",
            [f"the floor comes from {'the baseline' if baselines.entry(scope.name) else 'the target'} "
             f"for {scope.name} (SPEC 15.1)"])

    record.update(result="green", summary=outcome.summary(), tests=headline(outcome))
    return record, warnings, outcome


def _char_gain(layout, state, step, scope, report, baselines, record):
    """A char step must buy coverage, or say in the report why it could not (SPEC 8.1)."""
    entry = baselines.entry(scope.name)
    if entry is None:
        raise CheckFailed(
            f"scope {scope.name} has no baseline entry, so there is no \"before\" to compare a "
            f"char step against — run `pair baseline --scope {scope.name}` first (SPEC 8.1)")
    rose = report.line_rate > entry["line"] or report.branch_rate > entry["branch"]
    if rose:
        return
    reason = find_no_gain_note(layout, state, step)
    if not reason:
        raise CheckFailed(
            f"coverage did not rise ({report.line_rate}% line / {report.branch_rate}% branch "
            f"against a baseline of {entry['line']}/{entry['branch']}), and a char step exists to "
            f"buy coverage — append a `{NO_GAIN} <reason>` line to the step report in "
            f"pair/tasks/{state.task}/log.md and run `pair done` again (SPEC 8.1)")
    record["note"] = reason


def find_no_gain_note(layout, state, step):
    """The `⚠️ no coverage gain: <reason>` line from this step's entries in `log.md`, verbatim."""
    path = layout.log(state.task)
    if not path.is_file():
        return None
    found = None
    for entry in log.entries(path.read_text(encoding="utf-8")):
        if entry.step is not None and entry.step != step.n:
            continue
        for line in (entry.body or "").splitlines():
            stripped = line.strip()
            if stripped.startswith(NO_GAIN):
                found = stripped
    return found


def broken_links(root, rel_paths):
    """Relative Markdown links in the changed files that do not resolve (SPEC 8.1)."""
    problems = []
    for rel in rel_paths:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in MARKDOWN_LINK.findall(text):
            link = target.split("#")[0].strip()
            if not link or "://" in link or link.startswith(("mailto:", "#", "/")):
                continue
            resolved = (path.parent / link).resolve()
            if not resolved.exists():
                problems.append(f"{rel}: `{link}` does not resolve")
    return problems


def run_log(layout, task, step_number, outcome):
    """The full output goes to `local/runs/<task>/<step>.log`, never committed (SPEC 8.2)."""
    if outcome is None:
        return None
    path = layout.run_log(task, step_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"$ {outcome.command}\n[exit {outcome.code}]\n\n{outcome.output}",
                    encoding="utf-8")
    return path


def relative(path, root):
    try:
        return str(pathlib.Path(path).relative_to(root))
    except ValueError:
        return str(path)
