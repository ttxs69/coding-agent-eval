"""Full vertical-slice replay: harness + mock + tiny fixture, end-to-end."""

import json
import shutil
import subprocess
import sys


def test_full_vertical_slice_replay(tmp_path, tiny_task_path):
    """Re-run the Task 8 manual smoke test programmatically."""
    proj = tmp_path
    # copy the tiny fixture into a fresh tasks/ tree
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    repo = tasks / "repo"
    repo.mkdir()
    for child in (tiny_task_path / "repo").iterdir():
        dest = repo / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            dest.write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "pae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())

    # every required spec field is present
    for field in ("run_id", "task_id", "agent", "agent_version", "model", "mode",
                  "status", "started_at", "duration_sec", "harness_git_sha",
                  "task_source", "usage", "test_results", "patch", "workdir"):
        assert field in data, f"missing field: {field}"

    # test_results has both pre and post flight
    assert "pre_flight" in data["test_results"]
    assert "post_flight" in data["test_results"]
    assert "fail_to_pass" in data["test_results"]["post_flight"]
    assert "pass_to_pass" in data["test_results"]["post_flight"]


def test_aggregate_after_run(tmp_path, tiny_task_path):
    """After a run, pae report and pae build-site should work end-to-end."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    repo = tasks / "repo"
    repo.mkdir()
    for child in (tiny_task_path / "repo").iterdir():
        dest = repo / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            dest.write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    subprocess.run(
        [sys.executable, "-m", "pae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        check=True, capture_output=True, text=True, timeout=120,
    )

    # report --format table should run cleanly
    r = subprocess.run(
        [sys.executable, "-m", "pae", "report",
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0

    # build-site should produce an index.html
    site_out = proj / "site"
    r2 = subprocess.run(
        [sys.executable, "-m", "pae", "build-site",
         "--results-dir", str(proj / "results"),
         "--out-dir", str(site_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert r2.returncode == 0, r2.stderr
    assert (site_out / "index.html").exists()
