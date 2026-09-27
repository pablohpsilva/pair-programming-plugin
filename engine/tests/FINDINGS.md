# Spike findings (SPEC §23)

One section per [T] fact. Verdicts come from real runs; evidence is pasted, never paraphrased.
Runbook: `docs/SPIKES.md`. Spec changes caused by a finding go to `docs/SPEC-CHANGES.md`.

| # | Fact | Verdict | Spec impact |
|---|---|---|---|
| T1 | A plugin loads from an in-repo folder as a local marketplace | not run | — |
| T2 | A SessionStart hook's output reaches the model's context | not run | — |
| T3 | Hook `deny` is honoured in every permission mode | not run | — |
| T4 | The Bash tool runs without a TTY | **confirmed (stronger than assumed)** | §11.1 — see below |
| T5 | Exact `tool_input` field names for the file tools | not run | — |
| T6 | PreToolUse fires for a subagent's tool calls | not run | — |
| T7 | The llm-wiki layout (`wiki/`, `raw/`, `CLAUDE.md`) | not run | — |

---

## T4 — The Bash tool runs without a TTY

- **Verdict: confirmed, and more strongly than §11.1 assumed.** The Bash tool has no TTY on any
  of the three standard streams, and `/dev/tty` cannot even be *opened* — the controlling
  terminal is not merely redirected, it is absent from the process.
- **Tested on:** 2026-09-27 · Claude Code 2.1.267 · macOS 26.3.1 · Python 3.14.6 · darwin,
  from an interactive session running in a real terminal (`TERM=xterm-256color`, `CLAUDECODE=1`).
- **Evidence:**

```
$ python3 -c 'import sys; print("stdin",sys.stdin.isatty(),"| stdout",sys.stdout.isatty(),"| stderr",sys.stderr.isatty())'
stdin False | stdout False | stderr False

$ test -t 0 && echo "stdin IS a tty" || echo "stdin is NOT a tty"
stdin is NOT a tty

$ python3 -c 'open("/dev/tty","w")'
OSError: [Errno 6] Device not configured: '/dev/tty'

$ python3 -c 'print(open("/dev/tty").readline())'
read from /dev/tty: FAILED: OSError [Errno 6] Device not configured: '/dev/tty'
```

- **Why the second half matters more than the first.** §11.1's TTY check would be weak if the
  agent could open the engineer's terminal directly — `os.isatty` says nothing about that, since
  a process with piped stdio can still open `/dev/tty` and reach the controlling terminal. Here
  it cannot: `ENXIO`/"Device not configured" means the Bash tool's process has **no controlling
  terminal at all**. So layer 1 of §11.1 is genuine enforcement in this environment, not a speed
  bump: an agent cannot satisfy the confirmation prompt, and cannot fake one by writing to the
  engineer's screen either.
- **Spec impact:** none required. §11.1 stands as written. Two additions worth making:
  - §11.1 mechanism 1 should say *why* it works — the check is `os.isatty` **and** a successful
    `open("/dev/tty")`; the second is the one that cannot be spoofed by a wrapper that fakes a
    pty on stdio. Recommend requiring both.
  - §11.1's "stated limitation" paragraph stays accurate and unchanged: an agent running as the
    same OS user can still start its own pty (`script`, `expect`, `pty.spawn`) and drive the CLI
    through it. That is the bypass the paragraph already describes, and CI (§13) remains the
    backstop. **Not yet tested** — a follow-up probe (T4b) should try
    `python3 -c 'import pty,os; pty.spawn(["pair","ok"])'` once the CLI exists, and §22 should
    carry a test that the confirmation still refuses when it cannot read the expected token.
- **Caveat on generality:** one environment (macOS, this client version). Re-check on Linux and
  under `ssh`/`tmux` before treating it as a portable guarantee; D8 limits us to Linux and macOS,
  so a Linux run is the only other case that matters.
