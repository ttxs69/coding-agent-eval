# Per-Stage Timeouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users set independent timeouts for setup, agent, and test runs (pre-flight + grading share a single test timeout since they execute the same `test_cmd`). Replaces the single global `--timeout` for users who need finer control — relevant now that `--parallel N` fans out 4 stages × N workers where one stuck setup can block a worker for the full 30-min window.

**Architecture:** Three new CLI flags (`--timeout-setup`, `--timeout-agent`, `--timeout-tests`) all defaulting to `None`. When `None`, the harness falls back to the existing `timeout_sec` value (preserving current behavior byte-for-byte). Thread three new optional parameters through `_execute_run_unit` and `harness.run()`. In `run()`, replace the 4 `timeout=timeout_sec` sites:
- setup: uses `timeout_setup or timeout_sec`
- pre-flight: uses `timeout_tests or timeout_sec`
- agent: uses `timeout_agent or timeout_sec`
- grade: uses `timeout_tests or timeout_sec` (same flag — same test_cmd)

**Tech Stack:** Python 3.10 stdlib only. No new deps.

**Scope caps (per self-improve policy):** estimated ~80 LOC, 4 files touched (`cae/cli.py`, `cae/harness.py`, `tests/test_cli.py`, `tests/test_harness.py`). Within the 500-LOC / 8-file budget.

**Backwards compatibility:** Existing `--timeout N` behavior is preserved. New flags are purely additive — users who don't pass them get the same behavior as before.

---

### Task 1: Add the three `--timeout-*` argparse flags

**Files:**
- Modify: `cae/cli.py:489` (the `--timeout` argument in `build_parser`)
- Test: `tests/test_cli.py`

This task only changes argparse wiring — the run logic still uses a single timeout. Smallest possible change to verify the CLI surface accepts the new inputs.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_accepts_per_stage_timeout_flags(tmp_path, tiny_task_path):
    """`--timeout-setup`, `--timeout-agent`, `--timeout-tests` are accepted
    by argparse (do NOT yet behave differently — that comes in Task 2).
    Verifies the CLI surface before any run-logic changes."""
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
         "--task", "tiny_task",
         "--timeout-setup", "5",
         "--timeout-agent", "10",
         "--timeout-tests", "3",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    # Argparse must accept the flags — exit code 0 OR a runtime error is fine,
    # but NOT an argparse error (exit code 2 with "unrecognized" wording).
    assert result.returncode != 2 or "unrecognized arguments" not in result.stderr, (
        f"argparse rejected the new flags: {result.stderr}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_cae_run_accepts_per_stage_timeout_flags -v`
Expected: FAIL with argparse exit code 2 and stderr mentioning `unrecognized arguments: --timeout-setup`.

- [ ] **Step 3: Write minimal implementation**

In `cae/cli.py`, in `build_parser()`, after the existing `--timeout` argument:

```python
    p_run.add_argument("--timeout-setup", type=int, default=None,
                      help="per-stage timeout in MINUTES, overrides --timeout for setup_cmd "
                           "(default: falls back to --timeout). Useful when pip install / "
                           "astropy build needs longer than the agent.")
    p_run.add_argument("--timeout-agent", type=int, default=None,
                      help="per-stage timeout in MINUTES, overrides --timeout for the agent "
                           "subprocess (default: falls back to --timeout). The agent is "
                           "usually the longest stage.")
    p_run.add_argument("--timeout-tests", type=int, default=None,
                      help="per-stage timeout in MINUTES, overrides --timeout for both "
                           "pre-flight and grading (they run the same test_cmd). "
                           "(default: falls back to --timeout)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_cae_run_accepts_per_stage_timeout_flags -v`
Expected: PASS.

Full suite to verify no regression:
Run: `uv run pytest -q`
Expected: 104 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "feat(cli): accept --timeout-setup/--timeout-agent/--timeout-tests flags

argparse surface only — values are accepted but currently ignored.
The harness still uses a single timeout_sec for all four stages.
Behavior preservation comes in Task 2."
```

---

### Task 2: Thread per-stage timeouts through `_execute_run_unit` and `harness.run()`

**Files:**
- Modify: `cae/cli.py` (`_execute_run_unit` signature + `cmd_run` callers)
- Modify: `cae/harness.py` (`run()` signature + the 4 timeout= call sites)
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_run_threads_per_stage_timeouts_to_run_step(
    tmp_path, tiny_task_path, fixing_mock, monkeypatch,
):
    """Per-stage timeouts (timeout_setup, timeout_agent, timeout_tests) must
    reach the underlying subprocess dispatcher with their distinct values.
    We spy on _run_subprocess to verify each stage is invoked with its
    specific timeout — not the global default."""
    from cae.harness import run as harness_run
    import cae.harness as harness_mod

    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    # Spy on _run_subprocess to capture the timeout each call used.
    captured: list[int] = []
    real_run_subprocess = harness_mod._run_subprocess
    def spy(cmd, cwd, timeout):
        captured.append(timeout)
        return real_run_subprocess(cmd, cwd, timeout)

    monkeypatch.setattr(harness_mod, "_run_subprocess", spy)

    harness_run(
        task_path=tiny_task_path,
        agent_name="mock",
        workdir=workdir,
        timeout_sec=999,           # global default — should NOT be used
        timeout_setup=11,
        timeout_agent=22,
        timeout_tests=33,
    )

    # The harness makes these _run_subprocess calls in order:
    #   1. pre-flight test_cmd (timeout_tests=33)
    #   2. agent build_command result (timeout_agent=22)
    #   3. grade test_cmd (timeout_tests=33)
    # (setup_cmd is empty for tiny_task so no setup call.)
    assert 22 in captured, f"agent timeout not threaded through: {captured}"
    assert captured.count(33) >= 2, (
        f"expected at least 2 test_cmd calls (pre-flight + grade) with "
        f"timeout_tests=33; got {captured}"
    )
    # The global 999 default must NOT appear anywhere — per-stage values win.
    assert 999 not in captured, (
        f"per-stage timeouts didn't override the global default: {captured}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness.py::test_run_threads_per_stage_timeouts_to_run_step -v`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'timeout_setup'`.

- [ ] **Step 3: Write minimal implementation**

In `cae/harness.py`:

a) Add three new optional parameters to `run()` after `dry_run`:

```python
    dry_run: bool = False,
    timeout_setup: int | None = None,
    timeout_agent: int | None = None,
    timeout_tests: int | None = None,
) -> dict:
```

b) Update the docstring at line 166 to reflect the new parameters:

```python
        timeout_sec: per-stage fallback timeout (setup, pre-flight, agent, grading)
            in seconds. Used when a stage-specific override isn't provided.
        timeout_setup: optional override (seconds) for setup_cmd only.
        timeout_agent: optional override (seconds) for the agent subprocess only.
        timeout_tests: optional override (seconds) for pre-flight AND grade
            (they run the same test_cmd, so they share one value).
