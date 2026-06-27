import json
from pathlib import Path

import pytest

from cae.metrics import aggregate_results


@pytest.fixture
def two_results_dir(tmp_path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    (d / "r1.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "resolved", "duration_sec": 100, "usage": {"cost_usd": 0.1, "tokens_in": 1000, "tokens_out": 500},
        "test_results": {"pre_flight": {}, "post_flight": {}}, "task_id": "t1",
    }))
    (d / "r2.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "failed", "duration_sec": 200, "usage": {"cost_usd": 0.2, "tokens_in": 2000, "tokens_out": 800},
        "test_results": {"pre_flight": {}, "post_flight": {}}, "task_id": "t2",
    }))
    return d


def test_aggregate_pass_rate(two_results_dir):
    rows = aggregate_results(two_results_dir)
    assert len(rows) == 1
    assert rows[0]["agent"] == "claude-code"
    assert rows[0]["n_resolved"] == 1
    assert rows[0]["n_attempted"] == 2
    assert rows[0]["pass_rate"] == 0.5


def test_aggregate_median_cost(two_results_dir):
    rows = aggregate_results(two_results_dir)
    assert rows[0]["median_cost_usd"] == pytest.approx(0.15)  # median of [0.1, 0.2]


def test_aggregate_groups_by_agent_model_version(two_results_dir):
    (two_results_dir / "r3.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-sonnet-4-6",
        "status": "resolved", "duration_sec": 50, "usage": {"cost_usd": 0.05},
        "test_results": {}, "task_id": "t3",
    }))
    rows = aggregate_results(two_results_dir)
    assert len(rows) == 2


def test_aggregate_excludes_mock(two_results_dir):
    (two_results_dir / "r4.json").write_text(json.dumps({
        "agent": "mock", "agent_version": "0.1", "model": None,
        "status": "resolved", "duration_sec": 1, "usage": {"cost_usd": 0.0},
        "test_results": {}, "task_id": "tiny",
    }))
    rows = aggregate_results(two_results_dir)
    assert all(r["agent"] != "mock" for r in rows)


def test_aggregate_handles_null_cost(two_results_dir):
    (two_results_dir / "r5.json").write_text(json.dumps({
        "agent": "aider", "agent_version": "0.50", "model": None,
        "status": "resolved", "duration_sec": 80, "usage": {"cost_usd": None, "billing_mode": "subscription"},
        "test_results": {}, "task_id": "t4",
    }))
    rows = aggregate_results(two_results_dir)
    aider_row = next(r for r in rows if r["agent"] == "aider")
    # null cost is excluded from the median; with one data point and one null,
    # the median of the remaining single-point set is that point's value (None).
    assert aider_row["median_cost_usd"] is None


def test_aggregate_excludes_task_error_from_pass_rate(two_results_dir):
    """task_error / grader_error are harness-level failures (e.g. SWE-bench
    data quality issues), not agent failures. They should not count as
    'attempted' and should not drag down the pass rate."""
    (two_results_dir / "r6.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "task_error", "duration_sec": 0, "usage": {"cost_usd": None},
        "test_results": {}, "task_id": "broken",
        "error": "pre-flight validation failed",
    }))
    rows = aggregate_results(two_results_dir)
    assert len(rows) == 1
    assert rows[0]["n_attempted"] == 2  # r1, r2 only
    assert rows[0]["n_resolved"] == 1
    assert rows[0]["pass_rate"] == 0.5
    assert rows[0]["n_skipped_harness"] == 1


def test_aggregate_skipped_harness_zero_when_all_attempted(two_results_dir):
    rows = aggregate_results(two_results_dir)
    assert rows[0]["n_skipped_harness"] == 0


def test_aggregate_median_cache_tokens(two_results_dir):
    """Cache read/creation tokens are aggregated alongside input/output."""
    (two_results_dir / "r6.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "resolved", "duration_sec": 100, "usage": {
            "tokens_in": 100, "tokens_out": 50,
            "cache_read_tokens": 9000, "cache_creation_tokens": 200,
            "cost_usd": 0.42,
        },
        "test_results": {}, "task_id": "t3",
    }))
    rows = aggregate_results(two_results_dir)
    assert rows[0]["median_cache_read_tokens"] == 9000
    assert rows[0]["median_cache_creation_tokens"] == 200


