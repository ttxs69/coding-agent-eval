# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python package (`coding-agent-eval`, CLI: `cae`) for benchmarking CLI coding agents (Claude Code, Codex, Aider) on SWE-bench Verified tasks. Goal: a public, reproducible leaderboard showing pass rate, cost, and time per agent. See `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` for the full design.

## Environment

**uv-managed.** Python is pinned to **3.10** in `pyproject.toml` (`requires-python = ">=3.10,<3.11"`) because old astropy's Cython-generated C extensions don't build on 3.11+. Two extras: `dev` (pytest, ruff) and `astropy-build` (pinned `setuptools<60`, `setuptools_scm<8`, `extension-helpers<1`, `cython<3`, `pyerfa` — needed for the SWE-bench task setups).

```sh
uv sync --extra dev --extra astropy-build        # install everything
uv run cae --help                                # run the CLI
```

The lockfile is `uv.lock` (committed).

## Commands

```sh
# Run a single test
uv run pytest tests/test_harness.py::test_run_resolves_tiny_task_with_fixing_mock -v

# Run all tests
uv run pytest -v

# Lint
uv run ruff check cae tests

# Run a quick smoke eval (1 task, all available agents = 2-3 runs ≈ $1-3)
sh scripts/run_eval.sh 1

# Run a full eval
sh scripts/run_eval.sh                            # all tasks, all agents
sh scripts/run_eval.sh 4                          # first 4 tasks
sh scripts/run_eval.sh 1 claude-code              # 1 task, 1 agent
sh scripts/run_eval.sh 4 claude-code,codex        # 4 tasks, 2 agents

# Build the leaderboard site
uv run cae build-site --results-dir results --out-dir site
uv run cae build-site --publish                  # push to gh-pages
```

**Cost warning:** running an eval calls paid LLM APIs. A full run can cost $50–$100+. Always start with `sh scripts/run_eval.sh 1` for cheap e2e validation.

## Architecture

The pipeline is **import → run → grade → aggregate → publish**. The codebase is one Python package; all components are in `cae/`.

```
cae/
├── cli.py            # argparse entry point: cae run / add-task / list-agents / report / build-site
├── harness.py        # the 11-step run lifecycle (workdir → patch → grade → write result)
├── grader.py         # pass/fail logic given pre/post test results
├── parsers.py        # pytest output → {nodeid: TestStatus}
├── metrics.py        # aggregate results/*.json into leaderboard rows
├── site.py           # build static HTML from results
├── importer.py       # SWE-bench Verified → tasks/<id>/{task.json, repo/, tests.patch}
├── docker_run.py     # optional --docker mode (Container class for stateful execs)
├── render_table.py   # console table renderer
├── render_markdown.py
└── agents/           # one file per agent, registered in agents/__init__.py
    ├── base.py       # AgentAdapter Protocol, AgentResult, UsageInfo, Status, TestStatus
    ├── claude_code.py
    ├── codex.py
    ├── aider.py
    └── mock.py       # test-only, excluded from public leaderboard
```

**The harness's run lifecycle** (`cae/harness.py::run`): resolve task → fetch repo → apply test patch → setup → pre-flight → run agent → capture `git diff` → grade → write result JSON. The 11-step sequence is documented in the design doc under "Run Lifecycle".

## Key invariants

- **Result JSON is the source of truth.** Schema lives in the design doc; the harness writes it (`_result()`), the metrics aggregator reads it. Every result has `agent`, `agent_version`, `model`, `status`, `usage`, `test_results`, `patch`, `workdir`, `error`.
- **Status enum** (`cae/agents/base.py`): `resolved` | `failed` | `agent_error` | `timeout` | `task_error` | `grader_error`. The metrics layer treats `task_error` and `grader_error` as **harness-level failures**, not agent failures — they're excluded from `n_attempted` and tracked separately as `n_skipped_harness`.
- **Pre-flight validation** runs `test_cmd` once before the agent. If `fail_to_pass` tests don't all fail and `pass_to_pass` tests don't all pass, the task is rejected as `task_error` (without running the agent). The error message lists how many tests were missing vs. failed vs. passed — helps users tell apart "task is broken" from "SWE-bench dataset is broken".
- **Resume by default.** The harness skips any (task, agent) pair whose result JSON already exists. Re-running the same command resumes; `--force` overwrites.
- **Model and version are captured early** in the harness (before the first possible error path), so every result row — even `task_error` — records the agent's identity. This keeps the leaderboard from grouping pre-flight failures as a separate "(unknown)" row.
- **Tokens are reported by the agent, not computed.** claude-code reads from the JSON envelope; codex reads from `turn.completed`. Cache tokens (`cache_read_input_tokens` etc.) are tracked separately so the leaderboard can show cache hit rate.
- **Patches come from `git diff`, not the agent's own output.** The harness is the source of truth.

## Adding a new agent

One file under `cae/agents/<name>.py` implementing the `AgentAdapter` Protocol (`cae/agents/base.py`): `name`, `default_model`, `is_available()`, `version()`, `build_command()`, `parse_output()`. Register it in `cae/agents/__init__.py`'s `ADAPTERS` dict. Use `cae/agents/claude_code.py` as the template. Tests for the parser go in `tests/test_agents.py`.

