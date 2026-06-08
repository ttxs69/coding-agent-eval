# coding-agent-eval

Public, reproducible benchmark for CLI coding agents. Compare Claude Code, Codex, Aider, and more on the same set of real-world tasks.

**Live leaderboard:** [ttxs69.github.io/coding-agent-eval](https://ttxs69.github.io/coding-agent-eval/)

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

## Run a full eval

```
sh scripts/run_eval.sh           # all tasks in tasks/
sh scripts/run_eval.sh 1         # first task only (cheap e2e test)
sh scripts/run_eval.sh 4         # first 4 tasks
sh scripts/run_eval.sh --small   # alias for 4
sh scripts/run_eval.sh --help    # show usage
```

Tasks are picked in alphabetical order. The script runs every selected task × {claude-code, codex}, logs to `results/eval.log`, and prints an aggregated report at the end.

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

## How it works

- Tasks live under `tasks/<instance_id>/{task.json, repo/, tests.patch}`.
- The harness runs the agent in a workdir, captures `git diff` as the patch, then grades by re-running the test_cmd.
- Tokens and cost come from each agent's own output (no token math in the harness).
- The leaderboard aggregates `results/*.json` and filters out harness-level failures (task_error, grader_error) from the pass rate.

## Status

Pre-v1.
