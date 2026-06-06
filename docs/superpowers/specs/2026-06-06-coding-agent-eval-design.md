# Coding Agent Eval — Design

**Date:** 2026-06-06
**Status:** Approved (pending user review of this document)

## Purpose

A public, open-source benchmark for evaluating CLI-based coding agents (Claude Code, Codex, Aider, etc.) on real GitHub issues, with a static leaderboard and reproducible results. Goal: answer "which coding agent should I use, and at what cost?" with hard numbers rather than vibes.

## Goals & Non-Goals

**Goals**
- Compare Claude Code, Codex, Aider (and more) head-to-head on the same set of real-world tasks.
- Track pass rate, cost (USD), wall-clock time, and token usage per agent per task.
- Public, static, serverless leaderboard deployable to GitHub Pages.
- Fully reproducible: every leaderboard number can be re-run from a single command.
- Local-first dev loop; Docker opt-in for official leaderboard runs.

**Non-Goals (v1)**
- LLM-as-judge scoring.
- SDK-only / non-CLI agents (OpenHands etc.). Adapters can be added later via the same Protocol.
- Hosted multi-tenant UI; the site is read-only.
- Community task submissions via PR. Tasks are authored in-tree by maintainers.
- Historical charts; current state is in `results/`, history is in git log.

## Architecture

Single Python package `probe-agent-eval` (CLI: `pae`). All components are in one repo for v1; split only when a second contributor arrives.

```
probe-agent-eval/
├── pyproject.toml             # one Python package, "pae" CLI
├── pae/                       # source
│   ├── cli.py                 # entry point: pae run / build-site / add-task
│   ├── harness.py             # run loop: clone, run agent, capture patch, grade
│   ├── grader.py              # apply patch, run hidden tests, parse results
│   ├── metrics.py             # cost/time/tokens from agent stdout
│   ├── site.py                # build static leaderboard from results/
│   └── agents/                # one file per agent
│       ├── base.py            # AgentAdapter protocol
│       ├── claude_code.py
│       ├── codex.py
│       └── aider.py
├── tasks/                     # SWE-bench-style task definitions
│   └── <owner__repo__id>/
│       ├── task.json          # metadata, base_commit, setup_cmd, etc.
│       ├── repo/              # the repo at base_commit (git submodule or LFS)
│       └── tests/             # hidden test patch
├── results/                   # JSON output of runs (committed)
│   └── 2026-06-06T12-34-56__claude__django-12345.json
├── site/                      # generated static leaderboard
│   ├── index.html             # sortable table of agent × task
│   ├── tasks/<id>.html        # per-task detail
│   └── data/results.json      # aggregate for the table
├── docs/                      # how to add tasks, run evals, etc.
└── .github/workflows/         # optional: scheduled leaderboard refresh
```

**Key decisions:**
- **One Python package, one CLI.** `pae run`, `pae build-site`, `pae add-task`, `pae list-agents`.
- **Results are committed JSON.** No database. Reproducibility = "this commit shows the state of the leaderboard on date X."
- **Site is built, not served.** `pae build-site` writes `site/`; user pushes to GitHub Pages / S3 / `gh-pages` branch.

## Task Format

Tasks live at `tasks/<owner__repo__id>/task.json`. Format is SWE-bench-compatible in spirit so we can later import swebench's public set with a one-shot script.

```json
{
  "instance_id": "django__django-12345",
  "repo": "django/django",
  "base_commit": "abc1234...",
  "language": "python",
  "framework": "django",
  "difficulty": "medium",
  "prompt": "Title + body of the issue, verbatim or paraphrased.",
  "setup_cmd": "pip install -e . && pip install -r requirements.txt",
  "test_cmd": "python -m pytest tests/path/to/test_x.py -x",
  "fail_to_pass": ["tests.test_x.TestFoo.test_bar"],
  "pass_to_pass": ["tests.test_x.TestFoo.test_baz"]
}
```

- **`prompt` is what the agent sees.** The harness is free to support multiple prompt variants per task in the future (zero-shot, with hints, with repo context) to measure prompt sensitivity.
- **`setup_cmd` is local-only.** Ignored in Docker mode (image pre-bakes the env).
- **`fail_to_pass` / `pass_to_pass` are graded by test name, not by exit code.** More robust to flaky runners and partial fixes.
- The base repo and test patch can be stored as a git submodule, a git LFS pointer, or a one-shot clone script — implementation detail, not part of the spec.

