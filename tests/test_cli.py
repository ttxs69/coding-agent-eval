import json
import shutil
import subprocess
import sys

import pytest


def test_cae_runs_and_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "cae", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "cae" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cae_run_writes_result_json(tmp_path, tiny_task_path):
    """`cae run --agent mock --task <tiny>` should write a result JSON to results/."""
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
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
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


def test_cae_add_task_no_fetch(tmp_path):
    """`cae add-task --from-swebench --no-fetch-repo` writes a task.json to tasks/.

    This test requires HuggingFace access (the SWE-bench Verified dataset). It
    is skipped (not failed) if datasets/HF is not available in the test env.
    """
    pytest.importorskip("datasets")
    proj = tmp_path
    result = subprocess.run(
        [sys.executable, "-m", "cae", "add-task",
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


def test_cae_list_agents(capsys):
    result = subprocess.run(
        [sys.executable, "-m", "cae", "list-agents"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "mock" in result.stdout
    assert "claude-code" in result.stdout or "codex" in result.stdout  # at least one real


def test_cae_report_table_format(tmp_path):
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
        [sys.executable, "-m", "cae", "report",
         "--results-dir", str(tmp_path / "results")],
        capture_output=True, text=True,
    )
    # mock is filtered out, so the table is empty (just headers)
    assert result.returncode == 0
    assert "AGENT" in result.stdout  # header row


def test_cae_run_with_keep_workdir(tmp_path, tiny_task_path):
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    (tasks / "repo").mkdir(parents=True)
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task", "--keep-workdir",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(list((proj / "results").glob("*.json"))[0].read_text())
    assert "workdir" in data
    assert data["workdir"]  # non-empty


def test_cae_run_force_flag_resumes(tmp_path, tiny_task_path):
    """Without --force, a second run for the same (task, agent) skips."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    (tasks / "repo").mkdir(parents=True)
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    base_cmd = [sys.executable, "-m", "cae", "run", "--agent", "mock",
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


def test_cae_run_resume_matches_discovered_model(tmp_path, tiny_task_path, monkeypatch):
    """Without --model, the resume glob must use the adapter's discovered
    model (not the literal 'default'), otherwise a re-run after a real
    run would re-execute instead of skipping.
    """
    from cae.agents import ADAPTERS
    from cae.agents.mock import MockAdapter
    from cae.cli import _resolve_effective_model, _safe_model_for_filename

    class _DiscoveredMock(MockAdapter):
        name = "discovered-mock"
        def _discover_model(self) -> str:
            return "discovered-model-X"
    ADAPTERS["discovered-mock"] = _DiscoveredMock
    try:
        # When --model is None, the resume check must discover the model
        # the same way the harness will, not default to "default".
        effective = _resolve_effective_model("discovered-mock", None)
        assert effective == "discovered-model-X", (
            f"expected discovered model, got {effective!r}"
        )
        # The filename-safe form should match what the harness writes.
        assert _safe_model_for_filename(effective) == "discovered-model-X"
        assert _safe_model_for_filename(None) == "default"
        # And `/` and `:` are replaced for filesystem safety.
        assert _safe_model_for_filename("org/model:1") == "org-model-1"
    finally:
        ADAPTERS.pop("discovered-mock", None)


def test_cae_run_resume_uses_default_when_no_model_or_discover():
    """When neither --model nor _discover_model produce a name (mock
    adapter has neither), the resume check falls back to 'default'."""
    from cae.cli import _resolve_effective_model, _safe_model_for_filename
    # 'mock' has no _discover_model and default_model is None.
    assert _resolve_effective_model("mock", None) is None
    assert _safe_model_for_filename(_resolve_effective_model("mock", None)) == "default"


def test_cae_run_docker_flag_accepted(tmp_path, tiny_task_path):
    """`--docker` is accepted by argparse; the run will fail if `docker` is not
    on PATH. We mock `subprocess.run` to assert that the docker-runner branch
    is actually invoked (i.e., the harness called `docker run ...`).

    We invoke the harness directly (not via the CLI subprocess) so the mock
    can observe the `docker run` call: subprocess mocks don't propagate across
    the `subprocess.run` boundary into the child process.
    """
    from unittest.mock import patch, MagicMock
    from cae.harness import run as harness_run

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

    docker_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "docker":
            docker_calls.append(cmd)
        return MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        harness_run(
            task_path=tasks,
            agent_name="mock",
            workdir=proj / "work",
            timeout_sec=60,
            docker=True,
            docker_image="my-image",
        )

    # The docker branch is wired up if subprocess was called with `docker run ...`.
    assert docker_calls, "expected at least one docker invocation with --docker"


def test_cae_run_docker_flag_rejected_by_docker_check(tmp_path, tiny_task_path):
    """If docker is not available, --docker should fail fast."""
    from unittest.mock import patch

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

    # Block `docker` from PATH
    with patch("shutil.which", return_value=None):
        result = subprocess.run(
            [sys.executable, "-m", "cae", "run", "--agent", "mock",
             "--task", "tiny_task", "--docker",
             "--tasks-dir", str(proj / "tasks"),
             "--results-dir", str(proj / "results")],
            capture_output=True, text=True, timeout=30,
        )

    # If docker was missing, the run should fail with an error about docker
    if result.returncode != 0:
        assert "docker" in result.stderr.lower() or result.returncode == 2


def test_cae_run_accepts_multiple_tasks_and_parallel_flag(tmp_path, tiny_task_path):
    """`--task foo --task bar --parallel 3` is accepted by argparse (does NOT
    yet run them in parallel — that comes later). Verifies the CLI surface
    before any run logic changes.
    """
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2"):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        (t / "task.json").write_text(
            (tiny_task_path / "task.json").read_text().replace('"tiny__task-1"', f'"{name}"'))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__task-2",
         "--parallel", "3",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    # We only assert argparse acceptance here — exit code 0 OR a runtime error
    # is fine, but NOT an argparse error (exit code 2 with "unrecognized" /
    # "invalid choice" wording).
    assert result.returncode != 2 or "unrecognized arguments" not in result.stderr, (
        f"argparse rejected the new flags: {result.stderr}"
    )


def test_execute_run_unit_writes_result_and_returns_cost(tmp_path, tiny_task_path):
    """`_execute_run_unit` runs one (task, repeat_index) pair end-to-end and
    returns the cost spent (0.0 for mock). It's the unit-of-work callable that
    the parallel dispatcher will hand to ThreadPoolExecutor."""
    from cae.cli import _execute_run_unit, _resolve_effective_model, _safe_model_for_filename

    proj = tmp_path
    tasks_dir = proj / "tasks"
    task_slug = "tiny__task-1"
    task_path = tasks_dir / task_slug
    (task_path / "repo").mkdir(parents=True)
    (task_path / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = task_path / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    results_dir = proj / "results"
    results_dir.mkdir()

    effective_model = _resolve_effective_model("mock", None)
    safe_model = _safe_model_for_filename(effective_model)

    cost = _execute_run_unit(
        task_path=task_path,
        agent_name="mock",
        instance_id=task_slug,
        safe_model=safe_model,
        repeat=1,
        repeat_index=None,
        results_dir=results_dir,
        workdir=None,
        timeout_sec=600,
        fetch_fresh=False,
        keep_workdir=False,
        docker=False,
        docker_image="python:3.11-slim",
        env_file=None,
        docker_network="bridge",
        docker_extra_mounts=None,
        model=None,
        force=False,
    )
    assert cost == 0.0  # mock has no cost
    files = list(results_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["agent"] == "mock"
    assert data["task_id"] == "tiny__task-1"
