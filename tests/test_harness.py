import shutil
import subprocess
from pathlib import Path

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
    import json

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
    import json

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
