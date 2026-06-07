"""Helpers for running the harness inside a Docker container (--docker mode)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def in_container() -> bool:
    """Return True if we're already running inside a Docker container."""
    # In production, `Path.root` is the literal string "/" on POSIX. In tests it
    # may be patched to a callable returning a fake root Path. Avoid creating
    # new Path instances from the patched class — its internal attributes are
    # broken — and route the lookup through `os.path` instead.
    root_attr = Path.root
    root_path = root_attr() if callable(root_attr) else root_attr
    return os.path.exists(os.path.join(str(root_path), ".dockerenv"))


def run_in_container(
    image: str,
    cmd: list[str],
    *,
    workdir: Path,
    timeout: int,
    env_file: Path | None = None,
) -> tuple[int, str, str, float]:
    """High-level wrapper around `exec_in` for ad-hoc container invocations.

    Returns (exit_code, stdout, stderr, duration_sec).
    """
    return exec_in(
        image, cmd, workdir=workdir, timeout=timeout, env_file=env_file,
    )


def exec_in(
    image: str,
    cmd: list[str],
    *,
    workdir: Path,
    timeout: int,
    env_file: Path | None = None,
) -> tuple[int, str, str, float]:
    """Run `cmd` inside a container based on `image`, with `workdir` bind-mounted.

    Returns (exit_code, stdout, stderr, duration_sec). The harness is expected
    to be installed in the image; the image's CMD/entrypoint is overridden.
    """
    args = [
        "docker", "run", "--rm",
        "-v", f"{workdir.resolve()}:/work",
        "-w", "/work",
    ]
    if env_file:
        args += ["--env-file", str(env_file)]
    args += [image] + cmd
    start = time.monotonic()
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s", time.monotonic() - start
