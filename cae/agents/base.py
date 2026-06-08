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
    """Top-level task status (the spec's 6-value enum)."""

    RESOLVED = "resolved"
    FAILED = "failed"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    TASK_ERROR = "task_error"
    GRADER_ERROR = "grader_error"


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

    def is_available(self) -> bool: ...
    def version(self) -> str: ...
    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]: ...
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult: ...
