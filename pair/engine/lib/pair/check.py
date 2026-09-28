"""`pair check <gate>` — the CI backstop (SPEC 13).

The hook is a heuristic at the moment of the edit; these gates read the history and are the real
guarantee. Every gate reports `FAIL <gate> <commit|file>: <reason> (<rule ID>)` and never guesses at
an agent's identity — it asks whether *pair* made the change, keying on the `Pair-Action` trailer
(D6).
"""

import json
import pathlib

from pair import (boundaries as boundaries_mod, clock, commit as commit_mod,
                  coverage as coverage_mod, files, gitcmd, globs, log as log_mod, paths,
                  plan as plan_mod, redact, rules as rules_mod, state as state_mod, tomlio,
                  waivers as waivers_mod)
from pair.errors import CheckFailed, UsageError

GATES = ("protected", "commits", "approval", "red", "coverage", "boundaries", "secrets", "format")

# Which actions may legitimately write which protected paths (SPEC 13.1 `protected`).
ACTION_WRITES = {
    "init": ("pair/**", ".github/**", "AGENTS.md", "CLAUDE.md", ".claude/**", "githooks/**",
             "CODEOWNERS"),
    "upgrade": ("pair/engine/**", "pair/config.toml"),
    "baseline": ("pair/rules/baseline.toml",),
    "baseline-lower": ("pair/rules/baseline.toml",),
    "waive": ("pair/rules/waivers.toml",),
    "report": ("pair/reports/**",),
    "ok": ("pair/tasks/*/state.json", "pair/rules/baseline.toml"),
}
# Every pair action may write the task bookkeeping it owns.
TASK_WRITES = ("pair/tasks/*/state.json",)

STEP_KINDS_WITH_COVERAGE = ("char", "code", "refactor")


class Failure:
    def __init__(self, gate, where, reason, rule=None):
        self.gate = gate
        self.where = where
        self.reason = reason
        self.rule = rule

    def render(self):
        suffix = f" ({self.rule})" if self.rule else ""
        return f"FAIL {self.gate} {self.where}: {self.reason}{suffix}"

    def as_data(self):
        return {"gate": self.gate, "where": self.where, "reason": self.reason, "rule": self.rule}

    def __repr__(self):
        return f"Failure({self.gate}, {self.where})"


class Range:
    """The commits a gate looks at, and the small cache they all share."""

    def __init__(self, session, base, head):
        self.session = session
        self.layout = session.layout
        self.root = session.root
        self.config = session.config
        self.base = base
        self.head = head
        self.shas = gitcmd.commits_in_range(self.root, base, head)
        self._messages = {}
        self._files = {}

    def message(self, sha):
        if sha not in self._messages:
            self._messages[sha] = gitcmd.commit_message(self.root, sha)
        return self._messages[sha]

    def trailers(self, sha):
        return commit_mod.read_trailers(self.message(sha))

    def action(self, sha):
        return self.trailers(sha).get("Pair-Action")

    def files(self, sha):
        if sha not in self._files:
            self._files[sha] = gitcmd.commit_files(self.root, sha)
        return self._files[sha]

    def state_at(self, sha, task):
        text = gitcmd.show(self.root, sha, f"pair/tasks/{task}/state.json")
        if not text:
            return None
        try:
            return state_mod.State.loads(self.layout, text)
        except CheckFailed:
            return None

    def outside_files(self, sha):
        """Files outside `pair/`, excluding the pointer files (SPEC 13.1)."""
        return [rel for rel in self.files(sha)
                if not rel.startswith("pair/") and not paths.is_pointer_file(rel)]


# -- gates --------------------------------------------------------------------------------------

def gate_protected(scan):
    found = []
    for sha in scan.shas:
        action = scan.action(sha)
        allowed = list(TASK_WRITES) + list(ACTION_WRITES.get(action or "", ()))
        for rel in scan.files(sha):
            pattern = scan.config.protected(rel)
            if not pattern:
                continue
            if action and globs.match_any(rel, allowed):
                if action == "ok" and rel == "pair/rules/baseline.toml" \
                        and not _baseline_only_rose(scan, sha):
                    found.append(Failure("protected", sha[:8],
                                         "a `Pair-Action: ok` commit lowered a baseline value",
                                         "PAIR-006"))
                continue
            reason = (f"{rel} is protected and this commit has no Pair-Action permitted to write it"
                      if not action else
                      f"{rel} is protected and `Pair-Action: {action}` may not write it")
            found.append(Failure("protected", sha[:8], reason, "PAIR-006"))
    return found


