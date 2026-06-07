# Coding Agent Eval — Design

**Date:** 2026-06-06
**Status:** Approved
**Last reviewed:** 2026-06-07

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
│   ├── cli.py                 # entry point: pae run / build-site / add-task / list-agents / report
│   ├── harness.py             # run loop: fetch repo, apply test patch, run agent, capture patch, grade
│   ├── grader.py              # run test_cmd in workdir, parse per-test results into {test_name: status}
│   ├── importer.py            # pae add-task --from-swebench: pull, transform, write task
│   ├── metrics.py             # aggregation over results/*.json (used by build-site and report)
│   ├── site.py                # build static leaderboard from results/
│   └── agents/                # one file per agent
│       ├── base.py            # AgentAdapter protocol
│       ├── claude_code.py
│       ├── codex.py
│       ├── aider.py
│       └── mock.py            # first-class test adapter; excluded from public leaderboard
├── tasks/                     # SWE-bench-style task definitions
│   └── <owner__repo__id>/
│       ├── task.json          # metadata, base_commit, setup_cmd, etc.
│       ├── repo/              # the repo at base_commit (copied into workdir by default; --fetch-fresh clones from GitHub)
│       └── tests.patch        # hidden test patch (git-applied before pre-flight; no-op for hand-authored tasks)
├── results/                   # JSON output of runs (committed)
│   └── 2026-06-06T12-34-56__claude__django-12345.json
├── site/                      # generated static leaderboard
│   ├── index.html             # sortable table of agent × task
│   ├── tasks/<id>.html        # per-task detail
│   ├── reproducibility.html   # copied from docs/reproducibility.md
│   └── data/results.json      # aggregate for the table
├── docs/                      # how to add tasks, run evals, etc.
│   └── reproducibility.md     # source for site/reproducibility.html
└── .github/workflows/         # optional: scheduled leaderboard refresh
```

**Key decisions:**
- **One Python package, one CLI.** `pae run`, `pae build-site`, `pae add-task`, `pae list-agents`, `pae report`.
- **Results are committed JSON.** No database. Reproducibility = "this commit shows the state of the leaderboard on date X."
- **Site is built, not served.** `pae build-site` writes `site/`; user pushes to GitHub Pages / S3 / `gh-pages` branch.

## Task Format

Tasks live at `tasks/<owner__repo__id>/task.json`. Format is SWE-bench-compatible; the first 50 tasks are imported from SWE-bench Verified via `pae add-task --from-swebench` (see the [Importing Tasks from SWE-bench](#importing-tasks-from-swe-bench) section).

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
- **`setup_cmd` runs in both modes**: locally in the workdir, or via `docker exec` in Docker mode. The Docker image provides a baseline environment; `setup_cmd` typically installs language-specific deps (e.g. `pip install -e .`) on top of it.
- **`fail_to_pass` / `pass_to_pass` are graded by test name, not by exit code.** More robust to flaky runners and partial fixes.
- The base repo can be stored as a checked-in directory under `repo/` (the importer default), a git submodule, or a git LFS pointer — implementation detail.

## Importing Tasks from SWE-bench

Tasks are not hand-authored in v1 — the first **50 tasks** come from a one-shot import of [SWE-bench Verified](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified), the 500-problem human-validated subset curated with OpenAI. The importer is a core `pae add-task` mode, not a side script:

```bash
# Import a single instance
pae add-task --from-swebench django__django-12345

# Import a named subset
pae add-task --from-swebench --split verified --limit 50

# Import from a local SWE-bench checkout
pae add-task --from-swebench --dataset-path /path/to/SWE-bench --split verified
```

**What the importer does:**
1. Pulls the instance metadata (`repo`, `base_commit`, `prompt`, `FAIL_TO_PASS`, `PASS_TO_PASS`) from the SWE-bench dataset (HuggingFace `datasets` library or a local clone).
2. Renames fields to our schema (`FAIL_TO_PASS` → `fail_to_pass`, etc.).
3. Writes `task.json` to `tasks/<instance_id>/task.json`.
4. Records the base commit's repo state by shallow-cloning the repo at `base_commit` into `tasks/<id>/repo/`. (Git submodules are NOT used in v1 — the importer always produces a plain directory so the harness's step 3 `cp` works without submodule awareness.)
5. Records the test patch into `tasks/<id>/tests.patch` for reference and grading.
6. Sets a `source: {kind: "swe-bench", split: "verified", original_id: "..."}` field in `task.json` for provenance.

**Why v1, not v2:** a public leaderboard with zero real tasks is not credible. SWE-bench Verified is the de facto industry baseline (it's what OpenAI, Anthropic, etc. quote numbers from), and importing it for free gives us a comparable dataset on day one. Hand-authored tasks can be added later as supplementary signal.

**Upstream drift:** SWE-bench is stable but not frozen. The importer records the SWE-bench commit hash it imported from in the result metadata, so a result from "SWE-bench @ abc1234" can be re-run for reproducibility.

## Agent Interface

Defined as a `Protocol` in `pae/agents/base.py` so each adapter is free to handle its CLI's quirks without forcing a shared implementation.

```python
class AgentAdapter(Protocol):
    name: str                                  # "claude-code", "codex", "aider"
    default_model: str | None                  # e.g. "claude-opus-4-7" or None

    def is_available(self) -> bool:
        """Returns True if the underlying CLI is installed and runnable."""

    def version(self) -> str:
        """Returns the installed CLI's version string (e.g. from `claude --version`).
        Captured once per run, written to the result JSON as `agent_version`."""

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
    usage: UsageInfo       # best-effort: tokens_in, tokens_out, cost_usd, model
    exit_code: int
    duration_sec: float
