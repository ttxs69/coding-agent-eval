# coding-agent-eval

Public, reproducible benchmark for CLI coding agents. Compare Claude Code, Codex, Aider, and more on the same set of real-world tasks.

**Live leaderboard:** [ttxs69.github.io/coding-agent-eval](https://ttxs69.github.io/coding-agent-eval/)

> **Cost warning:** running an eval calls paid LLM APIs. A full eval (20 tasks × 3 agents) can easily cost $50–$100+ in API fees, depending on model and task length. **Start small** with `sh scripts/run_eval.sh 1` (one task, all agents = 2–3 runs ≈ $1–$3) to confirm everything works before scaling up. Use a cheap model first if your agent supports `--model` (e.g. `cae run --model claude-haiku-4-5`); the leaderboard's pass rate is the same but tokens cost a fraction.

## What is `cae`?

`cae` is the CLI for the benchmark. It has six subcommands:

| Command | What it does |
|---|---|
| `cae list-agents` | Show registered agent adapters and whether each is installed. |
| `cae list-tasks` | Show every task under `tasks/`, with status counts from `results/`. |
| `cae run` | Run one (task, agent) pair through the harness end-to-end. |
| `cae add-task` | Import a task from SWE-bench (or write one by hand). |
| `cae report` | Aggregate `results/*.json` into a console table. |
| `cae build-site` | Render the static leaderboard site from `results/`. |

`cae run` is the workhorse. It takes `--agent <name>` (a registered adapter) and a task, then runs the full lifecycle: prep workdir, apply test patch, run setup, pre-flight, run the agent, capture the patch, grade, write the result. Adding a new agent is a single file under `cae/agents/` that implements the `AgentAdapter` protocol — see `docs/adding-agents.md` for the full reference, and `cae/agents/claude_code.py` as a template.

The `scripts/run_eval.sh` wrapper just loops `cae run` over a list of tasks and agents so you don't have to type the loop by hand.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/).

```
uv sync --extra dev --extra astropy-build
uv run cae --help
```

Python 3.10 is pinned in `pyproject.toml` because some SWE-bench tasks (notably older astropy) have C extension code that won't build on 3.11+. uv will install 3.10 automatically.

## Add tasks

From SWE-bench Verified:

```
uv run cae add-task --from-swebench --limit 50
```

The split defaults to `test` (the only split in the dataset). To pull specific instances:

```
uv run cae add-task --from-swebench --instance-id django__django-12345
```

Tasks with malformed test IDs (a known SWE-bench data quality issue) are skipped automatically with a warning.

## Run a task

```
uv run cae list-agents
uv run cae run --agent mock --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/cae
```

The result is written to `/tmp/cae/<run_id>.json`. The harness skips any (task, agent) pair that already has a result — re-run the same command to resume after an interruption. Use `--force` to overwrite.

Useful flags on `cae run`:

- `--model <name>` — pin a specific model (overrides the agent's config). Pass e.g. `claude-sonnet-4-6` or `gpt-5`.
- `--max-cost-usd <float>` — abort the `--repeat` loop when cumulative cost reaches this value. Subscription-billed runs (cost_usd=None) count as $0. Pair with `--repeat` to cap a long-running eval.

## Run a full eval

```
sh scripts/run_eval.sh                              # all tasks, auto-detect agents
sh scripts/run_eval.sh 1                            # 1 task, auto-detect
sh scripts/run_eval.sh 4                            # first 4 tasks, auto-detect
sh scripts/run_eval.sh 1 claude-code                # 1 task, specific agent
sh scripts/run_eval.sh 4 claude-code,codex          # 4 tasks, comma-separated list
sh scripts/run_eval.sh --small                      # alias for 4
sh scripts/run_eval.sh --help                       # show usage
```

The script picks tasks alphabetically and auto-detects agents via `cae list-agents` (excluding the `mock` test adapter). Override with a comma-separated agent list. Each (task, agent) pair is one `cae run` invocation; results land in `results/eval.log` and per-run JSONs land in `results/`.

## Build the leaderboard site

```
uv run cae build-site --results-dir results --out-dir site
```

Deploy `site/` to GitHub Pages (or run `uv run cae build-site --publish` to push via the `gh` CLI). The published leaderboard lives at [ttxs69.github.io/coding-agent-eval](https://ttxs69.github.io/coding-agent-eval/).

## Development

```
uv run pytest -v
uv run ruff check cae tests
```

CI runs the same on every push/PR via `.github/workflows/test.yml`.

## How it works

- Tasks live under `tasks/<instance_id>/{task.json, repo/, tests.patch}`.
- The harness runs the agent in a workdir, captures `git diff` as the patch, then grades by re-running the test_cmd.
- Tokens and cost come from each agent's own output (no token math in the harness). Prompt-cache tokens are tracked separately so the leaderboard can show cache hit rate.
- The leaderboard aggregates `results/*.json` and filters out harness-level failures (task_error, grader_error) from the pass rate.

## Status

Pre-v1.