def _baseline_only_rose(scan, sha):
    after = _baseline_at(scan, sha)
    parents = gitcmd.lines(scan.root, "rev-parse", f"{sha}^", check=False)
    if not parents:
        return True
    before = _baseline_at(scan, parents[0])
    for name, entry in (before.get("scopes") or {}).items():
        now = (after.get("scopes") or {}).get(name)
        if now is None:
            return False
        if now.get("line", 0) < entry.get("line", 0) or now.get("branch", 0) < entry.get("branch", 0):
            return False
    return True


def _baseline_at(scan, sha):
    text = gitcmd.show(scan.root, sha, "pair/rules/baseline.toml")
    if not text:
        return {}
    try:
        return tomlio.loads(text, "pair/rules/baseline.toml")
    except CheckFailed:
        return {}


def gate_commits(scan):
    found = []
    for sha in scan.shas:
        trailers = scan.trailers(sha)
        action = trailers.get("Pair-Action")
        outside = scan.outside_files(sha)
        if outside and action not in ("ok", "revert"):
            found.append(Failure(
                "commits", sha[:8],
                f"changes {len(outside)} file(s) outside pair/ ({', '.join(outside[:5])}) without "
                f"being a `Pair-Action: ok` commit", "PAIR-002"))
            continue
        if action == "revert" and outside:
            reverts = trailers.get("Pair-Reverts")
            if not reverts:
                found.append(Failure("commits", sha[:8],
                                     "a revert commit must carry Pair-Reverts", "PAIR-002"))
            elif not _is_inverse(scan, sha, reverts):
                found.append(Failure("commits", sha[:8],
                                     f"is not the exact inverse of {reverts[:8]}", "PAIR-002"))
            continue
        if action != "ok":
            continue
        found += _ok_commit(scan, sha, trailers, outside)
    return found


def _ok_commit(scan, sha, trailers, outside):
    found = []
    task = trailers.get("Pair-Task")
    step_number = trailers.get("Pair-Step")
    state = scan.state_at(sha, task) if task else None
    if state is None or step_number is None:
        return [Failure("commits", sha[:8],
                        "a `Pair-Action: ok` commit needs Pair-Task, Pair-Step and a readable "
                        "state.json", "PAIR-003")]
    step = state.step(int(step_number))
    if step is None:
        return [Failure("commits", sha[:8],
                        f"state.json has no step {step_number}", "PAIR-003")]
    expected = set(step.evidence.get("committed_files") or step.files) if step.evidence \
        else set(step.files)
    allowed = expected | {f"pair/tasks/{task}/state.json", f"pair/tasks/{task}/log.md",
                          "pair/rules/baseline.toml"}
    extra = [rel for rel in scan.files(sha) if rel not in allowed]
    if extra:
        found.append(Failure("commits", sha[:8],
                             f"changes files outside step {step_number}'s set: "
                             f"{', '.join(sorted(extra)[:5])}", "PAIR-002"))
    if len(expected) > 1 and state.batch_for(step.n) is None and state.expedite is None:
        found.append(Failure("commits", sha[:8],
                             f"step {step_number} commits {len(expected)} files without a batch "
                             f"grant or expedite", "PAIR-004"))
    return found


def _is_inverse(scan, sha, reverted):
    """A revert's diff must be exactly the inverse of the commit it names.

    Compared as sorted multisets of changed lines: within a hunk, git writes removals before
    additions, so a true inverse has the same lines in the opposite sense but not in mirrored
    order.
    """
    forward = gitcmd.run(scan.root, "diff", f"{reverted}^", reverted, check=False).stdout
    backward = gitcmd.run(scan.root, "diff", f"{sha}^", sha, check=False).stdout
    return sorted(_flip(forward)) == sorted(_body(backward))


def _body(diff_text):
    return [line for line in diff_text.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]


def _flip(diff_text):
    flipped = []
    for line in _body(diff_text):
        flipped.append(("-" if line[0] == "+" else "+") + line[1:])
    return flipped


