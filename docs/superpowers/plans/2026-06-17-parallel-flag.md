# Parallel `--parallel N` Concurrent Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `cae run` accept multiple `--task` values and run them concurrently via `--parallel N`, replacing the external shell loop in `scripts/run_eval.sh` for the common case.

**Architecture:** Refactor `cmd_run` to extract a single-unit executor (`_execute_run_unit`) that runs ONE `(task, repeat_index)` pair end-to-end (resume check → harness call → result write → stdout print). Build a units list as the cross product of `tasks × repeat`. When `--parallel == 1` (or only one unit), iterate serially — current behavior preserved byte-for-byte. When `--parallel > 1` AND more than one unit, dispatch via `concurrent.futures.ThreadPoolExecutor` with a print lock so per-unit output stays coherent.

**Tech Stack:** Python 3.10 stdlib only — `concurrent.futures.ThreadPoolExecutor`, `threading.Lock`, `io.StringIO`. No new dependencies. Tests use the existing `tiny_task` fixture + `mock` adapter (no API spend).

**Safety properties already guaranteed by the harness (no changes needed):**
- Each unit gets its own workdir (`tempfile.mkdtemp(prefix="cae-")` in `cae/harness.py:209`)
- Each unit writes a uniquely-named result JSON: `<ts>__<agent>__<model>__<instance_id>__<i>.json` (timestamps may collide but `(instance_id, repeat_index)` disambiguates)
- The harness has no shared global mutable state between runs (the `_run_started_at` / `_git_sha_cache` globals in `cae/harness.py:39,157` are written but never read across runs in a way that affects results — both fall back to safe defaults if clobbered)

**Caveat (documented in `--max-cost-usd` help):** when running in parallel, the cost cap is best-effort. Each worker re-checks the shared `spent` total under a lock before starting, but N-1 in-flight workers may overshoot.

**Scope caps (per self-improve policy):** estimated ~120 LOC added/modified, 2 files touched (`cae/cli.py`, `tests/test_cli.py`) + 1 doc touch (`docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` line 266). Within the 500-LOC / 8-file budget.

---

### Task 1: Make `--task` repeatable and add `--parallel` argparse argument

**Files:**
- Modify: `cae/cli.py:334-363` (the `p_run` argparse block in `build_parser`)

