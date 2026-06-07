"""MockAdapter: a no-op CLI stub for harness smoke tests and unit tests.

This adapter is for tests and smoke runs only. It is registered as a first-class
adapter so the harness exercises every code path, but pae build-site filters
its results out of the public leaderboard. The default mock does NOT modify
the workdir — tests that need a known patch should pre-apply the patch to the
workdir before calling harness.run.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pae.agents.base import AgentAdapter, AgentResult, UsageInfo


MOCK_VERSION = "mock-0.1.0"


class MockAdapter:
    name = "mock"
    default_model = None

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return MOCK_VERSION

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        # The mock does its work in the constructor of the subprocess via a small
        # Python one-liner. We pass the workdir as the only arg. The "agent" is
        # no-op for the default mock — the harness then sees a clean diff.
        # Use sys.executable as the ultimate fallback so the mock works on systems
        # (e.g. macOS) where `python` is not in PATH but only `python3` is.
        python = shutil.which("python") or shutil.which("python3") or sys.executable
        return [python, "-c", "import sys; sys.exit(0)"]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(tokens_in=0, tokens_out=0, cost_usd=0.0, model=None, billing_mode="api"),
            exit_code=exit_code,
            duration_sec=0.0,
        )
