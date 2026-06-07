"""Shared pytest fixtures for pae tests."""

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="session")
def _ensure_python_on_path():
    """Make the running interpreter's bin dir visible on PATH for harness subprocesses.

    Task fixtures specify `test_cmd: "python -m pytest ..."`. When pytest is invoked
    via `.venv/bin/pytest` without activating the venv, `.venv/bin` is not on PATH
    and the harness's `shell=True` subprocess can't resolve `python`. This shim is
    equivalent to `source .venv/bin/activate` for the purpose of subprocess PATH.
    """
    bin_dir = str(Path(sys.executable).parent)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if bin_dir not in parts:
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    yield


@pytest.fixture
def tiny_task_path() -> Path:
    """Path to the in-tree tiny task fixture, used by harness integration tests."""
    return Path(__file__).parent / "fixtures" / "tiny_task"