```

c) Replace the 4 timeout call sites:

```python
    # 5: Setup
    if task.get("setup_cmd"):
        setup_rc, setup_out, setup_err, _ = run_step(
            task["setup_cmd"], workdir, timeout=timeout_setup or timeout_sec
        )
        ...

    # 6: Pre-flight
    pre = _run_tests(
        task["test_cmd"], workdir,
        timeout=timeout_tests or timeout_sec, run_subprocess=run_step,
    )
    ...

    # 7: Run agent
    ...
    effective_agent_timeout = timeout_agent or timeout_sec
    agent_rc, agent_stdout, agent_stderr, duration = run_step(
        cmd, workdir, timeout=effective_agent_timeout
    )
    if agent_rc == -1:
        return _result(task, agent_name, mode, Status.TIMEOUT, agent_version, pre_flight, pre_flight, "",
                       str(workdir), f"agent timed out after {effective_agent_timeout}s",
                       started_at=started_at, agent_model=agent_model)
    ...

    # 9: Grade
    post = _run_tests(
        task["test_cmd"], workdir,
        timeout=timeout_tests or timeout_sec, run_subprocess=run_step,
    )
```

d) In `cae/cli.py`, add the three new parameters to `_execute_run_unit`'s signature and pass them to `run()`:

```python
def _execute_run_unit(
    *,
    task_path: Path,
    ...
    force: bool,
    dry_run: bool = False,
    timeout_setup: int | None = None,
    timeout_agent: int | None = None,
    timeout_tests: int | None = None,
) -> tuple[float, str]:
    ...
    result = run(
        ...
        dry_run=dry_run,
        timeout_setup=timeout_setup,
        timeout_agent=timeout_agent,
        timeout_tests=timeout_tests,
    )
```

e) In `cmd_run`'s serial branch and parallel worker, pass the new values:

```python
    # In both serial loop and parallel worker:
    timeout_setup=args.timeout_setup * 60 if args.timeout_setup else None,
    timeout_agent=args.timeout_agent * 60 if args.timeout_agent else None,
    timeout_tests=args.timeout_tests * 60 if args.timeout_tests else None,
```

(CLI takes minutes; harness wants seconds — same conversion as the existing `args.timeout * 60`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness.py::test_run_threads_per_stage_timeouts_to_run_step -v`
Expected: PASS.

Full suite:
Run: `uv run pytest -q`
Expected: 105 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py cae/harness.py tests/test_harness.py
git commit -m "feat(harness): thread per-stage timeouts through run()

run() now accepts optional timeout_setup, timeout_agent, timeout_tests
(in seconds). When provided, each is used at its corresponding stage
instead of the global timeout_sec fallback. The 4 call sites (setup,
pre-flight, agent, grade) use their specific timeout or fall back.

