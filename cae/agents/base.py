"""Core types: AgentAdapter Protocol, AgentResult, UsageInfo, status enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Protocol, runtime_checkable

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of 3.11 StrEnum for older versions."""


class Status(StrEnum):
    """Top-level task status."""

    RESOLVED = "resolved"
    FAILED = "failed"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    TASK_ERROR = "task_error"
    GRADER_ERROR = "grader_error"
    DRY_RUN = "dry_run"


class TestStatus(StrEnum):
    """Per-test status (the spec's 5-value enum)."""

    # Tell pytest not to treat this as a test class (it starts with "Test").
    __test__ = False

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAIL = "xfail"


@dataclass
class UsageInfo:
    """Best-effort token and cost accounting. Fields are None when unknown.

    `tokens_in` is the *uncached* fresh input tokens. Cached input tokens
    are reported separately as `cache_read_tokens` (cache hits) and
    `cache_creation_tokens` (cache writes). All three contribute to
    billing on most APIs, but at different per-token rates.
    """

    tokens_in: int | None = None
    tokens_out: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    cost_usd: float | None = None
    model: str | None = None
    billing_mode: str = "api"  # "api" or "subscription"


@dataclass
class AgentResult:
    """Per-run output of an agent adapter (before harness extracts the patch)."""

    log: str = ""
    usage: UsageInfo = field(default_factory=UsageInfo)
    exit_code: int = 0
    duration_sec: float = 0.0


@runtime_checkable
class AgentAdapter(Protocol):
    """Contract every CLI agent adapter implements."""

    name: str
    default_model: str | None

    def is_available(self) -> bool:
        """True if the agent's CLI binary is installed and on PATH.

        The harness uses this to skip adapters whose agents aren't installed
        when iterating over registered adapters.
        """
        ...

    def version(self) -> str:
        """Version string (e.g. ``"claude-code 1.0.0"``).

        Returns ``"not-installed"`` or ``"unknown (<error>)"`` if the binary
        is missing or fails to report a version. Captured before the agent
        runs so every result row — even ``task_error`` — records agent identity.
        """
        ...

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        """Argv list to invoke the agent on ``prompt`` with cwd=``workdir``.

        ``model`` overrides ``default_model`` when given; adapters that don't
        support per-run model selection may ignore it. The harness runs the
        returned list directly via subprocess (or wraps it in ``sh -c`` for
        docker mode).
        """
        ...

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        """Convert the agent's stdout/stderr/exit_code into an ``AgentResult``.

        Populates usage (tokens, cost, model) and the raw log. The harness
        extracts the patch via ``git diff`` separately — this method should
        NOT try to parse the patch from agent output.
        """
        ...

    def validate_env(self) -> str | None:
        """Return None if the runtime environment is OK (API keys set,
        config files readable, etc.); otherwise return a short human-
        readable description of the problem (e.g. ``"ANTHROPIC_API_KEY
        not set and ~/.claude/settings.json has no API key"``).

        The harness calls this BEFORE setup so a broken env fails fast
        — saving the 1–10 minutes of pip install / astropy build that
        would otherwise happen before the agent subprocess discovers
        the problem. Default for adapters that don't override: None
        (no specific requirement).
        """
        ...
