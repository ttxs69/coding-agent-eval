# probe-agent-eval

Public, reproducible benchmark for CLI coding agents. Compare Claude Code, Codex, Aider, and more on the same set of real-world tasks. See `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` for the design.

## Quickstart

```
pip install -e ".[dev]"
pae --help
```

## Run a task

```
pae list-agents
pae run --agent mock --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/pae
```

The result is written to `/tmp/pae/<run_id>.json`.

## Add tasks

From SWE-bench Verified:

```
pae add-task --from-swebench --limit 50
```

Or by hand: see `docs/adding-tasks.md`.

## Build the leaderboard site

```
pae build-site --results-dir results --out-dir site
```

Deploy `site/` to GitHub Pages (or run `pae build-site --publish` to push via the `gh` CLI).

## Development

```
pytest -v
ruff check pae tests
```

## Status

Pre-v1. See `docs/superpowers/plans/2026-06-07-coding-agent-eval.md` for the implementation plan.
