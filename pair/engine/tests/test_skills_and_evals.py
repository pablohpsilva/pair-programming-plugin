"""The four skills (SPEC 9) and the eval suite (SPEC 21) keep their contracts."""

import json
import pathlib
import re
import subprocess

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ENGINE / "skills"
EVALS = ENGINE / "evals"

EXPECTED = {
    "pair": "Pair-programming protocol for repositories with a pair/ folder",
    "pair-plan": "Use when the pair task is in the planning phase",
    "pair-step": "Use when the pair task is in the stepping or review phase",
    "pair-close": "Use when the pair task is in the closing phase",
}
VENDORS = re.compile(r"(?i)\b(claude|anthropic|copilot|chatgpt|openai|gemini|codeium|devin)\b")


def skill_files():
    return sorted(SKILLS.glob("*/SKILL.md"))


def frontmatter(text):
    assert text.startswith("---\n"), "a skill starts with frontmatter"
    body = text.split("---\n", 2)
    found = {}
    for line in body[1].splitlines():
        if ":" in line:
            name, _, value = line.partition(":")
            found[name.strip()] = value.strip()
    return found, body[2]


def test_the_four_skills_exist_with_the_expected_folder_names():
    assert [path.parent.name for path in skill_files()] == \
        ["pair", "pair-close", "pair-plan", "pair-step"]


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_each_skill_has_name_and_description_frontmatter(path):
    meta, _ = frontmatter(path.read_text(encoding="utf-8"))
    assert meta["name"] == path.parent.name
    assert meta["description"].startswith(EXPECTED[path.parent.name])


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_each_skill_stays_under_150_lines(path):
    """SPEC 9: SHOULD stay under 150; the documented client limit is 500."""
    count = len(path.read_text(encoding="utf-8").splitlines())
    assert count < 150, f"{path.parent.name} is {count} lines"


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_no_skill_names_a_vendor(path):
    assert not VENDORS.search(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_no_skill_restates_a_rule_it_only_cites_the_id(path):
    """SPEC 9: skills cite rule IDs and use `pair find --rule <ID>` for the text."""
    text = path.read_text(encoding="utf-8")
    registry = (ENGINE / "defaults" / "rules.md").read_text(encoding="utf-8")
    bodies = [line.split("|")[2].strip() for line in registry.splitlines()
              if line.startswith("| ") and line.count("|") >= 4][1:]
    restated = [body for body in bodies if len(body) > 25 and body in text]
    assert restated == [], f"{path.parent.name} restates: {restated}"


def test_the_bootstrap_skill_covers_every_item_of_spec_9_1_in_order():
    text = (SKILLS / "pair" / "SKILL.md").read_text(encoding="utf-8")
    ordered = [
        "You are the driver",                     # 1 role and goal
        "First action, every session",            # 2 pair status and the phase map
        "pair:pair-plan",
        "pair:pair-step",
        "pair:pair-close",
        "pair start <id>",
        "COMM-001",                               # 3 communication and the challenge procedure
        "L2",
        "challenges you",
        "✅ pair ok",                         # 4 the four options
        "pair lesson propose",                    # 5 when corrected
        'pair find "<words>"',                     # 6 knowledge
        "KNOW-001",
        "SEC-002",
        "Stop and ask when",                      # 7
        "Never",                                  # 8
    ]
    positions = []
    for needle in ordered:
        assert needle in text, f"the bootstrap skill is missing {needle!r}"
        positions.append(text.index(needle))
    assert positions == sorted(positions), "the bootstrap skill's sections are out of SPEC 9.1 order"


def test_the_bootstrap_skill_lists_every_human_only_command():
    text = (SKILLS / "pair" / "SKILL.md").read_text(encoding="utf-8")
    from pair import flow
    for command in flow.HUMAN_ONLY:
        name = command.replace("lesson-", "lesson ").replace("report-write", "report --write")
        word = name.split()[0]
        assert word in text, f"the bootstrap skill does not mention {command}"


def test_the_step_skill_requires_verbatim_evidence_and_the_two_attempt_stop():
    text = (SKILLS / "pair-step" / "SKILL.md").read_text(encoding="utf-8")
    assert "verbatim" in text
    assert "two failed attempts" in text
    assert "Never" in text and "pair ok" in text.split("## Never")[1]


def test_the_plan_skill_names_the_step_orders_and_rule_8a():
    text = (SKILLS / "pair-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert "`stub` → `test` → `code`" in text
    assert "`test` → `code`" in text
    assert "char" in text
    assert "grant-batch" in text


def test_the_close_skill_names_every_walkthrough_duty():
    text = (SKILLS / "pair-close" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("walkthrough.md", "find_log", "promote_after", "pair export walkthrough",
                   "pair close"):
        assert needle in text, needle


# -- the plugin manifests ---------------------------------------------------------------------

def test_the_plugin_manifest_names_the_plugin_and_points_at_skills_and_hooks():
    data = json.loads((ENGINE / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "pair"
    assert data["skills"] == "./skills"
    assert data["hooks"] == "./hooks/hooks.json"


def test_the_marketplace_template_sits_at_the_root_and_points_at_the_engine():
    """The marketplace root is the folder holding `.claude-plugin/`, and SPEC 4 declares `./pair`."""
    data = json.loads((ENGINE / "templates" / "marketplace.json").read_text())
    assert data["name"] == "pair-local"
    assert [entry["source"] for entry in data["plugins"]] == ["./engine"]
    assert not (ENGINE / ".claude-plugin" / "marketplace.json").exists(), \
        "the engine ships only plugin.json; the marketplace manifest belongs at pair/"


def test_the_plugin_version_matches_the_engine_version():
    """T1.4: a local-directory marketplace reports `unknown` unless plugin.json pins it."""
    data = json.loads((ENGINE / ".claude-plugin" / "plugin.json").read_text())
    assert data["version"] == (ENGINE / "VERSION").read_text().strip()


def test_the_hooks_manifest_uses_the_star_matcher_and_the_three_events():
    data = json.loads((ENGINE / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(data) == {"SessionStart", "UserPromptSubmit", "PreToolUse"}
    assert data["PreToolUse"][0]["matcher"] == "*"
    for event, argument in (("SessionStart", "session-start"), ("UserPromptSubmit", "prompt"),
                            ("PreToolUse", "pre")):
        command = data[event][0]["hooks"][0]["command"]
        assert command.endswith(argument)
        assert "${CLAUDE_PLUGIN_ROOT}/lib/pair/hook.py" in command


def test_the_hook_runs_as_a_script_the_way_hooks_json_invokes_it(tmp_path):
    """hooks.json runs the file directly, so `lib/` is not on the path until the file adds it."""
    root = tmp_path / "repo"
    (root / "pair").mkdir(parents=True)
    (root / "pair" / "config.toml").write_text(
        'format = 1\nengine = "0.1.0"\ngovernance = "0.1"\n\n[project]\nname = "x"\n'
        'default_branch = "main"\n')
    payload = json.dumps({"cwd": str(root), "session_id": "s", "permission_mode": "default",
                          "tool_name": "Bash", "tool_input": {"command": "git commit -m x"}})
    import sys
    done = subprocess.run([sys.executable, str(ENGINE / "lib" / "pair" / "hook.py"), "pre"],
                          input=payload, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(root)})
    assert done.returncode == 0, done.stderr
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "PAIR-003" in decision["permissionDecisionReason"]


# -- the eval suite ----------------------------------------------------------------------------

def eval_cases():
    return sorted(path for path in EVALS.iterdir() if (path / "prompt.md").is_file())


def test_there_is_one_eval_case_per_spec_21_row():
    assert len(eval_cases()) == 16
    assert [path.name[:3] for path in eval_cases()] == [f"e{n:02d}" for n in range(1, 17)]


@pytest.mark.parametrize("case", eval_cases(), ids=lambda p: p.name)
def test_each_case_has_a_prompt_a_setup_and_graders(case):
    assert (case / "prompt.md").is_file()
    assert (case / "setup.json").is_file()
    graders = json.loads((case / "graders" / "graders.json").read_text())
    assert graders, "a case with no graders always passes"
    for grader in graders:
        assert grader["type"] in ("regex", "tool_used", "tool_order", "file_exists", "llm")


@pytest.mark.parametrize("case", eval_cases(), ids=lambda p: p.name)
def test_each_case_states_its_setup_and_its_pass_condition(case):
    text = (case / "prompt.md").read_text(encoding="utf-8")
    assert "**Setup:**" in text
    assert "**Passes when:**" in text


@pytest.mark.parametrize("case", eval_cases(), ids=lambda p: p.name)
def test_every_case_scaffolds_into_a_working_repository(case, tmp_path):
    target = tmp_path / case.name
    done = subprocess.run(["python3", str(EVALS / "scaffold.py"), str(case), str(target)],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (target / "pair" / "config.toml").is_file()

    status = subprocess.run([str(ENGINE / "bin" / "pair"), "status"], cwd=str(target),
                            capture_output=True, text=True)
    assert status.returncode == 0, status.stdout + status.stderr
    expected = json.loads((case / "setup.json").read_text()).get("phase")
    if expected is None:
        assert "no active task" in status.stdout
    else:
        assert f"phase: {expected}" in status.stdout


def test_e16_has_no_user_prompt_because_that_is_the_point():
    text = (EVALS / "e16-session-start-only" / "prompt.md").read_text(encoding="utf-8")
    assert "No user prompt" in text


def test_the_evals_readme_flags_the_unverified_grader_schema():
    text = (EVALS / "README.md").read_text(encoding="utf-8")
    assert "never verified" in text


def test_both_entry_points_refuse_an_interpreter_older_than_3_11():
    """D2 means `tomllib`, which arrived in 3.11. The message must say so, not traceback."""
    for path in (ENGINE / "bin" / "pair", ENGINE / "lib" / "pair" / "hook.py"):
        text = path.read_text(encoding="utf-8")
        assert "version_info" in text, path.name
        assert "3.11" in text, path.name
