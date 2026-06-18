# `validate_env()` Adapter Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `validate_env() -> str | None` method to the `AgentAdapter` Protocol. The harness calls it after capturing agent identity (step 4) and before setup (step 5), so missing API keys fail fast — saving the 1–10 minutes of `pip install` / astropy build that would otherwise happen before the agent call discovers the problem.

**Architecture:** New optional Protocol method. Default implementation returns `None` (no requirement). Each real adapter overrides to check its specific env vars / config files. Harness change: call `adapter.validate_env()` at step 4.5 (after agent identity, before setup); if it returns a non-None string, return `Status.AGENT_ERROR` with the message and skip the rest.

**Tech Stack:** Python 3.10 stdlib only. No new deps.

**Scope caps (per self-improve policy):** estimated ~80 LOC, 5 files touched (`cae/agents/base.py`, `cae/agents/mock.py`, `cae/harness.py`, `tests/test_harness.py`, `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md`). Within the 500-LOC / 8-file budget.

**Backwards compatibility:** Existing adapters (claude_code, codex, aider, mock) don't override `validate_env()` initially — they inherit the implicit "no specific requirement" contract via Python's `getattr(adapter, 'validate_env', None)`. The harness's call uses `getattr` defensively so adapters that don't define the method are unaffected. A follow-up iteration can fill in the per-adapter overrides once the hook is in place.

**Why this isn't done at step 7 (with `is_available()`):** `is_available()` is currently called right before `run_step(cmd, ...)`, so setup + pre-flight have already run. Setup is the expensive part (`pip install -e .[test]` on astropy routinely takes 2–5 minutes). Putting `validate_env()` at step 4.5 means we save that time when the env is broken. This is the ROI argument: the hook is more valuable the earlier it runs.

---

### Task 1: Add `validate_env()` to the Protocol + a default implementation in MockAdapter

**Files:**
- Modify: `cae/agents/base.py` (Protocol definition)
- Modify: `cae/agents/mock.py` (override returning None — documents the contract)
- Test: `tests/test_agents.py` (or a new `test_protocol.py` if no module exists)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agents.py` (or create `tests/test_protocol.py` if test_agents.py doesn't exist; check first with `ls tests/test_ag*.py`):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agents.py::test_validate_env_is_part_of_protocol tests/test_agents.py::test_mock_adapter_validate_env_returns_none -v`
Expected: FAIL — `_MissingValidateEnv` currently satisfies the Protocol; `MockAdapter().validate_env()` raises AttributeError.

- [ ] **Step 3: Write minimal implementation**

In `cae/agents/base.py`, add `validate_env()` to the `AgentAdapter` Protocol after `parse_output`:

```python
    def validate_env(self) -> str | None:
        """Return None if the runtime environment is OK (API keys set,
        config files readable, etc.); otherwise return a short human-
        readable description of the problem (e.g. ``"ANTHROPIC_API_KEY
        not set and ~/.claude/settings.json has no API key"``).

        The harness calls this BEFORE setup so a broken env fails fast
        — saving the 1–10 minutes of pip install / astropy build that
        would otherwise happen before the agent subprocess discovers
        the problem. Default for adapters that don't override: None
        (no specific requirement).
        """
        ...
```

