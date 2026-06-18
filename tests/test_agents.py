import json
import subprocess
from pathlib import Path

import pytest

from cae.agents import get_adapter, list_adapters
from cae.agents.mock import MockAdapter


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
    from cae.agents.claude_code import ClaudeCodeAdapter
    cmd = ClaudeCodeAdapter().build_command(Path("/tmp/x"), "do the thing", model=None)
    assert cmd[0] == "claude"
    # prompt should appear somewhere in the argv
    assert any("do the thing" in str(arg) for arg in cmd)
    # output-format json so we can parse cost/tokens reliably
    assert any("json" in str(arg) for arg in cmd)


def test_claude_code_parse_output_extracts_usage():
    from cae.agents.claude_code import ClaudeCodeAdapter
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
    from cae.agents.codex import CodexAdapter
    cmd = CodexAdapter().build_command(Path("/tmp/x"), "do the thing", model=None)
    assert cmd[0] == "codex"
    assert any("do the thing" in str(arg) for arg in cmd)
    # codex uses --json for parseable output
    assert any("json" in str(arg) for arg in cmd)


def test_codex_parse_output_extracts_usage():
    from cae.agents.codex import CodexAdapter
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
    # No cache fields in the input — defaults to None.
    assert result.usage.cache_read_tokens is None
    assert result.usage.cache_creation_tokens is None


def test_claude_parse_output_extracts_cache_tokens():
    """cache_read_input_tokens and cache_creation_input_tokens are part of
    Anthropic's billing model (cache reads cost ~10% of fresh input) so we
    capture them separately."""
    from cae.agents.claude_code import ClaudeCodeAdapter
    fake = json.dumps({
        "type": "result",
        "total_cost_usd": 0.42,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 9000,
            "cache_creation_input_tokens": 200,
        },
        "model": "claude-opus-4-7",
    })
    result = ClaudeCodeAdapter().parse_output(fake, "", 0)
    assert result.usage.tokens_in == 100
    assert result.usage.tokens_out == 50
    assert result.usage.cache_read_tokens == 9000
    assert result.usage.cache_creation_tokens == 200


def test_claude_parse_output_handles_missing_envelope():
    """If stdout has no valid JSON result envelope (claude crashed early,
    timed out, returned an error message, etc.), parse_output must still
    return a valid AgentResult — not raise NameError.

    Regression: cache_read/cache_creation were only assigned inside the
    `if envelope is not None:` branch; the return statement then referenced
    them unconditionally and crashed with NameError when no envelope was
    found.
    """
    from cae.agents.claude_code import ClaudeCodeAdapter
    # Real-world cases this covers:
    # - claude crashed before printing any JSON
    # - claude printed only tool-call JSON (no `type: result`)
    # - the output is plain stderr text
    for bad_stdout in ("", "Claude crashed.", "{\"type\": \"tool_use\"}\n", "not json at all"):
        result = ClaudeCodeAdapter().parse_output(bad_stdout, "some stderr", 1)
        assert result.usage.tokens_in is None
        assert result.usage.tokens_out is None
        assert result.usage.cost_usd is None
        assert result.usage.cache_read_tokens is None
        assert result.usage.cache_creation_tokens is None
        assert result.exit_code == 1


def test_codex_parse_output_extracts_cached_input_tokens():
    """Codex may use `cached_input_tokens` (its naming convention)."""
    from cae.agents.codex import CodexAdapter
    fake = json.dumps({
        "type": "turn.completed",
        "usage": {
            "input_tokens": 200,
            "output_tokens": 80,
            "cached_input_tokens": 5000,
            "cache_creation_input_tokens": 100,
        },
        "model": "gpt-5",
    })
    result = CodexAdapter().parse_output(fake, "", 0)
    assert result.usage.tokens_in == 200
    assert result.usage.cache_read_tokens == 5000
    assert result.usage.cache_creation_tokens == 100


def test_aider_adapter_build_command_includes_prompt():
    from cae.agents.aider import AiderAdapter
    cmd = AiderAdapter().build_command(Path("/tmp/x"), "do the thing", model=None)
    assert cmd[0] == "aider"
    assert "do the thing" in cmd
    # aider uses --yes for non-interactive runs
    assert "--yes" in cmd or "-y" in cmd


def test_aider_parse_output_no_native_json():
    """Aider doesn't emit JSON by default; cost is unknown."""
    from cae.agents.aider import AiderAdapter
    result = AiderAdapter().parse_output("Aider ran.", "", 0)
    assert result.usage.cost_usd is None
    assert result.usage.tokens_in is None
    assert result.exit_code == 0


def test_validate_env_is_part_of_protocol():
    """The AgentAdapter Protocol declares validate_env() so the harness
    can fail fast on missing API keys / config before setup runs."""
    from cae.agents.base import AgentAdapter
    # runtime_checkable Protocols check method existence via hasattr.
    # A class with all four existing methods but NOT validate_env should
    # NOT satisfy the Protocol after we add the method.
    class _MissingValidateEnv:
        name = "x"
        default_model = None
        def is_available(self): return True
        def version(self): return "x"
        def build_command(self, workdir, prompt, *, model): return []
        def parse_output(self, stdout, stderr, exit_code):
            from cae.agents.base import AgentResult
            return AgentResult()
    assert not isinstance(_MissingValidateEnv(), AgentAdapter), (
        "Protocol must require validate_env() after Task 1"
    )


def test_mock_adapter_validate_env_returns_none():
    """MockAdapter's validate_env() returns None — mock has no env
    requirements. Locks the default behavior."""
    from cae.agents.mock import MockAdapter
    assert MockAdapter().validate_env() is None
