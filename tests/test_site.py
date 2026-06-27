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


def test_merge_results_local_wins_on_duplicate_run_id(tmp_path):
    """When --include-archive hydrates from gh-pages, local results/ files
    must win on duplicate run_ids — local is newer (user just ran them),
    archive may have stale versions of the same run_id if a re-deploy
    happened. Without local-wins, we'd accidentally use the older copy."""
    from cae.site_archive import _merge_results
    # Set up local results dir with one file.
    local = tmp_path / "local"
    local.mkdir()
    local_data = {"run_id": "RUN-1", "agent": "claude-code", "task_id": "T1",
                  "status": "resolved", "usage": {"cost_usd": 1.0}, "local": True}
    (local / "RUN-1.json").write_text(__import__("json").dumps(local_data))

    # Archive has the SAME run_id but with older data (cost=$0.5).
    archive = {"RUN-1": {"run_id": "RUN-1", "agent": "claude-code", "task_id": "T1",
                          "status": "failed", "usage": {"cost_usd": 0.5}, "local": False},
               # Plus an archive-only entry that should be merged in.
               "RUN-2": {"run_id": "RUN-2", "agent": "codex", "task_id": "T2",
                         "status": "resolved", "usage": {"cost_usd": 0.25}, "local": False}}

    merged_dir = _merge_results(local, archive)
    files = {f.stem: __import__("json").loads(f.read_text())
             for f in merged_dir.glob("*.json")}

    assert set(files) == {"RUN-1", "RUN-2"}
    # RUN-1 from local (cost=$1.0, status=resolved) — not from archive.
    assert files["RUN-1"]["usage"]["cost_usd"] == 1.0
    assert files["RUN-1"]["status"] == "resolved"
    assert files["RUN-1"]["local"] is True
    # RUN-2 came from archive.
    assert files["RUN-2"]["usage"]["cost_usd"] == 0.25
    assert files["RUN-2"]["agent"] == "codex"


def test_fetch_archive_details_uses_git_archive(tmp_path, monkeypatch):
    """_fetch_archive_details runs `git archive <remote>/<branch> data/details`
    and parses each JSON in the extracted output. Mock subprocess to avoid
    needing a real gh-pages branch."""
    import subprocess
    from cae import site_archive

    # The function calls subprocess.run with the git archive command. Capture
    # the call args so we can assert shape, and substitute a tarball made
    # from our test data instead of actually running git archive.
    calls = []
    real_run = subprocess.run

    sample_results = [
        {"run_id": "A1", "agent": "claude-code", "task_id": "T1", "status": "resolved"},
        {"run_id": "A2", "agent": "codex", "task_id": "T2", "status": "failed"},
    ]

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        # Match the git archive | tar -xC pattern. cmd looks like:
        # ["git", "archive", "<remote>/<branch>", "data/details/", "--", ...]
        # but actually the function pipes git archive | tar, so cmd may be a
        # shell string. Be flexible: just return success and let the test
        # check the cmd captured.
        return real_run(["true"], *args, **kwargs)

    # Simpler approach: monkeypatch _extract_archive_via_git to return a
    # directory we pre-populate. That tests the parse step in isolation.
    fake_extract_dir = tmp_path / "extracted" / "data" / "details"
    fake_extract_dir.mkdir(parents=True)
    for r in sample_results:
        (fake_extract_dir / f"{r['run_id']}.json").write_text(__import__("json").dumps(r))

    monkeypatch.setattr(site_archive, "_extract_archive_via_git",
                        lambda remote, branch, dest: fake_extract_dir)

    archive = site_archive._fetch_archive_details(remote="origin", branch="gh-pages")
    assert set(archive) == {"A1", "A2"}
    assert archive["A1"]["agent"] == "claude-code"
    assert archive["A2"]["status"] == "failed"


def test_fetch_archive_details_returns_empty_when_git_fails(monkeypatch):
    """If git archive errors (no gh-pages branch, no network, etc.) we must
    return an empty dict, not crash. Better to silently fall back to
    local-only than to break the whole build."""
    from cae import site_archive

    def raising_extractor(remote, branch, dest):
        raise RuntimeError("git archive failed")

    monkeypatch.setattr(site_archive, "_extract_archive_via_git", raising_extractor)
    archive = site_archive._fetch_archive_details(remote="origin", branch="gh-pages")
    assert archive == {}


def test_build_site_with_include_archive_merges_with_remote(monkeypatch, tmp_path):
    """With include_archive=True, build_site aggregates local results +
    every archive entry whose run_id doesn't collide. Without
    include_archive, behavior is unchanged (default off)."""
    from cae import site as site_mod
    import json

    # Set up a local results dir with one file.
    local = tmp_path / "local_results"
    local.mkdir()
    (local / "LOCAL-1.json").write_text(json.dumps({
        "run_id": "LOCAL-1", "agent": "claude-code", "task_id": "T1",
        "status": "resolved", "usage": {"cost_usd": 1.0}, "test_results": {},
        "patch": "", "workdir": "/tmp/wd", "error": "",
    }))

    # Mock the archive: a single extra run with a different run_id.
    archive_data = {"ARCHIVE-1": {
        "run_id": "ARCHIVE-1", "agent": "codex", "task_id": "T2",
        "status": "resolved", "usage": {"cost_usd": 0.5}, "test_results": {},
        "patch": "", "workdir": "/tmp/wd", "error": "",
    }}
    monkeypatch.setattr(site_mod, "_fetch_archive_details", lambda **kw: archive_data)

    out = tmp_path / "site"
    site_mod.build_site(local, out, include_archive=True)

    # Leaderboard shows BOTH rows (local + archive).
    rows = json.loads((out / "data" / "results.json").read_text())
    agents = {r["agent"] for r in rows}
    assert "claude-code" in agents
    assert "codex" in agents


