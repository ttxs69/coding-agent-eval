import shutil
import subprocess

import pytest

from cae.agents import ADAPTERS
from cae.agents.mock import MockAdapter
from cae.harness import run


class _FixingMock(MockAdapter):
    """A mock that applies the gold fix to main.py when invoked as the agent.

    Also clears ``__pycache__`` so the post-flight test_cmd subprocess re-compiles
    the freshly modified ``main.py`` instead of importing the stale bytecode that
    pre-flight cached. (Python's pyc invalidation uses ``(mtime, size)`` and our
    one-character ``-``-to-``+`` swap changes neither when the rewrite happens
    inside the same filesystem-mtime second.)
    """

    def build_command(self, workdir, prompt, *, model):
        py = shutil.which("python") or shutil.which("python3") or "python3"
        script = (
            "import pathlib, shutil, sys\n"
            "wd = pathlib.Path(sys.argv[1])\n"
            "p = wd / 'main.py'\n"
            "p.write_text(p.read_text().replace('return a - b', 'return a + b'))\n"
            "cache = wd / '__pycache__'\n"
            "if cache.exists(): shutil.rmtree(cache)\n"
        )
        return [py, "-c", script, str(workdir)]


@pytest.fixture
def fixing_mock(monkeypatch):
    """Register _FixingMock as the 'mock' adapter for the duration of one test."""
    ADAPTERS["mock"] = _FixingMock
    yield
    ADAPTERS["mock"] = MockAdapter


def test_run_resolves_tiny_task_with_fixing_mock(tmp_path, tiny_task_path, fixing_mock):
    """End-to-end: harness runs the (custom) mock, mock writes the gold fix,
    pre-flight sees the bug, post-flight sees the fix, task is RESOLVED."""
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    result = run(task_path=tiny_task_path, agent_name="mock", workdir=workdir)

    assert result["status"] == "resolved"
    assert "main.py" in result["patch"]  # the harness captured a diff
    assert result["test_results"]["post_flight"]["fail_to_pass"]["test_main.py::test_add"] == "passed"
    assert result["test_results"]["post_flight"]["pass_to_pass"]["test_main.py::test_multiply"] == "passed"


# ---- pre-flight failure records model + version -------------------------

class _MockWithModel(MockAdapter):
    """A mock adapter that advertises a known model and version."""
    name = "mock-model"  # avoid colliding with the default "mock" key
    default_model = "test-model-1"
    def version(self) -> str:
        return "test-mock-0.1.0"


@pytest.fixture
def mock_with_model(monkeypatch):
    """Register _MockWithModel as 'mock-model' for the duration of one test."""
    ADAPTERS["mock-model"] = _MockWithModel
    yield
    ADAPTERS.pop("mock-model", None)


# ---- --model override ---------------------------------------------------

class _ModelCapturingMock(_MockWithModel):
    """Mock that records the model passed to build_command."""
    last_model: str | None = None
    def build_command(self, workdir, prompt, *, model):
        type(self).last_model = model
        # Just exit immediately so the harness doesn't run the agent.
        py = shutil.which("python") or "python3"
        return [py, "-c", "import sys; sys.exit(0)"]


@pytest.fixture
def model_capturing_mock(monkeypatch):
    ADAPTERS["mock-model"] = _ModelCapturingMock
    _ModelCapturingMock.last_model = None
    yield
    ADAPTERS.pop("mock-model", None)


def test_model_cli_flag_overrides_config(tmp_path, tiny_task_path, model_capturing_mock):
    """When --model is passed, it's forwarded to build_command and recorded
    as the result's `model` field, overriding the adapter's default."""

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    result = run(task_path=tiny_task_path, agent_name="mock-model",
                 workdir=workdir, model="user-chosen-model")

    assert _ModelCapturingMock.last_model == "user-chosen-model"
    assert result["model"] == "user-chosen-model"


def test_model_defaults_to_none_when_omitted(tmp_path, tiny_task_path, model_capturing_mock):
    """When --model is omitted, the adapter's default_model is used."""

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    result = run(task_path=tiny_task_path, agent_name="mock-model", workdir=workdir)

    # Default behavior: no --model means build_command receives None and the
    # result falls back to the adapter's default_model.
    assert _ModelCapturingMock.last_model is None
    assert result["model"] == "test-model-1"


