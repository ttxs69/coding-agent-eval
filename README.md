# coding-agent-eval

Public, reproducible benchmark for CLI coding agents. Compare Claude Code, Codex, Aider, and more on the same set of real-world tasks.

## Quickstart

```
pip install -e ".[dev]"
cae --help
```

**Note:** SWE-bench tasks from older repos (e.g. astropy) may need Python 3.10 and CFLAGS set — see "Environment" below.

## Add tasks

From SWE-bench Verified:

```
cae add-task --from-swebench --limit 50
```

The split defaults to `test` (the only split in the dataset). To pull specific instances:

```
cae add-task --from-swebench --instance-id django__django-12345
```

Tasks with malformed test IDs (a known SWE-bench data quality issue) are skipped automatically with a warning.

## Run a task

```
cae list-agents
cae run --agent mock --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/cae
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
cae build-site --results-dir results --out-dir site
```

Deploy `site/` to GitHub Pages (or run `cae build-site --publish` to push via the `gh` CLI).

## Environment

Some SWE-bench tasks (notably older astropy) have C extension code incompatible with Python 3.11+ and newer Clang. If setup_cmd fails with C compiler errors:

```
uv python install 3.10
uv venv .venv --python 3.10
.venv/bin/pip install --ignore-requires-python -e ".[dev]"
export CFLAGS="-Wno-incompatible-function-pointer-types -Wno-error=incompatible-function-pointer-types -Wno-implicit-function-declaration"
```

## Development

```
pytest -v
ruff check cae tests
```

## Status

Pre-v1.
