"""Aggregate result JSONs into leaderboard rows.

Used by both `cae build-site` (writes data/results.json) and `cae report`
(prints a console table). The mock adapter is filtered out, and statuses
that mean "the agent never really attempted the task" (task_error,
grader_error, dry_run) are excluded from `n_attempted` and `pass_rate`
so they don't drag down an otherwise-healthy agent. `dry_run` is the
"never even tried" case (the user passed --dry-run) and lands in
`n_skipped_harness` alongside task_error / grader_error.
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


def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a binomial proportion.

    For small N (which is the leaderboard's normal case — single-digit
    task counts) the naive ``p ± z·sqrt(p(1-p)/n)`` can produce intervals
    outside [0, 1] or even the upper bound below the observed proportion.
    Wilson's score interval avoids both pathologies and is the standard
    "show me the uncertainty" answer for tiny samples.

    Returns ``(low, high)``. When ``n == 0`` returns ``(0.0, 0.0)`` so the
    leaderboard renderer doesn't crash on a brand-new agent with no
    attempts yet — the caller can detect this via ``n_attempted == 0``.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * (z * z / (4 * n * n) + p * (1 - p) / n) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


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
        # With --repeat N, a task produces N result files. Count UNIQUE
        # task_ids so pass_rate stays in [0,1] (pass@k semantics: a task
        # counts as resolved if ANY repeat resolved). Without this,
        # 3 repeats × 1 resolved = pass_rate 3.0.
        attempted_task_ids = {r["task_id"] for r in attempted}
        resolved_task_ids = {r["task_id"] for r in attempted if r["status"] == "resolved"}
        n_resolved = len(resolved_task_ids)
        n_attempted = len(attempted_task_ids)
        # Track how many runs were skipped due to harness errors (so
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
            # Wilson 95% CI for the pass rate. Tells the reader the
            # "67%" row is actually "67% ± 20%" — important for tiny
            # samples (the leaderboard's normal case).
            "pass_rate_ci_low":  _wilson_ci(n_resolved, n_attempted)[0],
            "pass_rate_ci_high": _wilson_ci(n_resolved, n_attempted)[1],
            "median_cost_usd": _median([(r.get("usage") or {}).get("cost_usd") for r in attempted]),
            "median_duration_sec": _median([r.get("duration_sec") for r in attempted]),
            "median_tokens_in": _median([(r.get("usage") or {}).get("tokens_in") for r in attempted]),
            "median_tokens_out": _median([(r.get("usage") or {}).get("tokens_out") for r in attempted]),
            "median_cache_read_tokens": _median([(r.get("usage") or {}).get("cache_read_tokens") for r in attempted]),
            "median_cache_creation_tokens": _median([(r.get("usage") or {}).get("cache_creation_tokens") for r in attempted]),
            "last_run": max(r.get("started_at", "") for r in results),
        })
    rows.sort(key=lambda r: r["pass_rate"], reverse=True)
    return rows