def test_started_at_reflects_run_start_not_result_assembly(
    tmp_path, tiny_task_path, fixing_mock, monkeypatch,
):
    """`started_at` must reflect when the run started, not when the result
    was assembled. Otherwise a multi-minute agent run reports `started_at`
    minutes after it actually began — useless for ordering or correlating
    with logs.

    The harness captures this at the top of `run()` (via `_utc_now_iso()`)
    and threads it through to `_result()` as a local. This test pins that
    the consumer actually uses the captured time, not a fresh `now` call."""
    # Return distinct, increasing timestamps so we can tell which call
    # sourced started_at.
    counter = {"n": 0}
    def fake_now_iso():
        counter["n"] += 1
        return f"T{counter['n']:03d}"
    monkeypatch.setattr("cae.harness._utc_now_iso", fake_now_iso)

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    result = run(task_path=tiny_task_path, agent_name="mock", workdir=workdir)

    # The first _utc_now_iso() call happens at the top of run(); that's
    # the value started_at must reflect. If the value is a later T-number,
    # _result() is calling _utc_now_iso() directly instead of using the
    # captured `started_at` parameter.
    assert result["started_at"] == "T001", (
        f"started_at should be the first captured timestamp (T001, "
        f"captured at the top of run()), not {result['started_at']!r}."
    )


def test_started_at_independent_across_concurrent_runs(
    tmp_path, tiny_task_path, monkeypatch,
):
    """Two runs that overlap in time must each report their OWN started_at,
    not the most-recent value written by any thread. Under a module-global
    implementation, the later run's start timestamp clobbers the earlier
    run's value before the earlier run's `_result()` reads it back.

    Mocks `_utc_now_iso()` with a counter so each call returns a distinct
    `T001`, `T002`, ... value. Threads two `run()` calls with worker 1
    delayed enough to force overlap. Under the racy global, both results
    would carry the LATER T-value; under the local-var refactor, each
    result carries its OWN first-call value.
    """
    import threading
    import time
    import shutil as _shutil
    from cae.harness import run as harness_run

    counter = {"n": 0}
    counter_lock = threading.Lock()

    def fake_now_iso():
        with counter_lock:
            counter["n"] += 1
            return f"T{counter['n']:03d}"

    monkeypatch.setattr("cae.harness._utc_now_iso", fake_now_iso)

    # Two task dirs with distinct instance_ids (so result filenames don't collide).
    tasks_dir = tmp_path / "tasks"
    task_paths = []
    for name in ("tiny__task-A", "tiny__task-B"):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        (t / "task.json").write_text(
            (tiny_task_path / "task.json").read_text().replace('"tiny__task-1"', f'"{name}"'))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                _shutil.copytree(child, dest)
            else:
                _shutil.copy2(child, dest)
        task_paths.append(t)

    results: list[dict | None] = [None, None]
    errors: list[Exception | None] = [None, None]

    def worker(idx, pre_delay):
        try:
            time.sleep(pre_delay)
            results[idx] = harness_run(
                task_path=task_paths[idx],
                agent_name="mock",
                workdir=tmp_path / f"wd{idx}",
                timeout_sec=30,
            )
        except Exception as e:
            errors[idx] = e

    t1 = threading.Thread(target=worker, args=(0, 0.0))
    t2 = threading.Thread(target=worker, args=(1, 0.05))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors[0] is None, f"worker 0 raised: {errors[0]!r}"
    assert errors[1] is None, f"worker 1 raised: {errors[1]!r}"
    assert results[0] is not None and results[1] is not None

    # Each result's started_at must be the value _utc_now_iso() returned at
    # the top of THIS run() — i.e., the two values must differ. Under the
    # racy global, both would carry whichever thread wrote last.
    assert results[0]["started_at"] != results[1]["started_at"], (
        f"both runs reported the same started_at ({results[0]['started_at']!r}) "
        f"— suggests a shared global is being clobbered across concurrent "
        f"run() calls."
    )


