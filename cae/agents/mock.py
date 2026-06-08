"""MockAdapter: a no-op CLI stub for harness smoke tests and unit tests.

This adapter is for tests and smoke runs only. It is registered as a first-class
adapter so the harness exercises every code path, but cae build-site filters
its results out of the public leaderboard.

Behavior
--------
The default `MockAdapter` does NOT modify the workdir — it spawns `python3 -c
"import sys; sys.exit(0)"`, which exits 0 without touching anything. The
harness then runs `git diff` (no changes → empty patch) and grades the
result against the task's test_cmd. For most SWE-bench tasks, this means
the tests will fail (the bug is still there) and the result is `failed`.
For `tests/fixtures/tiny_task`, the harness's pre-flight check also fails
because the test names don't match what pytest emits — so the result is
`task_error`, not `failed`. Either way, the mock is a no-op smoke test
that exercises the harness's plumbing without paying for an LLM call.

The `_FixingMock` test fixture in `tests/test_harness.py` is a different
mock that DOES modify the workdir (it applies the gold fix to `main.py`).
It exists to give the integration test a deterministic "this task should
resolve" scenario without needing a real agent or API key. To use it,
the test re-registers it under the `mock` key in the ADAPTERS dict
for the duration of the test.
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
