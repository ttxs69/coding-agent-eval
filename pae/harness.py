"""Run loop: orchestrate one (task, agent) pair through the 11-step lifecycle.

This module implements local mode only in v1. Docker mode (pae/docker_run.py)
is added in Phase 5 (Task 22). Steps 1-11 follow the spec section "Run Lifecycle".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure `python` is on PATH for LOCAL subprocess calls. macOS only has `python3`
# on the default PATH; without this, test_cmd strings like `python -m pytest ...`
# fail with "command not found" when run via `subprocess.run(..., shell=True)`.
# This is ONLY needed for local mode — in docker mode the container has its own
# python, and prepending the host's venv path would break the container.
if "pae_skip_path_setup" not in os.environ:
    _venv_bin = Path(sys.executable).parent
    if str(_venv_bin) not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = f"{_venv_bin}{os.pathsep}{os.environ.get('PATH', '')}"

from pae.agents import get_adapter  # noqa: E402
from pae.agents.base import Status, TestStatus  # noqa: E402
from pae.grader import grade  # noqa: E402
from pae.parsers import parse_pytest_output  # noqa: E402


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id_for_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _run_subprocess(cmd: str | list[str], cwd: Path, timeout: int) -> tuple[int, str, str, float]:
    """Run a shell command, return (exit_code, stdout, stderr, duration_sec)."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd if isinstance(cmd, list) else cmd,
            shell=isinstance(cmd, str),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return -1, "", f"timeout after {timeout}s", elapsed


def _ensure_git_repo(workdir: Path) -> None:
    """Initialize a git repo in workdir if one doesn't exist, and commit all files."""
    if (workdir / ".git").exists():
        return
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "pae@local"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "pae"], cwd=workdir, check=True)
    # If workdir is empty except for .git (e.g., --no-fetch-repo or a SWE-bench
    # task that imported without a repo/), `git add .` is a no-op and `git commit`
    # would fail with "nothing to commit". Make an empty initial commit so
    # subsequent git operations (diff, status) work even on empty workdirs.
    non_git_entries = [p for p in workdir.iterdir() if p.name != ".git"]
    if not non_git_entries:
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "initial"],
                       cwd=workdir, check=True)
    else:
        subprocess.run(["git", "add", "."], cwd=workdir, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=workdir, check=True)


def _apply_test_patch(workdir: Path, task_dir: Path) -> bool:
    """Apply tests.patch if it exists. No-op for hand-authored tasks.

    Returns True if the patch was applied (or didn't exist), False if it
    failed to apply. Failure typically means the workdir doesn't have the
    repo source (e.g., --no-fetch-repo on a SWE-bench task).
    """
    patch = task_dir / "tests.patch"
    if not patch.exists():
        return True
    # Resolve the patch path to absolute so git can find it regardless of cwd.
    # (git apply runs with cwd=workdir, so a relative patch path would be
    # resolved against the workdir, not the original task location.)
    proc = subprocess.run(
        ["git", "apply", str(patch.resolve())],
        cwd=workdir, capture_output=True, text=True,
    )
    return proc.returncode == 0


def _run_tests(cmd: str, workdir: Path, timeout: int, run_subprocess=_run_subprocess) -> dict[str, TestStatus]:
    """Run a test command and parse its output via the pytest parser.

    `run_subprocess` is the (cmd, cwd, timeout) -> (rc, stdout, stderr, dur) callable.
    Defaults to the local-mode `_run_subprocess`; Task 22 swaps in a docker dispatcher.

    Returns {nodeid: TestStatus}.
    """
    exit_code, stdout, stderr, _ = run_subprocess(cmd, workdir, timeout=timeout)
    if exit_code not in (0, 1, 2, 3, 4, 5):  # pytest uses 0-5
        return {}
    return parse_pytest_output(stdout + "\n" + stderr)


def _fetch_fresh(repo: str, base_commit: str, dest: Path) -> None:
    """Clone `repo` at `base_commit` into `dest` (network)."""
    url = f"https://github.com/{repo}.git"
    subprocess.run(["git", "init", "-q", str(dest)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "fetch", "--depth=1", "origin", base_commit], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "checkout", base_commit], cwd=dest, check=True, capture_output=True)


def _git_sha_cached() -> str:
    """Return the harness's git short SHA, computed once per process."""
    global _git_sha_cache
    try:
        if _git_sha_cache is None:
            proc = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            _git_sha_cache = proc.stdout.strip()
        return _git_sha_cache
    except Exception:
        return "unknown"


