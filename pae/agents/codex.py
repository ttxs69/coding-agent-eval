"""Codex CLI adapter.

Invokes `codex -q <prompt> --json` in the workdir. Parses the final
turn.completed event for cost/tokens/model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pae.agents.base import AgentResult, UsageInfo


class CodexAdapter:
    name = "codex"
    default_model = "gpt-5"

    def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            return subprocess.check_output(["codex", "--version"], text=True).strip()
        except Exception as e:
            return f"unknown ({e})"

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = [
            "codex", "exec", prompt,
            "--json",  # JSONL event stream to stdout
            # Required for non-interactive (subprocess) use — without it, codex
            # asks for confirmation before running shell commands and the run hangs.
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model:
            cmd += ["-m", model]  # codex uses short -m for model
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        cost = None
        tokens_in = None
        tokens_out = None
        model = None
        try:
            for line in stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                obj = json.loads(line)
                if obj.get("type") == "turn.completed":
                    usage = obj.get("usage") or {}
                    cost = usage.get("cost_usd")
                    tokens_in = usage.get("input_tokens")
                    tokens_out = usage.get("output_tokens")
                    model = obj.get("model")
        except Exception:
            pass
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost, model=model, billing_mode="api",
            ),
            exit_code=exit_code,
        )