This task only changes argparse wiring — the run logic still processes the first task only. That's intentional: smallest possible change to verify the CLI surface accepts the new inputs before we touch any run logic.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_accepts_multiple_tasks_and_parallel_flag(tmp_path, tiny_task_path):
    """`--task foo --task bar --parallel 3` is accepted by argparse (does NOT
    yet run them in parallel — that comes later). Verifies the CLI surface
    before any run logic changes.
    """
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2"):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        (t / "task.json").write_text((tiny_task_path / "task.json").read_text().replace(
            '"tiny__task-1"', f'"{name}"'))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__task-2",
         "--parallel", "3",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    # We only assert argparse acceptance here — exit code 0 OR a runtime error
    # is fine, but NOT an argparse error (exit code 2 with "unrecognized" /
    # "invalid choice" wording).
    assert result.returncode != 2 or "unrecognized arguments" not in result.stderr, (
        f"argparse rejected the new flags: {result.stderr}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_cae_run_accepts_multiple_tasks_and_parallel_flag -v`
Expected: FAIL with argparse exit code 2 and stderr mentioning `unrecognized arguments: --parallel` (the second `--task` won't error since `--task` is currently `required=True` with a single string value — argparse will silently take the last one).

- [ ] **Step 3: Write minimal implementation**

In `cae/cli.py`, in `build_parser()`:

Change `p_run.add_argument("--task", required=True)` to:
```python
    p_run.add_argument("--task", action="append", required=True, dest="tasks",
                      help="task instance_id (repeatable for multi-task runs)")
```

Add after `--max-cost-usd` (line 362):
```python
    p_run.add_argument("--parallel", type=int, default=1,
                      help="run multiple --task / --repeat units concurrently with up to N "
                           "workers (default: 1 = serial). When >1, per-unit stdout is "
                           "buffered and printed atomically at completion. Budget cap "
                           "(--max-cost-usd) is best-effort under parallelism.")
```

Then update `cmd_run` (lines 44-120) to read `args.tasks` (a list) instead of `args.task` (a string). For now, iterate over the list serially — extract the existing loop body into the per-task work. Wrap the existing single-task body in `for task_id in args.tasks:` and replace `args.task` references with `task_id`:

```python
def cmd_run(args: argparse.Namespace) -> int:
    from cae.harness import run
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workdir) if args.workdir else None
    repeat = max(1, args.repeat)
    max_cost = args.max_cost_usd
    spent = 0.0

    for task_id in args.tasks:
        task_path = Path(args.tasks_dir) / task_id
        if not (task_path / "task.json").exists():
            print(f"error: task {task_id!r} not found at {task_path}", file=sys.stderr)
            return 2
        instance_id = json.loads((task_path / "task.json").read_text())["instance_id"]
        effective_model = _resolve_effective_model(args.agent, args.model)
        safe_model = _safe_model_for_filename(effective_model)

        for i in range(1, repeat + 1):
            if max_cost is not None and spent > max_cost:
                print(
                    f"budget exhausted: spent ${spent:.4f} > max ${max_cost:.4f}; stopping at i={i}/{repeat}",
                    file=sys.stderr,
                )
                break
            repeat_index = i if repeat > 1 else None
            suffix = f"__{i}" if repeat_index is not None else ""
            out_pattern = f"*__{args.agent}__{safe_model}__{instance_id}{suffix}.json"
            existing = list(results_dir.glob(out_pattern))
            if existing and not args.force:
                print(f"skipping {out_pattern}: {len(existing)} existing result(s). Use --force to overwrite.")
                continue
            result = run(
                task_path=task_path,
                agent_name=args.agent,
                workdir=workdir,
                timeout_sec=args.timeout * 60,
                fetch_fresh=args.fetch_fresh,
                keep_workdir=args.keep_workdir,
                docker=args.docker,
                docker_image=args.docker_image,
                env_file=Path(args.env_file) if args.env_file else None,
                docker_network=args.docker_network,
                docker_extra_mounts=[tuple(m.split(":", 1)) for m in args.docker_mount.split(",")] if args.docker_mount else None,
                model=args.model,
                repeat=repeat,
                repeat_index=repeat_index,
            )
            out = results_dir / f"{result['run_id']}.json"
            out.write_text(json.dumps(result, indent=2, default=str))
            print(f"wrote {out}")
            print(f"status: {result['status']}")
            cost = (result.get("usage") or {}).get("cost_usd") or 0.0
            spent += cost
            if max_cost is not None:
                print(f"spent: ${spent:.4f} / max ${max_cost:.4f}")
    return 0
```

(For now, `--parallel` is accepted by argparse but ignored. The next task wires it up.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_cae_run_accepts_multiple_tasks_and_parallel_flag -v`
Expected: PASS (argparse accepts the flags; both tasks run serially producing 2 result files).

Also run the full suite to ensure no regressions:
Run: `uv run pytest -q`
Expected: 92 passed, 2 skipped (one new test added).

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "feat(cli): make --task repeatable and accept --parallel N

argparse surface only — --parallel is accepted but currently ignored.
The serial loop over args.tasks preserves byte-for-byte behavior of the
previous single-task implementation.

Self-improve feature: closes the 'v1 is single-threaded' gap noted in
docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md:266."
```

---

### Task 2: Extract `_execute_run_unit` helper for one (task, repeat-index) unit

**Files:**
- Modify: `cae/cli.py:44-120` (the body of `cmd_run`)
- Test: `tests/test_cli.py`

Pure refactor — no behavior change. Pulls the "do one unit of work" logic into a callable so Task 3 can dispatch it via a thread pool.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_execute_run_unit_writes_result_and_returns_cost(tmp_path, tiny_task_path):
    """`_execute_run_unit` runs one (task, repeat_index) pair end-to-end and
    returns the cost spent (0.0 for mock). It's the unit-of-work callable that
    the parallel dispatcher will hand to ThreadPoolExecutor."""
    from cae.cli import _execute_run_unit, _resolve_effective_model, _safe_model_for_filename

    proj = tmp_path
    tasks_dir = proj / "tasks"
    task_slug = "tiny__task-1"
    task_path = tasks_dir / task_slug
    (task_path / "repo").mkdir(parents=True)
    (task_path / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = task_path / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    results_dir = proj / "results"
    results_dir.mkdir()

    effective_model = _resolve_effective_model("mock", None)
    safe_model = _safe_model_for_filename(effective_model)

    cost = _execute_run_unit(
        task_path=task_path,
        agent_name="mock",
        instance_id=task_slug,
        safe_model=safe_model,
        repeat=1,
        repeat_index=None,
        results_dir=results_dir,
        workdir=None,
        timeout_sec=600,
        fetch_fresh=False,
        keep_workdir=False,
        docker=False,
        docker_image="python:3.11-slim",
        env_file=None,
        docker_network="bridge",
        docker_extra_mounts=None,
        model=None,
        force=False,
    )
    assert cost == 0.0  # mock has no cost
    files = list(results_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["agent"] == "mock"
    assert data["task_id"] == "tiny__task-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_execute_run_unit_writes_result_and_returns_cost -v`
Expected: FAIL with `ImportError: cannot import name '_execute_run_unit' from 'cae.cli'`.

- [ ] **Step 3: Write minimal implementation**

In `cae/cli.py`, extract the inner loop body into a module-level function. Place it above `cmd_run`. The function takes primitive args (no `argparse.Namespace`) so it's testable in isolation and thread-safe:

```python
def _execute_run_unit(
    *,
    task_path: Path,
    agent_name: str,
    instance_id: str,
    safe_model: str,
    repeat: int,
    repeat_index: int | None,
    results_dir: Path,
    workdir: Path | None,
    timeout_sec: int,
    fetch_fresh: bool,
    keep_workdir: bool,
    docker: bool,
    docker_image: str,
    env_file: Path | None,
    docker_network: str,
    docker_extra_mounts: list[tuple[str, str]] | None,
    model: str | None,
    force: bool,
) -> float:
    """Run ONE (task, repeat_index) pair end-to-end. Returns cost_usd spent.

    Skips (returns 0.0) if a result file already exists and `force` is False.
    """
    from cae.harness import run
    suffix = f"__{repeat_index}" if repeat_index is not None else ""
    out_pattern = f"*__{agent_name}__{safe_model}__{instance_id}{suffix}.json"
    existing = list(results_dir.glob(out_pattern))
    if existing and not force:
        print(f"skipping {out_pattern}: {len(existing)} existing result(s). Use --force to overwrite.")
        return 0.0
    result = run(
        task_path=task_path,
        agent_name=agent_name,
        workdir=workdir,
        timeout_sec=timeout_sec,
        fetch_fresh=fetch_fresh,
        keep_workdir=keep_workdir,
        docker=docker,
        docker_image=docker_image,
        env_file=env_file,
        docker_network=docker_network,
        docker_extra_mounts=docker_extra_mounts,
        model=model,
        repeat=repeat,
        repeat_index=repeat_index,
    )
    out = results_dir / f"{result['run_id']}.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out}")
    print(f"status: {result['status']}")
    return (result.get("usage") or {}).get("cost_usd") or 0.0
```

Then rewrite `cmd_run` to call it (still serial — parallel comes next):

```python
def cmd_run(args: argparse.Namespace) -> int:
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workdir) if args.workdir else None
    repeat = max(1, args.repeat)
    max_cost = args.max_cost_usd
    spent = 0.0

    docker_extra_mounts = ([tuple(m.split(":", 1)) for m in args.docker_mount.split(",")]
                          if args.docker_mount else None)
    env_file = Path(args.env_file) if args.env_file else None

    effective_model = _resolve_effective_model(args.agent, args.model)
    safe_model = _safe_model_for_filename(effective_model)

    for task_id in args.tasks:
        task_path = Path(args.tasks_dir) / task_id
        if not (task_path / "task.json").exists():
            print(f"error: task {task_id!r} not found at {task_path}", file=sys.stderr)
            return 2
        instance_id = json.loads((task_path / "task.json").read_text())["instance_id"]

        for i in range(1, repeat + 1):
            if max_cost is not None and spent > max_cost:
                print(
                    f"budget exhausted: spent ${spent:.4f} > max ${max_cost:.4f}; stopping at i={i}/{repeat}",
                    file=sys.stderr,
                )
                break
            repeat_index = i if repeat > 1 else None
            spent += _execute_run_unit(
                task_path=task_path,
                agent_name=args.agent,
                instance_id=instance_id,
                safe_model=safe_model,
                repeat=repeat,
                repeat_index=repeat_index,
                results_dir=results_dir,
                workdir=workdir,
                timeout_sec=args.timeout * 60,
                fetch_fresh=args.fetch_fresh,
                keep_workdir=args.keep_workdir,
                docker=args.docker,
                docker_image=args.docker_image,
                env_file=env_file,
                docker_network=args.docker_network,
                docker_extra_mounts=docker_extra_mounts,
                model=args.model,
                force=args.force,
            )
            if max_cost is not None:
                print(f"spent: ${spent:.4f} / max ${max_cost:.4f}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_execute_run_unit_writes_result_and_returns_cost -v`
Expected: PASS.

Also re-run the full suite to confirm no regressions from the refactor:
Run: `uv run pytest -q`
Expected: 93 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "refactor(cli): extract _execute_run_unit from cmd_run

Pure refactor — no behavior change. Sets up Task 3 (parallel dispatch)
by making the unit-of-work callable independently testable."
```

---

### Task 3: Wire up `ThreadPoolExecutor` dispatch when `--parallel > 1`

**Files:**
- Modify: `cae/cli.py:44-120` (replace the inner double-loop in `cmd_run`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_parallel_produces_all_results(tmp_path, tiny_task_path):
    """`--task A --task B --parallel 2` produces two result files."""
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for name in ("tiny__task-1", "tiny__task-2"):
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
         "--task", "tiny__task-1", "--task", "tiny__task-2",
         "--parallel", "2",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    files = sorted(proj / "results").glob("*.json")
    # Filter to result files (skip stray JSON like .gitkeep etc.)
    result_files = [f for f in files if "__mock__" in f.name]
    assert len(result_files) == 2, (
        f"expected 2 result files, got {len(result_files)}: {[f.name for f in result_files]}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_cae_run_parallel_produces_all_results -v`
Expected: FAIL — `--parallel` is currently ignored, so only 1 of the 2 tasks runs (because `cmd_run` iterates serially... wait, after Task 2 it iterates over `args.tasks` serially, so BOTH should run). 

Actually this test should ALREADY pass after Task 2 (which iterates `args.tasks` serially). Update the test to also assert parallel-specific behavior: capture total wall time and assert it's noticeably faster than serial would be. Since mock is fast, timing is flaky — instead, mock the harness to introduce artificial delay and assert speedup.

**Better test:** Replace the test body with one that injects a slow mock adapter via `monkeypatch` so we can observe concurrency. Append this instead:

```python
def test_cae_run_parallel_is_concurrent(tmp_path, tiny_task_path, monkeypatch):
    """When --parallel=N, N units run concurrently. We verify by patching the
    mock adapter's build_command path with a slow function and checking that
    total wall time is ~1x the per-unit time, not ~N x."""
    import time
    import os

    # Make the tiny task's setup_cmd include a sleep so each unit takes ~1s.
    proj = tmp_path
    tasks_dir = proj / "tasks"
    for idx, name in enumerate(("tiny__task-1", "tiny__task-2", "tiny__task-3")):
        t = tasks_dir / name
        (t / "repo").mkdir(parents=True)
        task_json = json.loads((tiny_task_path / "task.json").read_text())
        task_json["instance_id"] = name
        # Inject a sleep into test_cmd via a shell `;` separator that runs BEFORE pytest.
        # The mock adapter doesn't sleep, but this makes the unit's overall runtime ~1s.
        task_json["setup_cmd"] = "sleep 1"
        (t / "task.json").write_text(json.dumps(task_json))
        for child in (tiny_task_path / "repo").iterdir():
            dest = t / "repo" / child.name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
    (proj / "results").mkdir()

    def run_cae(parallel: int) -> float:
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-m", "cae", "run", "--agent", "mock",
             "--task", "tiny__task-1", "--task", "tiny__task-2", "--task", "tiny__task-3",
             "--parallel", str(parallel),
             "--tasks-dir", str(tasks_dir),
             "--results-dir", str(proj / "results"),
             "--force"],
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        return time.monotonic() - start

    serial = run_cae(1)
    parallel = run_cae(3)
    # 3 units @ ~1s each. Serial ~3s; parallel-3 ~1s. Allow generous slack.
    assert parallel < serial * 0.6, (
        f"parallel ({parallel:.1f}s) not meaningfully faster than serial ({serial:.1f}s)"
    )
```

Run: `uv run pytest tests/test_cli.py::test_cae_run_parallel_is_concurrent -v`
Expected: FAIL — `--parallel` is ignored, so parallel wall time ≈ serial wall time.

- [ ] **Step 3: Write minimal implementation**

In `cae/cli.py`, replace the body of `cmd_run` with a units-list + dispatcher:

```python
def cmd_run(args: argparse.Namespace) -> int:
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workdir) if args.workdir else None
    repeat = max(1, args.repeat)
    max_cost = args.max_cost_usd
    docker_extra_mounts = ([tuple(m.split(":", 1)) for m in args.docker_mount.split(",")]
                          if args.docker_mount else None)
    env_file = Path(args.env_file) if args.env_file else None
    effective_model = _resolve_effective_model(args.agent, args.model)
    safe_model = _safe_model_for_filename(effective_model)

    # Validate tasks up front so we don't start parallel work only to fail late.
    units: list[tuple[Path, str, int | None]] = []
    for task_id in args.tasks:
        task_path = Path(args.tasks_dir) / task_id
        if not (task_path / "task.json").exists():
            print(f"error: task {task_id!r} not found at {task_path}", file=sys.stderr)
            return 2
        instance_id = json.loads((task_path / "task.json").read_text())["instance_id"]
        for i in range(1, repeat + 1):
            units.append((task_path, instance_id, i if repeat > 1 else None))

    parallel = max(1, args.parallel)
    if parallel == 1 or len(units) <= 1:
        # Serial path: preserve current behavior exactly (no output buffering).
        spent = 0.0
        for task_path, instance_id, repeat_index in units:
            if max_cost is not None and spent > max_cost:
                print(
                    f"budget exhausted: spent ${spent:.4f} > max ${max_cost:.4f}",
                    file=sys.stderr,
                )
                break
            spent += _execute_run_unit(
                task_path=task_path, agent_name=args.agent, instance_id=instance_id,
                safe_model=safe_model, repeat=repeat, repeat_index=repeat_index,
                results_dir=results_dir, workdir=workdir, timeout_sec=args.timeout * 60,
                fetch_fresh=args.fetch_fresh, keep_workdir=args.keep_workdir,
                docker=args.docker, docker_image=args.docker_image, env_file=env_file,
                docker_network=args.docker_network, docker_extra_mounts=docker_extra_mounts,
                model=args.model, force=args.force,
            )
            if max_cost is not None:
                print(f"spent: ${spent:.4f} / max ${max_cost:.4f}")
        return 0

    # Parallel path: ThreadPoolExecutor with output buffering + budget lock.
    import io
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print_lock = threading.Lock()
    budget_lock = threading.Lock()
    spent_box = [0.0]  # mutable holder so workers can update via closure

    def worker(unit):
        task_path, instance_id, repeat_index = unit
        # Best-effort budget check under lock.
        with budget_lock:
            if max_cost is not None and spent_box[0] > max_cost:
                return ("skip", instance_id, repeat_index, 0.0)
        buf = io.StringIO()

        def emit(line):
            buf.write(line + "\n")

        # Redirect this unit's prints into the buffer by swapping print's file kwarg.
        # We can't easily override the global print; instead, we capture by having
        # _execute_run_unit emit via a callable. For now, _execute_run_unit uses
        # module-level print(); we redirect stdout for the duration of the call.
        import contextlib
        import sys as _sys
        orig_stdout = _sys.stdout
        with contextlib.redirect_stdout(buf):
            cost = _execute_run_unit(
                task_path=task_path, agent_name=args.agent, instance_id=instance_id,
                safe_model=safe_model, repeat=repeat, repeat_index=repeat_index,
                results_dir=results_dir, workdir=workdir, timeout_sec=args.timeout * 60,
                fetch_fresh=args.fetch_fresh, keep_workdir=args.keep_workdir,
                docker=args.docker, docker_image=args.docker_image, env_file=env_file,
                docker_network=args.docker_network, docker_extra_mounts=docker_extra_mounts,
                model=args.model, force=args.force,
            )
        with budget_lock:
            spent_box[0] += cost
        return ("ok", instance_id, repeat_index, cost, buf.getvalue())

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [pool.submit(worker, u) for u in units]
        for fut in as_completed(futures):
            result = fut.result()
            tag = result[0]
            instance_id = result[1]
            with print_lock:
                if tag == "skip":
                    print(f"[{instance_id}] skipped: budget exhausted")
                    continue
                _, _, _, cost, output = result
                print(f"--- {instance_id} (cost ${cost:.4f}) ---")
                if output:
                    print(output.rstrip())
                if max_cost is not None:
                    with budget_lock:
                        cur = spent_box[0]
                    print(f"total spent: ${cur:.4f} / max ${max_cost:.4f}")
    return 0
```

Note: the `contextlib.redirect_stdout` approach is process-wide, which means while a worker holds it, other workers' prints also go to that buffer. This is the standard caveat of using `redirect_stdout` from threads. Two options:

A. **Accept it.** Since each worker only prints around the call to `_execute_run_unit`, and we hold the lock when emitting the buffered content, output ends up coherent (just possibly interleaved per-line if two workers print at the same instant). Mock adapter prints nothing during runs, so this is fine for tests.

B. **Refactor `_execute_run_unit` to return its output as a string instead of printing it.** Cleaner, but a bigger change.

We'll go with B in Task 4 to make the output truly clean. For Task 3, option A is enough to pass the concurrency test.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_cae_run_parallel_is_concurrent tests/test_cli.py::test_cae_run_parallel_produces_all_results -v`
Expected: PASS for both.

Full suite:
Run: `uv run pytest -q`
Expected: 94 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "feat(cli): dispatch --parallel > 1 via ThreadPoolExecutor

When --parallel N > 1 and there's more than one (task, repeat-index)
unit, units are dispatched to a ThreadPoolExecutor with N workers.
Each unit's stdout is buffered and printed atomically under a lock.
Budget cap (--max-cost-usd) is checked under a separate lock; it is
best-effort and may overshoot by up to N-1 in-flight units."
```

---

### Task 4: Refactor `_execute_run_unit` to return its output (instead of printing)

**Files:**
- Modify: `cae/cli.py` (`_execute_run_unit` signature + `cmd_run` callers)
- Test: `tests/test_cli.py`

`contextlib.redirect_stdout` is process-wide — under threads, two workers' prints collide. The fix: make `_execute_run_unit` return its output as a string, so the worker can capture cleanly without redirecting global stdout.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_execute_run_unit_returns_output_string(tmp_path, tiny_task_path):
    """`_execute_run_unit` returns (cost, output_lines) — no printing."""
    from cae.cli import _execute_run_unit, _resolve_effective_model, _safe_model_for_filename

    proj = tmp_path
    tasks_dir = proj / "tasks"
    task_slug = "tiny__task-1"
    task_path = tasks_dir / task_slug
    (task_path / "repo").mkdir(parents=True)
    (task_path / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = task_path / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    results_dir = proj / "results"
    results_dir.mkdir()

    effective_model = _resolve_effective_model("mock", None)
    safe_model = _safe_model_for_filename(effective_model)

    cost, output = _execute_run_unit(
        task_path=task_path,
        agent_name="mock",
        instance_id=task_slug,
        safe_model=safe_model,
        repeat=1,
        repeat_index=None,
        results_dir=results_dir,
        workdir=None,
        timeout_sec=600,
        fetch_fresh=False,
        keep_workdir=False,
        docker=False,
        docker_image="python:3.11-slim",
        env_file=None,
        docker_network="bridge",
        docker_extra_mounts=None,
        model=None,
        force=False,
    )
    assert cost == 0.0
    assert isinstance(output, str)
    assert "wrote" in output
    assert "status:" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_execute_run_unit_returns_output_string -v`
Expected: FAIL — `_execute_run_unit` currently returns just a float, not `(float, str)`.

- [ ] **Step 3: Write minimal implementation**

Change `_execute_run_unit` to collect lines into a list and return `(cost, output)`:

```python
def _execute_run_unit(
    *,
    task_path: Path,
    agent_name: str,
    instance_id: str,
    safe_model: str,
    repeat: int,
    repeat_index: int | None,
    results_dir: Path,
    workdir: Path | None,
    timeout_sec: int,
    fetch_fresh: bool,
    keep_workdir: bool,
    docker: bool,
    docker_image: str,
    env_file: Path | None,
    docker_network: str,
    docker_extra_mounts: list[tuple[str, str]] | None,
    model: str | None,
    force: bool,
) -> tuple[float, str]:
    """Run ONE (task, repeat_index) pair end-to-end.

    Returns (cost_usd, output_text) where output_text is the lines that
    would otherwise have been printed. Callers decide whether to print
    (serial mode) or buffer + emit atomically (parallel mode).
    """
    from cae.harness import run
    lines: list[str] = []
    suffix = f"__{repeat_index}" if repeat_index is not None else ""
    out_pattern = f"*__{agent_name}__{safe_model}__{instance_id}{suffix}.json"
    existing = list(results_dir.glob(out_pattern))
    if existing and not force:
        lines.append(
            f"skipping {out_pattern}: {len(existing)} existing result(s). Use --force to overwrite."
        )
        return 0.0, "\n".join(lines)
    result = run(
        task_path=task_path, agent_name=agent_name, workdir=workdir,
        timeout_sec=timeout_sec, fetch_fresh=fetch_fresh, keep_workdir=keep_workdir,
        docker=docker, docker_image=docker_image, env_file=env_file,
        docker_network=docker_network, docker_extra_mounts=docker_extra_mounts,
        model=model, repeat=repeat, repeat_index=repeat_index,
    )
    out = results_dir / f"{result['run_id']}.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    lines.append(f"wrote {out}")
    lines.append(f"status: {result['status']}")
    cost = (result.get("usage") or {}).get("cost_usd") or 0.0
    return cost, "\n".join(lines)
```

Update `cmd_run` to handle the new return shape:

In the **serial branch** of `cmd_run`:
```python
        cost, output = _execute_run_unit(...)
        if output:
            print(output)
        spent += cost
```

In the **parallel branch** of `cmd_run`, drop the `contextlib.redirect_stdout` wrapper:
```python
        cost, output = _execute_run_unit(...)
        with budget_lock:
            spent_box[0] += cost
        return ("ok", instance_id, repeat_index, cost, output)
```

Also delete the `import contextlib` and `import sys as _sys` lines that are no longer needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_execute_run_unit_returns_output_string tests/test_cli.py::test_execute_run_unit_writes_result_and_returns_cost tests/test_cli.py::test_cae_run_parallel_is_concurrent tests/test_cli.py::test_cae_run_parallel_produces_all_results -v`
Expected: 4 PASS.

The second test (`test_execute_run_unit_writes_result_and_returns_cost`) needs to be updated to expect a tuple. Apply this Edit to that test:

Change:
```python
    cost = _execute_run_unit(
        ...
    )
    assert cost == 0.0  # mock has no cost
```
to:
```python
    cost, _output = _execute_run_unit(
        ...
    )
    assert cost == 0.0  # mock has no cost
```

Full suite:
Run: `uv run pytest -q`
Expected: 95 passed, 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "refactor(cli): _execute_run_unit returns (cost, output) tuple

Previously the unit function printed directly to stdout, which collides
under concurrent.futures threads (stdout is process-wide). Returning
the output as a string lets the parallel dispatcher buffer + emit each
unit's output atomically under a lock."
```

---

### Task 5: Test that one unit's failure doesn't kill the others in parallel mode

**Files:**
- Modify: `tests/test_cli.py`

This is a regression guard: a task_error in one unit must not abort the pool. The harness already returns a result dict with `status: task_error` rather than raising, but we want a test that locks that contract in for the parallel path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_run_parallel_isolates_task_errors(tmp_path, tiny_task_path):
    """If one unit hits a task_error (missing repo, bad patch, etc.),
    the other units still complete and write results. The harness returns
    task_error as a status rather than raising; this test locks that in
    for the parallel dispatch path.
    """
    proj = tmp_path
    tasks_dir = proj / "tasks"
    # tiny__task-1: healthy
    healthy = tasks_dir / "tiny__task-1"
    (healthy / "repo").mkdir(parents=True)
    (healthy / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        dest = healthy / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    # tiny__broken: setup_cmd fails → harness returns task_error
    broken = tasks_dir / "tiny__broken"
    (broken / "repo").mkdir(parents=True)
    bad_json = json.loads((tiny_task_path / "task.json").read_text())
    bad_json["instance_id"] = "tiny__broken"
    bad_json["setup_cmd"] = "false"  # always exits non-zero
    (broken / "task.json").write_text(json.dumps(bad_json))
    for child in (tiny_task_path / "repo").iterdir():
        dest = broken / "repo" / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)

    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1", "--task", "tiny__broken",
         "--parallel", "2",
         "--tasks-dir", str(tasks_dir),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # Both result files must exist, regardless of the broken task.
    result_files = sorted(f.name for f in (proj / "results").glob("*__mock__*.json"))
    assert any("tiny__task-1" in n for n in result_files), result_files
    assert any("tiny__broken" in n for n in result_files), result_files

    # The broken task's status must be task_error, not a crash.
    broken_file = next(f for f in (proj / "results").glob("*__mock__*tiny__broken*.json"))
    broken_data = json.loads(broken_file.read_text())
    assert broken_data["status"] == "task_error", broken_data["status"]
```

- [ ] **Step 2: Run test — it should already pass**

Run: `uv run pytest tests/test_cli.py::test_cae_run_parallel_isolates_task_errors -v`
Expected: PASS. The harness already isolates errors (returns `task_error` status rather than raising); the parallel dispatcher inherits that for free.

If it FAILS, that's a real regression in the parallel path — investigate before moving on.

- [ ] **Step 3: Add a one-line doc comment to `cmd_run`'s parallel branch**

In `cae/cli.py`, just inside the `with ThreadPoolExecutor(...)` block, add a comment so future readers know this is intentional:

```python
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        # The harness returns task_error / agent_error as result statuses
        # rather than raising, so a failing unit doesn't poison the pool.
        futures = [pool.submit(worker, u) for u in units]
```

- [ ] **Step 4: Re-run the test to confirm green**

Run: `uv run pytest tests/test_cli.py::test_cae_run_parallel_isolates_task_errors -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "test(cli): parallel dispatch isolates per-unit task_errors

Regression guard: a task_error in one (task, repeat) unit must not
abort the pool. The harness returns task_error as a status rather
than raising, so this holds for free — this test locks the contract
in for the parallel path."
```

---

### Task 6: Update the design spec to reflect that `--parallel` is implemented

**Files:**
- Modify: `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md:266` (the "Concurrency: v1 is single-threaded. A `--parallel N` flag can come later." line)

- [ ] **Step 1: Read the surrounding context**

Run: `grep -n -B2 -A2 "single-threaded" docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md`
Expected: shows the line in context, plus the open-questions section if it's listed there too.

- [ ] **Step 2: Update the spec**

In `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md`, find the "Concurrency: v1 is single-threaded. A `--parallel N` flag can come later." line and replace with:

```
Concurrency: `--parallel N` runs multiple `(task, repeat-index)` units concurrently via a thread pool. Each unit gets its own workdir and result file (filename includes instance_id + repeat index, so concurrent writes don't collide). Default is `--parallel 1` (serial) which preserves the original v1 behavior. Budget cap (`--max-cost-usd`) is best-effort under parallelism — up to N-1 in-flight units may overshoot.
```

If the same phrasing appears in an "Open Questions" section, mark it resolved.

- [ ] **Step 3: Sanity-check the docs build still works**

Run: `uv run pytest tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md
git commit -m "docs: mark --parallel N as implemented in the design spec

Removes the 'v1 is single-threaded' caveat and documents the actual
concurrency model (thread pool, per-unit workdir, best-effort budget)."
```

---

## Self-Review

**1. Spec coverage.** The design spec's deferral ("Concurrency: v1 is single-threaded. A `--parallel N` flag can come later.") is the entire spec basis for this feature. Task 6 marks it done. No other spec section mentions concurrency.

**2. Placeholder scan.** Searched the plan for "TBD", "TODO", "implement later", "add appropriate error handling", "handle edge cases", "Similar to Task N". None found. Every step has either concrete code or a concrete command + expected output.

**3. Type consistency.** `_execute_run_unit`'s signature is identical in Task 2 (introduced) and Task 4 (return type widened from `float` to `tuple[float, str]`). Tests in Task 2 vs Task 4 use the matching shape. `safe_model`, `instance_id`, `repeat_index` parameter names match across all callers. `spent_box` (the budget holder) is named consistently in the parallel branch.

**4. Risk check.** Per self-improve policy:
- No new dependencies (stdlib `concurrent.futures`, `threading`, `io` only). ✓
- No schema/migration changes (result JSON shape unchanged). ✓
- No breaking API/CLI changes (`--task foo` still works — `action="append"` is backwards-compatible for single values). ✓ Wait — actually `action="append"` with `required=True` means `--task foo` produces `["foo"]` (a list), which IS a breaking change for any code reading `args.task` as a string. Confined to `cmd_run` which we're rewriting in the same task. No other call site reads `args.task`. ✓
- LOC cap: estimated ~150 LOC added across `cae/cli.py` (under the 500 cap). ✓
- Files touched: `cae/cli.py`, `tests/test_cli.py`, `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` = 3 files (under the 8 cap). ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-parallel-flag.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