_git_sha_cache: str | None = None


def run(
    task_path: Path,
    agent_name: str,
    workdir: Path | None = None,
    timeout_sec: int = 1800,
    fetch_fresh: bool = False,
    keep_workdir: bool = False,
    docker: bool = False,
    docker_image: str = "python:3.11-slim",
    env_file: Path | None = None,
    docker_network: str = "bridge",
    docker_extra_mounts: list[tuple[str, str]] | None = None,
    repeat: int = 1,
    repeat_index: int | None = None,
) -> dict:
    """Run a single (task, agent) pair through the full harness. Return the result dict.

    Args:
        task_path: path to a directory containing task.json (and optional tests.patch, repo/).
        agent_name: name of a registered adapter (e.g. "mock", "claude-code").
        workdir: optional pre-populated workdir. If None, harness creates a tempdir.
        timeout_sec: per-stage timeout (setup, pre-flight, agent, grading).
        fetch_fresh: if True (and workdir is auto-created), clone repo at base_commit
            from GitHub instead of copying from task_path/repo/.
        keep_workdir: if True, don't delete the workdir after the run.
        docker: if True, run setup / pre-flight / agent / grading inside a Docker container.
        docker_image: base image for docker mode.
        env_file: env file passed to `docker run --env-file` (for API keys).
        repeat: total number of times this run is being repeated (1 = no repeat).
        repeat_index: 1-based index of this specific run within a repeated batch.
            When `repeat=1`, this is None and the run_id omits the suffix.

    This function runs a SINGLE run. The CLI is responsible for looping when
    `repeat > 1` (see Task 19). `duration_sec` in the result is the duration of
    this single run, not the batch.

    Returns a dict matching the spec's Output JSON shape.
    """
    task_dir = Path(task_path)
    task = json.loads((task_dir / "task.json").read_text())
    fail_to_pass = task["fail_to_pass"]
    pass_to_pass = task["pass_to_pass"]
    mode = "docker" if docker else "local"

    # 1-3: Resolve task, create workdir, fetch repo
    workdir_owned = workdir is None
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="pae-"))
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if workdir_owned:
        if fetch_fresh:
            _fetch_fresh(task["repo"], task["base_commit"], workdir)
        else:
            repo_src = task_dir / "repo"
            if repo_src.exists():
                for child in repo_src.iterdir():
                    dest = workdir / child.name
                    if child.is_dir():
                        shutil.copytree(child, dest)
                    else:
                        shutil.copy2(child, dest)

    _ensure_git_repo(workdir)
    if not _apply_test_patch(workdir, task_dir):
        return _result(task, agent_name, mode, Status.TASK_ERROR, "unknown", {}, {}, "", str(workdir),
                       f"could not apply tests.patch — workdir is empty (use --fetch-fresh or "
                       f"run without --no-fetch-repo). Patch: {task_dir / 'tests.patch'}")

    # Pick a subprocess runner: local (default) or docker (one container, multiple execs).
    # In docker mode, start ONE container and exec into it for each step so state
    # (e.g. `pip install pytest` in setup_cmd) persists to test_cmd.
    if docker:
        from pae.docker_run import Container
        container = Container(
            docker_image, workdir,
            env_file=env_file,
            network=docker_network,
            extra_mounts=docker_extra_mounts,
        )
    else:
        container = None

    def run_step(cmd, cwd, timeout):
        if container is not None:
            return container.run(
                cmd if isinstance(cmd, list) else cmd.split(),
                timeout=timeout,
            )
        return _run_subprocess(cmd, cwd, timeout=timeout)

    # 5: Setup
    if task.get("setup_cmd"):
        setup_rc, _, setup_err, _ = run_step(task["setup_cmd"], workdir, timeout=timeout_sec)
        if setup_rc != 0:
            return _result(task, agent_name, mode, Status.TASK_ERROR, "unknown", {}, {}, "", str(workdir),
                           f"setup_cmd failed: {setup_err[:200]}")

    # 6: Pre-flight
    pre = _run_tests(task["test_cmd"], workdir, timeout=timeout_sec, run_subprocess=run_step)
    pre_flight = {"fail_to_pass": {n: pre.get(n, TestStatus.ERROR).value for n in fail_to_pass},
                  "pass_to_pass": {n: pre.get(n, TestStatus.ERROR).value for n in pass_to_pass}}
    # validate: fail_to_pass tests should currently fail, pass_to_pass should currently pass
    pre_fails_correctly = all(pre_flight["fail_to_pass"][n] != "passed" for n in fail_to_pass)
    pre_passes_correctly = all(pre_flight["pass_to_pass"][n] == "passed" for n in pass_to_pass)
    if not (pre_fails_correctly and pre_passes_correctly):
        return _result(task, agent_name, mode, Status.TASK_ERROR, "unknown", pre_flight, pre_flight, "",
                       str(workdir), "pre-flight validation failed: fail_to_pass tests do not all fail, "
                       "or pass_to_pass tests do not all pass")

    # 7: Run agent
    adapter = get_adapter(agent_name)
    if not adapter.is_available():
        return _result(task, agent_name, mode, Status.AGENT_ERROR, "unknown", pre_flight, pre_flight, "",
                       str(workdir), f"agent {agent_name} not available")
    agent_version = adapter.version()
    cmd = adapter.build_command(workdir, task["prompt"], model=None)
    agent_rc, agent_stdout, agent_stderr, duration = run_step(cmd, workdir, timeout=timeout_sec)
    if agent_rc == -1:
        return _result(task, agent_name, mode, Status.TIMEOUT, agent_version, pre_flight, pre_flight, "",
                       str(workdir), f"agent timed out after {timeout_sec}s")
    parsed = adapter.parse_output(agent_stdout, agent_stderr, agent_rc)
    if parsed.exit_code != 0:
        return _result(task, agent_name, mode, Status.AGENT_ERROR, agent_version, pre_flight, pre_flight, "",
                       str(workdir), f"agent exited non-zero: {parsed.exit_code}")

    # 8: Capture patch
    diff_proc = subprocess.run(["git", "diff"], cwd=workdir, capture_output=True, text=True)
    patch = diff_proc.stdout

    # 9: Grade
    post = _run_tests(task["test_cmd"], workdir, timeout=timeout_sec, run_subprocess=run_step)
    post_flight = {"fail_to_pass": {n: post.get(n, TestStatus.ERROR).value for n in fail_to_pass},
                   "pass_to_pass": {n: post.get(n, TestStatus.ERROR).value for n in pass_to_pass}}
    status = grade({"fail_to_pass": {n: TestStatus(v) for n, v in pre_flight["fail_to_pass"].items()},
                    "pass_to_pass": {n: TestStatus(v) for n, v in pre_flight["pass_to_pass"].items()}},
                   {"fail_to_pass": {n: TestStatus(v) for n, v in post_flight["fail_to_pass"].items()},
                    "pass_to_pass": {n: TestStatus(v) for n, v in post_flight["pass_to_pass"].items()}})

    # Clean up the workdir if we created it and the user doesn't want to keep it.
    # Done here (after grading) rather than via try/finally because we want the
    # result dict's `workdir` field to point to a path that existed when the run
    # finished; the caller can disable cleanup with --keep-workdir.
    if workdir_owned and not keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)

    return _result(task, agent_name, mode, status, agent_version, pre_flight, post_flight, patch,
                   str(workdir), "", agent_model=parsed.usage.model,
                   agent_duration=duration, agent_usage=parsed.usage, repeat=repeat, repeat_index=repeat_index)