def gate_approval(scan):
    found = []
    for sha in scan.shas:
        trailers = scan.trailers(sha)
        if trailers.get("Pair-Action") != "ok":
            continue
        task = trailers.get("Pair-Task")
        step_number = trailers.get("Pair-Step")
        if not task or step_number is None:
            found.append(Failure("approval", sha[:8],
                                 "an ok commit needs Pair-Task and Pair-Step", "PAIR-001"))
            continue
        if not _has_approval_ancestor(scan, sha, task):
            found.append(Failure("approval", sha[:8],
                                 f"no `Pair-Action: approve` or `expedite` for {task} in this "
                                 f"commit's ancestry", "PAIR-001"))
            continue
        state = scan.state_at(sha, task)
        step = state.step(int(step_number)) if state else None
        if step is None:
            found.append(Failure("approval", sha[:8],
                                 f"state.json at this commit has no step {step_number}",
                                 "PAIR-001"))
            continue
        approved = step.approved_plan_sha256
        parents = gitcmd.lines(scan.root, "rev-parse", f"{sha}^", check=False)
        plan_text = gitcmd.show(scan.root, parents[0], f"pair/tasks/{task}/plan.md") \
            if parents else None
        actual = plan_mod.sha256(plan_text) if plan_text is not None else None
        if approved and actual and approved != actual:
            found.append(Failure("approval", sha[:8],
                                 f"step {step_number} was approved against a different plan "
                                 f"({approved[:8]} vs {actual[:8]})", "PAIR-001"))
    return found


def _has_approval_ancestor(scan, sha, task):
    for candidate in gitcmd.lines(scan.root, "rev-list", sha):
        trailers = commit_mod.read_trailers(gitcmd.commit_message(scan.root, candidate))
        if trailers.get("Pair-Task") != task:
            continue
        if trailers.get("Pair-Action") in ("approve", "expedite"):
            return True
    return False


def gate_red(scan):
    """Every test-kind ok commit must have been red at that commit (TEST-001)."""
    found = []
    for sha in scan.shas:
        trailers = scan.trailers(sha)
        if trailers.get("Pair-Action") != "ok" or trailers.get("Pair-Kind") != "test":
            continue
        task = trailers.get("Pair-Task")
        state = scan.state_at(sha, task) if task else None
        step = state.step(int(trailers["Pair-Step"])) if state and trailers.get("Pair-Step") \
            else None
        if step is None:
            continue
        scope, trouble = scan.session.scopes.resolve_all(step.files)
        if scope is None or not scope.has("test"):
            continue                     # C34: nothing to run, so nothing to check
        outcome = _run_in_worktree(scan, sha, scope, "test")
        if outcome is None:
            continue
        code, output = outcome
        if code == 0:
            found.append(Failure("red", sha[:8],
                                 f"the scope suite passes at this commit, so step "
                                 f"{trailers['Pair-Step']} was never red", "TEST-001"))
            continue
        wrong = _first_match(output, scan.config.wrong_reason_patterns)
        if wrong:
            found.append(Failure("red", sha[:8],
                                 f"the suite failed for the wrong reason (matched {wrong!r})",
                                 "TEST-001"))
    return found


def _first_match(text, patterns):
    import re
    for pattern in patterns or ():
        try:
            if re.search(pattern, text):
                return pattern
        except re.error:
            if pattern in text:
                return pattern
    return None


def _run_in_worktree(scan, sha, scope, command_name):
    """Run a scope command at a past commit, in a throwaway worktree."""
    import shutil
    import subprocess
    import tempfile
    command = scope.command(command_name)
    if not command:
        return None
    folder = tempfile.mkdtemp(prefix="pair-check-")
    try:
        made = gitcmd.run(scan.root, "worktree", "add", "--detach", folder, sha, check=False)
        if made.returncode != 0:
            return None
        work = pathlib.Path(folder) / scope.cwd
        done = subprocess.run(command, shell=True, cwd=str(work), capture_output=True, text=True,
                              timeout=scope.timeout_seconds)
        return done.returncode, done.stdout + done.stderr
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        gitcmd.run(scan.root, "worktree", "remove", "--force", folder, check=False)
        shutil.rmtree(folder, ignore_errors=True)


