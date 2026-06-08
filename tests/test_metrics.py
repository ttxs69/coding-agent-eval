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
