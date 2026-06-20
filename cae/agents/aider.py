"""Aider CLI adapter.

Invokes `aider --yes --message <prompt>` in the workdir. Aider prints a
summary line at the end of each run shaped like::

    Tokens: 667 sent, 64 received. Cost: $0.0049 message, $0.0049 session.

We regex-scan stdout for the last such line and extract tokens + cost.
If aider crashes before printing it (or the format changes), tokens and
cost stay None — we don't guess. The patch is captured separately by
the harness via ``git diff``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentResult, UsageInfo

# Match the LAST occurrence in case aider prints interim tallies.
# Shape: "Tokens: <int> sent, <int> received. Cost: $<float> message, $<float> session."
_USAGE_RE = re.compile(
    r"Tokens:\s*(?P<tin>\d+)\s+sent,\s*(?P<tout>\d+)\s+received\."
    r"\s*Cost:\s*\$(?P<cost>[\d.]+)\s+message,\s*\$(?P<session>[\d.]+)\s+session"
)


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
        tokens_in = None
        tokens_out = None
        cost = None
        # finditer so we get the last match (aider prints interim tallies too).
        matches = list(_USAGE_RE.finditer(stdout))
        if matches:
            m = matches[-1]
            tokens_in = int(m.group("tin"))
            tokens_out = int(m.group("tout"))
            # Session cost is the cumulative bill for the whole run; that's
            # what we want for the leaderboard. (Message cost is per-turn.)
            cost = float(m.group("session"))
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost, model=None, billing_mode="api",
            ),
            exit_code=exit_code,
        )