def gate_coverage(scan):
    found = []
    baselines = coverage_mod.Baselines.load(scan.layout.baseline)
    touched = {}
    for sha in scan.shas:
        trailers = scan.trailers(sha)
        if trailers.get("Pair-Action") != "ok":
            continue
        if trailers.get("Pair-Kind") not in STEP_KINDS_WITH_COVERAGE:
            continue
        task = trailers.get("Pair-Task")
        state = scan.state_at(sha, task) if task else None
        step = state.step(int(trailers["Pair-Step"])) if state and trailers.get("Pair-Step") \
            else None
        if step is None:
            continue
        scope, _ = scan.session.scopes.resolve_all(step.files)
        if scope is not None and scope.has("coverage"):
            touched.setdefault(scope.name, scope)

    found += _baseline_never_decreased(scan)
    found += _pragmas(scan)

    for name, scope in sorted(touched.items()):
        env_path = scan.layout.coverage_xml(scope.path)
        if not env_path.is_file():
            found.append(Failure("coverage", name,
                                 f"no coverage report at {env_path.name}: run the scope's coverage "
                                 f"command with PAIR_COVERAGE_XML set (SPEC 13.2)", "COV-001"))
            continue
        report = coverage_mod.Report.load(env_path)
        floor_line, floor_branch = baselines.floor(name, scope.target,
                                                   scan.config.ratchet_tolerance)
        if report.line_rate < floor_line or report.branch_rate < floor_branch:
            found.append(Failure("coverage", name,
                                 f"{report.line_rate}% line / {report.branch_rate}% branch is "
                                 f"below the floor {floor_line}/{floor_branch}", "COV-001"))
        changed = {}
        for sha in scan.shas:
            for rel in scan.files(sha):
                if files.classify(rel, scan.config) != "code":
                    continue
                if scan.session.scopes.resolve(rel) is not scope and \
                        (scan.session.scopes.resolve(rel) or scope).name != name:
                    continue
                changed.setdefault(rel, set()).update(
                    gitcmd.changed_lines(scan.root, rel, ref=scan.base))
        percentage, uncovered = coverage_mod.changed_lines_covered(report, changed)
        if percentage < scan.config.changed_lines_target:
            for rel, numbers in sorted(uncovered.items()):
                found.append(Failure("coverage", rel,
                                     f"changed lines not covered: "
                                     f"{', '.join(str(n) for n in numbers)}", "COV-002"))
    return found


def _baseline_never_decreased(scan):
    found = []
    for sha in scan.shas:
        if "pair/rules/baseline.toml" not in scan.files(sha):
            continue
        if scan.action(sha) == "baseline-lower":
            continue
        if not _baseline_only_rose(scan, sha):
            found.append(Failure("coverage", sha[:8],
                                 "a baseline value decreased outside a `pair baseline --lower` "
                                 "commit", "COV-003"))
    return found


def _pragmas(scan):
    found = []
    exclusions = _exclusions(scan)
    for sha in scan.shas:
        for rel in scan.files(sha):
            if files.classify(rel, scan.config) not in ("code", "tests"):
                continue
            path = scan.root / rel
            if not path.is_file():
                continue
            before = gitcmd.show(scan.root, f"{sha}^", rel) or ""
            after = gitcmd.show(scan.root, sha, rel) or ""
            added = _added_pragma_lines(before, after)
            if added and not globs.match_any(rel, exclusions):
                found.append(Failure("coverage", rel,
                                     f"a coverage-ignore pragma was added on line(s) "
                                     f"{', '.join(str(n) for n in added)} in a file no approved "
                                     f"exclusion covers", "COV-004"))
    return found


def _added_pragma_lines(before, after):
    was = set(coverage_mod.find_pragmas(before))
    now = coverage_mod.find_pragmas(after)
    old_lines = before.splitlines()
    kept = {line for number, line in enumerate(old_lines, 1) if number in was}
    added = []
    for number in now:
        line = after.splitlines()[number - 1]
        if line not in kept:
            added.append(number)
    return added


def _exclusions(scan):
    """Approved coverage exclusions from every scope's RULES.md (SPEC 10.8)."""
    found = []
    for scope in scan.session.scopes:
        path = scope.rules_md
        if not path.is_file():
            continue
        inside = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().lower().startswith("## coverage exclusions"):
                inside = True
                continue
            if inside and line.startswith("## "):
                inside = False
            if inside:
                for hit in plan_mod.BACKTICKED.findall(line):
                    found.append(hit)
    return found


def gate_boundaries(scan):
    graph = boundaries_mod.Boundaries.load(scan.layout.boundaries)
    if not graph.configured:
        return []
    touched = set()
    for sha in scan.shas:
        touched.update(scan.files(sha))
    return [Failure("boundaries", problem.split(":")[0], problem.split(": ", 1)[1], "ARCH-001")
            for problem in graph.violations(scan.root, sorted(touched))]


def gate_secrets(scan):
    found = []
    for sha in scan.shas:
        diff = gitcmd.run(scan.root, "diff", f"{sha}^", sha, "--", "pair/", check=False).stdout
        for line in diff.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for name, _ in redact.findall(line[1:]):
                found.append(Failure("secrets", sha[:8],
                                     f"an added line in pair/ matches a {name} pattern",
                                     "SEC-001"))
    return found


