import json
from pathlib import Path

import pytest

from pae.site import build_site


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
