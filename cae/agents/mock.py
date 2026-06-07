"""MockAdapter: a no-op CLI stub for harness smoke tests and unit tests.

This adapter is for tests and smoke runs only. It is registered as a first-class
adapter so the harness exercises every code path, but pae build-site filters
its results out of the public leaderboard. The default mock does NOT modify
the workdir — tests that need a known patch should pre-apply the patch to the
workdir before calling harness.run.
"""

from __future__ import annotations

from pathlib import Path

from cae.agents.base import AgentResult, UsageInfo


MOCK_VERSION = "mock-0.1.0"


class MockAdapter:
    name = "mock"
    default_model = None

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return MOCK_VERSION

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        # Use `python3` (not a host-resolved path) so this works in both local
        # mode (the harness prepends the venv bin to PATH, which has python3)
        # and docker mode (the container has its own /usr/local/bin/python3).
        return ["python3", "-c", "import sys; sys.exit(0)"]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(tokens_in=0, tokens_out=0, cost_usd=0.0, model=None, billing_mode="api"),
            exit_code=exit_code,
            duration_sec=0.0,
        )