def test_preflight_task_error_records_agent_model_and_version(
    tmp_path, tiny_task_path, mock_with_model,
):
    """When pre-flight fails (test names don't match pytest output), the result
    should still record agent_version and agent_model so the leaderboard doesn't
    group pre-flight failures as a separate '(unknown)' row."""
    import json

    bad_task = tmp_path / "bad_task"
    bad_task.mkdir()
    (bad_task / "task.json").write_text(json.dumps({
        "instance_id": "bad__task-1",
        "repo": "bad/repo",
        "base_commit": "0" * 40,
        "prompt": "do something",
        "setup_cmd": "",
        "test_cmd": "python -m pytest -vs",
        # pytest will run test_main.py::test_add and test_main.py::test_multiply.
        # Pretend fail_to_pass/pass_to_pass reference tests that don't exist.
        "fail_to_pass": ["test_main.py::test_does_not_exist"],
        "pass_to_pass": ["test_main.py::test_also_missing"],
    }))
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    result = run(task_path=bad_task, agent_name="mock-model", workdir=workdir)

    assert result["status"] == "task_error"
    # agent_version + agent_model are captured even though the agent never ran.
    assert result["agent_version"] == "test-mock-0.1.0"
    assert result["model"] == "test-model-1"
    # And the error message is diagnostic, listing what was missing.
    assert "not in pytest output" in result["error"]
    assert "fail_to_pass" in result["error"]
    assert "pass_to_pass" in result["error"]


def test_dry_run_short_circuits_before_agent_call(
    tmp_path, tiny_task_path, fixing_mock,
):
    """--dry-run runs setup and pre-flight, then stops before invoking the
    agent. The result has status='dry_run' and a would_run_command field
    containing the adapter's build_command argv. No agent subprocess is
    actually executed."""
    from cae.harness import run as harness_run

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # fixing_mock.build_command returns [py, "-c", script, workdir]. Under
    # dry-run we expect this exact argv to surface in the result and the
    # script to NOT have been executed (so main.py keeps its bug).
    result = harness_run(
        task_path=tiny_task_path,
        agent_name="mock",
        workdir=workdir,
        timeout_sec=30,
        dry_run=True,
    )

    assert result["status"] == "dry_run", (
        f"expected dry_run, got {result['status']!r}"
    )
    assert "would_run_command" in result, "result must include would_run_command"
    cmd = result["would_run_command"]
    # The command is the list returned by _FixingMock.build_command.
    assert isinstance(cmd, (list, str)) and cmd, "would_run_command must be non-empty"
    # main.py still contains the bug — the fixing script did NOT run.
    assert "return a - b" in (workdir / "main.py").read_text(), (
        "dry-run must not have invoked the agent (main.py still has the bug)"
    )
    # Pre-flight ran (the harness validated test IDs); post-flight did not.
    assert "pre_flight" in result["test_results"]
    assert result["test_results"].get("post_flight") in (None, {}, ""), (
        "dry-run must not populate post_flight (no patch to grade against)"
    )
    # No patch (agent didn't run, no diff to capture).
    assert result["patch"] == ""


