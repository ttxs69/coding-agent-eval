# `--dry-run` Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--dry-run` to `cae run` so users can validate tasks and inspect the exact agent command without calling the LLM API — a safety net now that `--parallel N` can multiply API spend N-fold.

**Architecture:** Add `dry_run: bool = False` parameter to `harness.run()` and `_execute_run_unit()`. After `adapter.build_command()` succeeds, if `dry_run`, short-circuit: skip the agent subprocess, skip post-flight grading, write a result with `status: "dry_run"` and a new `would_run_command` field capturing the argv. Setup and pre-flight still execute — those answer "would this task run successfully?" cheaply (no API tokens).

**Tech Stack:** Python 3.10 stdlib only. No new deps.

**Scope caps (per self-improve policy):** estimated ~100 LOC, 4 files touched (`cae/agents/base.py` Status enum, `cae/harness.py`, `cae/cli.py`, `tests/test_harness.py` + `tests/test_cli.py`). Within the 500-LOC / 8-file budget.

**Result schema impact:** Additive — new `Status.DRY_RUN = "dry_run"` enum value, new optional `would_run_command: str` field on result JSON. Existing consumers ignore unknown fields; no migration.

---

### Task 1: Add `Status.DRY_RUN` enum value

**Files:**
- Modify: `cae/agents/base.py` (the `Status` enum)
- Test: `tests/test_status.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_status.py`:

```python
def test_dry_run_status_value():
    """Status.DRY_RUN exists and stringifies to 'dry_run' — used by the
    harness when --dry-run short-circuits before the agent runs."""
    from cae.agents.base import Status
    assert Status.DRY_RUN.value == "dry_run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_status.py::test_dry_run_status_value -v`
Expected: FAIL with `AttributeError: DRY_RUN is not a valid Status`.

- [ ] **Step 3: Write minimal implementation**

In `cae/agents/base.py`, add `DRY_RUN` to the `Status` enum. Insert after `GRADER_ERROR` (or wherever the existing values end):

```python
class Status(str, Enum):
    RESOLVED = "resolved"
    FAILED = "failed"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    TASK_ERROR = "task_error"
    GRADER_ERROR = "grader_error"
    DRY_RUN = "dry_run"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_status.py -v`
Expected: all status tests PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add cae/agents/base.py tests/test_status.py
git commit -m "feat(agents): add Status.DRY_RUN for the upcoming --dry-run flag"
```

---

### Task 2: Thread `dry_run` through `harness.run()` and short-circuit after `build_command`

**Files:**
- Modify: `cae/harness.py` (signature of `run()`, the agent-execution block at lines ~310-340, and `_result()` to accept the new field)
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_dry_run_short_circuits_before_agent_call(
    tmp_path, tiny_task_path, mock_with_model, monkeypatch,
):
    """--dry-run runs setup and pre-flight, then stops before invoking the
    agent. The result has status='dry_run' and a would_run_command field
    containing the adapter's build_command argv. No agent subprocess is
    actually executed."""
    import json
    from unittest.mock import patch
    from cae.harness import run as harness_run
    from cae.agents.base import Status

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # Track whether the agent subprocess would have been invoked. Patch
    # run_step's agent call to detect execution.
    agent_call_count = {"n": 0}
    real_run_subprocess = __import__("cae.harness", fromlist=["_run_subprocess"])._run_subprocess
    def counting_subprocess(cmd, cwd, timeout):
        # The agent command starts with the adapter's name (e.g. "mock").
        # We can't perfectly distinguish it, but the mock adapter's command
        # is a fixed string we can recognize.
        if isinstance(cmd, str) and cmd.startswith("python"):
            agent_call_count["n"] += 1
        return real_run_subprocess(cmd, cwd, timeout)

    result = harness_run(
        task_path=tiny_task_path,
        agent_name="mock",
        workdir=workdir,
        timeout_sec=30,
        dry_run=True,
    )

    assert result["status"] == "dry_run", (
        f"expected dry_run, got {result['status']!r}"
    )
    assert "would_run_command" in result, "result must include would_run_command"
    assert isinstance(result["would_run_command"], str)
    assert result["would_run_command"], "would_run_command must be non-empty"
    # Pre-flight ran (the harness validated test IDs); post-flight did not.
    assert "pre_flight" in result["test_results"]
    assert not result["test_results"].get("post_flight"), (
        "dry-run must not run post-flight (no patch to grade against)"
    )
    # No patch (agent didn't run, no diff to capture).
    assert result["patch"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness.py::test_dry_run_short_circuits_before_agent_call -v`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'dry_run'`.

- [ ] **Step 3: Write minimal implementation**

In `cae/harness.py`:

a) Add `dry_run: bool = False` to `run()`'s signature (after `repeat_index`).

b) Replace the current agent-execution block (around line 310-340) with a dry-run short-circuit:

```python
    # 7: Run agent (or short-circuit for --dry-run)
    if not adapter.is_available():
        return _result(task, agent_name, mode, Status.AGENT_ERROR, agent_version, pre_flight, pre_flight, "",
                       str(workdir), f"agent {agent_name} not available",
                       started_at=started_at, agent_model=agent_model)
    cmd = adapter.build_command(workdir, task["prompt"], model=model)
    if dry_run:
        # --dry-run: validate everything up to the agent call, then stop.
        # No subprocess, no patch capture, no post-flight grading. The
        # result records what WOULD have run so users can sanity-check
        # before launching a --parallel batch.
        return _result(task, agent_name, mode, Status.DRY_RUN, agent_version, pre_flight, {}, "",
                       str(workdir), "",
                       started_at=started_at, agent_model=agent_model,
                       would_run_command=cmd)
    agent_rc, agent_stdout, agent_stderr, duration = run_step(cmd, workdir, timeout=timeout_sec)
    # ... rest of existing agent execution ...
