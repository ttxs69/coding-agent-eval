"""Claude Code CLI adapter.

Invokes `claude -p <prompt> --output-format json` in the workdir and parses the
final JSON envelope for cost/tokens. is_available() runs `claude --version` to
confirm the binary is on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pae.agents.base import AgentResult, UsageInfo


class ClaudeCodeAdapter:
    name = "claude-code"
    default_model = "claude-opus-4-7"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            out = subprocess.check_output(["claude", "--version"], text=True, stderr=subprocess.STDOUT)
            return out.strip().split("\n")[0]
        except Exception as e:
            return f"unknown ({e})"

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        cost = None
        tokens_in = None
        tokens_out = None
        model = None
        # Claude Code's --output-format json emits a final JSON envelope. The
        # harness may also have other JSON lines (tool calls etc.) — we look
        # for the last "type": "result" entry.
        try:
            envelope = None
            for line in stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                obj = json.loads(line)
                if obj.get("type") == "result":
                    envelope = obj
            if envelope is not None:
                cost = envelope.get("total_cost_usd")
                usage = envelope.get("usage") or {}
                tokens_in = usage.get("input_tokens")
                tokens_out = usage.get("output_tokens")
                model = envelope.get("model")
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
