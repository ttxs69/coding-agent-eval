# Reproducibility

Every leaderboard row can be reproduced from a single command.

## What's in a result

Each `results/<run_id>.json` captures:

- `agent`, `agent_version`, `model` — what was run
- `mode` — `local` or `docker`
- `started_at`, `harness_git_sha` — when and with which code
- `task_source` — the SWE-bench split and upstream commit
- `patch`, `test_results` — what the agent produced and how the tests ran

## Reproducing a row

Given a row, find the `agent` and the task list, then run:

```
cae run --agent <agent> --task <task_id> [--docker]
```

For the official leaderboard, always use `--docker` so the run is reproducible across machines. Without it, results depend on the local Python/library versions in the workdir.

## Upstream drift

If the SWE-bench dataset is updated, old results can still be re-run because `task_source.swe_bench_commit` is recorded in the result JSON. The importer writes this at import time.
