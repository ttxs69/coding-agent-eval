import json
import shutil
import subprocess
import sys


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
