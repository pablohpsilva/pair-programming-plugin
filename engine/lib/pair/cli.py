"""`pair <command>` — the single entry point (SPEC 11).

Exit codes: 0 ok · 1 a check failed or a precondition wasn't met · 2 usage · 3 human-only or
owner-only refusal. Every command takes `--json`.

`main` returns the exit code rather than calling `sys.exit`, so the whole CLI is testable in-process
— which is what lets the human-only commands be tested at all without faking a terminal in
production code.
"""

import argparse
import json
import sys

from pair import (check as check_mod, clock, doctor as doctor_mod, find as find_mod, flow,
                  index as index_mod, init as init_mod, paths, plan as plan_mod, report as report_mod,
                  rules as rules_mod, state as state_mod, upgrade as upgrade_mod)
from pair.errors import CheckFailed, PairError, Refused, UsageError


class Printer:
    def __init__(self, stdout, stderr, as_json):
        self.stdout = stdout
        self.stderr = stderr
        self.as_json = as_json

    def outcome(self, outcome, extra=None):
        if self.as_json:
            body = dict(outcome.data)
            body.update(extra or {})
            body["lines"] = outcome.lines
            if outcome.warnings:
                body["warnings"] = outcome.warnings
            self.stdout.write(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
            return 0
        for line in outcome.lines:
            self.stdout.write(line + "\n")
        for warning in outcome.warnings:
            self.stderr.write(f"! {warning}\n")
        return 0

    def lines(self, lines, data=None):
        return self.outcome(flow.Outcome(lines, data))

    def failure(self, problem):
        if self.as_json:
            self.stdout.write(json.dumps({"ok": False, "error": problem.message,
                                          "details": problem.details}, indent=2) + "\n")
        else:
            self.stderr.write(problem.message + "\n")
            for line in problem.details:
                self.stderr.write(f"  - {line}\n")
        return problem.exit_code


def build_parser():
    parser = argparse.ArgumentParser(prog="pair", add_help=True,
                                     description="pair — the engineer decides, the agent proposes")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--version", action="store_true", help="print the engine version")
    subs = parser.add_subparsers(dest="command")

    subs.add_parser("status").add_argument("--line", action="store_true")
    subs.add_parser("diff")
    subs.add_parser("plan-check")
    subs.add_parser("done")
    subs.add_parser("approve")
    subs.add_parser("ok")
    subs.add_parser("reopen")
    subs.add_parser("pause")
    subs.add_parser("doctor")
    subs.add_parser("index")

    start = subs.add_parser("start")
    start.add_argument("task")
    start.add_argument("--mode", default="agent-drives", choices=list(state_mod.MODES))
    start.add_argument("--no-branch", action="store_true")

    subs.add_parser("rework").add_argument("note")
    subs.add_parser("resume").add_argument("task")
    subs.add_parser("handoff").add_argument("handle")
    subs.add_parser("abandon").add_argument("reason")
    subs.add_parser("mode").add_argument("mode", choices=list(state_mod.MODES))
    subs.add_parser("close")

    revert = subs.add_parser("revert")
    revert.add_argument("task")
    revert.add_argument("--step", type=int)

    grant = subs.add_parser("grant-batch")
    grant.add_argument("--step", type=int, required=True)
    grant.add_argument("--paths", required=True)
    grant.add_argument("--max-files", type=int, required=True)
    grant.add_argument("--include-tests", action="store_true")

    find = subs.add_parser("find")
    find.add_argument("query", nargs="?", default="")
    find.add_argument("--source")
    find.add_argument("--scope")
    find.add_argument("--rule")
    find.add_argument("-n", type=int)

    baseline = subs.add_parser("baseline")
    baseline.add_argument("--scope")
    baseline.add_argument("--lower", action="store_true")
    baseline.add_argument("--reason")

    waive = subs.add_parser("waive")
    waive.add_argument("rule", nargs="?")
    waive.add_argument("--reason")
    waive.add_argument("--scope", action="append", default=[])
    waive.add_argument("--expires")
    waive.add_argument("--remove", type=int)

    expedite = subs.add_parser("expedite")
    expedite.add_argument("task")
    expedite.add_argument("--test-paths", required=True)
    expedite.add_argument("--paths", required=True)
    expedite.add_argument("--reason", required=True)
    expedite.add_argument("--no-branch", action="store_true")

    lesson = subs.add_parser("lesson")
    lesson_subs = lesson.add_subparsers(dest="lesson_command")
    propose = lesson_subs.add_parser("propose")
    propose.add_argument("text")
    propose.add_argument("--domain", required=True)
    for name in ("accept", "edit", "reject"):
        each = lesson_subs.add_parser(name)
        each.add_argument("number", type=int)
        if name == "edit":
            each.add_argument("--text")
    lesson_subs.add_parser("dispute").add_argument("lesson_id")

    export = subs.add_parser("export")
    export.add_argument("what", choices=["walkthrough"])
    export.add_argument("task", nargs="?")

    report = subs.add_parser("report")
    report.add_argument("--since")
    report.add_argument("--write", action="store_true")

    checker = subs.add_parser("check")
    checker.add_argument("gate")
    checker.add_argument("--base", required=True)
    checker.add_argument("--head", default="HEAD")

    upgrade = subs.add_parser("upgrade")
    upgrade.add_argument("--from", dest="source", required=True)

    initialise = subs.add_parser("init")
    initialise.add_argument("--sources", action="store_true",
                            help="only detect and register knowledge sources")
    initialise.add_argument("--no-agents-md", action="store_true")
    return parser


def main(argv=None, stdout=None, stderr=None, confirm=None, root=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return 0 if stop.code == 0 else 2

    printer = Printer(stdout, stderr, getattr(args, "json", False))
    if args.version:
        version = (paths.Layout(root or ".").engine / "VERSION")
        stdout.write((version.read_text().strip() if version.is_file() else "0.1.0") + "\n")
        return 0
    if not args.command:
        parser.print_help(stdout)
        return 2

    try:
        if args.command == "init":
            return _init(args, printer, confirm, root)
        session = flow.Session.open(root, confirm=confirm)
        return _dispatch(args, session, printer)
    except PairError as problem:
        return printer.failure(problem)
    except KeyboardInterrupt:                                       # pragma: no cover
        stderr.write("interrupted\n")
        return 1


def _dispatch(args, session, printer):
    command = args.command
    if command == "status":
        if args.line:
            return printer.lines([flow.status_line(session)])
        return printer.outcome(flow.status(session))
    if command == "diff":
        return printer.outcome(_diff(session))
    if command == "plan-check":
        return printer.outcome(flow.plan_check(session))
    if command == "start":
        return printer.outcome(flow.start(session, args.task, args.mode, args.no_branch))
    if command == "approve":
        return printer.outcome(flow.approve(session))
    if command == "done":
        return printer.outcome(flow.done(session))
    if command == "ok":
        return printer.outcome(flow.ok(session))
    if command == "rework":
        return printer.outcome(flow.rework(session, args.note))
    if command == "reopen":
        return printer.outcome(flow.reopen(session))
    if command == "pause":
        return printer.outcome(flow.pause(session))
    if command == "resume":
        return printer.outcome(flow.resume(session, args.task))
    if command == "handoff":
        return printer.outcome(flow.handoff(session, args.handle))
    if command == "abandon":
        return printer.outcome(flow.abandon(session, args.reason))
    if command == "mode":
        return printer.outcome(flow.mode(session, args.mode))
    if command == "close":
        return printer.outcome(flow.close(session))
    if command == "revert":
        return printer.outcome(flow.revert(session, args.task, args.step))
    if command == "grant-batch":
        patterns = [part.strip() for part in args.paths.split(",") if part.strip()]
        return printer.outcome(flow.grant_batch(session, args.step, patterns, args.max_files,
                                                args.include_tests))
    if command == "baseline":
        return printer.outcome(flow.baseline(session, args.scope, args.lower, args.reason))
    if command == "waive":
        if args.remove is not None:
            return printer.outcome(flow.waive_remove(session, args.remove))
        if not args.rule:
            raise UsageError("pair waive needs a rule ID, or --remove <n>")
        return printer.outcome(flow.waive(session, args.rule, args.reason, args.scope,
                                          args.expires, session.active_id()))
    if command == "expedite":
        return printer.outcome(flow.expedite(
            session, args.task, _globs(args.test_paths), _globs(args.paths), args.reason,
            args.no_branch))
    if command == "lesson":
        return _lesson(args, session, printer)
    if command == "export":
        return printer.outcome(flow.export_walkthrough(session, args.task))
    if command == "index":
        return printer.outcome(_index(session))
    if command == "find":
        return _find(args, session, printer)
    if command == "doctor":
        return _doctor(session, printer)
    if command == "report":
        return _report(args, session, printer)
    if command == "check":
        return _check(args, session, printer)
    if command == "upgrade":
        return _upgrade(args, session, printer)
    raise UsageError(f"unknown command {command!r}")


def _globs(text):
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def _lesson(args, session, printer):
    which = args.lesson_command
    if which == "propose":
        return printer.outcome(flow.lesson_propose(session, args.text, args.domain))
    if which in ("accept", "reject"):
        return printer.outcome(flow.lesson_decide(session, which, args.number))
    if which == "edit":
        return printer.outcome(flow.lesson_decide(session, "edit", args.number,
                                                  getattr(args, "text", None)))
    if which == "dispute":
        return printer.outcome(flow.lesson_dispute(session, args.lesson_id))
    raise UsageError("pair lesson needs propose, accept, edit, reject or dispute")


def _diff(session):
    """The current step's file set, including untracked files (SPEC 11.2)."""
    from pair import evidence, gitcmd
    state = session.state()
    step = state.current
    if step is None:
        return flow.Outcome(["no current step"], {"files": []})
    found = evidence.file_set(session.root, state, step, session.config)
    lines = []
    for rel in found:
        if gitcmd.is_tracked(session.root, rel):
            lines.append(gitcmd.run(session.root, "diff", "--", rel, check=False).stdout.rstrip())
        else:
            lines.append(gitcmd.run(session.root, "diff", "--no-index", "/dev/null", rel,
                                    check=False).stdout.rstrip())
    return flow.Outcome([line for line in lines if line], {"files": found})


def _index(session):
    built, resolved = index_mod.build(session.layout, session.config)
    built.save(session.layout.index_file)
    lines = [f"indexed {len(built.chunks)} chunks from {len(built.files)} files"]
    for each in resolved:
        mark = " (empty)" if each.empty else ""
        lines.append(f"  {each.type} {each.path}: {len(each.files)} files{mark}")
    return flow.Outcome(lines, {"chunks": len(built.chunks), "files": len(built.files)})


def _find(args, session, printer):
    if args.rule:
        rule = find_mod.by_rule(session.registry, args.rule)
        if rule is None:
            raise CheckFailed(f"{args.rule} is not a known rule")
        return printer.outcome(flow.Outcome([rule.raw],
                                            {"rule": rule.id, "tier": rule.tier,
                                             "source": rule.source, "row": rule.raw}))
    if not args.query:
        raise UsageError('pair find needs a query: pair find "<words>", or --rule <ID>')
    built, _ = index_mod.refresh(session.layout, session.config)
    limit = args.n or session.config.max_results
    hits = find_mod.search(built, args.query, limit=limit, source_type=args.source,
                           scope=args.scope)
    find_mod.log_query(session.layout, session.active_id(), args.query, hits)
    if not hits:
        return printer.outcome(flow.Outcome([f"no hits for {args.query!r}"], {"hits": []}))
    return printer.outcome(flow.Outcome(
        [hit.render(session.config.stale_days) for hit in hits],
        {"hits": [hit.as_data() for hit in hits]}))


def _doctor(session, printer):
    notes = doctor_mod.run(session)
    verdict = doctor_mod.worst(notes)
    outcome = flow.Outcome([note.render() for note in notes] + [f"— {verdict}"],
                           {"verdict": verdict, "notes": [note.as_data() for note in notes]})
    printer.outcome(outcome)
    return 1 if verdict == "error" else 0


def _report(args, session, printer):
    report = report_mod.build(session, args.since)
    if args.write:
        session.require_human("report-write")
        path = report_mod.write(session, report)
        from pair import commit
        sha, warnings = commit.action_commit(session.root, [session.rel(path)], "report",
                                            session.config.governance,
                                            f"docs(pair): report {clock.today()[:7]}")
        return printer.outcome(flow.Outcome(report.lines + [f"written to {session.rel(path)}"],
                                            dict(report.data, commit=sha), warnings))
    return printer.outcome(flow.Outcome(report.lines, report.data))


def _check(args, session, printer):
    failures = check_mod.run(session, args.gate, args.base, args.head)
    if not failures:
        return printer.outcome(flow.Outcome([f"{args.gate}: ok"], {"gate": args.gate, "ok": True}))
    printer.outcome(flow.Outcome([failure.render() for failure in failures],
                                 {"gate": args.gate, "ok": False,
                                  "failures": [f.as_data() for f in failures]}))
    return 1


def _upgrade(args, session, printer):
    import shutil
    session.require_human("upgrade")
    folder = upgrade_mod.temporary_folder()
    try:
        fetched = upgrade_mod.fetch(args.source, folder + "/engine")
        summary = upgrade_mod.diff(session, fetched)
        target = upgrade_mod.target_format(fetched)
        current = session.config.format
        applied = []
        upgrade_mod.replace(session, fetched)
        if target > current:
            applied = upgrade_mod.run_migrations(session, session.layout.engine, current, target)
        upgrade_mod.stamp_config(session, upgrade_mod.version_of(session.layout.engine), target)
        touched = upgrade_mod.stamp_states(session, target)
        from pair import commit
        paths_to_commit = [session.rel(session.layout.engine), session.rel(session.layout.config)]
        paths_to_commit += touched
        sha, warnings = commit.action_commit(session.root, paths_to_commit, "upgrade",
                                            session.config.governance,
                                            f"chore(pair): engine {summary['from']} → "
                                            f"{summary['to']}")
        lines = [f"engine {summary['from']} → {summary['to']}",
                 f"{len(summary['added'])} added, {len(summary['changed'])} changed, "
                 f"{len(summary['removed'])} removed"]
        if applied:
            lines.append("migrations: " + ", ".join(applied))
        lines.append(f"format {current} → {target}")
        return printer.outcome(flow.Outcome(lines, dict(summary, commit=sha, migrations=applied),
                                            warnings))
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _init(args, printer, confirm, root):
    """`init` runs before there is a pair/ to load, so it builds its own session (SPEC 11.4)."""
    from pair import config as config_mod, gitcmd, tty
    start = paths.find_root(root)
    base = paths.Layout(start or (root or ".")).root
    if not gitcmd.is_repo(base):
        raise CheckFailed(f"{base} is not a git repository — run `git init` first")

    layout = paths.Layout(base)
    existing = layout.config.is_file()
    if existing:
        session = flow.Session.open(base, confirm=confirm)
    else:
        layout.pair_dir.mkdir(parents=True, exist_ok=True)
        layout.config.write_text(_seed_config(base), encoding="utf-8")
        session = flow.Session.open(base, confirm=confirm)

    packages = init_mod.detect_packages(session.root)
    source_entries = [entry for entry in _detected_sources(session)]
    plan = init_mod.build_plan(session, packages, source_entries,
                              with_agents_md=not args.no_agents_md)
    new, changed, same = plan.diff_against(session.root)

    lines = [f"pair init in {session.root}"]
    lines.append(f"packages: {', '.join(p['path'] or '<root>' for p in packages) or 'none found'}")
    lines.append(f"sources: {', '.join(entry['path'] for entry in source_entries) or 'none found'}")
    lines += [f"  + {rel}" for rel in new]
    lines += [f"  ~ {rel}" for rel in changed]
    if same:
        lines.append(f"  = {len(same)} file(s) already correct")
    lines += ["", *plan.notes]

    if existing and not (new or changed):
        return printer.outcome(flow.Outcome(lines + ["nothing to change"], {"changed": False}))

    session.require_human("init")
    written = init_mod.apply(session, plan)
    sha, warnings = init_mod.commit_init(session, written)
    return printer.outcome(flow.Outcome(lines + [f"committed {sha[:8]}"],
                                        {"changed": True, "written": written, "commit": sha},
                                        warnings))


def _seed_config(root):
    from pair import gitcmd, tomlio
    return tomlio.dumps({
        "format": 1, "engine": _engine_version(), "governance": "0.1",
        "project": {"name": root.name,
                    "default_branch": gitcmd.current_branch(root) or "main"},
    })


def _engine_version():
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else "0.1.0"


def _detected_sources(session):
    from pair import sources as sources_mod
    for entry in sources_mod.detect(session.root):
        found = dict(entry)
        found.pop("optional", None)
        yield found


if __name__ == "__main__":                                          # pragma: no cover
    sys.exit(main())