In `cae/agents/mock.py`, add the explicit override (documenting the contract even though it's the same as the implicit default):

```python
    def validate_env(self) -> str | None:
        """Mock has no env requirements — always returns None."""
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agents.py -v`
Expected: PASS.

Full suite:
Run: `uv run pytest -q`
Expected: 108 passed, 2 skipped (106 baseline + 2 new tests).

- [ ] **Step 5: Commit**

```bash
git add cae/agents/base.py cae/agents/mock.py tests/test_agents.py
git commit -m "feat(agents): add validate_env() to AgentAdapter Protocol

Optional method returns None (env OK) or a short error string (env
broken). Default contract: no requirement. MockAdapter overrides to
explicitly return None — documents the contract for future adapters.

Self-improve feature: lets the harness fail fast on missing API keys
before pip install / astropy build wastes 1-10 minutes."
```

---

### Task 2: Harness calls `validate_env()` at step 4.5 (after agent identity, before setup)

**Files:**
- Modify: `cae/harness.py` (the agent-identity block at lines ~218-235, add validate_env check after)
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_harness_agent_errors_when_validate_env_returns_a_message(
    tmp_path, tiny_task_path, monkeypatch,
):
    """When validate_env() returns a non-None message, the harness must:
    1. Return status='agent_error'
    2. Include the message in the error field
    3. NOT execute setup_cmd (proving the check ran before setup)
    """
    from cae.agents import ADAPTERS
    from cae.agents.mock import MockAdapter
    from cae.harness import run as harness_run

    setup_ran = {"yes": False}

    class _BadEnvMock(MockAdapter):
        name = "bad-env-mock"
        default_model = "test-model-1"
        def validate_env(self) -> str | None:
            return "ANTHROPIC_API_KEY not set"
        # Override setup detection by hijacking run_step would be too
        # invasive; instead we set a sentinel in setup_cmd and check
        # whether the workdir's setup_cmd touched it.

    # Set up workdir with a setup_cmd that creates a marker file.
    # If validate_env() runs BEFORE setup, the marker file is never created.
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # Use a custom task.json that includes a setup_cmd creating a marker.
    bad_task = tmp_path / "bad_task"
    bad_task.mkdir()
    import json
    task_data = json.loads((tiny_task_path / "task.json").read_text())
    task_data["setup_cmd"] = f"touch {workdir / 'SETUP_RAN.marker'}"
    (bad_task / "task.json").write_text(json.dumps(task_data))
    # No repo needed for this check.

    ADAPTERS["bad-env-mock"] = _BadEnvMock
    try:
        result = harness_run(
            task_path=bad_task,
            agent_name="bad-env-mock",
            workdir=workdir,
            timeout_sec=30,
        )
    finally:
        ADAPTERS.pop("bad-env-mock", None)

    assert result["status"] == "agent_error", (
        f"expected agent_error, got {result['status']}"
    )
    assert "ANTHROPIC_API_KEY" in (result["error"] or ""), result["error"]
    # The marker file must NOT exist — setup didn't run.
    assert not (workdir / "SETUP_RAN.marker").exists(), (
        "setup_cmd ran anyway — validate_env check is in the wrong place "
        "(must run BEFORE setup)"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness.py::test_harness_agent_errors_when_validate_env_returns_a_message -v`
Expected: FAIL — `validate_env()` is never called; setup runs; marker file exists; assertion fails. (Status might be `task_error` or `resolved` depending on how the empty-repo task plays out, but the marker-file check will catch it.)

- [ ] **Step 3: Write minimal implementation**

In `cae/harness.py`, after the agent-identity capture block (after `_ensure_git_repo(workdir)`, before the setup block at line ~280), insert:

```python
    # 4.5: Validate agent environment (fail fast on missing API keys etc.).
    # Runs BEFORE setup so a broken env doesn't waste the 1-10 minutes of
    # pip install / astropy build that setup often takes. Uses getattr
    # defensively so adapters that don't define validate_env() (e.g. older
    # third-party adapters) are treated as "no requirement".
    _validate_env = getattr(adapter, "validate_env", None)
    if _validate_env is not None:
        try:
            env_problem = _validate_env()
        except Exception as e:
            env_problem = f"validate_env() raised: {e!r}"
        if env_problem:
            return _result(task, agent_name, mode, Status.AGENT_ERROR, agent_version, {}, {}, "",
                           str(workdir), f"agent environment invalid: {env_problem}",
                           started_at=started_at, agent_model=agent_model)
```

(Note: place this AFTER `_ensure_git_repo` so the workdir is in a known state for any future adapter that wants to inspect files; place BEFORE setup so we save the setup cost.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness.py::test_harness_agent_errors_when_validate_env_returns_a_message -v`
Expected: PASS.

Full suite:
Run: `uv run pytest -q`
Expected: 109 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/harness.py tests/test_harness.py
git commit -m "feat(harness): call validate_env() before setup (step 4.5)

When validate_env() returns a non-None message, the harness returns
Status.AGENT_ERROR with the message and skips setup entirely. Uses
getattr defensively so adapters that don't define the method inherit
the implicit 'no requirement' default.

Placed BEFORE setup so a broken env fails fast — saves the 1-10
minutes of pip install / astropy build that would otherwise run
before the agent subprocess discovers the problem."
```

---

### Task 3: Verify --dry-run still works (validate_env should NOT block dry-run)

**Files:**
- Modify: `tests/test_harness.py` (or `tests/test_cli.py`)

`--dry-run` short-circuits at step 7 (after build_command). `validate_env()` runs at step 4.5. So a dry-run with a bad env currently would fail at step 4.5 BEFORE reaching the dry-run short-circuit. That's the WRONG behavior — dry-run should always work for inspection purposes.

Two options:
- A. Move validate_env() to AFTER the dry-run check (at step 7).
- B. Skip validate_env() when dry_run=True.

Option B preserves the cost-saving benefit for real runs while keeping dry-run unconditional. Implement B.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_dry_run_skips_validate_env_check(
    tmp_path, tiny_task_path, monkeypatch,
):
    """--dry-run should NOT be blocked by validate_env(). Dry-run is for
    inspection ('what would this batch invoke?') and must work even on
    machines with missing API keys, so users can sanity-check before
    fixing the env. The cost-saving validate_env check applies only to
    real runs."""
    from cae.agents import ADAPTERS
    from cae.agents.mock import MockAdapter
    from cae.harness import run as harness_run

    class _BadEnvMock(MockAdapter):
        name = "bad-env-mock-2"
        default_model = "test-model-1"
        def validate_env(self) -> str | None:
            return "ANTHROPIC_API_KEY not set"
        def build_command(self, workdir, prompt, *, model):
            return ["fake-binary", "--prompt", prompt]

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    ADAPTERS["bad-env-mock-2"] = _BadEnvMock
    try:
        result = harness_run(
            task_path=tiny_task_path,
            agent_name="bad-env-mock-2",
            workdir=workdir,
            timeout_sec=30,
            dry_run=True,
        )
    finally:
        ADAPTERS.pop("bad-env-mock-2", None)

    assert result["status"] == "dry_run", (
        f"--dry-run must short-circuit BEFORE validate_env; got {result['status']}"
    )
    assert result["would_run_command"], "dry-run result should have would_run_command"
```

- [ ] **Step 2: Run test — verify it FAILS first (the test exposes the bug in Task 2's placement)**

Run: `uv run pytest tests/test_harness.py::test_dry_run_skips_validate_env_check -v`
Expected: FAIL — Task 2 placed validate_env at step 4.5 (before setup), but dry-run short-circuits at step 7 (after setup). So validate_env runs first and returns agent_error before dry-run can kick in.

- [ ] **Step 3: Write minimal implementation**

Wrap the validate_env check from Task 2 in `if not dry_run:`:

```python
    # 4.5: Validate agent environment (fail fast on missing API keys etc.).
    # Runs BEFORE setup so a broken env doesn't waste the 1-10 minutes of
    # pip install / astropy build that setup often takes. SKIPPED under
    # --dry-run because dry-run is for inspection (users without API keys
    # should be able to see what would be invoked).
    if not dry_run:
        _validate_env = getattr(adapter, "validate_env", None)
        if _validate_env is not None:
            try:
                env_problem = _validate_env()
            except Exception as e:
                env_problem = f"validate_env() raised: {e!r}"
            if env_problem:
                return _result(task, agent_name, mode, Status.AGENT_ERROR, agent_version, {}, {}, "",
                               str(workdir), f"agent environment invalid: {env_problem}",
                               started_at=started_at, agent_model=agent_model)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness.py::test_dry_run_skips_validate_env_check tests/test_harness.py::test_harness_agent_errors_when_validate_env_returns_a_message -v`
Expected: both PASS.

Full suite:
Run: `uv run pytest -q`
Expected: 110 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/harness.py tests/test_harness.py
git commit -m "fix(harness): skip validate_env under --dry-run

validate_env runs at step 4.5 (before setup) to save pip install time
on real runs. But --dry-run is for inspection ('what would this batch
invoke?') and should work even when env is broken, so users can
sanity-check before fixing the env. Wrap the check in 'if not dry_run'
so dry-run always short-circuits to its own return at step 7."
```

---

### Task 4: Update design spec to document validate_env()

**Files:**
- Modify: `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` (the "Adding a new agent" section, near where is_available() is documented)

- [ ] **Step 1: Find the right insertion point**

Run: `grep -n "is_available\|Adding a new agent\|adapter" docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md | head -10`

- [ ] **Step 2: Update the spec**

Find a suitable bullet under "Adding a new agent" (or the adapter Protocol section) and add:

```markdown
- **`validate_env()` (optional)** — return `None` if the runtime environment is OK (API keys set, config readable, etc.); return a short human-readable message otherwise. The harness calls this BEFORE `setup_cmd` so a broken env fails fast (saving the 1–10 minutes of pip install / astropy build that would otherwise happen first). Skipped under `--dry-run`. Adapters that don't define it inherit the implicit "no requirement" default.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md
git commit -m "docs: document validate_env() Protocol hook in the design spec"
```

---

## Self-Review

**1. Spec coverage.** Task 4 adds a new bullet under "Adding a new agent". No other spec section needs touching.

**2. Placeholder scan.** Searched for "TBD", "TODO", "implement later", "add appropriate error handling". None found. Every step has concrete code.

**3. Type consistency.** `validate_env() -> str | None` is consistent across the Protocol definition, MockAdapter override, and harness call site. Return shape: None = OK, non-None string = error message.

**4. Risk check.** Per self-improve policy:
- No new dependencies. ✓
- No schema changes (result JSON unchanged — agent_error is an existing status). ✓
- No breaking CLI changes. ✓
- LOC: ~80 (within 500 cap). ✓
- Files: 5 (`cae/agents/base.py`, `cae/agents/mock.py`, `cae/harness.py`, `tests/test_harness.py`, `docs/superpowers/specs/.../design.md`) + 1 plan = 6 (within 8 cap). ✓

**5. Adapters NOT updated.** claude_code/codex/aider don't get `validate_env()` overrides in this iteration. They inherit the "no requirement" default via `getattr`. A follow-up iteration could add per-adapter overrides (e.g., claude_code checks `ANTHROPIC_API_KEY` or `~/.claude/settings.json`). Keeping this iteration focused on the hook itself.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-validate-env-hook.md`. Inline TDD execution (scope is ~80 LOC, well under the 200 LOC subagent-dispatch threshold).