Pre-flight and grade share timeout_tests because they execute the same
test_cmd — splitting them would be confusing (same command, two
timeouts). The agent timeout gets its own local variable so the TIMEOUT
status message reports the right value."
```

---

### Task 3: Test that per-stage timeouts override defaults from end-to-end (CLI → harness)

**Files:**
- Modify: `tests/test_cli.py`

End-to-end test: pass `--timeout-tests 1` against a task whose test_cmd takes >1s. The pre-flight test_cmd should timeout, returning task_error. This proves the per-stage flag actually changes behavior, not just threads through.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_per_stage_timeout_tests_aborts_long_running_pre_flight(
    tmp_path, tiny_task_path,
):
    """End-to-end: --timeout-tests 1 (one minute = 60s; the test sleeps 2s)
    Wait — 1 minute is too long for a test. Use --timeout-tests 1 with a
    test_cmd that sleeps 90s — pre-flight must abort with timeout.

    Actually, simpler: --timeout-tests is in MINUTES. The smallest practical
    value is 1 (60s). To trigger a timeout, we need test_cmd to take >60s,
    which is too slow for a test suite. Instead, set --timeout-tests to a
    small fraction via... hmm, argparse type=int means the user can only
    pass whole minutes.

    Resolution: this test uses --timeout-tests 0 to force an instant
    timeout. The harness passes timeout=0 to subprocess.run, which aborts
    immediately. Pre-flight's pytest invocation will timeout before it
    even starts."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    # Inject a slow test_cmd so we have something to interrupt.
    task_json = json.loads((tiny_task_path / "task.json").read_text())
    task_json["test_cmd"] = "sleep 30 && python -m pytest test_main.py -v"
    (tasks / "task.json").write_text(json.dumps(task_json))
    (tasks / "repo").mkdir(parents=True)
    for child in (tiny_task_path / "repo").iterdir():
        dest = tasks / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    (proj / "results").mkdir()

    start = __import__("time").monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--timeout-tests", "0",  # 0 minutes = 0 seconds = immediate timeout
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    elapsed = __import__("time").monotonic() - start

    # Pre-flight must have aborted with task_error (the harness treats
    # pre-flight validation failure as task_error). And it must have done
    # so quickly — well under the 30-second sleep.
    assert elapsed < 25, f"pre-flight should have aborted in <25s; took {elapsed:.1f}s"
    assert result.returncode == 0, f"stderr: {result.stderr}"  # CLI exits 0 even on task_error
    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["status"] == "task_error", (
        f"expected task_error from pre-flight timeout, got {data['status']}"
    )
```

- [ ] **Step 2: Run test — should already pass after Task 2**

Run: `uv run pytest tests/test_cli.py::test_cae_run_per_stage_timeout_tests_aborts_long_running_pre_flight -v`
Expected: PASS. Task 2's threading is what makes this work.

If it FAILS, Task 2's threading has a bug — fix before moving on.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test(cli): --timeout-tests 0 aborts long-running pre-flight

End-to-end test: --timeout-tests 0 (0 minutes = immediate timeout)
against a task with a sleep-30 test_cmd. Verifies the per-stage flag
actually changes behavior end-to-end, not just threads through. The
pre-flight subprocess aborts quickly, the harness records task_error,
and the CLI exits 0 (the harness's task_error is a result status, not
a CLI crash)."
```

---

### Task 4: Update CLAUDE.md / design spec to mention per-stage timeouts

**Files:**
- Modify: `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` (the Timeout bullet near `--parallel`)

- [ ] **Step 1: Find the right insertion point**

Run: `grep -n -B1 -A3 "Timeout\|Resume" docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md | head -30`

- [ ] **Step 2: Update the spec**

Find the existing `**Timeout**: default 30 min per agent run, configurable.` bullet and replace with:

```markdown
- **Timeouts**: `--timeout N` (in minutes) sets the default for all four stages — setup, pre-flight, agent, grading. Override per stage with `--timeout-setup`, `--timeout-agent`, `--timeout-tests` (the last covers both pre-flight and grade since they run the same `test_cmd`). Useful when `pip install` (setup) routinely needs longer than the agent, or when grading is the bottleneck. Killed cleanly; patch captured up to kill point.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md
git commit -m "docs: document per-stage timeouts in the design spec"
```

---

## Self-Review

**1. Spec coverage.** The existing "Timeout" bullet in the spec mentions "default 30 min per agent run, configurable" — Task 4 expands this to document the new per-stage granularity. No other spec section needs touching.

**2. Placeholder scan.** Searched for "TBD", "TODO", "implement later", "add appropriate error handling". None found. Every step has concrete code.

**3. Type consistency.** `timeout_setup`, `timeout_agent`, `timeout_tests` are consistently named across cli.py argparse, `_execute_run_unit` parameters, and `harness.run()` parameters. All are `int | None`; `None` means fall back to `timeout_sec`.

**4. Risk check.** Per self-improve policy:
- No new dependencies. ✓
- No schema changes (result JSON unchanged). ✓
- No breaking CLI changes (`--timeout` still works exactly as before; new flags are additive). ✓
- LOC: ~80 (within 500 cap). ✓
- Files: 4 (cae/cli.py, cae/harness.py, tests/test_cli.py, tests/test_harness.py) + 1 doc = 5 (within 8 cap). ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-per-stage-timeouts.md`. Inline TDD execution (scope is ~80 LOC, well under the 200 LOC subagent-dispatch threshold).