## Agent Interface

Defined as a `Protocol` in `pae/agents/base.py` so each adapter is free to handle its CLI's quirks without forcing a shared implementation.

```python
class AgentAdapter(Protocol):
    name: str                                  # "claude-code", "codex", "aider"
    default_model: str | None                  # e.g. "claude-opus-4-7" or None

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        """Returns the argv to run."""

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        """Normalize each CLI's quirks into a single AgentResult."""
```

`AgentResult`:
```python
@dataclass
class AgentResult:
    patch: str             # git diff captured by harness (uniform across agents)
    log: str               # raw stdout+stderr for debugging
    usage: UsageInfo       # best-effort: tokens_in, tokens_out, cost_usd, model_used
    exit_code: int
    duration_sec: float
```

The harness captures the patch uniformly via `git diff` on the workdir — we do not trust any agent's own diff output. The adapter's only job for patches is to set the working directory and let the agent run.

## Run Lifecycle

```
pae run --agent claude --task django-12345 [--docker] [--timeout 30m]
   │
   ├─ 1. Resolve task → load tasks/django__django-12345/task.json
   ├─ 2. Create workdir (temp dir; /tmp/pae-XXXX or ~/.cache/pae/work)
   ├─ 3. Fetch repo
   │     ├─ Local:  git clone <repo> workdir && git checkout <base_commit>
   │     └─ Docker: docker exec into container, same commands
   ├─ 4. Setup
   │     ├─ Local:  run setup_cmd in workdir
   │     └─ Docker: docker exec setup_cmd
   ├─ 5. Pre-flight: run test_cmd, snapshot pass/fail per test name
   │     └─ Validate: fail_to_pass tests currently fail, pass_to_pass currently pass
   │        (If a task fails this check, mark as task_error, do not run agent)
   ├─ 6. Run agent
   │     ├─ Local:  subprocess(agent.build_command(workdir, prompt))
   │     └─ Docker: docker exec subprocess(...)  (or docker run with bind-mount)
   ├─ 7. Capture patch
   │     └─ git diff workdir → patch (uniform, regardless of agent's claims)
   ├─ 8. Grade
   │     └─ Re-run test_cmd, parse per-test results
   ├─ 9. Write results/<timestamp>__<agent>__<task_id>.json
   └─ 10. Cleanup workdir (or keep if --keep-workdir, for debugging)
```

## Grading

A task is `resolved` iff **all** of:
- Every test in `fail_to_pass` now passes (was failing → now passing)
- Every test in `pass_to_pass` still passes (no regressions)

A task is `failed` if either condition fails. No partial credit at the task level; per-test results are logged so partial credit is recoverable later.

### Status enum

`resolved` | `failed` | `agent_error` (CLI missing, crashed) | `timeout` | `task_error` (broken pre-flight) | `grader_error` (test runner misconfigured)

Broken tasks and agent crashes must not silently count as "failed" alongside legitimate attempts. Each status is reported separately on the site.

## Docker Mode

- The harness `docker run`s a task-specified base image (e.g. `python:3.11-slim`, `node:20`) with a bind-mounted workdir, then `docker exec`s the remaining steps. One image can serve many tasks.
- API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are passed via `--env-file` or `-e`. The user controls the file; it is never committed.
- `--docker` is the only flag that flips the mode; commands and results schema are otherwise identical.
- Pre-flight, agent run, and grading all happen inside the container via `docker exec`.

## Resilience

- **Timeout**: default 30 min per agent run, configurable. Killed cleanly; patch captured up to kill point.
- **Workdir cleanup**: default delete after run. `--keep-workdir` prints the path in the result JSON for debugging.
- **Resume**: if `results/<run>.json` already exists, skip with a warning. `--force` to overwrite. Interrupted batches are restartable.
- **Concurrency**: v1 is single-threaded. A `--parallel N` flag can come later.

## Output JSON