def gate_format(scan):
    found = []
    found += _parses(scan)
    found += _active_plans(scan)
    found += _logs_appended_only(scan)
    found += _waivers(scan)
    found += _rule_ids(scan)
    return found


def _parses(scan):
    found = []
    for rel, loader in (("pair/config.toml", tomlio.load),
                        ("pair/rules/waivers.toml", tomlio.load_if_present),
                        ("pair/rules/boundaries.toml", tomlio.load_if_present),
                        ("pair/rules/baseline.toml", tomlio.load_if_present)):
        path = scan.root / rel
        try:
            loader(path, rel)
        except CheckFailed as problem:
            found.append(Failure("format", rel, problem.message))
    for task in state_mod.find_tasks(scan.layout):
        try:
            state_mod.State.load(scan.layout, task)
        except CheckFailed as problem:
            found.append(Failure("format", f"pair/tasks/{task}/state.json", problem.message))
    for path in sorted(scan.layout.learnings.glob("*.md")) if \
            scan.layout.learnings.is_dir() else []:
        from pair import lessons as lessons_mod
        loaded = lessons_mod.Domain.load(path)
        for number, line in enumerate(loaded.lines, start=1):
            if line.startswith("- ") and not lessons_mod.LESSON.match(line):
                found.append(Failure("format", f"{path.relative_to(scan.root)}:{number}",
                                     "this line starts a lesson but does not match the grammar "
                                     "(SPEC 10.5)"))
    return found


def _active_plans(scan):
    found = []
    for task in state_mod.find_tasks(scan.layout):
        try:
            state = state_mod.State.load(scan.layout, task)
        except CheckFailed:
            continue
        if not state.is_open:
            continue
        plan_path = scan.layout.plan(task)
        if not plan_path.is_file():
            continue
        problems = plan_mod.check(plan_mod.load(plan_path), state, scan.config,
                                  scan.session.scopes, scan.session.lesson_ids())
        for problem in problems:
            found.append(Failure("format", f"pair/tasks/{task}/plan.md", problem))
    return found


def _logs_appended_only(scan):
    """Append-only, checked commit by commit (SPEC 10.3).

    Comparing the working tree against the range's base would miss a log created inside the range,
    and would miss an entry that was changed and then changed back.
    """
    found = []
    for task in state_mod.find_tasks(scan.layout):
        rel = f"pair/tasks/{task}/log.md"
        for sha in scan.shas:
            if rel not in scan.files(sha):
                continue
            parents = gitcmd.lines(scan.root, "rev-parse", f"{sha}^", check=False)
            before = gitcmd.show(scan.root, parents[0], rel) if parents else None
            if before is None:
                continue
            after = gitcmd.show(scan.root, sha, rel) or ""
            for problem in log_mod.changed_entries(before, after):
                found.append(Failure("format", f"{rel}@{sha[:8]}", problem))
        current = scan.root / rel
        latest = gitcmd.show(scan.root, scan.head, rel)
        if current.is_file() and latest is not None:
            for problem in log_mod.changed_entries(latest,
                                                   current.read_text(encoding="utf-8")):
                found.append(Failure("format", rel, problem))
    return found


def _waivers(scan):
    store = waivers_mod.Waivers.load(scan.layout.waivers)
    return [Failure("format", "pair/rules/waivers.toml",
                    f"{waiver.rule} expired on {waiver.expires} — remove it with "
                    f"`pair waive --remove <n>`")
            for waiver in store.expired()]


def _rule_ids(scan):
    registry = rules_mod.Registry.load(scan.layout)
    return [Failure("format", "pair/rules", problem) for problem in registry.problems()]


RUNNERS = {
    "protected": gate_protected,
    "commits": gate_commits,
    "approval": gate_approval,
    "red": gate_red,
    "coverage": gate_coverage,
    "boundaries": gate_boundaries,
    "secrets": gate_secrets,
    "format": gate_format,
}


def run(session, gate, base, head="HEAD"):
    """Run one gate, or `all` in SPEC order. Returns the failures."""
    if gate not in GATES and gate != "all":
        raise UsageError(f"{gate!r} is not a gate ({', '.join(GATES)}, or all)")
    scan = Range(session, base, head)
    names = GATES if gate == "all" else (gate,)
    found = []
    for name in names:
        found += RUNNERS[name](scan)
    return found
