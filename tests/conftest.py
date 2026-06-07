"""Shared pytest fixtures for pae tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tiny_task_path() -> Path:
    """Path to the in-tree tiny task fixture, used by harness integration tests."""
    return Path(__file__).parent / "fixtures" / "tiny_task"
