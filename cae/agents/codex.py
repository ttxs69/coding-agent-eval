"""Codex CLI adapter.

Invokes `codex -q <prompt> --json` in the workdir. Parses the final
turn.completed event for cost/tokens/model.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentResult, UsageInfo


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

    def validate_env(self) -> str | None:
        """Codex CLI reads its API key from OPENAI_API_KEY (or its own
        config). The CLI handles auth failures itself, so we only do a
        light check here. Returns None until a follow-up tightens this."""
        return None

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

    def _discover_model(self) -> str | None:
        """Best-effort: try to read the model from codex's config.toml.

        Codex doesn't expose the active model in its JSONL output. The most
        reliable source is the user's config file (e.g.~/.codex/config.toml),
        which has a `model = "..."` line. Falls back to default_model if
        the config isn't readable (e.g. in a container without a mount).
        """
        try:
            config_path = Path(
                os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex"))
            ) / "config.toml"
            if config_path.exists():
                for line in config_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("model = "):
                        return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return self.default_model

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        cost = None
        tokens_in = None
        tokens_out = None
        cache_read = None
        cache_creation = None
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
                    # Codex's schema may evolve; capture cache fields
                    # opportunistically and leave None if absent.
                    cache_read = usage.get("cached_input_tokens") or usage.get("cache_read_input_tokens")
                    cache_creation = usage.get("cache_creation_input_tokens")
                    # Model is not in turn.completed; try other places
                    model = obj.get("model") or obj.get("model_id")
        except Exception:
            pass
        # If no model found in output, read from codex's config
        if model is None:
            model = self._discover_model()
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=tokens_in, tokens_out=tokens_out,
                cache_read_tokens=cache_read,
                cache_creation_tokens=cache_creation,
                cost_usd=cost, model=model, billing_mode="api",
            ),
            exit_code=exit_code,
        )