def test_dry_run_cleans_up_owned_workdir(tmp_path, tiny_task_path, fixing_mock):
    """The dry-run short-circuit must NOT leak the tempdir it created.
    The workdir cleanup at the end of run() only runs on the success path;
    a previous version of dry-run returned before that cleanup, leaving
    a /tmp/cae-* directory behind on every dry-run invocation. Under
    --parallel N --dry-run, that would leak N tempdirs per batch.

    Regression: pass workdir=None (so the harness creates + owns the
    tempdir) and keep_workdir=False, then assert the tempdir is gone
    after the call returns."""
    import os
    from cae.harness import run as harness_run

    result = harness_run(
        task_path=tiny_task_path,
        agent_name="mock",
        workdir=None,           # harness creates + owns the tempdir
        timeout_sec=30,
        keep_workdir=False,
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    workdir_path = result["workdir"]
    assert workdir_path, "result must record the workdir path"
    assert not os.path.exists(workdir_path), (
        f"dry-run leaked tempdir at {workdir_path}; cleanup must run "
        f"on the dry-run return path too"
    )


def test_dry_run_skips_is_available_check(tmp_path, tiny_task_path, monkeypatch):
    """--dry-run should short-circuit BEFORE the is_available() check.
    Otherwise on a machine that doesn't have the agent binary installed
    (a common sanity-check scenario — 'what would this parallel batch
    actually invoke?'), dry-run returns agent_error instead of dry_run
    and the user never sees would_run_command.

    Test: register a custom adapter whose is_available() returns False,
    run with dry_run=True, assert status='dry_run' and would_run_command
    is populated. The adapter's build_command still works because it
    just assembles an argv list — it doesn't need the binary on PATH."""
    from cae.agents import ADAPTERS
    from cae.agents.mock import MockAdapter
    from cae.harness import run as harness_run

    class _UnavailableMock(MockAdapter):
        name = "unavailable-mock"
        default_model = "test-model-1"
        def is_available(self) -> bool:
            return False
        def build_command(self, workdir, prompt, *, model):
            return ["fake-agent-binary", "--workdir", str(workdir), "--prompt", prompt]

    # Set up workdir with the tiny task's repo so pre-flight can pass.
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    ADAPTERS["unavailable-mock"] = _UnavailableMock
    try:
        result = harness_run(
            task_path=tiny_task_path,
            agent_name="unavailable-mock",
            workdir=workdir,
            timeout_sec=30,
            dry_run=True,
        )
    finally:
        ADAPTERS.pop("unavailable-mock", None)

    assert result["status"] == "dry_run", (
        f"expected dry_run (not agent_error from is_available()=False), "
        f"got {result['status']!r}"
    )
    assert result["would_run_command"] == [
        "fake-agent-binary", "--workdir", str(workdir),
        "--prompt", "Fix the add() function so it returns a + b instead of a - b.",
    ], result["would_run_command"]


def test_run_threads_per_stage_timeouts_to_run_step(
    tmp_path, tiny_task_path, fixing_mock, monkeypatch,
):
    """Per-stage timeouts (timeout_setup, timeout_agent, timeout_tests) must
    reach the underlying subprocess dispatcher with their distinct values.
    We spy on _run_subprocess to verify each stage is invoked with its
    specific timeout — not the global default."""
    from cae.harness import run as harness_run
    import cae.harness as harness_mod

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # Spy on _run_subprocess to capture the timeout each call used.
    captured: list[int] = []
    real_run_subprocess = harness_mod._run_subprocess
    def spy(cmd, cwd, timeout):
        captured.append(timeout)
        return real_run_subprocess(cmd, cwd, timeout)

    monkeypatch.setattr(harness_mod, "_run_subprocess", spy)

    harness_run(
        task_path=tiny_task_path,
        agent_name="mock",
        workdir=workdir,
        timeout_sec=999,           # global default — should NOT be used
        timeout_setup=11,
        timeout_agent=22,
        timeout_tests=33,
    )

    # The harness makes these _run_subprocess calls in order:
    #   1. pre-flight test_cmd (timeout_tests=33)
    #   2. agent build_command result (timeout_agent=22)
    #   3. grade test_cmd (timeout_tests=33)
    # (setup_cmd is empty for tiny_task so no setup call.)
    assert 22 in captured, f"agent timeout not threaded through: {captured}"
    assert captured.count(33) >= 2, (
        f"expected at least 2 test_cmd calls (pre-flight + grade) with "
        f"timeout_tests=33; got {captured}"
    )
    # The global 999 default must NOT appear anywhere — per-stage values win.
    assert 999 not in captured, (
        f"per-stage timeouts didn't override the global default: {captured}"
    )


def test_harness_agent_errors_when_validate_env_returns_a_message(
    tmp_path, tiny_task_path, monkeypatch,
):
    """When validate_env() returns a non-None message, the harness must:
    1. Return status='agent_error'
    2. Include the message in the error field
    3. NOT execute setup_cmd (proving the check ran before setup)
    """
    from cae.agents import ADAPTERS
    from cae.agents.mock import MockAdapter
    from cae.harness import run as harness_run

    class _BadEnvMock(MockAdapter):
        name = "bad-env-mock"
        default_model = "test-model-1"
        def validate_env(self) -> str | None:
            return "ANTHROPIC_API_KEY not set"

    # Set up workdir with a setup_cmd that creates a marker file.
    # If validate_env() runs BEFORE setup, the marker file is never created.
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # Use a custom task.json that includes a setup_cmd creating a marker.
    import json
    bad_task = tmp_path / "bad_task"
    bad_task.mkdir()
    task_data = json.loads((tiny_task_path / "task.json").read_text())
    task_data["setup_cmd"] = f"touch {workdir / 'SETUP_RAN.marker'}"
    (bad_task / "task.json").write_text(json.dumps(task_data))

    ADAPTERS["bad-env-mock"] = _BadEnvMock
    try:
        result = harness_run(
            task_path=bad_task,
            agent_name="bad-env-mock",
            workdir=workdir,
            timeout_sec=30,
        )
    finally:
        ADAPTERS.pop("bad-env-mock", None)

    assert result["status"] == "agent_error", (
        f"expected agent_error, got {result['status']}"
    )
    assert "ANTHROPIC_API_KEY" in (result["error"] or ""), result["error"]
    # The marker file must NOT exist — setup didn't run.
    assert not (workdir / "SETUP_RAN.marker").exists(), (
        "setup_cmd ran anyway — validate_env check is in the wrong place "
        "(must run BEFORE setup)"
    )