## Testing

Tests live in `tests/`. The tiny task fixture in `tests/fixtures/tiny_task/` is the canonical e2e test — it has a known bug + known fix that the `_FixingMock` adapter applies. Mock-only, no API calls. Use `uv run pytest tests/test_harness.py -v` to run the harness tests; the full suite takes ~30s.

## Sites & deployment

- `site/` is gitignored — it's a build artifact.
- The site is deployed to the `gh-pages` branch via `scripts/deploy_site.sh` (uses `git worktree` + `rsync` without `--delete` + `git push --force-with-lease`). The script is **non-destructive**: detail files on `gh-pages` that aren't in the current build (e.g. historical result details from previous evals) are preserved. To remove stale files from `gh-pages`, edit the worktree manually or run rsync with `--delete` locally — don't make destructive deploys the default.
- **Leaderboard vs detail archive:** `cae build-site --include-archive` (default off) fetches every `data/details/*.json` ever published to `origin/gh-pages` and merges it with local `results/` for the leaderboard aggregation. Local results win on duplicate `run_id` (local is newer). The flag is opt-in because it costs a `git fetch` per build; without it the leaderboard reflects only local `results/`, which means every fresh deploy can shrink the visible leaderboard as old result files are cleaned up locally. To get the full picture across deploys, pass `--include-archive` to `cae build-site` (and to `scripts/deploy_site.sh` if used).
- Live site: <https://ttxs69.github.io/coding-agent-eval/>.

## Common gotchas

- **astropy CFLAGS.** `pip install -e .[test]` inside the workdir needs `CFLAGS="-Wno-incompatible-function-pointer-types -Wno-error=incompatible-function-pointer-types -Wno-implicit-function-declaration"` on macOS with newer Clang. The pinned toolchain in the `astropy-build` extra is also required. Without both, the setup step fails with C compile errors in the wcslib wrappers.
- **astropy + Python 3.10 (collections.abc).** Old astropy uses `collections.MutableSequence` (and friends), removed in Python 3.10. `scripts/patch_astropy_collections.sh` rewrites those to `collections.abc.X` across all task repos; `scripts/run_eval.sh` runs it automatically before the eval. Idempotent — re-runs are safe.
- **astropy + numpy 2.x.** Old astropy uses `np.product` and friends, removed in numpy 2.0. The venv must have `numpy<2`. `scripts/run_eval.sh` auto-downgrades after `uv sync` (idempotent — no-op if already <2) and logs the change. Manual runs need `uv pip install 'numpy<2'`. (`astropy-build` extra intentionally doesn't pin numpy — see comment in `pyproject.toml`.)
- **Computed cost vs reported cost.** Some agent CLIs (notably codex) emit token counts in their output but no `cost_usd` field. For those, `cae/pricing.py::compute_cost` looks the model up in `cae/pricing.json` (public-list USD-per-million-token rates) and computes `cost = (tokens_in × input + tokens_out × output + cache_read × cache_read + cache_creation × cache_creation) / 1_000_000`. Models not in the table get `cost_usd: null` — we don't guess. Gateways/proxies may charge differently than public list, so treat computed numbers as estimates. To add a model: edit `cae/pricing.json`. To override at runtime without editing the file: `export CAE_PRICING_JSON=/path/to/your/pricing.json` (entries there take precedence). To backfill cost on existing `results/*.json` files after a pricing change: `uv run python scripts/reprice_results.py` (use `--dry-run` first).
- **pytest 9.x + old astropy setup.cfg.** Pytest 9 crashes inside `_do_configure` on old astropy's `setup.cfg` because `cache_dir` resolves to None. `scripts/run_eval.sh` sets `PYTEST_ADDOPTS=-p no:cacheprovider` to work around this. (Manual runs need the same env var.)
- **SWE-bench data quality.** 8/20 astropy tasks have truncated test IDs in `FAIL_TO_PASS`/`PASS_TO_PASS` (e.g. `test_x[ceci` with no closing `]`). Pre-flight catches these as `task_error`. The importer filters obviously-malformed IDs at import time; tasks with all-malformed lists are skipped via `MalformedTestIdsError`.
- **Model routing via `ANTHROPIC_BASE_URL`.** If `ANTHROPIC_BASE_URL` points to a non-Anthropic gateway (e.g. a GLM proxy that speaks the Anthropic API protocol), `cae run --agent claude-code` records `model: <gateway-routed-name>` in the result JSON — not the actual Claude model. The eval is still a valid "Claude Code (the CLI)" eval; just be aware the leaderboard row reflects the gateway's model, not Anthropic's.
- **uv venvs don't ship `pip`.** The run_eval.sh script needs `pip` on PATH for the task setups; uv venvs only have `pip3`. Workaround: `ln -sf pip3 .venv/bin/pip`. (Not needed for harness commands, only for the task setup_cmd that runs inside the workdir.)
- **Zsh glob gotcha.** When using `rm -f results/*.json` in a zsh context, use `find results -name "*.json" -delete` or `noglob rm` to avoid `no matches found` errors from `set -u` or default `nomatch`.
