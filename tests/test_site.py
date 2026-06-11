import json
from pathlib import Path

import pytest

from cae.site import build_site


@pytest.fixture
def site_inputs(tmp_path) -> tuple[Path, Path]:
    results = tmp_path / "results"
    results.mkdir()
    (results / "r1.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "resolved", "duration_sec": 100, "usage": {"cost_usd": 0.1},
        "task_id": "t1", "started_at": "2026-06-07T00:00:00Z",
        "test_results": {}, "patch": "diff --git a/x b/x\n+1",
    }))
    out = tmp_path / "site"
    return results, out


def test_build_site_creates_index_html(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    assert (out / "index.html").exists()
    html = (out / "index.html").read_text()
    assert "claude-code" in html
    assert "Pass rate" in html or "PASS" in html


def test_build_site_creates_results_json(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    data = json.loads((out / "data" / "results.json").read_text())
    assert len(data) == 1
    assert data[0]["agent"] == "claude-code"


def test_build_site_creates_per_task_page(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    assert (out / "tasks" / "t1.html").exists()


def test_build_site_preserves_each_run_detail_dump(tmp_path):
    """When a (task, agent) pair has multiple runs (e.g. --repeat 3, or
    runs with different --model values), each run produces a result JSON.
    The site's per-run detail dump (under data/details/) must preserve
    every run, not collapse them into a single file.

    Regression: detail filename was `{task_id}__{agent}.json`, which
    collides across repeats/models — only the last one (alphabetically
    by source filename) survived. External tools that consume the dumps
    silently lost data."""
    results = tmp_path / "results"
    results.mkdir()
    # Same (task, agent), three different runs (different models / repeats).
    for i, (model, status) in enumerate([
        ("claude-opus-4-7", "resolved"),
        ("claude-sonnet-4-6", "failed"),
        ("claude-opus-4-7", "failed"),  # a repeat
    ]):
        (results / f"2026-06-{10+i:02d}__claude-code__{model}__t1.json").write_text(json.dumps({
            "agent": "claude-code", "agent_version": "1.0", "model": model,
            "status": status, "duration_sec": 100, "usage": {"cost_usd": 0.1},
            "task_id": "t1", "started_at": f"2026-06-{10+i:02d}T00:00:00Z",
            "test_results": {}, "patch": "",
        }))
    out = tmp_path / "site"
    build_site(results, out)
    details = sorted((out / "data" / "details").glob("*.json"))
    assert len(details) == 3, (
        f"expected 3 detail dumps (one per run), got {len(details)}: "
        f"{[p.name for p in details]}. Detail filename collapses runs into one."
    )
