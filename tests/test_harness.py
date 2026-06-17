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
