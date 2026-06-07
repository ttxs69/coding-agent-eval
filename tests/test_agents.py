import json
import subprocess
from pathlib import Path

import pytest

from pae.agents import get_adapter, list_adapters
from pae.agents.mock import MockAdapter


def test_mock_adapter_is_available():
    assert MockAdapter().is_available() is True


def test_mock_adapter_version():
    assert MockAdapter().version() == "mock-0.1.0"


def test_mock_adapter_build_command_runs_a_subprocess():
    cmd = MockAdapter().build_command(Path("/tmp"), "do the thing", model=None)
    assert isinstance(cmd, list)
    assert cmd[0]  # non-empty argv


def test_mock_adapter_does_not_modify_workdir(tmp_path: Path):
    """The default mock is a no-op. Running its command in a git-initialized
    workdir should leave the workdir unchanged (no diff after the run)."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    (workdir / "main.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    adapter = MockAdapter()
    cmd = adapter.build_command(workdir, "fix the bug", model=None)
    subprocess.run(cmd, cwd=workdir, check=True, capture_output=True)
    diff = subprocess.run(["git", "diff"], cwd=workdir, capture_output=True, text=True)
    assert diff.stdout.strip() == ""


def test_get_adapter_returns_mock_instance():
    adapter = get_adapter("mock")
    assert isinstance(adapter, MockAdapter)


def test_get_adapter_unknown_raises():
    with pytest.raises(ValueError, match="Unknown agent adapter"):
        get_adapter("does-not-exist")


def test_list_adapters_includes_mock():
    names = [a["name"] for a in list_adapters()]
    assert "mock" in names
    # mock is always available (it's a Python class, not a CLI)
    mock_entry = next(a for a in list_adapters() if a["name"] == "mock")
    assert mock_entry["available"] is True


def test_claude_code_adapter_build_command_includes_prompt():
    from pae.agents.claude_code import ClaudeCodeAdapter
    cmd = ClaudeCodeAdapter().build_command(Path("/tmp/x"), "do the thing", model=None)
    assert cmd[0] == "claude"
    # prompt should appear somewhere in the argv
    assert any("do the thing" in str(arg) for arg in cmd)
    # output-format json so we can parse cost/tokens reliably
    assert any("json" in str(arg) for arg in cmd)


def test_claude_code_parse_output_extracts_usage():
    from pae.agents.claude_code import ClaudeCodeAdapter
    # Claude Code's --output-format json emits a final assistant message with usage
    fake_json = json.dumps({
        "type": "result",
        "total_cost_usd": 0.12,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "model": "claude-opus-4-7",
    })
    result = ClaudeCodeAdapter().parse_output(fake_json, "", 0)
    assert result.usage.cost_usd == 0.12
    assert result.usage.tokens_in == 100
    assert result.usage.tokens_out == 50
    assert result.usage.model == "claude-opus-4-7"


def test_codex_adapter_build_command_includes_prompt():
    from pae.agents.codex import CodexAdapter
    cmd = CodexAdapter().build_command(Path("/tmp/x"), "do the thing", model=None)
    assert cmd[0] == "codex"
    assert any("do the thing" in str(arg) for arg in cmd)
    # codex uses --json for parseable output
    assert any("json" in str(arg) for arg in cmd)


def test_codex_parse_output_extracts_usage():
    from pae.agents.codex import CodexAdapter
    fake = json.dumps({
        "type": "turn.completed",
        "usage": {"input_tokens": 200, "output_tokens": 80, "cost_usd": 0.05},
        "model": "gpt-5",
    })
    result = CodexAdapter().parse_output(fake, "", 0)
    assert result.usage.cost_usd == 0.05
    assert result.usage.tokens_in == 200
    assert result.usage.tokens_out == 80
    assert result.usage.model == "gpt-5"