def _result(task, agent_name, mode, status, agent_version, pre_flight, post_flight, patch,
            workdir, error, agent_model=None, agent_duration=0.0, agent_usage=None,
            repeat: int = 1, repeat_index: int | None = None):
    """Build a result dict in the spec's Output JSON shape."""
    suffix = f"__{repeat_index}" if repeat_index is not None else ""
    return {
        "run_id": f"{_run_id_for_now()}__{agent_name}__{task['instance_id']}{suffix}",
        "task_id": task["instance_id"],
        "agent": agent_name,
        "agent_version": agent_version,
        "model": agent_model,
        "mode": mode,
        "status": status.value,
        "started_at": _utc_now_iso(),
        "duration_sec": agent_duration,
        "harness_git_sha": _git_sha_cached(),
        "task_source": task.get("source"),
        "usage": {
            "tokens_in": agent_usage.tokens_in if agent_usage else None,
            "tokens_out": agent_usage.tokens_out if agent_usage else None,
            "cost_usd": agent_usage.cost_usd if agent_usage else None,
            "billing_mode": agent_usage.billing_mode if agent_usage else "api",
        },
        "test_results": {"pre_flight": pre_flight, "post_flight": post_flight},
        "patch": patch,
        "workdir": workdir,
        "error": error,
    }