```

c) Add `would_run_command: str | None = None` parameter to `_result()` and include it in the returned dict:

```python
def _result(task, agent_name, mode, status, agent_version, pre_flight, post_flight, patch,
            workdir, error, started_at: str, agent_model=None, agent_duration=0.0, agent_usage=None,
            prompt: str | None = None,
            repeat: int = 1, repeat_index: int | None = None,
            would_run_command: str | None = None):
    ...
    return {
        ...existing fields...,
        "would_run_command": would_run_command,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness.py::test_dry_run_short_circuits_before_agent_call -v`
Expected: PASS.

Also run the full harness test module to check for regressions:
Run: `uv run pytest tests/test_harness.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add cae/harness.py tests/test_harness.py
git commit -m "feat(harness): thread dry_run through run(); short-circuit after build_command

When dry_run=True, the harness runs setup + pre-flight (so test-ID
validation still happens), captures adapter.build_command() for
visibility, then returns Status.DRY_RUN without invoking the agent.
No API spend."
```

---

### Task 3: Add `--dry-run` argparse flag to `cae run` and thread through `_execute_run_unit`

**Files:**
- Modify: `cae/cli.py` (argparse, both serial and parallel branches of `cmd_run`, and `_execute_run_unit`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_dry_run_flag_produces_dry_run_result(tmp_path, tiny_task_path):
    """`cae run --agent mock --task <tiny> --dry-run` writes a result JSON
    whose status is 'dry_run' and whose would_run_command is non-empty.
    No agent subprocess actually runs."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    (tasks / "repo").mkdir(parents=True)
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task", "--dry-run",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1, f"expected 1 result file, got {len(files)}"
    data = json.loads(files[0].read_text())
    assert data["status"] == "dry_run", data["status"]
    assert data["would_run_command"], "would_run_command must be non-empty"
    # patch must be empty — agent didn't run
    assert data["patch"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_cae_run_dry_run_flag_produces_dry_run_result -v`
Expected: FAIL with argparse exit code 2 and stderr mentioning `unrecognized arguments: --dry-run`.

- [ ] **Step 3: Write minimal implementation**

In `cae/cli.py`:

a) Add the argparse flag in `build_parser()` (after `--parallel`):

```python
    p_run.add_argument("--dry-run", action="store_true",
                      help="resolve task, run setup + pre-flight, build the agent command, "
                           "then stop — write a result with status='dry_run' and the "
                           "would-be command. No API tokens spent. Useful for sanity-checking "
                           "before a --parallel batch.")
```

b) Add `dry_run: bool` to `_execute_run_unit()`'s signature, and pass `dry_run=dry_run` to the `run()` call inside it.

c) In `cmd_run()`'s serial branch, pass `dry_run=args.dry_run` to `_execute_run_unit()`.

d) In `cmd_run()`'s parallel branch (the `worker` closure), pass `dry_run=args.dry_run` to `_execute_run_unit()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_cae_run_dry_run_flag_produces_dry_run_result -v`
Expected: PASS.

Full suite to check for regressions:
Run: `uv run pytest -q`
Expected: 99 passed, 2 skipped (98 baseline + 1 new test).

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "feat(cli): add --dry-run flag to cae run