```

The harness captures the patch uniformly via `git diff` on the workdir — we do not trust any agent's own diff output. The adapter's only job for patches is to set the working directory and let the agent run.

`pae list-agents` calls `is_available()` on every registered adapter and prints a table of which ones are usable in the current environment. Pre-run, the harness re-checks `is_available()` for each requested agent and fails fast with a clear error if any are missing — no mid-run "command not found" surprises.

A `MockAdapter` ships as a first-class adapter (registered alongside Claude Code / Codex / Aider) for use in tests and smoke runs. It writes a pre-canned patch from the test fixture to the workdir, so the full harness can be exercised without API keys. It is clearly marked as a test-only adapter in `pae list-agents`.

**`MockAdapter` results are excluded from the public leaderboard.** `pae build-site` filters out any result whose `agent` field is `mock`. (Test runs still produce result JSON for local development; only the aggregation step filters them out.)

## Run Lifecycle

```
pae run --agent claude --task django-12345 [--docker] [--timeout 30m] [--repeat N]
   │
   ├─ 1. Resolve task → load tasks/django__django-12345/task.json
   ├─ 2. Create workdir (temp dir; /tmp/pae-XXXX or ~/.cache/pae/work)
   ├─ 3. Fetch repo into workdir
   │     ├─ Local:  copy tasks/<id>/repo/ → workdir (offline, deterministic, default)
   │     │          --fetch-fresh: git clone <repo> workdir && git checkout <base_commit> (network, up-to-date)
   │     └─ Docker: docker exec copy (or clone) into the container's workdir
   ├─ 4. Apply test patch (if `tasks/<id>/tests.patch` exists)
   │     └─ git apply tasks/<id>/tests.patch in workdir
   │        (No-op for hand-authored tasks where test cases are already in the repo.)
   ├─ 5. Setup
   │     ├─ Local:  run setup_cmd in workdir
   │     └─ Docker: docker exec setup_cmd
   ├─ 6. Pre-flight: run test_cmd, snapshot pass/fail per test name
   │     └─ Validate: fail_to_pass tests currently fail, pass_to_pass currently pass
   │        (If a task fails this check, mark as task_error, do not run agent)
   ├─ 7. Run agent
   │     ├─ Local:  subprocess(agent.build_command(workdir, prompt))
   │     └─ Docker: docker exec subprocess(...)  (or docker run with bind-mount)
   ├─ 8. Capture patch
   │     └─ git diff workdir → patch (uniform, regardless of agent's claims)
   ├─ 9. Grade
   │     └─ Re-run test_cmd, parse per-test results
   ├─ 10. Write results/<timestamp>__<agent>__<task_id>[__<repeat-index>].json
   │      (Repeat-index is omitted when --repeat is 1.)
   └─ 11. Cleanup workdir (or keep if --keep-workdir, for debugging)
```

## Grading

A task is `resolved` iff **all** of:
- Every test in `fail_to_pass` now passes (was failing → now passing)
- Every test in `pass_to_pass` still passes (no regressions)

A task is `failed` if either condition fails. No partial credit at the task level; per-test results are logged so partial credit is recoverable later.

**Per-test result statuses** (used in the `test_results` JSON map):
- `passed` — test ran and asserted success
- `failed` — test ran and asserted failure (counts against the task)
- `error` — test could not run (collection error, missing import, etc.); distinct from `failed` so we can tell "the agent's code is broken" from "the grader's harness is broken"
- `skipped` — test was intentionally skipped (e.g. via `pytest.skip`); not counted as pass or fail
- `xfail` — expected failure; not counted as pass or fail

Only `passed` and `failed` are grading-relevant. A test in `fail_to_pass` must end as `passed` for the task to resolve; any other status (`failed`, `error`, `skipped`, `xfail`) means the task is `failed`. Similarly, a test in `pass_to_pass` must end as `passed`; any other status is a regression. The other statuses are recorded for diagnostics so we can distinguish "agent's code is broken" (`failed`) from "grader is broken" (`error`) from "test was skipped" (`skipped`/`xfail`).

**Test-name parsing** is per-runner. The grader ships one parser per supported test runner (pytest, unittest, cargo test, npm test, go test). Each parser maps the runner's native output to `{test_name: status}`. New runners = new parser file, no core changes.

### Status enum

`resolved` | `failed` | `agent_error` (CLI missing, crashed) | `timeout` | `task_error` (broken pre-flight) | `grader_error` (test runner failed to start, or its output could not be parsed for per-test results; per-test `error` statuses during a successful run are recorded but don't trigger this)

Broken tasks and agent crashes must not silently count as "failed" alongside legitimate attempts. Each status is reported separately on the site.

## Docker Mode

- The harness `docker run`s a task-specified base image (e.g. `python:3.11-slim`, `node:20`) with a bind-mounted workdir, then `docker exec`s the remaining steps. One image can serve many tasks.
- API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are passed via `--env-file` or `-e`. The user controls the file; it is never committed.
- `--docker` is the only flag that flips the mode; commands and results schema are otherwise identical.
- Pre-flight, agent run, and grading all happen inside the container via `docker exec`.

## Resilience

- **Timeout**: default 30 min per agent run, configurable. Killed cleanly; patch captured up to kill point.
- **Workdir cleanup**: default delete after run. `--keep-workdir` prints the path in the result JSON for debugging.
- **Resume**: if any result file for the requested (task, agent) pair already exists in `results/`, skip with a warning. `--force` to overwrite. With `--repeat N`, runs whose index already has a result file are skipped; missing indices are run. Interrupted batches are restartable by re-running the same `pae run` command.
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
  "harness_git_sha": "da1b1d0",
  "task_source": {"kind": "swe-bench", "split": "verified", "original_id": "django__django-12345", "swe_bench_commit": "abc1234"},
  "usage": { "tokens_in": 12345, "tokens_out": 6789, "cost_usd": 0.42, "billing_mode": "api" },
  "test_results": {
    "pre_flight": {
      "fail_to_pass": {"tests.test_x.TestFoo.test_bar": "failed"},
      "pass_to_pass": {"tests.test_x.TestFoo.test_baz": "passed"}
    },
    "post_flight": {
      "fail_to_pass": {"tests.test_x.TestFoo.test_bar": "passed"},
      "pass_to_pass": {"tests.test_x.TestFoo.test_baz": "passed"}
    }
  },
  "patch": "diff --git a/...",
  "workdir": "/tmp/pae-XXXX"
}
```

**Field capture notes:**
- `agent_version` — captured by the adapter from the installed CLI's own version output (e.g. `claude --version`) at run start. The exact mechanism is adapter-defined; the contract is "the version string of the agent CLI that produced this patch."
- `started_at` — UTC ISO 8601 with `Z` suffix.
- `run_id` — filesystem-safe variant of `started_at`: same instant, colons replaced with dashes, slashes removed. Filename-safe.
- `mode` — `"local"` (default) or `"docker"`. `--docker` flag flips it.
- `model` is recorded once at the top level; the `usage` block deliberately omits it to avoid duplication.

## Metrics & Static Site

`pae build-site` reads every `results/*.json` and produces:

- **`data/results.json`** — one row per (agent, model, agent_version) tuple with: `pass_rate`, `n_resolved`, `n_attempted`, median `cost_usd`, median `duration_sec`, median `tokens_in` / `tokens_out`, and `last_run` timestamp.
- **`data/details/<task_id>__<agent>.json`** — per-run detail for the per-task pages.

**Median unit:** each row's medians are computed over **all individual runs** in `results/` for that (agent, model, agent_version) tuple. If a user runs `--repeat 3` on a task, all three runs are data points (this is intentional — it lets users opt into variance measurement). Median over a small `n` is reported as-is; no bootstrap or confidence interval in v1.

**`n_attempted` is the count of unique tasks** in `results/` for that row, not the count of runs. This makes `5/5` comparable to `32/50`: a row with `--repeat 3` on 10 tasks shows `n_attempted: 10`, not `30`. The run count is implicit in the medians.

**Cost tracking and subscription billing.** `cost_usd` is best-effort. For per-token API billing the adapter populates it from the agent's own accounting. For subscription-billed usage (Claude Max, ChatGPT Pro, etc.) the cost is unknown and `cost_usd` is `null`; a `billing_mode` field is recorded in the result JSON with value `api` or `subscription`. The site shows `cost_usd` as `$?` for subscription rows so users know it's a known unknown, not missing data.

**`n_attempted` is always shown alongside `pass_rate`** so a row with 5/5 does not look better than a row with 32/50.

### Site pages

- **`index.html`** — sortable leaderboard. Columns: Agent, Model, Pass rate, # tasks, Median cost, Median time, Median tokens, Last run. Click headers to sort.
- **`tasks/<id>.html`** — per-task detail. The issue prompt at the top, then one collapsible section per agent showing: status badge, syntax-highlighted patch, per-test results (which `fail_to_pass` now pass, which `pass_to_pass` are no longer passing — including `failed`, `error`, `skipped`, `xfail`), time, cost.
- **Footer** — generation timestamp + git SHA of the harness that built the site.

### Tech

Plain HTML + ~50 lines of vanilla JS for sorting. No React, no bundler, no build step beyond `pae build-site`. CSS is hand-rolled, ~100 lines, dark-mode via `prefers-color-scheme`. Diff highlighting uses [highlight.js](https://highlightjs.org/) (single ~50KB file, no JS framework) loaded from a local copy in `site/vendor/`. Total `site/` weight: a few hundred KB even with hundreds of tasks.

### Hosting

User pushes `site/` to `gh-pages` branch, or `pae build-site --publish` shells out to the `gh` CLI. We do not bundle our own deployer.

### Console reporting (local dev)

The static site is the canonical published view, but for local development `pae report --format table` prints a console table of aggregated metrics for all `results/*.json` files in the current directory, sorted by `pass_rate` descending by default, reusing the same aggregation logic as `pae build-site`. This is the same data the site shows, just printed to stdout — no separate code path. Useful when iterating on a task or comparing two agents in the terminal without leaving to look at a browser.

## Reproducibility

Every result JSON captures everything needed to reproduce a single number:
- `agent`, `agent_version`, `model`
- `mode` (local vs docker) + the docker image digest if docker
- `started_at`, harness `git_sha` (added by harness at write time)
- Full `patch` and `test_results`

The site footer links to `reproducibility.html`. The source `docs/reproducibility.md` is hand-written at the project root and copied (markdown → HTML, rendered with a small inline renderer — no external dependency) to `site/reproducibility.html` by `pae build-site`. No magic, no hidden state. The doc content: "to reproduce row X, run `pae run --agent X --task <list> --docker` with this harness SHA."

## Testing Strategy

The harness itself must be tested, not just trusted. Three layers:

1. **Unit tests** for pure logic (grading rules, status enum, JSON aggregation, per-runner parsers). These run without Docker, network, or API keys.
2. **Integration tests** for the run loop, using the `MockAdapter` (which writes a pre-canned patch to the workdir) end-to-end against a tiny fixture task. This exercises the full local flow (clone, apply test patch, setup, pre-flight, agent, grade, write result) with a known-bug-and-known-fix task. Integration tests use a small local fixture repo committed to the repo, not network.
3. **Live smoke test** (manual, not in CI): one real task, one real agent, on a developer machine. Catches environment issues that mocks can't. Documented in `docs/smoke-test.md`.

A test task fixture is checked in at `pae/tests/fixtures/tiny_task/` (under the package, not at the project root, to avoid confusion with the user-facing `tasks/` directory) with a known-bug-and-known-fix so the integration test has a deterministic expected outcome.

## Open Questions (Resolved During Brainstorming)

- **Q: Server or no server?** A: Static site, no server. Results in JSON, site generated and pushed.
- **Q: Which agents v1?** A: Claude Code, Codex, Aider (CLI-only, Protocol-based). `MockAdapter` ships as a first-class test adapter.
- **Q: Real tasks or synthetic?** A: Real (SWE-bench style). First 50 tasks imported from SWE-bench Verified.
- **Q: What metrics?** A: Pass rate, cost, time, tokens. Subscription-billed runs show `null` cost.
- **Q: Local or Docker first?** A: Local default, Docker opt-in.
- **Q: Hand-author tasks or import?** A: Import SWE-bench Verified for v1; hand-authored tasks can supplement later.
- **Q: Concurrency in v1?** A: Single-threaded. `--parallel N` deferred.
- **Q: Public reporting?** A: Static site is canonical; `pae report --format table` is the local-dev view.
