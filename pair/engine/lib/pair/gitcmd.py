"""The only module that runs git.

Everything else asks for what it needs by name, so there is one place to look when a git invocation
is wrong, and one place that knows pair never touches the index outside its own commits (SPEC 8.2).
"""

import subprocess

from pair.errors import CheckFailed

WRITE_SUBCOMMANDS = frozenset("""
add commit push merge rebase reset checkout switch restore stash apply am cherry-pick revert tag
branch update-ref update-index config rm mv clean worktree filter-branch notes
""".split())


class GitFailed(CheckFailed):
    def __init__(self, args, result):
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        super().__init__(f"git {' '.join(args)} failed ({result.returncode})", detail[:10])
        self.result = result


def run(root, *args, check=True, env=None, stdin=None):
    """Run git in `root`. `check=False` returns the result whatever the exit code."""
    result = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, input=stdin, env=env,
    )
    if check and result.returncode != 0:
        raise GitFailed(args, result)
    return result


def out(root, *args, check=True):
    return run(root, *args, check=check).stdout.strip()


def lines(root, *args, check=True):
    text = run(root, *args, check=check).stdout
    return [line for line in text.splitlines() if line]


# -- reading ------------------------------------------------------------------------------------

def is_repo(root):
    return run(root, "rev-parse", "--git-dir", check=False).returncode == 0


def head(root):
    return out(root, "rev-parse", "HEAD")


def has_commits(root):
    return run(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def current_branch(root):
    name = out(root, "rev-parse", "--abbrev-ref", "HEAD")
    return None if name == "HEAD" else name


def branch_exists(root, name):
    return run(root, "rev-parse", "--verify", f"refs/heads/{name}", check=False).returncode == 0


def status_porcelain(root):
    """[(code, path)] for every change git reports, including untracked-not-ignored."""
    entries = []
    # `-uall` matters: by default git reports an untracked *directory* as one entry, so a new file
    # in a new folder would never match a grant's `**/*.py` glob (SPEC 8.2).
    for line in lines(root, "status", "--porcelain", "-uall"):
        code, rest = line[:2], line[3:]
        if " -> " in rest:                       # a rename reports old -> new
            rest = rest.split(" -> ", 1)[1]
        entries.append((code.strip(), rest.strip().strip('"')))
    return entries


def modified_tracked(root, exclude_prefix=None):
    """Tracked paths with a change in the worktree or the index."""
    found = []
    for code, path in status_porcelain(root):
        if code == "??":
            continue
        if exclude_prefix and path.startswith(exclude_prefix):
            continue
        found.append(path)
    return sorted(set(found))


def staged(root):
    return sorted(set(lines(root, "diff", "--cached", "--name-only")))


def untracked(root):
    return sorted(set(lines(root, "ls-files", "--others", "--exclude-standard")))


def is_tracked(root, rel):
    return bool(out(root, "ls-files", "--", rel, check=False))


def config_get(root, name):
    result = run(root, "config", "--get", name, check=False)
    return result.stdout.strip() or None


def last_commit_date(root, rel):
    """ISO date of the newest commit touching `rel`, or None when it is untracked."""
    return out(root, "log", "-1", "--format=%cs", "--", rel, check=False) or None


def show(root, ref, rel):
    """File content at a revision, or None when it does not exist there."""
    result = run(root, "show", f"{ref}:{rel}", check=False)
    return result.stdout if result.returncode == 0 else None


def merge_base(root, base, head_ref):
    return out(root, "merge-base", base, head_ref)


def commits_in_range(root, base, head_ref, first_parent=False):
    """SHAs oldest-first over `merge-base(base, head)..head`, merge commits excluded (SPEC 13.1)."""
    args = ["rev-list", "--reverse", "--no-merges"]
    if first_parent:
        args.append("--first-parent")
    args.append(f"{merge_base(root, base, head_ref)}..{head_ref}")
    return lines(root, *args)


def commit_message(root, sha):
    return run(root, "log", "-1", "--format=%B", sha).stdout


def commit_files(root, sha):
    """Paths changed by one commit, against its first parent."""
    return sorted(set(lines(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m",
                            "--first-parent", sha)))


def find_commits(root, *greps):
    """SHAs whose message matches every `grep` (SPEC 7.2: a step's commit is found, never stored)."""
    args = ["log", "--all", "--format=%H", "--all-match"]
    for grep in greps:
        args += ["--grep", grep]
    return lines(root, *args)


def diff_numstat(root, ref, rel):
    return lines(root, "diff", "--numstat", ref, "--", rel)


def changed_lines(root, rel, ref="HEAD"):
    """Line numbers added or modified in `rel` relative to `ref`.

    An untracked file has no `ref` side, so every line counts (SPEC 8.2).
    """
    if not is_tracked(root, rel):
        try:
            body = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return set()
        return set(range(1, len(body.splitlines()) + 1))
    text = run(root, "diff", "-U0", ref, "--", rel, check=False).stdout
    return _added_lines(text)


def _added_lines(diff_text):
    """Parse `@@ -a,b +c,d @@` hunk headers; only the new-side numbers matter."""
    found = set()
    for line in diff_text.splitlines():
        if not line.startswith("@@"):
            continue
        try:
            new_part = line.split("+", 1)[1].split("@@", 1)[0].strip()
        except IndexError:
            continue
        start, _, count = new_part.partition(",")
        try:
            first = int(start)
            length = int(count) if count else 1
        except ValueError:
            continue
        found.update(range(first, first + length))
    return found


# -- writing ------------------------------------------------------------------------------------

def create_branch(root, name):
    run(root, "checkout", "-b", name)


def checkout(root, name):
    run(root, "checkout", name)


def commit_only(root, message, rel_paths, env=None):
    """`git commit --only -- <paths>` (SPEC 11.3). Nothing else may reach the commit."""
    existing = [p for p in rel_paths if (root / p).exists() or is_tracked(root, p)]
    if not existing:
        raise CheckFailed("nothing to commit: none of the listed paths exist")
    run(root, "add", "--", *existing)
    run(root, "commit", "--only", "-m", message, "--", *existing, env=env)
    return head(root)


def revert(root, sha):
    """`git revert --no-edit`, returning (ok, output). A conflict is reported, never resolved."""
    result = run(root, "revert", "--no-edit", sha, check=False)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def amend_message(root, message):
    run(root, "commit", "--amend", "-m", message)