```json
{
  "run_id": "2026-06-06T12-34-56__claude__django-12345",
  "task_id": "django__django-12345",
  "agent": "claude-code",
  "agent_version": "1.0.42",
  "model": "claude-opus-4-7",
  "mode": "local",
  "status": "resolved",
  "started_at": "2026-06-06T12:34:56Z",
  "duration_sec": 412.7,
  "usage": { "tokens_in": 12345, "tokens_out": 6789, "cost_usd": 0.42, "model": "claude-opus-4-7" },
  "test_results": {
    "fail_to_pass": {"tests.test_x.TestFoo.test_bar": "passed"},
    "pass_to_pass": {"tests.test_x.TestFoo.test_baz": "passed"}
  },
  "patch": "diff --git a/...",
  "workdir": "/tmp/pae-XXXX"
}
```

## Metrics & Static Site

`pae build-site` reads every `results/*.json` and produces:

- **`data/results.json`** — one row per (agent, model, agent_version) tuple with: `pass_rate`, `n_resolved`, `n_attempted`, median `cost_usd`, median `duration_sec`, median `tokens_in` / `tokens_out`, and `last_run` timestamp.
- **`data/details/<task_id>__<agent>.json`** — per-run detail for the per-task pages.

**`n_attempted` is always shown alongside `pass_rate`** so a row with 5/5 does not look better than a row with 32/50.

### Site pages

- **`index.html`** — sortable leaderboard. Columns: Agent, Model, Pass rate, # tasks, Median cost, Median time, Median tokens, Last run. Click headers to sort.
- **`tasks/<id>.html`** — per-task detail. The issue prompt at the top, then one collapsible section per agent showing: status badge, syntax-highlighted patch, per-test results (which `fail_to_pass` now pass, which `pass_to_pass` regressed), time, cost.
- **Footer** — generation timestamp + git SHA of the harness that built the site.

### Tech

Plain HTML + ~50 lines of vanilla JS for sorting. No React, no bundler, no build step beyond `pae build-site`. CSS is hand-rolled, ~100 lines, dark-mode via `prefers-color-scheme`. Diff highlighting uses [highlight.js](https://highlightjs.org/) (single ~50KB file, no JS framework) loaded from a local copy in `site/vendor/`. Total `site/` weight: a few hundred KB even with hundreds of tasks.

### Hosting

User pushes `site/` to `gh-pages` branch, or `pae build-site --publish` shells out to the `gh` CLI. We do not bundle our own deployer.

## Reproducibility

Every result JSON captures everything needed to reproduce a single number:
- `agent`, `agent_version`, `model`
- `mode` (local vs docker) + the docker image digest if docker
- `started_at`, harness `git_sha` (added by harness at write time)
- Full `patch` and `test_results`

The site footer links to `reproducibility.md`: "to reproduce row X, run `pae run --agent X --task <list> --docker` with this harness SHA." No magic, no hidden state.

## Testing Strategy

The harness itself must be tested, not just trusted. Three layers:

1. **Unit tests** for pure logic (grading rules, status enum, JSON aggregation). These run without Docker, network, or API keys.
2. **Integration tests** for the run loop, using a **mock agent** that just writes a known patch to the workdir. This exercises the full local flow (clone, setup, agent, grade) end-to-end against a tiny fixture task (single Python file, single test). Integration tests use a small local fixture repo committed to the repo, not network.
3. **Live smoke test** (manual, not in CI): one real task, one real agent, on a developer machine. Catches environment issues that mocks can't. Documented in `docs/smoke-test.md`.

A test task fixture is checked in at `pae/tests/fixtures/tiny_task/` (under the package, not at the project root, to avoid confusion with the user-facing `tasks/` directory) with a known-bug-and-known-fix so the integration test has a deterministic expected outcome.

## Open Questions (Resolved During Brainstorming)

- **Q: Server or no server?** A: Static site, no server. Results in JSON, site generated and pushed.
- **Q: Which agents v1?** A: Claude Code, Codex, Aider (CLI-only, Protocol-based).
- **Q: Real tasks or synthetic?** A: Real (SWE-bench style).
- **Q: What metrics?** A: Pass rate, cost, time, tokens.
- **Q: Local or Docker first?** A: Local default, Docker opt-in.
