"""Aider CLI adapter.

Invokes `aider --yes --message <prompt>` in the workdir. Aider doesn't emit
structured JSON by default, so cost and tokens are unknown (null) unless the
user pipes `--analytics` or similar. The adapter still runs the agent and
captures the patch via the harness's git diff.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentResult, UsageInfo


class AiderAdapter:
    name = "aider"
    default_model = None  # aider uses the user's configured model; no cae default

    def is_available(self) -> bool:
        return shutil.which("aider") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            return subprocess.check_output(["aider", "--version"], text=True).strip()
        except Exception as e:
            return f"unknown ({e})"

    def validate_env(self) -> str | None:
        """Aider supports multiple backends (Anthropic, OpenAI, local LLMs),
        each with its own env requirements. The backend is chosen at runtime
        via --model, so we can't check generically here. Returns None until
        a follow-up adds per-backend checks."""
        return None

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = ["aider", "--yes", "--message", prompt, "--no-auto-commits"]
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=None, tokens_out=None,
                cost_usd=None, model=None, billing_mode="api",
            ),
            exit_code=exit_code,
        )
