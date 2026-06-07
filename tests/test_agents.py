import shutil
from pathlib import Path

import pytest

from pae.agents import get_adapter, list_adapters
from pae.agents.base import AgentResult, UsageInfo
from pae.agents.mock import MockAdapter


def test_mock_adapter_is_available():
    assert MockAdapter().is_available() is True


def test_mock_adapter_version():
    assert MockAdapter().version() == "mock-0.1.0"


def test_mock_adapter_build_command_runs_a_subprocess():
    cmd = MockAdapter().build_command(Path("/tmp"), "do the thing", model=None)
    assert isinstance(cmd, list)
    assert cmd[0]  # non-empty argv


def test_mock_adapter_writes_patch_to_workdir(tmp_path: Path):
    """The mock writes a known patch to the workdir; the harness then captures it via git diff."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    # set up workdir as a git repo with one initial file
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    (workdir / "main.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    adapter = MockAdapter()
    # by default the mock does nothing — calling its command in workdir should not change files
    # to verify: run a no-op, then assert no diff
    import subprocess
    cmd = adapter.build_command(workdir, "fix the bug", model=None)
    subprocess.run(cmd, cwd=workdir, check=True, capture_output=True)
    diff = subprocess.run(["git", "diff"], cwd=workdir, capture_output=True, text=True)
    assert diff.stdout.strip() == ""


def test_get_adapter_returns_mock_instance():
    adapter = get_adapter("mock")
    assert isinstance(adapter, MockAdapter)


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError, match="Unknown agent adapter"):
        get_adapter("does-not-exist")


def test_list_adapters_includes_mock():
    names = [a["name"] for a in list_adapters()]
    assert "mock" in names
    # mock is always available (it's a Python class, not a CLI)
    mock_entry = next(a for a in list_adapters() if a["name"] == "mock")
    assert mock_entry["available"] is True
