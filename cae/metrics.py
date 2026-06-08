"""Aggregate result JSONs into leaderboard rows.

Used by both `cae build-site` (writes data/results.json) and `cae report`
(prints a console table). The mock adapter is filtered out, and statuses
that mean "the agent never really attempted the task" (task_error,
grader_error) are excluded from `n_attempted` and `pass_rate` so they
don't drag down an otherwise-healthy agent.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

# Statuses that count as "the agent actually tried the task". Resolved
# and failed are the two grading outcomes; timeout and agent_error mean
# the harness ran the agent but it didn't produce a usable result.
# task_error / grader_error mean the harness couldn't even grade.
ATTEMPTED_STATUSES = {"resolved", "failed", "timeout", "agent_error"}


def _median(values: list[float | None]) -> float | None:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return statistics.median(non_null)


def aggregate_results(results_dir: Path) -> list[dict]:
    """Read all *.json in results_dir and return one row per (agent, model, agent_version)."""
    files = sorted(results_dir.glob("*.json"))
    by_key: dict[tuple[str, str | None, str | None], list[dict]] = defaultdict(list)
    for f in files:
        data = json.loads(f.read_text())
        if data.get("agent") == "mock":  # exclude test adapter
            continue
        key = (data["agent"], data.get("model"), data.get("agent_version"))
        by_key[key].append(data)

    rows: list[dict] = []
    for (agent, model, version), results in by_key.items():
        # Only count tasks where the agent actually tried (i.e. pre-flight
        # passed and the agent ran). task_error / grader_error mean the
        # task itself is ungradeable and shouldn't penalise the agent.
        attempted = [r for r in results if r.get("status") in ATTEMPTED_STATUSES]
        n_resolved = sum(1 for r in attempted if r["status"] == "resolved")
        n_attempted = len({r["task_id"] for r in attempted})
        # Track how many tasks were skipped due to harness errors (so
        # the user can see "X attempted of Y total" in the table).
        n_skipped = len(results) - len(attempted)
        rows.append({
            "agent": agent,
            "model": model,
            "agent_version": version,
            "n_resolved": n_resolved,
            "n_attempted": n_attempted,
            "n_skipped_harness": n_skipped,
            "pass_rate": n_resolved / n_attempted if n_attempted else 0.0,
            "median_cost_usd": _median([(r.get("usage") or {}).get("cost_usd") for r in attempted]),
            "median_duration_sec": _median([r.get("duration_sec") for r in attempted]),
            "median_tokens_in": _median([(r.get("usage") or {}).get("tokens_in") for r in attempted]),
            "median_tokens_out": _median([(r.get("usage") or {}).get("tokens_out") for r in attempted]),
            "last_run": max(r.get("started_at", "") for r in results),
        })
    rows.sort(key=lambda r: r["pass_rate"], reverse=True)
    return rows
