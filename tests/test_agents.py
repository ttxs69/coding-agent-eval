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
    """Aider's usage is in a 'Tokens: X sent, Y received. Cost: $Z ...' line,
    not JSON. If that line is missing from stdout (e.g. aider crashed early),
    tokens + cost stay None — we don't guess."""
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


def test_real_adapters_satisfy_protocol():
    """All registered adapters must satisfy isinstance(x, AgentAdapter).
    Adding validate_env() to the Protocol made this fail for duck-typed
    adapters (claude_code/codex/aider) that don't explicitly define the
    method. Each adapter must override validate_env() — even just to
    return None — to keep the runtime_checkable contract honest."""
    from cae.agents import ADAPTERS
    from cae.agents.base import AgentAdapter
    failing = []
    for name, cls in ADAPTERS.items():
        # Instantiate; some adapters may take no constructor args.
        try:
            instance = cls()
        except Exception as e:
            failing.append(f"{name}: failed to instantiate ({e!r})")
            continue
        if not isinstance(instance, AgentAdapter):
            failing.append(name)
    assert not failing, (
        f"these adapters fail isinstance(x, AgentAdapter): {failing}. "
        f"Each must override validate_env() to satisfy the Protocol."
    )


def test_codex_parse_output_computes_cost_from_tokens_for_known_model(monkeypatch):
    """Codex CLI doesn't emit cost_usd in its turn.completed event — only
    token counts. The adapter must compute cost = tokens × pricing for
    models in the pricing table. Verifies the math: input + output + cache
    fields each multiplied by their per-million-token price."""
    from cae.agents.codex import CodexAdapter
    # Bypass _discover_model() so the test is hermetic — we control which
    # model the cost computation sees. claude-sonnet-4-6 is in the default
    # pricing table.
    adapter = CodexAdapter()
    monkeypatch.setattr(adapter, "_discover_model", lambda: "claude-sonnet-4-6")
    # Simulate codex's actual output shape (verified via `codex exec --json`):
    # {"type":"turn.completed","usage":{"input_tokens":N,"cached_input_tokens":N,
    #                                    "output_tokens":N,"reasoning_output_tokens":N}}
    # No cost_usd field — codex CLI doesn't emit it.
    fake_stdout = (
        '{"type":"thread.started","thread_id":"x"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"turn.completed","usage":{'
        '"input_tokens":1000000,'
        '"cached_input_tokens":500000,'
        '"output_tokens":100000,'
        '"reasoning_output_tokens":50000}}\n'
    )
    result = adapter.parse_output(fake_stdout, "", 0)
    assert result.usage.cost_usd is not None, (
        "cost_usd should be computed from tokens × pricing for known models"
    )
    assert result.usage.cost_usd > 0
    # Token extraction still works (regression check).
    assert result.usage.tokens_in == 1000000
    assert result.usage.tokens_out == 100000
    assert result.usage.cache_read_tokens == 500000


def test_codex_parse_output_returns_none_cost_for_unknown_model(monkeypatch):
    """If the model isn't in the pricing table, cost stays None — same as
    the current behavior. We don't guess."""
    from cae.agents.codex import CodexAdapter
    adapter = CodexAdapter()
    monkeypatch.setattr(adapter, "_discover_model", lambda: "some-unknown-experimental-model")
    fake_stdout = (
        '{"type":"turn.completed","usage":{'
        '"input_tokens":1000,"output_tokens":100}}\n'
    )
    result = adapter.parse_output(fake_stdout, "", 0)
    assert result.usage.cost_usd is None, (
        "cost should be None when model isn't in the pricing table"
    )
    # Tokens still captured.
    assert result.usage.tokens_in == 1000
    assert result.usage.tokens_out == 100


def test_aider_parse_output_extracts_tokens_and_cost():
    """Aider prints 'Tokens: X sent, Y received. Cost: $Z message, $W session.'
    to stdout at the end of a run. The adapter must extract tokens_in,
    tokens_out, and cost_usd from that line — otherwise aider's leaderboard
    row has $null cost (same gap codex had before its parser fix)."""
    from cae.agents.aider import AiderAdapter
    # Capture the actual shape aider prints (verified via `aider --message ...`).
    fake_stdout = (
        "Aider v0.86.2\n"
        "Model: anthropic/claude-opus-4-7 with whole edit format\n"
        "Added hello.py to the chat.\n"
        "Applied edit to hello.py\n"
        "\n"
        "Tokens: 667 sent, 64 received. Cost: $0.0049 message, $0.0049 session.\n"
    )
    result = AiderAdapter().parse_output(fake_stdout, "", 0)
    assert result.usage.tokens_in == 667, f"expected 667 sent, got {result.usage.tokens_in}"
    assert result.usage.tokens_out == 64, f"expected 64 received, got {result.usage.tokens_out}"
    assert result.usage.cost_usd is not None
    assert abs(result.usage.cost_usd - 0.0049) < 1e-6, (
        f"expected cost ~0.0049 (aider's session cost), got {result.usage.cost_usd}"
    )


def test_aider_parse_output_handles_missing_usage_line():
    """If aider crashes before printing the Tokens/Cost line (or the format
    changes), parse_output must not crash — return None tokens/cost and
    preserve exit_code. Better to record a None-cost result than to lose
    the whole run."""
    from cae.agents.aider import AiderAdapter
    fake_stdout = "Aider v0.86.2\nSome error happened before usage was printed.\n"
    result = AiderAdapter().parse_output(fake_stdout, "", 99)
    assert result.usage.tokens_in is None
    assert result.usage.tokens_out is None
    assert result.usage.cost_usd is None
    assert result.exit_code == 99
