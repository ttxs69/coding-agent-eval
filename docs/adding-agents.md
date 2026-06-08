# Adding an Agent

`cae` supports any CLI-driven coding agent that can run with a working directory, a prompt on stdin or argv, and emit its work as filesystem changes. The four built-in adapters are `claude-code`, `codex`, `aider`, and `mock` (test-only).

## The `AgentAdapter` Protocol

Every adapter implements a small Protocol defined in `cae/agents/base.py`:

```python
class AgentAdapter(Protocol):
    name: str                          # registered name, e.g. "claude-code"
    default_model: str | None          # e.g. "claude-opus-4-7" or None

    def is_available(self) -> bool: ...
    def version(self) -> str: ...
    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]: ...
    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult: ...
```

- `is_available()` — returns True if the underlying CLI is on PATH and runnable. `cae list-agents` calls this.
- `version()` — returns the installed CLI's version string (e.g. from `agent --version`). The harness captures this once per run.
- `build_command(workdir, prompt, *, model)` — returns the argv to spawn. The harness runs this in the workdir after pre-flight passes. `model` is the value of `cae run --model`, or `None` if the user didn't set one.
- `parse_output(stdout, stderr, exit_code)` — extracts `usage: UsageInfo` (tokens, cost, model) from whatever JSON the agent emits. The harness trusts your adapter to translate the agent's quirks.

The patch the agent produced is captured uniformly by `git diff` after the run; you do **not** need to surface the patch in `parse_output`.

## Template: `cae/agents/claude_code.py`

The Claude Code adapter is the cleanest reference. Read it before writing your own — the structure maps 1:1 to the Protocol above.

```python
class ClaudeCodeAdapter:
    name = "claude-code"
    default_model = "claude-opus-4-7"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def version(self) -> str:
        # Return a string; "unknown" if it can't be read.
        ...

    def build_command(self, workdir, prompt, *, model):
        cmd = ["claude", "-p", prompt, "--output-format", "json",
               "--dangerously-skip-permissions"]   # non-interactive
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout, stderr, exit_code):
        # Find the last "type": "result" entry in stdout, pull
        # `total_cost_usd`, `usage.input_tokens`, etc. Cache fields
        # live under `usage.cache_read_input_tokens` for Claude.
        ...
```

## Register the adapter

In `cae/agents/__init__.py`, import your class and add it to the `ADAPTERS` dict:

```python
from cae.agents.my_agent import MyAgentAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "aider": AiderAdapter,
    "my-agent": MyAgentAdapter,   # <-- add this
}
```

The string key is what users pass to `cae run --agent my-agent` and what `cae list-agents` displays.

## Test your adapter

In `tests/test_agents.py`, follow the pattern of `test_claude_parse_output_extracts_cache_tokens` / `test_codex_parse_output_extracts_cached_input_tokens`:

```python
def test_my_agent_parse_output_extracts_usage():
    from cae.agents.my_agent import MyAgentAdapter
    fake_stdout = json.dumps({"type": "result", "usage": {...}, "model": "..."})
    result = MyAgentAdapter().parse_output(fake_stdout, "", 0)
    assert result.usage.cost_usd == 0.42
    assert result.usage.tokens_in == 100
```

For a full end-to-end check, run:
```
uv run cae run --agent my-agent --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/cae
```

The result JSON should be `status: resolved` (since `tiny_task` has a known fix) — though that depends on whether your CLI is actually wired up to the fix; the goal is just to see a non-error status and sensible token/cost numbers.

## Tips

- The harness's `parse_output` only has access to the agent's stdout/stderr/exit_code. If the agent's accounting is in a sidecar log file, your adapter needs to read it from the workdir.
- The harness runs your agent in the workdir; you don't need to set `cwd` yourself. Just trust it.
- If the agent needs non-interactive flags (Claude's `--dangerously-skip-permissions`, Codex's `--dangerously-bypass-approvals-and-sandbox`), put them in `build_command`. Without them, the agent will hang waiting for user input.
- `UsageInfo` has fields for `tokens_in`, `tokens_out`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, and `model`. Fill in whatever the agent reports; leave the rest as None.