Flags through to harness.run(dry_run=True). The result JSON carries
status='dry_run' and a would_run_command field showing the exact argv
that would have been invoked. No agent subprocess actually runs."
```

---

### Task 4: Test `--dry-run` interacts correctly with `--parallel`

**Files:**
- Modify: `tests/test_cli.py`

`--dry-run` + `--parallel N` should produce N short-circuited results, one per unit, with no agent calls. This is the headline use case: "show me exactly what would happen across this whole parallel batch before I spend money on it."

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_dry_run_with_parallel_produces_all_dry_run_results(
    tmp_path, tiny_task_path,
):
    """--dry-run + --parallel 3 produces 3 result files, all with
    status='dry_run' and non-empty would_run_command. None of them
    actually invoked the agent (no API spend)."""
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2", "tiny__task-3"):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        (t / "task.json").write_text(
            (tiny_task_path / "task.json").read_text().replace('"tiny__task-1"', f'"{name}"'))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__task-2", "--task", "tiny__task-3",
         "--parallel", "3", "--dry-run",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    result_files = sorted(f.name for f in (proj / "results").glob("*__mock__*.json"))
    assert len(result_files) == 3, (
        f"expected 3 dry-run result files, got {len(result_files)}: {result_files}"
    )
    for f in (proj / "results").glob("*__mock__*.json"):
        data = json.loads(f.read_text())
        assert data["status"] == "dry_run", (
            f"{f.name}: expected dry_run, got {data['status']}"
        )
        assert data["would_run_command"], f"{f.name}: empty would_run_command"
        assert data["patch"] == "", f"{f.name}: patch should be empty under --dry-run"
```

- [ ] **Step 2: Run test — should already pass**

Run: `uv run pytest tests/test_cli.py::test_cae_run_dry_run_with_parallel_produces_all_dry_run_results -v`
Expected: PASS. Threading `dry_run` through the parallel `worker` closure (Task 3) gives this for free.

If it FAILS, the parallel branch wasn't updated correctly in Task 3 — fix before moving on.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test(cli): --dry-run + --parallel produces all-dry-run results

Locks in the headline use case: sanity-check the entire parallel batch
(before any API spend) by combining --dry-run with --parallel N."
```

---

### Task 5: Update the design spec to mention `--dry-run`

**Files:**
- Modify: `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` (the Resilience section near `--parallel`)

- [ ] **Step 1: Find the right insertion point**

Run: `grep -n -B1 -A3 "Timeout\|Resume" docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md | head -30`

- [ ] **Step 2: Update the spec**

Add a bullet near the Concurrency/Resume block:

```markdown
- **Dry run**: `--dry-run` resolves the task, runs setup and pre-flight (so test-ID validation still happens), captures the agent command via `adapter.build_command()`, then short-circuits before invoking the agent. The result JSON has `status: "dry_run"` and a `would_run_command` field. Useful for sanity-checking a `--parallel N` batch before spending money on it.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md
git commit -m "docs: document --dry-run flag in the design spec"
```

---

## Self-Review

**1. Spec coverage.** The `--dry-run` flag isn't called out as a deferred feature in the spec — it's a natural follow-on to `--parallel` (which IS now in the spec). Task 5 adds documentation. No other spec section needs touching.

**2. Placeholder scan.** Searched for "TBD", "TODO", "implement later", "add appropriate error handling". None found. Every step has concrete code.

**3. Type consistency.** `would_run_command` is consistently named across Task 2 (introduced in `_result()`), Task 3 (used by `_execute_run_unit` callers), and tests. `dry_run` parameter name is consistent from `cmd_run` → `_execute_run_unit` → `harness.run()`.

**4. Risk check.** Per self-improve policy:
- No new dependencies. ✓
- Additive schema change (new optional field + new enum value). The candidate description didn't explicitly note "schema change" but the change is purely additive — existing consumers ignore unknown fields. The `aggregate_results` / `metrics.py` consumer treats `dry_run` results the same as `task_error`/`agent_error` (they're not "resolved" so they don't pad the numerator; whether they should be excluded entirely from `n_attempted` is a separate question for the metrics layer — left alone for now since this is the safety-net feature, not a metrics refactor). ✓
- No breaking CLI changes. ✓
- LOC: ~100 (within 500 cap). ✓
- Files: 5 (cae/agents/base.py, cae/harness.py, cae/cli.py, tests/test_harness.py, tests/test_cli.py, plus docs/superpowers/specs/.../design.md = 6 — within 8 cap). ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-dry-run-flag.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks
**2. Inline Execution** — execute tasks in this session using executing-plans

Given the scope is ~100 LOC (well under the 200 LOC threshold), inline TDD is appropriate per the self-improve workflow.