def test_aggregate_pass_rate_capped_at_one_with_repeats(tmp_path):
    """With --repeat N, a single task produces N result files. n_attempted
    counts UNIQUE task_ids (1 for a repeated task), so n_resolved must also
    count unique resolved tasks — otherwise pass_rate goes above 1.0.

    Convention is pass@k: a task counts as resolved if ANY repeat resolved.
    """
    d = tmp_path / "results"
    d.mkdir()
    # Same task t1, repeated 3 times, all resolved.
    for i in (1, 2, 3):
        (d / f"r{i}.json").write_text(json.dumps({
            "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
            "status": "resolved", "duration_sec": 100,
            "usage": {"cost_usd": 0.1}, "test_results": {}, "task_id": "t1",
        }))
    rows = aggregate_results(d)
    assert len(rows) == 1
    assert rows[0]["n_attempted"] == 1, "one unique task"
    # n_resolved must use unique-task semantics to match n_attempted.
    assert rows[0]["n_resolved"] == 1, (
        f"expected 1 unique resolved task, got n_resolved={rows[0]['n_resolved']}. "
        f"pass_rate is now {rows[0]['pass_rate']} which is > 1.0 — invalid."
    )
    assert rows[0]["pass_rate"] == 1.0


def test_aggregate_pass_at_k_resolves_if_any_repeat_resolves(tmp_path):
    """pass@k semantics: a task counts as resolved if ANY repeat resolved.
    If 1/3 repeats resolve, the task is still resolved."""
    d = tmp_path / "results"
    d.mkdir()
    # Task t1: 3 repeats, only the 2nd resolves.
    for i, status in [(1, "failed"), (2, "resolved"), (3, "failed")]:
        (d / f"r{i}.json").write_text(json.dumps({
            "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
            "status": status, "duration_sec": 100,
            "usage": {"cost_usd": 0.1}, "test_results": {}, "task_id": "t1",
        }))
    # Task t2: 2 repeats, neither resolves.
    for i, status in [(1, "failed"), (2, "failed")]:
        (d / f"t2_r{i}.json").write_text(json.dumps({
            "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
            "status": status, "duration_sec": 100,
            "usage": {"cost_usd": 0.1}, "test_results": {}, "task_id": "t2",
        }))
    rows = aggregate_results(d)
    assert rows[0]["n_attempted"] == 2  # t1, t2
    assert rows[0]["n_resolved"] == 1   # t1 (one repeat resolved)
    assert rows[0]["pass_rate"] == 0.5


def test_wilson_ci_basic_case():
    """For 2/3 success, the 95% Wilson CI should be roughly (20%, 94%).
    Hand-checked against the standard formula — see
    https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval."""
    from cae.metrics import _wilson_ci
    low, high = _wilson_ci(2, 3)
    assert 0.15 < low < 0.30, f"low={low}"
    assert 0.88 < high < 0.98, f"high={high}"


def test_wilson_ci_perfect_score():
    """3/3 success → low near 30%, high 100%."""
    from cae.metrics import _wilson_ci
    low, high = _wilson_ci(3, 3)
    assert 0.25 < low < 0.45, f"low={low}"
    assert high == 1.0, f"high={high} (should be exactly 1.0 for all-success)"


def test_wilson_ci_zero_successes():
    """0/3 success → low = 0.0, high roughly 60-70%."""
    from cae.metrics import _wilson_ci
    low, high = _wilson_ci(0, 3)
    assert low == 0.0
    assert 0.55 < high < 0.80, f"high={high}"


def test_wilson_ci_zero_total_returns_neutral():
    """0/0 (no attempts) → return (0.0, 0.0) so the CI column doesn't
    crash the renderer. The leaderboard row's n_attempted is 0 in this
    case, so pass_rate is also 0.0 — caller can decide not to render the CI."""
    from cae.metrics import _wilson_ci
    low, high = _wilson_ci(0, 0)
    assert low == 0.0
    assert high == 0.0


def test_aggregate_results_includes_wilson_ci_fields(tmp_path):
    """aggregate_results should add pass_rate_ci_low / pass_rate_ci_high
    to every row so the leaderboard renderer can display the uncertainty
    alongside the point estimate."""
    import json
    results = tmp_path / "results"
    results.mkdir()
    # 2 resolved of 3 attempts for claude-code
    for i, status in enumerate(["resolved", "resolved", "failed"]):
        (results / f"r{i}.json").write_text(json.dumps({
            "agent": "claude-code", "model": "m", "agent_version": "1.0",
            "task_id": f"t{i}", "status": status, "started_at": "2026-06-27T00:00:00Z",
            "duration_sec": 100, "usage": {"cost_usd": 0.1},
        }))
    from cae.metrics import aggregate_results
    rows = aggregate_results(results)
    assert len(rows) == 1
    assert "pass_rate_ci_low" in rows[0]
    assert "pass_rate_ci_high" in rows[0]
    assert 0.15 < rows[0]["pass_rate_ci_low"] < 0.30
    assert 0.88 < rows[0]["pass_rate_ci_high"] < 0.98
