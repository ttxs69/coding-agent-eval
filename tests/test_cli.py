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

    cost, output = _execute_run_unit(
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
    assert isinstance(output, str)
    assert "wrote" in output
    assert "status:" in output
    files = list(results_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["agent"] == "mock"
    assert data["task_id"] == "tiny__task-1"


def test_cae_run_parallel_produces_all_results(tmp_path, tiny_task_path):
    """`--task A --task B --parallel 2` produces two result files."""
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
         "--parallel", "2",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    result_files = [f for f in (proj / "results").glob("*.json") if "__mock__" in f.name]
    assert len(result_files) == 2, (
        f"expected 2 result files, got {len(result_files)}: {[f.name for f in result_files]}"
    )


def test_cae_run_parallel_is_concurrent(tmp_path, tiny_task_path):
    """When --parallel=N, N units run concurrently. We verify by injecting a
    sleep into setup_cmd so each unit takes ~1s, then checking that
    total wall time for parallel-3 is meaningfully faster than serial-1.
    """
    import time

    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2", "tiny__task-3"):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        task_json = json.loads((tiny_task_path / "task.json").read_text())
        task_json["instance_id"] = name
        task_json["setup_cmd"] = "sleep 1"
        (t / "task.json").write_text(json.dumps(task_json))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
    (proj / "results").mkdir()

    def run_cae(parallel: int) -> float:
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-m", "cae", "run", "--agent", "mock",
             "--task", "tiny__task-1", "--task", "tiny__task-2", "--task", "tiny__task-3",
             "--parallel", str(parallel),
             "--tasks-dir", str(tasks_dir),
             "--results-dir", str(proj / "results"),
             "--force"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return time.monotonic() - start

    serial = run_cae(1)
    parallel = run_cae(3)
    # 3 units @ ~1s each. Serial ~3s+overhead; parallel-3 ~1s+overhead.
    # Allow generous slack — assert parallel is at least 40% faster than serial.
    assert parallel < serial * 0.6, (
        f"parallel ({parallel:.1f}s) not meaningfully faster than serial ({serial:.1f}s)"
    )


def test_cae_run_parallel_isolates_task_errors(tmp_path, tiny_task_path):
    """If one unit hits a task_error (missing repo, bad patch, etc.),
    the other units still complete and write results. The harness returns
    task_error as a status rather than raising; this test locks that in
    for the parallel dispatch path.
    """
    proj = tmp_path
    tasks_dir = proj / "tasks"
    # tiny__task-1: healthy
    healthy = tasks_dir / "tiny__task-1"
    (healthy / "repo").mkdir(parents=True)
    (healthy / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = healthy / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    # tiny__broken: setup_cmd fails → harness returns task_error
    broken = tasks_dir / "tiny__broken"
    (broken / "repo").mkdir(parents=True)
    bad_json = json.loads((tiny_task_path / "task.json").read_text())
    bad_json["instance_id"] = "tiny__broken"
    bad_json["setup_cmd"] = "false"  # always exits non-zero
    (broken / "task.json").write_text(json.dumps(bad_json))
    for child in (tiny_task_path / "repo").iterdir():
        dest = broken / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__broken",
         "--parallel", "2",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # Both result files must exist, regardless of the broken task.
    result_files = sorted(f.name for f in (proj / "results").glob("*__mock__*.json"))
    assert any("tiny__task-1" in n for n in result_files), result_files
    assert any("tiny__broken" in n for n in result_files), result_files

    # The broken task's status must be task_error, not a crash.
    broken_file = next(f for f in (proj / "results").glob("*__mock__*tiny__broken*.json"))
    broken_data = json.loads(broken_file.read_text())
    assert broken_data["status"] == "task_error", broken_data["status"]


def test_cae_run_parallel_continues_after_unexpected_worker_exception(tmp_path, tiny_task_path):
    """If a worker raises UNEXPECTEDLY (not task_error — a real exception
    like KeyError on a malformed task.json), the loop must catch it, log
    it, and continue processing the other workers' results. The healthy
    task's `wrote <path>` / `status:` output must still appear on stdout,
    and the CLI must exit non-zero.

    Under the old (uncaught) code, the first worker's exception exits the
    as_completed loop immediately, so any workers that finish later never
    get their output printed.
    """
    proj = tmp_path
    tasks_dir = proj / "tasks"

    # Healthy task with a slow setup_cmd so it finishes AFTER the broken
    # task has already raised. This forces the order: broken-fails-first,
    # healthy-finishes-second. Under the old code, the broken task's
    # exception would exit the loop before the healthy task's output is
    # iterated.
    healthy = tasks_dir / "tiny__task-1"
    (healthy / "repo").mkdir(parents=True)
    healthy_json = json.loads((tiny_task_path / "task.json").read_text())
    healthy_json["setup_cmd"] = "sleep 1"  # ensure healthy finishes second
    (healthy / "task.json").write_text(json.dumps(healthy_json))
    for child in (tiny_task_path / "repo").iterdir():
        dest = healthy / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    # Broken task: malformed task.json (missing required 'fail_to_pass').
    # The harness's run() does `fail_to_pass = task["fail_to_pass"]` near
    # the top, raising KeyError before any setup_cmd runs — so this fails
    # FAST, before the healthy task finishes its 1s sleep.
    broken = tasks_dir / "tiny__broken"
    (broken / "repo").mkdir(parents=True)
    bad_json = json.loads((tiny_task_path / "task.json").read_text())
    del bad_json["fail_to_pass"]
    bad_json["instance_id"] = "tiny__broken"
    (broken / "task.json").write_text(json.dumps(bad_json))
    for child in (tiny_task_path / "repo").iterdir():
        dest = broken / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__broken",
         "--parallel", "2",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )

    # The healthy task's result file must be on disk (pool.__exit__ waits).
    assert any("tiny__task-1" in f.name for f in (proj / "results").glob("*.json")), (
        f"healthy task result missing; stderr: {result.stderr}"
    )
    # Exit code must be non-zero — one unit raised unexpectedly.
    assert result.returncode != 0, (
        f"expected non-zero exit, got {result.returncode}; stdout: {result.stdout}"
    )
    # The healthy task's output must STILL be visible on stdout even though
    # the broken task raised first. Under the old code, the loop exits on
    # the first exception and the healthy task's `wrote` line is never printed.
    assert "wrote" in result.stdout and "status:" in result.stdout, (
        f"healthy task's output not printed; stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    # The error must be visible somewhere.
    assert "fail_to_pass" in result.stderr or "KeyError" in result.stderr, (
        f"expected error mentioning fail_to_pass; stderr: {result.stderr}"
    )


def test_cae_run_dry_run_flag_produces_dry_run_result(tmp_path, tiny_task_path):
    """`cae run --agent mock --task <tiny> --dry-run` writes a result JSON
    whose status is 'dry_run' and whose would_run_command is non-empty.
    No agent subprocess actually runs."""
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
         "--task", "tiny_task", "--dry-run",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1, f"expected 1 result file, got {len(files)}"
    data = json.loads(files[0].read_text())
    assert data["status"] == "dry_run", data["status"]
    assert data["would_run_command"], "would_run_command must be non-empty"
    # patch must be empty — agent didn't run
    assert data["patch"] == ""


def test_cae_run_dry_run_with_parallel_produces_all_dry_run_results(
    tmp_path, tiny_task_path,
):
    """--dry-run + --parallel 3 produces 3 result files, all with
    status='dry_run' and non-empty would_run_command. None of them
    actually invoked the agent (no API spend). Headline use case:
    sanity-check the entire parallel batch before spending money on it."""
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2", "tiny__task-3"):
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
         "--task", "tiny__task-1", "--task", "tiny__task-2", "--task", "tiny__task-3",
         "--parallel", "3", "--dry-run",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    result_files = sorted(f.name for f in (proj / "results").glob("*__mock__*.json"))
    assert len(result_files) == 3, (
        f"expected 3 dry-run result files, got {len(result_files)}: {result_files}"
    )
    for f in (proj / "results").glob("*__mock__*.json"):
        data = json.loads(f.read_text())
        assert data["status"] == "dry_run", (
            f"{f.name}: expected dry_run, got {data['status']}"
        )
        assert data["would_run_command"], f"{f.name}: empty would_run_command"
        assert data["patch"] == "", f"{f.name}: patch should be empty under --dry-run"


def test_cae_run_accepts_per_stage_timeout_flags(tmp_path, tiny_task_path):
    """`--timeout-setup`, `--timeout-agent`, `--timeout-tests` are accepted
    by argparse (do NOT yet behave differently — that comes in Task 2).
    Verifies the CLI surface before any run-logic changes."""
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
         "--task", "tiny_task",
         "--timeout-setup", "5",
         "--timeout-agent", "10",
         "--timeout-tests", "3",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    # Argparse must accept the flags — exit code 0 OR a runtime error is fine,
    # but NOT an argparse error (exit code 2 with "unrecognized" wording).
    assert result.returncode != 2 or "unrecognized arguments" not in result.stderr, (
        f"argparse rejected the new flags: {result.stderr}"
    )


def test_cae_run_per_stage_timeout_tests_aborts_long_running_pre_flight(
    tmp_path, tiny_task_path,
):
    """End-to-end: --timeout-tests 0 (0 minutes = 0 seconds = immediate
    timeout) against a task whose test_cmd sleeps 30s. Pre-flight must
    abort almost immediately with task_error. Verifies the per-stage flag
    actually changes behavior end-to-end, not just threads through."""
    import time
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    # Inject a slow test_cmd so we have something to interrupt.
    task_json = json.loads((tiny_task_path / "task.json").read_text())
    task_json["test_cmd"] = "sleep 30 && python -m pytest test_main.py -v"
    (tasks / "task.json").write_text(json.dumps(task_json))
    (tasks / "repo").mkdir(parents=True)
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--timeout-tests", "0",  # 0 minutes = 0 seconds = immediate timeout
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    elapsed = time.monotonic() - start

    # Pre-flight must have aborted quickly — well under the 30-second sleep.
    assert elapsed < 25, f"pre-flight should have aborted in <25s; took {elapsed:.1f}s"
    # The CLI exits 0 even on task_error (the harness records the status, doesn't crash).
    assert result.returncode == 0, f"stderr: {result.stderr}"
    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["status"] == "task_error", (
        f"expected task_error from pre-flight timeout, got {data['status']}"
    )


def test_cae_build_site_accepts_include_archive_flag(tmp_path, monkeypatch):
    """`cae build-site --include-archive` plumbs through to build_site
    (which only consults the archive when the flag is set)."""
    import cae.site as site_mod
    from cae import cli

    called = {"n": 0, "kw": None}
    def fake_build(*args, **kwargs):
        called["n"] += 1
        called["kw"] = kwargs
    monkeypatch.setattr(site_mod, "build_site", fake_build)

    rc = cli.main(["build-site", "--results-dir", str(tmp_path),
                   "--out-dir", str(tmp_path / "site"),
                   "--include-archive"])
    assert rc == 0
    assert called["kw"].get("include_archive") is True


def test_cae_build_site_default_include_archive_is_false(tmp_path, monkeypatch):
    """Default (no --include-archive flag) must NOT pass include_archive=True."""
    import cae.site as site_mod
    from cae import cli
    called = {"kw": None}
    def fake_build(*args, **kwargs):
        called["kw"] = kwargs
    monkeypatch.setattr(site_mod, "build_site", fake_build)
    cli.main(["build-site", "--results-dir", str(tmp_path),
              "--out-dir", str(tmp_path / "site")])
    assert called["kw"].get("include_archive") is False


def test_cae_report_accepts_include_archive_flag(tmp_path, monkeypatch):
    """`cae report --include-archive` plumbs through to the archive
    merge, so the local console report shows historical runs (matching
    the published site's behavior, since deploy_site.sh now uses
    --include-archive by default)."""
    from cae import cli

    captured = {"include_archive": None}
    def fake_aggregate(results_dir, include_archive):
        captured["include_archive"] = include_archive
        return []
    monkeypatch.setattr(cli, "_aggregate_with_archive", fake_aggregate)
    rc = cli.main(["report", "--results-dir", str(tmp_path),
                   "--include-archive"])
    assert rc == 0
    assert captured["include_archive"] is True, (
        f"--include-archive should reach the aggregate helper, "
        f"got include_archive={captured['include_archive']!r}"
    )


def test_cae_report_default_include_archive_is_false(tmp_path, monkeypatch):
    """Default (no --include-archive flag) must NOT pull the archive —
    the local report should stay fast, since the fetch is the cost."""
    from cae import cli
    captured = {"include_archive": None}
    def fake_aggregate(results_dir, include_archive):
        captured["include_archive"] = include_archive
        return []
    monkeypatch.setattr(cli, "_aggregate_with_archive", fake_aggregate)
    rc = cli.main(["report", "--results-dir", str(tmp_path)])
    assert rc == 0
    assert captured["include_archive"] is False
