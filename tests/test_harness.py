import shutil
import subprocess

import pytest

from pae.agents import ADAPTERS
from pae.agents.mock import MockAdapter
from pae.harness import run


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
