"""Helpers for running the harness inside a Docker container (--docker mode)."""

from __future__ import annotations

import atexit
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


class Container:
    """A long-lived container for running multiple commands with shared state.

    Per the spec: the harness starts ONE container with `docker run -d`
    (detached, with bind-mounted workdir), then `docker exec` subsequent
    commands into it. State persists across execs (e.g. `pip install pytest`
    in setup_cmd is visible to test_cmd).

    Use as a context manager:

        with Container(image, workdir) as c:
            rc, out, err, _ = c.run(["pip", "install", "pytest"])
            rc, out, err, _ = c.run(["python", "-m", "pytest"])

    The container is removed on exit (normal or exception).
    """

    def __init__(
        self,
        image: str,
        workdir: Path,
        *,
        env_file: Path | None = None,
    ):
        self.image = image
        self.workdir = workdir
        self.env_file = env_file
        self.container_id: str | None = None
        self._start()

    def _start(self) -> None:
        args = [
            "docker", "run", "-d", "--rm",
            "-v", f"{self.workdir.resolve()}:/work",
            "-w", "/work",
            "--label", "pae.managed=true",
        ]
        if self.env_file:
            args += ["--env-file", str(self.env_file)]
        # Long-running container; we exec into it. `sleep infinity` keeps it
        # alive between our execs and is killed by `--rm` on container exit.
        # Use the image's default PATH (don't inherit host's PATH which may
        # contain host-only paths to the venv's `python` that the container
        # doesn't have). `docker run` already provides a clean PATH by default
        # (it composes from the image's ENV PATH, not the host's).
        args += [self.image, "sleep", "infinity"]
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
        self.container_id = proc.stdout.strip()
        # Register an atexit hook to clean up the container if the harness
        # exits via any path (early return, exception, or normal completion
        # without explicit stop()). atexit is best-effort but covers the
        # common cases.
        atexit.register(self._atexit_stop)

    def _atexit_stop(self) -> None:
        # atexit hooks run on interpreter shutdown; suppress all errors to
        # avoid noise during normal exit.
        try:
            self.stop()
        except Exception:
            pass

    def run(
        self, cmd: list[str], *, timeout: int = 1800,
    ) -> tuple[int, str, str, float]:
        """Run `cmd` inside the container via `docker exec`. Returns (rc, out, err, dur)."""
        if not self.container_id:
            raise RuntimeError("Container not started")
        args = ["docker", "exec", "-w", "/work", self.container_id, *cmd]
        start = time.monotonic()
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - start
        except subprocess.TimeoutExpired:
            return -1, "", f"timeout after {timeout}s", time.monotonic() - start

    def stop(self) -> None:
        """Stop and remove the container. Idempotent."""
        if self.container_id:
            subprocess.run(
                ["docker", "stop", self.container_id],
                capture_output=True, text=True,
            )
            # --rm on docker run ensures removal, but be defensive
            subprocess.run(
                ["docker", "rm", "-f", self.container_id],
                capture_output=True, text=True,
            )
            self.container_id = None

    def __enter__(self) -> "Container":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