def test_build_site_default_does_not_call_archive(monkeypatch, tmp_path):
    """Default include_archive=False must NOT touch the git archive —
    that's the whole point of opt-in. Verifies the flag is wired through,
    not silently always-on."""
    from cae import site as site_mod
    import json

    called = {"n": 0}
    def spy(**kw):
        called["n"] += 1
        return {}
    monkeypatch.setattr(site_mod, "_fetch_archive_details", spy)

    local = tmp_path / "local_results"
    local.mkdir()
    (local / "LOCAL-1.json").write_text(json.dumps({
        "run_id": "LOCAL-1", "agent": "claude-code", "task_id": "T1",
        "status": "resolved", "usage": {"cost_usd": 1.0}, "test_results": {},
        "patch": "", "workdir": "/tmp/wd", "error": "",
    }))

    site_mod.build_site(local, tmp_path / "site")
    assert called["n"] == 0, "include_archive=False must not call the archive"


def test_build_site_include_archive_cleans_up_temp_dir(monkeypatch, tmp_path):
    """The temp merged dir created by _merge_results must be cleaned up
    when build_site returns — otherwise /tmp/cae-merged-XXXX/ leaks
    forever across repeated CI builds."""
    from cae import site as site_mod
    import json

    local = tmp_path / "local_results"
    local.mkdir()
    (local / "LOCAL-1.json").write_text(json.dumps({
        "run_id": "LOCAL-1", "agent": "claude-code", "task_id": "T1",
        "status": "resolved", "usage": {"cost_usd": 1.0}, "test_results": {},
        "patch": "", "workdir": "/tmp/wd", "error": "",
    }))
    archive = {"ARCHIVE-1": {
        "run_id": "ARCHIVE-1", "agent": "codex", "task_id": "T2",
        "status": "resolved", "usage": {"cost_usd": 0.5}, "test_results": {},
        "patch": "", "workdir": "/tmp/wd", "error": "",
    }}
    monkeypatch.setattr(site_mod, "_fetch_archive_details", lambda **kw: archive)

    merged_dirs = []
    real_merge = site_mod._merge_results
    def spy_merge(local, archive):
        out = real_merge(local, archive)
        merged_dirs.append(out)
        return out
    monkeypatch.setattr(site_mod, "_merge_results", spy_merge)

    site_mod.build_site(local, tmp_path / "site", include_archive=True)
    assert merged_dirs, "merge should have run"
    assert not merged_dirs[0].exists(), (
        f"temp merged dir {merged_dirs[0]} should be cleaned up after build"
    )


def test_fmt_pass_rate_zero_attempts_renders_just_percent():
    """n=0 must NOT show 'CI 0-0%' (that's noisy and misleading). The
    renderer short-circuits to just '0%' when n=0, since the caller
    should detect n_attempted==0 separately."""
    from cae.site import _fmt_pass_rate
    assert _fmt_pass_rate({"pass_rate": 0.0, "n_attempted": 0,
                            "pass_rate_ci_low": 0.0, "pass_rate_ci_high": 0.0}) == "0%"


def test_fmt_pass_rate_basic_2_of_3():
    """2/3 resolved at 95% Wilson CI is (0.21, 0.94) — renders as
    '67% (CI 21-94%)'. Locks the integer-rounding format so a future
    change to % formatting (e.g. one decimal) breaks the test."""
    from cae.site import _fmt_pass_rate
    out = _fmt_pass_rate({"pass_rate": 2/3, "n_attempted": 3,
                           "pass_rate_ci_low": 0.2077, "pass_rate_ci_high": 0.9385})
    assert out == "67% (CI 21–94%)", f"got {out!r}"


def test_fmt_pass_rate_missing_ci_fields_falls_back():
    """If the new pass_rate_ci_low/high fields are missing (e.g. row
    came from an older build without the Wilson fields), the renderer
    must not crash — fall back to the bare percentage."""
    from cae.site import _fmt_pass_rate
    assert _fmt_pass_rate({"pass_rate": 0.5, "n_attempted": 4}) == "50%"


def test_aggregate_results_round_trips_through_json_with_new_fields(tmp_path):
    """Lock the data/results.json schema: pass_rate_ci_low/high must
    survive a json.dumps/loads round-trip. Without this, a future
    refactor that drops the fields would silently break the public
    leaderboard JSON contract."""
    import json
    results = tmp_path / "results"
    results.mkdir()
    (results / "r.json").write_text(json.dumps({
        "agent": "claude-code", "model": "m", "agent_version": "1.0",
        "task_id": "t", "status": "resolved", "started_at": "2026-06-27T00:00:00Z",
        "duration_sec": 100, "usage": {"cost_usd": 0.1},
    }))
    from cae.metrics import aggregate_results
    rows = aggregate_results(results)
    # Round-trip through json (the path data/results.json takes).
    payload = json.loads(json.dumps(rows, default=str))
    assert "pass_rate_ci_low" in payload[0]
    assert "pass_rate_ci_high" in payload[0]
    # The CI values should be in [0, 1] (Wilson is well-defined).
    assert 0.0 <= payload[0]["pass_rate_ci_low"] <= 1.0
    assert 0.0 <= payload[0]["pass_rate_ci_high"] <= 1.0
