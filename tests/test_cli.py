import json
import shutil
import subprocess
import sys

import pytest


def test_pae_runs_and_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "pae", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "pae" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_pae_run_writes_result_json(tmp_path, tiny_task_path):
    """`pae run --agent mock --task <tiny>` should write a result JSON to results/."""
    # copy the fixture into tasks/ under tmp cwd
    proj = tmp_path
    (proj / "tasks" / "tiny__task-1" / "repo").mkdir(parents=True)
    for src in (tiny_task_path.iterdir()):
        if src.name == "repo":
            for child in src.iterdir():
                dest = proj / "tasks" / "tiny__task-1" / "repo" / child.name
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)
        else:
            dest = proj / "tasks" / "tiny__task-1" / src.name
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "pae", "run", "--agent", "mock",
         "--task", "tiny__task-1",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1, f"expected 1 result file, got {len(files)}: {files}"
    data = json.loads(files[0].read_text())
    assert data["agent"] == "mock"
    assert data["task_id"] == "tiny__task-1"
    assert data["status"] in {"resolved", "failed"}  # the mock doesn't fix the bug, so likely failed


def test_pae_add_task_no_fetch(tmp_path):
    """`pae add-task --from-swebench --no-fetch-repo` writes a task.json to tasks/.

    This test requires HuggingFace access (the SWE-bench Verified dataset). It
    is skipped (not failed) if datasets/HF is not available in the test env.
    """
    pytest.importorskip("datasets")
    proj = tmp_path
    result = subprocess.run(
        [sys.executable, "-m", "pae", "add-task",
         "--from-swebench", "--limit", "1", "--no-fetch-repo",
         "--tasks-dir", str(proj / "tasks")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"add-task failed: {result.stderr}"
    tasks = list((proj / "tasks").iterdir())
    assert len(tasks) == 1
    task_json = json.loads((tasks[0] / "task.json").read_text())
    assert task_json["source"]["kind"] == "swe-bench"
    assert "fail_to_pass" in task_json


def test_pae_list_agents(capsys):
    result = subprocess.run(
        [sys.executable, "-m", "pae", "list-agents"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "mock" in result.stdout
    assert "claude-code" in result.stdout or "codex" in result.stdout  # at least one real


def test_pae_report_table_format(tmp_path):
    """Write two result files and verify report prints a table."""
    import json
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "r1.json").write_text(json.dumps({
        "agent": "mock", "agent_version": "0.1", "model": None,
        "status": "resolved", "duration_sec": 1, "usage": {"cost_usd": 0.0},
        "task_id": "t1", "started_at": "2026-06-07T00:00:00Z",
        "test_results": {},
    }))
    result = subprocess.run(
        [sys.executable, "-m", "pae", "report",
         "--results-dir", str(tmp_path / "results")],
        capture_output=True, text=True,
    )
    # mock is filtered out, so the table is empty (just headers)
    assert result.returncode == 0
    assert "AGENT" in result.stdout  # header row


def test_pae_run_with_keep_workdir(tmp_path, tiny_task_path):
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "pae", "run", "--agent", "mock",
         "--task", "tiny_task", "--keep-workdir",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(list((proj / "results").glob("*.json"))[0].read_text())
    assert "workdir" in data
    assert data["workdir"]  # non-empty


def test_pae_run_force_flag_resumes(tmp_path, tiny_task_path):
    """Without --force, a second run for the same (task, agent) skips."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    base_cmd = [sys.executable, "-m", "pae", "run", "--agent", "mock",
                "--task", "tiny_task",
                "--tasks-dir", str(proj / "tasks"),
                "--results-dir", str(proj / "results")]

    r1 = subprocess.run(base_cmd, capture_output=True, text=True)
    assert r1.returncode == 0
    n_after_first = len(list((proj / "results").glob("*.json")))

    r2 = subprocess.run(base_cmd, capture_output=True, text=True)
    assert "skipping" in r2.stdout or n_after_first == len(list((proj / "results").glob("*.json")))

    r3 = subprocess.run(base_cmd + ["--force"], capture_output=True, text=True)
    assert r3.returncode == 0
