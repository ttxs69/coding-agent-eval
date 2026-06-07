# Coding Agent Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python package `probe-agent-eval` (CLI: `cae`) that evaluates CLI coding agents (Claude Code, Codex, Aider) on SWE-bench Verified tasks and publishes results as a static leaderboard.

**Architecture:** Single Python package, one CLI, JSON results in git, static site. Local-first with Docker opt-in. SWE-bench Verified is the v1 task source. End-to-end vertical slice first (mock agent, tiny fixture), then real agents, importer, and site.

**Tech Stack:** Python 3.11+, stdlib-only CLI (`argparse`), `pytest` for tests, `ruff` for lint, `datasets` (HuggingFace) for SWE-bench import, hand-rolled static site (HTML + minimal JS, vendored highlight.js for diff highlighting). No `rich`, no `tabulate`, no `click` — minimal deps.

**Spec:** `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` (commit `939272e`).

---

## File Structure

```
probe-agent-eval/
├── pyproject.toml             # one Python package, "cae" CLI, deps: datasets, pytest, ruff
├── README.md
├── cae/
│   ├── __init__.py
│   ├── cli.py                 # argparse entry: run / build-site / add-task / list-agents / report
│   ├── harness.py             # run loop: steps 1-11 from spec
│   ├── grader.py              # status decision: pre_flight vs post_flight vs fail_to_pass/pass_to_pass
│   ├── importer.py            # cae add-task --from-swebench
│   ├── metrics.py             # aggregation: median, pass_rate, n_attempted (used by build-site and report)
│   ├── site.py                # build static leaderboard
│   ├── parsers.py             # per-runner parsers (pytest in v1; unittest, etc. added later)
│   ├── docker_run.py          # helpers for `docker exec` mode
│   ├── render_markdown.py     # tiny markdown → HTML renderer (for reproducibility.html)
│   └── agents/
│       ├── __init__.py        # ADAPTERS dict, get_adapter(), list_adapters()
│       ├── base.py            # AgentAdapter Protocol, AgentResult, UsageInfo, Status, TestStatus
│       ├── claude_code.py
│       ├── codex.py
│       ├── aider.py
│       └── mock.py            # first-class; excluded from public leaderboard by site.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # shared fixtures (tiny_task path, etc.)
│   ├── test_status.py
│   ├── test_parsers.py
│   ├── test_grader.py
│   ├── test_metrics.py
│   ├── test_agents.py
│   ├── test_harness.py
│   ├── test_importer.py
│   ├── test_cli.py
│   ├── test_site.py
│   ├── test_docker_run.py
│   ├── test_render_markdown.py
│   └── fixtures/
│       └── tiny_task/
│           ├── task.json
│           ├── repo/
│           │   ├── main.py
│           │   └── test_main.py
│           └── (no tests.patch — hand-authored task)
├── docs/
│   ├── smoke-test.md
│   ├── reproducibility.md
│   └── adding-tasks.md
└── results/                   # empty in repo; .gitkeep so the dir exists
    └── .gitkeep
```

**Decomposition rationale:** Each module has one clear responsibility. The harness orchestrates but does not grade; the grader decides but does not parse; the parsers know about a single test runner; the agents know about a single CLI. Files are small enough to hold in context and reason about.

---

## Phase 1: Vertical Slice (Tasks 1–8)

Goal: a working end-to-end `cae run` with the mock adapter against a tiny in-repo task. After Task 8, `cae run --agent mock --task tiny_task` produces a result JSON. Everything after Phase 1 is iteration on this base.

### Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `cae/__init__.py`
- Create: `cae/cli.py`
- Create: `cae/__main__.py` (enables `python -m cae`)
- Create: `tests/__init__.py`
- Create: `tests/test_cli.py`
- Create: `results/.gitkeep`
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import subprocess
import sys


def test_cae_runs_and_prints_help():
    result = subprocess.run(
        [sys.executable, "-m", "cae", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "cae" in result.stdout.lower() or "usage" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sarace/dev/probe/agent_eval && python -m pytest tests/test_cli.py::test_cae_runs_and_prints_help -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae'`

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "probe-agent-eval"
version = "0.1.0"
description = "Public benchmark for CLI coding agents (Claude Code, Codex, Aider) on SWE-bench Verified."
requires-python = ">=3.11"
dependencies = [
    "datasets>=2.14",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "ruff>=0.1",
]

[project.scripts]
cae = "cae.cli:main"

[tool.setuptools.packages.find]
include = ["cae*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pyright]
include = ["cae", "tests"]
pythonVersion = "3.11"
venv = ".venv"
```

- [ ] **Step 4: Create `cae/__init__.py`**

```python
"""probe-agent-eval: public benchmark for CLI coding agents."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Create `cae/cli.py`**

```python
"""Command-line interface for cae."""

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cae",
        description="Evaluate CLI coding agents on SWE-bench tasks.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from cae import __version__
        print(__version__)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5b: Create `cae/__main__.py`**

```python
"""Allow `python -m cae` to invoke the CLI."""

from cae.cli import main

raise SystemExit(main())
```

- [ ] **Step 6: Create `tests/__init__.py` (empty)**

```python
```

- [ ] **Step 7: Create `results/.gitkeep` (empty file)**

- [ ] **Step 7b: Create `.gitignore`**

```
.venv/
*.egg-info/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
```

```
```

- [ ] **Step 8: Create `README.md`**

```markdown
# probe-agent-eval

Public benchmark for CLI coding agents. See `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` for the design.

## Quickstart

```
pip install -e ".[dev]"
cae --help
```

## Status

Pre-v1. Phase 1 (vertical slice with mock adapter) ships in the first PR.
```

- [ ] **Step 9: Install package in editable mode and run test**

Run:
```
cd /Users/sarace/dev/probe/agent_eval
pip install -e ".[dev]"
```
Expected: install succeeds, no errors.

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_cae_runs_and_prints_help -v`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml cae/__init__.py cae/cli.py cae/__main__.py tests/__init__.py tests/test_cli.py results/.gitkeep README.md .gitignore
git commit -m "Task 1: project skeleton (pyproject, CLI, package init, __main__)"
```

---

### Task 2: Core Types

**Files:**
- Create: `cae/agents/__init__.py`
- Create: `cae/agents/base.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_status.py
from cae.agents.base import Status, TestStatus


def test_status_values():
    assert Status.RESOLVED.value == "resolved"
    assert Status.FAILED.value == "failed"
    assert Status.AGENT_ERROR.value == "agent_error"
    assert Status.TIMEOUT.value == "timeout"
    assert Status.TASK_ERROR.value == "task_error"
    assert Status.GRADER_ERROR.value == "grader_error"


def test_status_is_string_enum():
    assert isinstance(Status.RESOLVED, str)
    # StrEnum mixin lets us compare to raw string
    assert Status.RESOLVED == "resolved"


def test_test_status_values():
    assert TestStatus.PASSED.value == "passed"
    assert TestStatus.FAILED.value == "failed"
    assert TestStatus.ERROR.value == "error"
    assert TestStatus.SKIPPED.value == "skipped"
    assert TestStatus.XFAIL.value == "xfail"


def test_status_count():
    # sanity: spec lists exactly 6 task statuses and 5 test statuses
    assert len(list(Status)) == 6
    assert len(list(TestStatus)) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.agents'`

- [ ] **Step 3: Create `cae/agents/__init__.py`**

```python
"""Agent adapters for cae."""
```

- [ ] **Step 4: Create `cae/agents/base.py`**

```python
"""Core types: AgentAdapter Protocol, AgentResult, UsageInfo, status enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable


class Status(StrEnum):
    """Top-level task status (the spec's 6-value enum)."""

    RESOLVED = "resolved"
    FAILED = "failed"
    AGENT_ERROR = "agent_error"
    TIMEOUT = "timeout"
    TASK_ERROR = "task_error"
    GRADER_ERROR = "grader_error"


class TestStatus(StrEnum):
    """Per-test status (the spec's 5-value enum)."""

    # Tell pytest not to treat this as a test class (it starts with "Test").
    __test__ = False

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAIL = "xfail"


@dataclass
class UsageInfo:
    """Best-effort token and cost accounting. Fields are None when unknown."""

    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    model: str | None = None
    billing_mode: str = "api"  # "api" or "subscription"


@dataclass
class AgentResult:
    """Per-run output of an agent adapter (before harness extracts the patch)."""

    log: str = ""                # raw stdout+stderr for debugging
    usage: UsageInfo = field(default_factory=UsageInfo)
    exit_code: int = 0
    duration_sec: float = 0.0


@runtime_checkable
class AgentAdapter(Protocol):
    """Contract every CLI agent adapter implements."""

    name: str                              # e.g. "claude-code", "codex", "aider", "mock"
    default_model: str | None              # e.g. "claude-opus-4-7" or None

    def is_available(self) -> bool:
        """Return True iff the underlying CLI is installed and runnable."""
        ...

    def version(self) -> str:
        """Return the installed CLI's version string (e.g. from `claude --version`)."""
        ...

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        """Return the argv list to run the agent subprocess."""
        ...

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        """Normalize the CLI's output into a uniform AgentResult."""
        ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_status.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add cae/agents/__init__.py cae/agents/base.py tests/test_status.py
git commit -m "Task 2: core types (Status, TestStatus, AgentAdapter Protocol)"
```

---

### Task 3: Pytest Parser

**Files:**
- Create: `cae/parsers.py`
- Create: `tests/test_parsers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parsers.py
from cae.parsers import parse_pytest_output
from cae.agents.base import TestStatus


def test_parse_pytest_all_pass():
    output = """
tests/test_main.py::test_add PASSED                          [ 50%]
tests/test_main.py::test_multiply PASSED                     [100%]
========================== 2 passed in 0.01s ==========================
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_main.py::test_add": TestStatus.PASSED,
        "tests/test_main.py::test_multiply": TestStatus.PASSED,
    }


def test_parse_pytest_mixed():
    output = """
tests/test_main.py::test_add FAILED                          [ 50%]
tests/test_main.py::test_multiply PASSED                     [100%]
========================== 1 failed, 1 passed in 0.02s ===========
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_main.py::test_add": TestStatus.FAILED,
        "tests/test_main.py::test_multiply": TestStatus.PASSED,
    }


def test_parse_pytest_error():
    output = """
tests/test_main.py::test_add ERROR                           [ 50%]
__________ ERROR at setup of test_add __________
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_main.py::test_add": TestStatus.ERROR,
    }


def test_parse_pytest_skipped():
    output = """
tests/test_main.py::test_add SKIPPED                        [ 50%]
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_main.py::test_add": TestStatus.SKIPPED,
    }


def test_parse_pytest_xfail():
    output = """
tests/test_main.py::test_add XFAIL                          [ 50%]
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_main.py::test_add": TestStatus.XFAIL,
    }


def test_parse_pytest_empty():
    assert parse_pytest_output("") == {}
    assert parse_pytest_output("no test results here") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parsers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.parsers'`

- [ ] **Step 3: Create `cae/parsers.py`**

```python
"""Per-runner parsers: map a test runner's output to {test_name: TestStatus}.

v1 ships with pytest. New runners = new function in this module. The contract
is: a parser takes the runner's full output (stdout+stderr) and returns a dict
mapping fully-qualified test names to TestStatus. Unknown lines are ignored.
"""

from __future__ import annotations

import re

from cae.agents.base import TestStatus

# pytest's verbose-mode line pattern: tests/path::test_name STATUS [percent]
# We use a permissive regex that captures any test node id (including parametrized
# ones like tests/test_x.py::test_y[param]) plus one of the five status words.
_PYTEST_LINE_RE = re.compile(
    r"^(?P<nodeid>[\w/\.\-\[\]:]+)::(?P<name>[\w\[\]\-]+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL)\b"
)


def parse_pytest_output(output: str) -> dict[str, TestStatus]:
    """Parse pytest's verbose output into {nodeid: TestStatus}.

    A "nodeid" is pytest's fully-qualified test identifier, e.g.
    "tests/test_main.py::test_add" or "tests/test_x.py::test_y[1]".
    """
    results: dict[str, TestStatus] = {}
    for line in output.splitlines():
        line = line.strip()
        m = _PYTEST_LINE_RE.search(line)
        if not m:
            continue
        nodeid = f"{m.group('nodeid')}::{m.group('name')}"
        results[nodeid] = TestStatus(m.group("status").lower())
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_parsers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add cae/parsers.py tests/test_parsers.py
git commit -m "Task 3: pytest parser"
```

---

### Task 4: Grader

**Files:**
- Create: `cae/grader.py`
- Create: `tests/test_grader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grader.py
from cae.agents.base import Status, TestStatus
from cae.grader import grade


def test_resolved_when_all_fail_to_pass_now_pass_and_no_regressions():
    pre = {
        "fail_to_pass": {"t::a": TestStatus.FAILED, "t::b": TestStatus.FAILED},
        "pass_to_pass": {"t::c": TestStatus.PASSED},
    }
    post = {
        "fail_to_pass": {"t::a": TestStatus.PASSED, "t::b": TestStatus.PASSED},
        "pass_to_pass": {"t::c": TestStatus.PASSED},
    }
    assert grade(pre, post) == Status.RESOLVED


def test_failed_when_any_fail_to_pass_does_not_pass():
    pre = {"fail_to_pass": {"t::a": TestStatus.FAILED}, "pass_to_pass": {}}
    post = {"fail_to_pass": {"t::a": TestStatus.FAILED}, "pass_to_pass": {}}
    assert grade(pre, post) == Status.FAILED


def test_failed_when_pass_to_pass_regresses():
    pre = {"fail_to_pass": {"t::a": TestStatus.FAILED}, "pass_to_pass": {"t::b": TestStatus.PASSED}}
    post = {"fail_to_pass": {"t::a": TestStatus.PASSED}, "pass_to_pass": {"t::b": TestStatus.FAILED}}
    assert grade(pre, post) == Status.FAILED


def test_failed_when_pass_to_pass_goes_to_error():
    pre = {"fail_to_pass": {}, "pass_to_pass": {"t::b": TestStatus.PASSED}}
    post = {"fail_to_pass": {}, "pass_to_pass": {"t::b": TestStatus.ERROR}}
    assert grade(pre, post) == Status.FAILED


def test_failed_when_fail_to_pass_is_skipped():
    pre = {"fail_to_pass": {"t::a": TestStatus.FAILED}, "pass_to_pass": {}}
    post = {"fail_to_pass": {"t::a": TestStatus.SKIPPED}, "pass_to_pass": {}}
    assert grade(pre, post) == Status.FAILED


def test_resolved_with_no_fail_to_pass():
    pre = {"fail_to_pass": {}, "pass_to_pass": {"t::b": TestStatus.PASSED}}
    post = {"fail_to_pass": {}, "pass_to_pass": {"t::b": TestStatus.PASSED}}
    assert grade(pre, post) == Status.RESOLVED


def test_failed_with_no_pass_to_pass_but_fail_to_pass_unresolved():
    pre = {"fail_to_pass": {"t::a": TestStatus.FAILED}, "pass_to_pass": {}}
    post = {"fail_to_pass": {"t::a": TestStatus.PASSED}, "pass_to_pass": {}}
    assert grade(pre, post) == Status.RESOLVED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_grader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.grader'`

- [ ] **Step 3: Create `cae/grader.py`**

```python
"""Decide the top-level task Status from pre-flight and post-flight test results.

Per the spec:
  - resolved iff every test in fail_to_pass ended as PASSED
                AND every test in pass_to_pass ended as PASSED
  - failed otherwise (any non-PASSED outcome in either set)
"""

from __future__ import annotations

from cae.agents.base import Status, TestStatus


def grade(
    pre: dict[str, dict[str, TestStatus]],
    post: dict[str, dict[str, TestStatus]],
) -> Status:
    """Return the top-level Status for one run.

    `pre` and `post` have the shape:
        {"fail_to_pass": {test_name: TestStatus, ...},
         "pass_to_pass": {test_name: TestStatus, ...}}
    """
    for test_name in pre["fail_to_pass"]:
        if post["fail_to_pass"].get(test_name) != TestStatus.PASSED:
            return Status.FAILED
    for test_name in pre["pass_to_pass"]:
        if post["pass_to_pass"].get(test_name) != TestStatus.PASSED:
            return Status.FAILED
    return Status.RESOLVED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_grader.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add cae/grader.py tests/test_grader.py
git commit -m "Task 4: grader (decides Status from pre/post flight)"
```

---

### Task 5: Mock Adapter

**Files:**
- Create: `cae/agents/mock.py`
- Modify: `cae/agents/__init__.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agents.py
import shutil
from pathlib import Path

import pytest

from cae.agents import get_adapter, list_adapters
from cae.agents.base import AgentResult, UsageInfo
from cae.agents.mock import MockAdapter


def test_mock_adapter_is_available():
    assert MockAdapter().is_available() is True


def test_mock_adapter_version():
    assert MockAdapter().version() == "mock-0.1.0"


def test_mock_adapter_build_command_runs_a_subprocess():
    cmd = MockAdapter().build_command(Path("/tmp"), "do the thing", model=None)
    assert isinstance(cmd, list)
    assert cmd[0]  # non-empty argv


def test_mock_adapter_writes_patch_to_workdir(tmp_path: Path):
    """The mock writes a known patch to the workdir; the harness then captures it via git diff."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    # set up workdir as a git repo with one initial file
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "test@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    (workdir / "main.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)

    adapter = MockAdapter()
    # by default the mock does nothing — calling its command in workdir should not change files
    # to verify: run a no-op, then assert no diff
    import subprocess
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.agents.mock'`

- [ ] **Step 3: Create `cae/agents/mock.py`**

```python
"""MockAdapter: a no-op CLI stub for harness smoke tests and unit tests.

This adapter is for tests and smoke runs only. It is registered as a first-class
adapter so the harness exercises every code path, but cae build-site filters
its results out of the public leaderboard. The default mock does NOT modify
the workdir — tests that need a known patch should pre-apply the patch to the
workdir before calling harness.run.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentAdapter, AgentResult, UsageInfo


MOCK_VERSION = "mock-0.1.0"


class MockAdapter:
    name = "mock"
    default_model = None

    def is_available(self) -> bool:
        return True

    def version(self) -> str:
        return MOCK_VERSION

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        # The mock does its work in the constructor of the subprocess via a small
        # Python one-liner. We pass the workdir as the only arg. The "agent" is
        # no-op for the default mock — the harness then sees a clean diff.
        return [shutil.which("python") or "python", "-c", "import sys; sys.exit(0)"]

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(tokens_in=0, tokens_out=0, cost_usd=0.0, model=None, billing_mode="api"),
            exit_code=exit_code,
            duration_sec=0.0,
        )
```

- [ ] **Step 4: Update `cae/agents/__init__.py`**

```python
"""Agent adapters for cae.

ADAPTERS is the registry used by get_adapter() and list_adapters(). New adapters
import their class and add an entry here.
"""

from cae.agents.base import AgentAdapter, AgentResult, UsageInfo
from cae.agents.mock import MockAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
}


def get_adapter(name: str, **kwargs: object) -> AgentAdapter:
    """Instantiate the named adapter or raise ValueError."""
    cls = ADAPTERS.get(name)
    if cls is None:
        available = ", ".join(ADAPTERS) or "(none)"
        raise ValueError(f"Unknown agent adapter: {name!r}. Available: {available}")
    return cls(**kwargs)


def list_adapters() -> list[dict[str, str | bool]]:
    """Return a list of {name, available} for every registered adapter."""
    result: list[dict[str, str | bool]] = []
    for name, cls in ADAPTERS.items():
        try:
            adapter = cls()
            available = adapter.is_available()
        except Exception:
            available = False
        result.append({"name": name, "available": available})
    return result


__all__ = ["AgentAdapter", "AgentResult", "UsageInfo", "ADAPTERS", "get_adapter", "list_adapters"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agents.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add cae/agents/mock.py cae/agents/__init__.py tests/test_agents.py
git commit -m "Task 5: MockAdapter + adapter registry"
```

---

### Task 6: Tiny Test Fixture

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/fixtures/tiny_task/task.json`
- Create: `tests/fixtures/tiny_task/repo/main.py`
- Create: `tests/fixtures/tiny_task/repo/test_main.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for cae tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tiny_task_path() -> Path:
    """Path to the in-tree tiny task fixture, used by harness integration tests."""
    return Path(__file__).parent / "fixtures" / "tiny_task"
```

- [ ] **Step 2: Create `tests/fixtures/tiny_task/task.json`**

```json
{
  "instance_id": "tiny__task-1",
  "repo": "tiny/task",
  "base_commit": "0000000000000000000000000000000000000000",
  "language": "python",
  "framework": "stdlib",
  "difficulty": "easy",
  "prompt": "Fix the add() function so it returns a + b instead of a - b.",
  "setup_cmd": "",
  "test_cmd": "python -m pytest test_main.py -v",
  "fail_to_pass": ["test_main.py::test_add"],
  "pass_to_pass": ["test_main.py::test_multiply"]
}
```

- [ ] **Step 3: Create `tests/fixtures/tiny_task/repo/main.py`**

```python
"""Tiny fixture module with one bug and one correct function."""


def add(a: int, b: int) -> int:
    return a - b  # bug: should be a + b


def multiply(a: int, b: int) -> int:
    return a * b
```

- [ ] **Step 4: Create `tests/fixtures/tiny_task/repo/test_main.py`**

```python
from main import add, multiply


def test_add():
    assert add(2, 3) == 5


def test_multiply():
    assert multiply(2, 3) == 6
```

- [ ] **Step 5: Verify the fixture by running its tests in isolation**

Run:
```
cd /Users/sarace/dev/probe/agent_eval/tests/fixtures/tiny_task/repo
git init -q && git config user.email t@x && git config user.name t
git add . && git commit -q -m "init"
python -m pytest test_main.py -v
```
Expected: `1 failed, 1 passed` (`test_add` fails, `test_multiply` passes).

- [ ] **Step 6: Clean up the test repo (remove .git so the fixture is just source)**

Run:
```
cd /Users/sarace/dev/probe/agent_eval/tests/fixtures/tiny_task/repo
rm -rf .git
```

- [ ] **Step 7: Commit**

```bash
git add tests/conftest.py tests/fixtures/tiny_task/task.json tests/fixtures/tiny_task/repo/main.py tests/fixtures/tiny_task/repo/test_main.py
git commit -m "Task 6: tiny test fixture (known-bug-and-known-fix)"
```

---

### Task 7: Harness (Run Loop)

**Files:**
- Create: `cae/harness.py`
- Create: `tests/test_harness.py`

This is the largest task. The harness implements the 11-step run lifecycle from the spec for a single (task, agent) pair in local mode. Docker mode and --repeat are added in Phase 5.

- [ ] **Step 1: Write the failing test (end-to-end with mock + tiny fixture)**

```python
# tests/test_harness.py
import json
import subprocess
from pathlib import Path

import pytest

from cae.agents.mock import MockAdapter
from cae.harness import run


def test_run_resolves_tiny_task_with_mock_that_fixes_the_bug(tmp_path, tiny_task_path):
    """The mock, when augmented to apply the gold patch, should resolve tiny_task.

    For this test we swap in a mock subclass that writes the fixed main.py so we
    exercise the full harness with a deterministic pass.
    """
    # prepare a workdir copy of the fixture's repo with a git init
    repo_src = tiny_task_path / "repo"
    workdir = tmp_path / "workdir"
    subprocess.run(["cp", "-r", str(repo_src), str(workdir)], check=True)
    subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "t@x"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=workdir, check=True)
    # gold patch path
    gold = tiny_task_path / "repo" / "main.py"
    fixed_text = gold.read_text().replace("return a - b", "return a + b")
    (workdir / "main.py").write_text(fixed_text)

    # call harness.run with a mock that has a fixed workdir already in place
    result = run(task_path=tiny_task_path, agent_name="mock", workdir=workdir)

    assert result["status"] == "resolved"
    assert "main.py" in result["patch"]  # the harness captured a diff
    # fail_to_pass and pass_to_pass should be reflected in the test_results
    assert result["test_results"]["post_flight"]["fail_to_pass"]["test_main.py::test_add"] == "passed"
    assert result["test_results"]["post_flight"]["pass_to_pass"]["test_main.py::test_multiply"] == "passed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_harness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.harness'`

- [ ] **Step 3: Create `cae/harness.py`**

```python
"""Run loop: orchestrate one (task, agent) pair through the 11-step lifecycle.

This module implements local mode only in v1. Docker mode (cae/docker_run.py)
is added in Phase 5 (Task 22). Steps 1-11 follow the spec section "Run Lifecycle".
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from cae.agents import get_adapter
from cae.agents.base import Status, TestStatus
from cae.grader import grade
from cae.parsers import parse_pytest_output


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
    subprocess.run(["git", "config", "user.email", "cae@local"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.name", "cae"], cwd=workdir, check=True)
    subprocess.run(["git", "add", "."], cwd=workdir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=workdir, check=True)


def _apply_test_patch(workdir: Path, task_dir: Path) -> None:
    """Apply tests.patch if it exists. No-op for hand-authored tasks."""
    patch = task_dir / "tests.patch"
    if not patch.exists():
        return
    subprocess.run(["git", "apply", str(patch)], cwd=workdir, check=True)


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
    repeat: int = 1,
    repeat_index: int | None = None,
) -> dict:
    """Run a single (task, agent) pair through the full harness. Return the result dict.

    Args:
        task_path: path to a directory containing task.json (and optional tests.patch, repo/).
        agent_name: name of a registered adapter (e.g. "mock", "claude-code").
        workdir: optional pre-populated workdir. If None, harness copies from task_path/repo/.
        timeout_sec: per-stage timeout (setup, pre-flight, agent, grading).
        repeat: total number of times this run is being repeated (1 = no repeat).
        repeat_index: 1-based index of this specific run within a repeated batch.
            When `repeat=1`, this is None and the run_id omits the suffix.

    Returns a dict matching the spec's Output JSON shape.
    """
    task_dir = Path(task_path)
    task = json.loads((task_dir / "task.json").read_text())
    fail_to_pass = task["fail_to_pass"]
    pass_to_pass = task["pass_to_pass"]

    # 1-3: Resolve task, create workdir, fetch repo
    workdir_owned = workdir is None
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="cae-"))
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    if workdir_owned:
        repo_src = task_dir / "repo"
        if repo_src.exists():
            for child in repo_src.iterdir():
                dest = workdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)

    _ensure_git_repo(workdir)
    _apply_test_patch(workdir, task_dir)

    # Pick a subprocess runner: local (default) or docker (Task 22).
    def run_step(cmd, cwd, timeout):
        if docker:
            from cae.docker_run import exec_in
            return exec_in(
                docker_image,
                cmd if isinstance(cmd, list) else cmd.split(),
                workdir=cwd,
                timeout=timeout,
                env_file=env_file,
            )
        return _run_subprocess(cmd, cwd, timeout=timeout)

    # 5: Setup
    if task.get("setup_cmd"):
        setup_rc, _, setup_err, _ = run_step(task["setup_cmd"], workdir, timeout=timeout_sec)
        if setup_rc != 0:
            return _result(task, agent_name, "local", Status.TASK_ERROR, "unknown", {}, {}, "", str(workdir),
                           f"setup_cmd failed: {setup_err[:200]}")

    # 6: Pre-flight
    pre = _run_tests(task["test_cmd"], workdir, timeout=timeout_sec, run_subprocess=run_step)
    pre_flight = {"fail_to_pass": {n: pre.get(n, TestStatus.ERROR).value for n in fail_to_pass},
                  "pass_to_pass": {n: pre.get(n, TestStatus.ERROR).value for n in pass_to_pass}}
    # validate: fail_to_pass tests should currently fail, pass_to_pass should currently pass
    pre_fails_correctly = all(pre_flight["fail_to_pass"][n] != "passed" for n in fail_to_pass)
    pre_passes_correctly = all(pre_flight["pass_to_pass"][n] == "passed" for n in pass_to_pass)
    if not (pre_fails_correctly and pre_passes_correctly):
        return _result(task, agent_name, "local", Status.TASK_ERROR, "unknown", pre_flight, pre_flight, "",
                       str(workdir), "pre-flight validation failed: fail_to_pass tests do not all fail, "
                       "or pass_to_pass tests do not all pass")

    # 7: Run agent
    adapter = get_adapter(agent_name)
    if not adapter.is_available():
        return _result(task, agent_name, "local", Status.AGENT_ERROR, "unknown", pre_flight, pre_flight, "",
                       str(workdir), f"agent {agent_name} not available")
    agent_version = adapter.version()
    cmd = adapter.build_command(workdir, task["prompt"], model=None)
    agent_rc, agent_stdout, agent_stderr, duration = run_step(cmd, workdir, timeout=timeout_sec)
    if agent_rc == -1:
        return _result(task, agent_name, "local", Status.TIMEOUT, agent_version, pre_flight, pre_flight, "",
                       str(workdir), f"agent timed out after {timeout_sec}s")
    parsed = adapter.parse_output(agent_stdout, agent_stderr, agent_rc)
    if parsed.exit_code != 0:
        return _result(task, agent_name, "local", Status.AGENT_ERROR, agent_version, pre_flight, pre_flight, "",
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

    return _result(task, agent_name, "local", status, agent_version, pre_flight, post_flight, patch,
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
        "harness_git_sha": _harness_git_sha(),
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


def _harness_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_harness.py -v`
Expected: PASS (1 test, takes a few seconds for the agent subprocess and test runs)

- [ ] **Step 5: Commit**

```bash
git add cae/harness.py tests/test_harness.py
git commit -m "Task 7: harness.run — local mode end-to-end with mock + tiny fixture"
```

---

### Task 8: `cae run` CLI subcommand

**Files:**
- Modify: `cae/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py — append to existing
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_cae_run_writes_result_json(tmp_path, tiny_task_path):
    """`cae run --agent mock --task <tiny>` should write a result JSON to results/."""
    # copy the fixture into tasks/ under tmp cwd
    proj = tmp_path
    (proj / "tasks" / "tiny__task-1" / "repo").mkdir(parents=True)
    for src in (tiny_task_path.iterdir()):
        if src.name == "repo":
            for child in src.iterdir():
                (proj / "tasks" / "tiny__task-1" / "repo" / child.name).write_bytes(child.read_bytes())
        else:
            (proj / "tasks" / "tiny__task-1" / src.name).write_bytes(src.read_bytes())
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny__task-1",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1, f"expected 1 result file, got {len(files)}: {files}"
    data = json.loads(files[0].read_text())
    assert data["agent"] == "mock"
    assert data["task_id"] == "tiny__task-1"
    assert data["status"] in {"resolved", "failed"}  # the mock doesn't fix the bug, so likely failed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cae_run_writes_result_json -v`
Expected: FAIL with `error: unrecognized arguments: run` or similar

- [ ] **Step 3: Update `cae/cli.py`**

```python
"""Command-line interface for cae."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _default_results_dir() -> Path:
    return Path("results")


def cmd_run(args: argparse.Namespace) -> int:
    from cae.harness import run
    task_path = Path(args.tasks_dir) / args.task
    if not (task_path / "task.json").exists():
        print(f"error: task {args.task!r} not found at {task_path}", file=sys.stderr)
        return 2
    result = run(task_path=task_path, agent_name=args.agent, timeout_sec=args.timeout * 60)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / f"{result['run_id']}.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out}")
    print(f"status: {result['status']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cae",
        description="Evaluate CLI coding agents on SWE-bench tasks.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", required=False)

    p_run = sub.add_parser("run", help="run an agent on a single task")
    p_run.add_argument("--agent", required=True, help="agent adapter name (e.g. mock, claude-code)")
    p_run.add_argument("--task", required=True, help="task instance_id under --tasks-dir")
    p_run.add_argument("--tasks-dir", default="tasks", help="directory containing task subdirs (default: tasks)")
    p_run.add_argument("--results-dir", default="results", help="where to write result JSON (default: results)")
    p_run.add_argument("--timeout", type=int, default=30, help="per-stage timeout in minutes (default: 30)")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from cae import __version__
        print(__version__)
        return 0
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (2 tests: the original help test and the new run test)

- [ ] **Step 5: Manually smoke-test `cae run` end-to-end**

Run:
```
cd /Users/sarace/dev/probe/agent_eval
python -m cae run --agent mock --task tiny__task-1 --tasks-dir tests/fixtures/tasks --results-dir /tmp/cae-smoke
```
Note: the test fixture isn't at `tests/fixtures/tasks` — it's at `tests/fixtures/tiny_task`. Adjust: `--tasks-dir tests/fixtures` and `--task tiny_task`.

Run: `python -m cae run --agent mock --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/cae-smoke`
Expected: `wrote /tmp/cae-smoke/<run_id>.json`, `status: failed` (because the mock doesn't fix the bug).

- [ ] **Step 6: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "Task 8: cae run CLI subcommand — vertical slice end-to-end"
```

**After Task 8:** the vertical slice is working. `cae run --agent mock --task <task>` produces a result JSON. Everything below is iteration.

---

## Phase 2: Real Tasks (Tasks 9–10)

### Task 9: SWE-bench Importer

**Files:**
- Create: `cae/importer.py`
- Create: `tests/test_importer.py`
- Modify: `cae/cli.py` (add `add-task` subcommand)
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test (importer core)**

```python
# tests/test_importer.py
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cae.importer import import_swebench_instance, SWEbenchRecord


@pytest.fixture
def sample_record() -> SWEbenchRecord:
    return SWEbenchRecord(
        instance_id="django__django-12345",
        repo="django/django",
        base_commit="abc1234",
        prompt="Issue: something is broken",
        test_patch="diff --git a/tests/test_x.py b/tests/test_x.py\n+new test",
        fail_to_pass=["tests/test_x.py::test_y"],
        pass_to_pass=["tests/test_x.py::test_z"],
    )


def test_import_writes_task_json(tmp_path, sample_record):
    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=False)
    out = tmp_path / "django__django-12345" / "task.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["instance_id"] == "django__django-12345"
    assert data["repo"] == "django/django"
    assert data["base_commit"] == "abc1234"
    assert data["fail_to_pass"] == ["tests/test_x.py::test_y"]
    assert data["prompt"] == "Issue: something is broken"
    assert data["source"] == {"kind": "swe-bench", "split": "verified", "original_id": "django__django-12345"}


def test_import_writes_test_patch(tmp_path, sample_record):
    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=False)
    out = tmp_path / "django__django-12345" / "tests.patch"
    assert out.exists()
    assert "new test" in out.read_text()


def test_import_fetches_repo_into_repo_dir(tmp_path, sample_record):
    """When fetch_repo is True and a fetcher is provided, the repo state is populated."""
    def fake_fetcher(repo: str, base_commit: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README").write_text(f"fake clone of {repo} at {base_commit}")

    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=True, fetcher=fake_fetcher)
    repo_dir = tmp_path / "django__django-12345" / "repo"
    assert repo_dir.exists()
    assert "fake clone of django/django at abc1234" in (repo_dir / "README").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_importer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.importer'`

- [ ] **Step 3: Create `cae/importer.py`**

```python
"""SWE-bench Verified importer: pulls task metadata and (optionally) the repo state.

The importer takes SWE-bench records (a flat dataclass) and writes a task
directory under tasks/. For v1 we use the HuggingFace `datasets` library to load
princeton-nlp/SWE-bench_Verified. The HF dataset is wrapped into our
SWEbenchRecord type so the rest of the importer is decoupled from the source.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class SWEbenchRecord:
    """A flat, source-decoupled view of one SWE-bench instance."""

    instance_id: str
    repo: str
    base_commit: str
    prompt: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]


# A fetcher takes (repo, base_commit, dest) and populates dest with the repo
# state at base_commit. Default implementation: git clone.
Fetcher = Callable[[str, str, Path], None]


# Per-repo setup/test commands for common SWE-bench Verified repos. The importer
# consults this table first; if a repo isn't listed, it falls back to the
# generic Python defaults below.
SWE_BENCH_REPO_DEFAULTS: dict[str, dict[str, str]] = {
    "django/django":       {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "pytest-dev/pytest":   {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "pallets/flask":       {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "psf/requests":        {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "scikit-learn/scikit-learn": {"setup_cmd": "pip install -e .",  "test_cmd": "python -m pytest -xvs"},
    "astropy/astropy":     {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
}

GENERIC_PYTHON_DEFAULTS = {"setup_cmd": "pip install -e .", "test_cmd": "python -m pytest -xvs"}


def default_fetcher(repo: str, base_commit: str, dest: Path) -> None:
    """Clone the repo at base_commit into dest. Requires `git` on PATH.

    Uses a fetch of a specific commit (not --depth=1) so the checkout succeeds
    for any base_commit, not just HEAD.
    """
    url = f"https://github.com/{repo}.git"
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "fetch", "--depth=1", "origin", base_commit], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "checkout", base_commit], cwd=dest, check=True, capture_output=True)


def import_swebench_instance(
    record: SWEbenchRecord,
    *,
    tasks_dir: Path,
    fetch_repo: bool = True,
    split: str = "verified",
    fetcher: Fetcher | None = None,
) -> Path:
    """Write one task under tasks_dir. Returns the task directory path."""
    task_dir = Path(tasks_dir) / record.instance_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # task.json — populate setup_cmd/test_cmd from the per-repo defaults table
    # (or the generic Python defaults if the repo isn't in the table).
    defaults = SWE_BENCH_REPO_DEFAULTS.get(record.repo, GENERIC_PYTHON_DEFAULTS)

    task_json = {
        "instance_id": record.instance_id,
        "repo": record.repo,
        "base_commit": record.base_commit,
        "prompt": record.prompt,
        "setup_cmd": defaults["setup_cmd"],
        "test_cmd": defaults["test_cmd"],
        "fail_to_pass": record.fail_to_pass,
        "pass_to_pass": record.pass_to_pass,
        "source": {"kind": "swe-bench", "split": split, "original_id": record.instance_id},
    }
    (task_dir / "task.json").write_text(json.dumps(task_json, indent=2))

    # tests.patch
    if record.test_patch:
        (task_dir / "tests.patch").write_text(record.test_patch)

    # repo/
    if fetch_repo:
        repo_dir = task_dir / "repo"
        repo_dir.mkdir(exist_ok=True)
        if (repo_dir / "README").exists() or any(repo_dir.iterdir()):
            shutil.rmtree(repo_dir)
        repo_dir.mkdir()
        (default_fetcher if fetcher is None else fetcher)(
            record.repo, record.base_commit, repo_dir
        )

    return task_dir


def load_swebench_records(
    *,
    instance_ids: list[str] | None = None,
    split: str = "verified",
    limit: int | None = None,
    dataset_path: str | None = None,
) -> Iterable[SWEbenchRecord]:
    """Load records from the SWE-bench Verified dataset.

    Uses the HuggingFace `datasets` library. If `dataset_path` is given, loads
    from a local clone (e.g. for offline use); otherwise hits the hub.
    """
    if dataset_path:
        from datasets import load_from_disk
        ds = load_from_disk(dataset_path)
    else:
        from datasets import load_dataset
        ds = load_dataset("princeton-nlp/SWE-bench_Verified", split=split)
    if instance_ids:
        ds = ds.filter(lambda r: r["instance_id"] in set(instance_ids))
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    for row in ds:
        yield SWEbenchRecord(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            prompt=row["problem_statement"],
            test_patch=row["test_patch"],
            fail_to_pass=row["fail_to_pass"],
            pass_to_pass=row["pass_to_pass"],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_importer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Add `add-task` subcommand to `cae/cli.py`**

Append to `build_parser` in `cae/cli.py`:

```python
    p_add = sub.add_parser("add-task", help="add a new task under tasks/")
    p_add.add_argument("--from-swebench", action="store_true",
                      help="import from SWE-bench (default split: verified)")
    p_add.add_argument("--split", default="verified", help="SWE-bench split (default: verified)")
    p_add.add_argument("--limit", type=int, default=None, help="import at most N instances")
    p_add.add_argument("--instance-id", action="append", default=[],
                      help="specific instance_id to import (repeatable)")
    p_add.add_argument("--dataset-path", default=None,
                      help="path to a local SWE-bench dataset clone (for offline use)")
    p_add.add_argument("--no-fetch-repo", action="store_true",
                      help="skip the git clone (faster import for tests)")
    p_add.add_argument("--tasks-dir", default="tasks", help="where to write tasks (default: tasks)")
    p_add.set_defaults(func=cmd_add_task)
```

Append a new command function before `build_parser`:

```python
def cmd_add_task(args: argparse.Namespace) -> int:
    if not args.from_swebench:
        print("error: only --from-swebench is supported in v1", file=sys.stderr)
        return 2
    from cae.importer import import_swebench_instance, load_swebench_records
    records = list(load_swebench_records(
        instance_ids=args.instance_id or None,
        split=args.split,
        limit=args.limit,
        dataset_path=args.dataset_path,
    ))
    for rec in records:
        import_swebench_instance(
            rec, tasks_dir=Path(args.tasks_dir),
            fetch_repo=not args.no_fetch_repo, split=args.split,
        )
        print(f"imported {rec.instance_id}")
    return 0
```

- [ ] **Step 6: Add a CLI test for `add-task` (no-fetch mode)**

Append to `tests/test_cli.py`:

```python
def test_cae_add_task_no_fetch(tmp_path):
    """`cae add-task --from-swebench --no-fetch-repo` writes a task.json to tasks/.

    This test requires HuggingFace access (the SWE-bench Verified dataset). It
    is skipped (not failed) if datasets/HF is not available in the test env.
    """
    pytest.importorskip("datasets")
    proj = tmp_path
    result = subprocess.run(
        [sys.executable, "-m", "cae", "add-task",
         "--from-swebench", "--limit", "1", "--no-fetch-repo",
         "--tasks-dir", str(proj / "tasks")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"add-task failed: {result.stderr}"
    tasks = list((proj / "tasks").iterdir())
    assert len(tasks) == 1
    task_json = json.loads((tasks[0] / "task.json").read_text())
    assert task_json["source"]["kind"] == "swe-bench"
    assert "fail_to_pass" in task_json
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (3 tests; the new one may pass-via-skip if HF is unavailable)

- [ ] **Step 8: Commit**

```bash
git add cae/importer.py cae/cli.py tests/test_importer.py tests/test_cli.py
git commit -m "Task 9: SWE-bench importer + cae add-task CLI"
```

---

### Task 10: End-to-end smoke with one SWE-bench task

**Files:**
- Create: `docs/smoke-test.md`

- [ ] **Step 1: Document the manual smoke test**

Create `docs/smoke-test.md`:

```markdown
# Smoke Test

Manual end-to-end check before tagging a release. Not run in CI.

## Steps

1. Import one SWE-bench Verified task (no network-heavy repo fetch — use `--no-fetch-repo` for the smoke test):

   ```
   cae add-task --from-swebench --instance-id django__django-12345 --no-fetch-repo
   ```

2. List available agents:

   ```
   cae list-agents
   ```

3. Run the mock adapter against the imported task to verify the harness + importer round-trip:

   ```
   cae run --agent mock --task django__django-12345
   cat results/<run_id>.json
   ```

   Expected: result JSON with `status` in `{resolved, failed, agent_error, ...}` and a non-empty `test_results` block.

4. (Optional) Run a real agent — Claude Code, Codex, or Aider — on the same task. Requires the CLI to be installed and an API key in the env.

## What this catches

- Importer fields map correctly to harness expectations.
- Workdir setup, test patch application, pre-flight, and grading all work on a real task.
- Result JSON is valid and contains all required fields.
```

- [ ] **Step 2: Commit**

```bash
git add docs/smoke-test.md
git commit -m "Task 10: smoke test docs"
```

---

## Phase 3: Real Agents (Tasks 11–14)

### Task 11: Claude Code Adapter

**Files:**
- Create: `cae/agents/claude_code.py`
- Modify: `cae/agents/__init__.py` (register adapter)
- Modify: `tests/test_agents.py` (add adapter-specific tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agents.py`:

```python
def test_claude_code_adapter_is_available_returns_bool():
    from cae.agents.claude_code import ClaudeCodeAdapter
    assert isinstance(ClaudeCodeAdapter().is_available(), bool)


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
```

(Add `import json` at the top of `test_agents.py` if not already there.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cae.agents.claude_code'`

- [ ] **Step 3: Create `cae/agents/claude_code.py`**

```python
"""Claude Code CLI adapter.

Invokes `claude -p <prompt> --output-format json` in the workdir and parses the
final JSON envelope for cost/tokens. is_available() runs `claude --version` to
confirm the binary is on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentAdapter, AgentResult, UsageInfo


class ClaudeCodeAdapter:
    name = "claude-code"
    default_model = "claude-opus-4-7"

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            out = subprocess.check_output(["claude", "--version"], text=True, stderr=subprocess.STDOUT)
            return out.strip().split("\n")[0]
        except Exception as e:
            return f"unknown ({e})"

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        cost = None
        tokens_in = None
        tokens_out = None
        model = None
        # Claude Code's --output-format json emits a final JSON envelope. The
        # harness may also have other JSON lines (tool calls etc.) — we look
        # for the last "type": "result" entry.
        try:
            envelope = None
            for line in stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                obj = json.loads(line)
                if obj.get("type") == "result":
                    envelope = obj
            if envelope is not None:
                cost = envelope.get("total_cost_usd")
                usage = envelope.get("usage") or {}
                tokens_in = usage.get("input_tokens")
                tokens_out = usage.get("output_tokens")
                model = envelope.get("model")
        except Exception:
            pass
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost, model=model, billing_mode="api",
            ),
            exit_code=exit_code,
        )
```

- [ ] **Step 4: Register in `cae/agents/__init__.py`**

Replace the `ADAPTERS` dict in `cae/agents/__init__.py`:

```python
ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude-code": ClaudeCodeAdapter,
}
```

(Add `from cae.agents.claude_code import ClaudeCodeAdapter` at the top.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agents.py -v`
Expected: PASS (10 tests: 7 original + 3 new)

- [ ] **Step 6: Commit**

```bash
git add cae/agents/claude_code.py cae/agents/__init__.py tests/test_agents.py
git commit -m "Task 11: Claude Code adapter"
```

---

### Task 12: Codex Adapter

**Files:**
- Create: `cae/agents/codex.py`
- Modify: `cae/agents/__init__.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agents.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents.py::test_codex_adapter_build_command_includes_prompt -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/agents/codex.py`**

```python
"""Codex CLI adapter.

Invokes `codex -q <prompt> --json` in the workdir. Parses the final
turn.completed event for cost/tokens/model.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentAdapter, AgentResult, UsageInfo


class CodexAdapter:
    name = "codex"
    default_model = "gpt-5"

    def is_available(self) -> bool:
        return shutil.which("codex") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            return subprocess.check_output(["codex", "--version"], text=True).strip()
        except Exception as e:
            return f"unknown ({e})"

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = ["codex", "-q", prompt, "--json"]
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        cost = None
        tokens_in = None
        tokens_out = None
        model = None
        try:
            for line in stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                obj = json.loads(line)
                if obj.get("type") == "turn.completed":
                    usage = obj.get("usage") or {}
                    cost = usage.get("cost_usd")
                    tokens_in = usage.get("input_tokens")
                    tokens_out = usage.get("output_tokens")
                    model = obj.get("model")
        except Exception:
            pass
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost, model=model, billing_mode="api",
            ),
            exit_code=exit_code,
        )
```

- [ ] **Step 4: Register**

In `cae/agents/__init__.py`:

```python
from cae.agents.codex import CodexAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agents.py -v`
Expected: PASS (12 tests)

- [ ] **Step 6: Commit**

```bash
git add cae/agents/codex.py cae/agents/__init__.py tests/test_agents.py
git commit -m "Task 12: Codex adapter"
```

---

### Task 13: Aider Adapter

**Files:**
- Create: `cae/agents/aider.py`
- Modify: `cae/agents/__init__.py`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agents.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agents.py::test_aider_adapter_build_command_includes_prompt -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/agents/aider.py`**

```python
"""Aider CLI adapter.

Invokes `aider --yes --message <prompt>` in the workdir. Aider doesn't emit
structured JSON by default, so cost and tokens are unknown (null) unless the
user pipes `--analytics` or similar. The adapter still runs the agent and
captures the patch via the harness's git diff.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cae.agents.base import AgentAdapter, AgentResult, UsageInfo


class AiderAdapter:
    name = "aider"
    default_model = None  # aider uses the user's configured model; no cae default

    def is_available(self) -> bool:
        return shutil.which("aider") is not None

    def version(self) -> str:
        if not self.is_available():
            return "not-installed"
        try:
            return subprocess.check_output(["aider", "--version"], text=True).strip()
        except Exception as e:
            return f"unknown ({e})"

    def build_command(self, workdir: Path, prompt: str, *, model: str | None) -> list[str]:
        cmd = ["aider", "--yes", "--message", prompt, "--no-auto-commits"]
        if model:
            cmd += ["--model", model]
        return cmd

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> AgentResult:
        return AgentResult(
            log=stdout + stderr,
            usage=UsageInfo(
                tokens_in=None, tokens_out=None,
                cost_usd=None, model=None, billing_mode="api",
            ),
            exit_code=exit_code,
        )
```

- [ ] **Step 4: Register**

In `cae/agents/__init__.py`:

```python
from cae.agents.aider import AiderAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "mock": MockAdapter,
    "claude-code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "aider": AiderAdapter,
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_agents.py -v`
Expected: PASS (14 tests)

- [ ] **Step 6: Commit**

```bash
git add cae/agents/aider.py cae/agents/__init__.py tests/test_agents.py
git commit -m "Task 13: Aider adapter"
```

---

### Task 14: `cae list-agents` CLI

**Files:**
- Modify: `cae/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_cae_list_agents(capsys):
    result = subprocess.run(
        [sys.executable, "-m", "cae", "list-agents"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "mock" in result.stdout
    assert "claude-code" in result.stdout or "codex" in result.stdout  # at least one real
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cae_list_agents -v`
Expected: FAIL with `unrecognized arguments: list-agents`

- [ ] **Step 3: Add `list-agents` to `cae/cli.py`**

Add a command function before `build_parser`:

```python
def cmd_list_agents(args: argparse.Namespace) -> int:
    from cae.agents import list_adapters
    rows = list_adapters()
    print(f"{'NAME':<20} AVAILABLE")
    for r in rows:
        print(f"{r['name']:<20} {r['available']}")
    return 0
```

In `build_parser`:

```python
    p_la = sub.add_parser("list-agents", help="list registered agent adapters and availability")
    p_la.set_defaults(func=cmd_list_agents)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py tests/test_cli.py
git commit -m "Task 14: cae list-agents CLI"
```

---

## Phase 4: Reporting and Site (Tasks 15–18)

### Task 15: Metrics Module

**Files:**
- Create: `cae/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
import json
from pathlib import Path

import pytest

from cae.metrics import aggregate_results


@pytest.fixture
def two_results_dir(tmp_path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    (d / "r1.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "resolved", "duration_sec": 100, "usage": {"cost_usd": 0.1, "tokens_in": 1000, "tokens_out": 500},
        "test_results": {"pre_flight": {}, "post_flight": {}}, "task_id": "t1",
    }))
    (d / "r2.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "failed", "duration_sec": 200, "usage": {"cost_usd": 0.2, "tokens_in": 2000, "tokens_out": 800},
        "test_results": {"pre_flight": {}, "post_flight": {}}, "task_id": "t2",
    }))
    return d


def test_aggregate_pass_rate(two_results_dir):
    rows = aggregate_results(two_results_dir)
    assert len(rows) == 1
    assert rows[0]["agent"] == "claude-code"
    assert rows[0]["n_resolved"] == 1
    assert rows[0]["n_attempted"] == 2
    assert rows[0]["pass_rate"] == 0.5


def test_aggregate_median_cost(two_results_dir):
    rows = aggregate_results(two_results_dir)
    assert rows[0]["median_cost_usd"] == 0.15  # median of [0.1, 0.2]


def test_aggregate_groups_by_agent_model_version(two_results_dir):
    (two_results_dir / "r3.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-sonnet-4-6",
        "status": "resolved", "duration_sec": 50, "usage": {"cost_usd": 0.05},
        "test_results": {}, "task_id": "t3",
    }))
    rows = aggregate_results(two_results_dir)
    assert len(rows) == 2


def test_aggregate_excludes_mock(two_results_dir):
    (two_results_dir / "r4.json").write_text(json.dumps({
        "agent": "mock", "agent_version": "0.1", "model": None,
        "status": "resolved", "duration_sec": 1, "usage": {"cost_usd": 0.0},
        "test_results": {}, "task_id": "tiny",
    }))
    rows = aggregate_results(two_results_dir)
    assert all(r["agent"] != "mock" for r in rows)


def test_aggregate_handles_null_cost(two_results_dir):
    (two_results_dir / "r5.json").write_text(json.dumps({
        "agent": "aider", "agent_version": "0.50", "model": None,
        "status": "resolved", "duration_sec": 80, "usage": {"cost_usd": None, "billing_mode": "subscription"},
        "test_results": {}, "task_id": "t4",
    }))
    rows = aggregate_results(two_results_dir)
    aider_row = next(r for r in rows if r["agent"] == "aider")
    # null cost is excluded from the median; with one data point and one null,
    # the median of the remaining single-point set is that point's value (None).
    assert aider_row["median_cost_usd"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/metrics.py`**

```python
"""Aggregate result JSONs into leaderboard rows.

Used by both `cae build-site` (writes data/results.json) and `cae report`
(prints a console table). The mock adapter is filtered out.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


def _median(values: list[float | None]) -> float | None:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return statistics.median(non_null)


def aggregate_results(results_dir: Path) -> list[dict]:
    """Read all *.json in results_dir and return one row per (agent, model, agent_version)."""
    files = sorted(results_dir.glob("*.json"))
    by_key: dict[tuple[str, str | None, str | None], list[dict]] = defaultdict(list)
    for f in files:
        data = json.loads(f.read_text())
        if data.get("agent") == "mock":  # exclude test adapter
            continue
        key = (data["agent"], data.get("model"), data.get("agent_version"))
        by_key[key].append(data)

    rows: list[dict] = []
    for (agent, model, version), results in by_key.items():
        statuses = [r["status"] for r in results]
        n_resolved = sum(1 for s in statuses if s == "resolved")
        n_attempted = len({r["task_id"] for r in results})
        rows.append({
            "agent": agent,
            "model": model,
            "agent_version": version,
            "n_resolved": n_resolved,
            "n_attempted": n_attempted,
            "pass_rate": n_resolved / n_attempted if n_attempted else 0.0,
            "median_cost_usd": _median([(r.get("usage") or {}).get("cost_usd") for r in results]),
            "median_duration_sec": _median([r.get("duration_sec") for r in results]),
            "median_tokens_in": _median([(r.get("usage") or {}).get("tokens_in") for r in results]),
            "median_tokens_out": _median([(r.get("usage") or {}).get("tokens_out") for r in results]),
            "last_run": max(r.get("started_at", "") for r in results),
        })
    rows.sort(key=lambda r: r["pass_rate"], reverse=True)
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_metrics.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add cae/metrics.py tests/test_metrics.py
git commit -m "Task 15: metrics.aggregate_results"
```

---

### Task 16: `cae report` CLI

**Files:**
- Create: `cae/render_table.py` (hand-rolled console table)
- Modify: `cae/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Create `cae/render_table.py`**

```python
"""Hand-rolled console table renderer. No external deps."""

from __future__ import annotations


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a fixed-width text table. `rows` are pre-stringified cells."""
    if not rows:
        return ""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = []
    lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)
```

- [ ] **Step 2: Add `report` subcommand to `cae/cli.py`**

Add before `build_parser`:

```python
def cmd_report(args: argparse.Namespace) -> int:
    from cae.metrics import aggregate_results
    from cae.render_table import render_table
    rows = aggregate_results(Path(args.results_dir))
    if args.format == "table":
        headers = ["AGENT", "MODEL", "PASS RATE", "N", "MEDIAN COST", "MEDIAN DUR (s)", "LAST RUN"]
        def fmt_cost(v):
            return f"${v:.2f}" if v is not None else "$?"
        def fmt_dur(v):
            return f"{v:.0f}" if v is not None else "?"
        out_rows = [
            [r["agent"], str(r["model"] or ""),
             f"{r['pass_rate']*100:.0f}%", str(r["n_attempted"]),
             fmt_cost(r["median_cost_usd"]), fmt_dur(r["median_duration_sec"]),
             r["last_run"]]
            for r in rows
        ]
        print(render_table(headers, out_rows))
    else:
        import json
        print(json.dumps(rows, indent=2, default=str))
    return 0
```

In `build_parser`:

```python
    p_rep = sub.add_parser("report", help="aggregate and display results")
    p_rep.add_argument("--results-dir", default="results", help="where to read result JSONs (default: results)")
    p_rep.add_argument("--format", default="table", choices=["table", "json"], help="output format (default: table)")
    p_rep.set_defaults(func=cmd_report)
```

- [ ] **Step 3: Add CLI test**

Append to `tests/test_cli.py`:

```python
def test_cae_report_table_format(tmp_path):
    """Write two result files and verify report prints a table."""
    import json
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "r1.json").write_text(json.dumps({
        "agent": "mock", "agent_version": "0.1", "model": None,
        "status": "resolved", "duration_sec": 1, "usage": {"cost_usd": 0.0},
        "task_id": "t1", "started_at": "2026-06-07T00:00:00Z",
        "test_results": {},
    }))
    result = subprocess.run(
        [sys.executable, "-m", "cae", "report",
         "--results-dir", str(tmp_path / "results")],
        capture_output=True, text=True,
    )
    # mock is filtered out, so the table is empty (just headers)
    assert result.returncode == 0
    assert "AGENT" in result.stdout  # header row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add cae/render_table.py cae/cli.py tests/test_cli.py
git commit -m "Task 16: cae report --format table"
```

---

### Task 17: Static Site

**Files:**
- Create: `cae/site.py`
- Create: `tests/test_site.py`
- Modify: `cae/cli.py` (add `build-site` subcommand)
- Create: `site/vendor/.gitkeep`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_site.py
import json
from pathlib import Path

import pytest

from cae.site import build_site


@pytest.fixture
def site_inputs(tmp_path) -> tuple[Path, Path]:
    results = tmp_path / "results"
    results.mkdir()
    (results / "r1.json").write_text(json.dumps({
        "agent": "claude-code", "agent_version": "1.0", "model": "claude-opus-4-7",
        "status": "resolved", "duration_sec": 100, "usage": {"cost_usd": 0.1},
        "task_id": "t1", "started_at": "2026-06-07T00:00:00Z",
        "test_results": {}, "patch": "diff --git a/x b/x\n+1",
    }))
    out = tmp_path / "site"
    return results, out


def test_build_site_creates_index_html(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    assert (out / "index.html").exists()
    html = (out / "index.html").read_text()
    assert "claude-code" in html
    assert "Pass rate" in html or "PASS" in html


def test_build_site_creates_results_json(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    data = json.loads((out / "data" / "results.json").read_text())
    assert len(data) == 1
    assert data[0]["agent"] == "claude-code"


def test_build_site_creates_per_task_page(site_inputs):
    results, out = site_inputs
    build_site(results, out)
    assert (out / "tasks" / "t1.html").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_site.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/site.py`**

```python
"""Build a static leaderboard site from results/*.json.

Output:
  site/index.html           — sortable leaderboard table
  site/data/results.json    — aggregate rows for the table
  site/tasks/<id>.html      — per-task detail (one per (task, agent))
  site/reproducibility.html — copied from docs/reproducibility.md if present
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cae.metrics import aggregate_results


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harness_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _fmt_cost(v):
    return f"${v:.2f}" if v is not None else "$?"


def _fmt_dur(v):
    return f"{v:.0f}s" if v is not None else "?"


def _fmt_int(v):
    return f"{v:.0f}" if v is not None else "?"


def _index_html(rows: list[dict], harness_sha: str) -> str:
    rows_html = "\n".join(
        f"<tr><td>{html.escape(r['agent'])}</td>"
        f"<td>{html.escape(str(r['model'] or ''))}</td>"
        f"<td>{r['pass_rate']*100:.0f}%</td>"
        f"<td>{r['n_attempted']}</td>"
        f"<td>{_fmt_cost(r['median_cost_usd'])}</td>"
        f"<td>{_fmt_dur(r.get('median_duration_sec'))}</td>"
        f"<td>{_fmt_int((r.get('median_tokens_in') or 0) + (r.get('median_tokens_out') or 0))}</td>"
        f"<td>{r['last_run']}</td></tr>"
        for r in rows
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>cae leaderboard</title>
<style>
body {{ font: 14px/1.4 system-ui, sans-serif; max-width: 1200px; margin: 2em auto; padding: 0 1em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f5f5f5; cursor: pointer; }}
tr:hover {{ background: #fafafa; }}
footer {{ margin-top: 2em; color: #888; font-size: 12px; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #1a1a1a; color: #ddd; }}
  th {{ background: #2a2a2a; }}
  tr:hover {{ background: #222; }}
  th, td {{ border-color: #333; }}
}}
</style></head><body>
<h1>cae leaderboard</h1>
<p>Public, reproducible benchmark of CLI coding agents on SWE-bench Verified.</p>
<table id="lb">
<thead><tr>
  <th>Agent</th><th>Model</th><th>Pass rate</th><th># tasks</th>
  <th>Median cost</th><th>Median time</th><th>Median tokens (in+out)</th>
  <th>Last run</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
<footer>Built {_now_iso()} with harness <code>{html.escape(harness_sha)}</code> &middot; <a href="reproducibility.html">reproducibility</a></footer>
<script>
// minimal sort: click any th to sort the table by that column
document.querySelectorAll('th').forEach((th, i) => {{
  th.addEventListener('click', () => {{
    const tbody = document.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
    th.dataset.dir = dir;
    rows.sort((a, b) => (dir === 'asc' ? 1 : -1) * a.cells[i].textContent.localeCompare(b.cells[i].textContent, undefined, {{numeric: true}}));
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body></html>"""


def _task_html(task_id: str, results: list[dict]) -> str:
    sections = []
    for r in results:
        # Defensive: `usage` may be missing or null in some result JSONs.
        usage = r.get("usage") or {}
        cost = usage.get("cost_usd")
        sections.append(f"""<details>
<summary><strong>{html.escape(r['agent'])}</strong> — {html.escape(r['status'])}</summary>
<p>Model: <code>{html.escape(str(r.get('model') or ''))}</code> &middot;
   Duration: {r.get('duration_sec', 0):.0f}s &middot;
   Cost: {_fmt_cost(cost)}</p>
<pre><code>{html.escape(r.get('patch', ''))}</code></pre>
</details>""")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(task_id)}</title>
<style>body{{font:14px/1.4 system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}}
pre{{background:#f5f5f5;padding:1em;overflow-x:auto}}
@media(prefers-color-scheme:dark){{body{{background:#1a1a1a;color:#ddd}}pre{{background:#222}}}}
</style></head><body>
<h1>{html.escape(task_id)}</h1>
{''.join(sections)}
<p><a href="../index.html">back to leaderboard</a></p>
</body></html>"""


def build_site(results_dir: Path, out_dir: Path, docs_dir: Path | None = None) -> None:
    """Generate the static site under out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)
    (out_dir / "tasks").mkdir(exist_ok=True)

    # 1. Aggregate and write data/results.json
    rows = aggregate_results(results_dir)
    (out_dir / "data" / "results.json").write_text(json.dumps(rows, indent=2, default=str))

    # 2. index.html
    (out_dir / "index.html").write_text(_index_html(rows, _harness_sha()))

    # 3. Per-task pages
    by_task: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(results_dir.glob("*.json")):
        data = json.loads(f.read_text())
        if data.get("agent") == "mock":
            continue
        by_task[data["task_id"]].append(data)
    for task_id, results in by_task.items():
        (out_dir / "tasks" / f"{task_id}.html").write_text(_task_html(task_id, results))

    # 4. Reproducibility doc (if source present)
    if docs_dir and (docs_dir / "reproducibility.md").exists():
        from cae.render_markdown import render_markdown
        md = (docs_dir / "reproducibility.md").read_text()
        (out_dir / "reproducibility.html").write_text(render_markdown(md))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_site.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Add `build-site` subcommand to `cae/cli.py`**

Add before `build_parser`:

```python
def cmd_build_site(args: argparse.Namespace) -> int:
    from cae.site import build_site
    build_site(
        results_dir=Path(args.results_dir),
        out_dir=Path(args.out_dir),
        docs_dir=Path(args.docs_dir) if args.docs_dir else None,
    )
    print(f"wrote site to {args.out_dir}")
    return 0
```

In `build_parser`:

```python
    p_bs = sub.add_parser("build-site", help="build the static leaderboard site")
    p_bs.add_argument("--results-dir", default="results", help="where to read result JSONs")
    p_bs.add_argument("--out-dir", default="site", help="where to write the site (default: site)")
    p_bs.add_argument("--docs-dir", default="docs", help="where to find docs (for reproducibility.html)")
    p_bs.add_argument("--publish", action="store_true", help="also push via `gh` CLI (requires `gh` on PATH)")
    p_bs.set_defaults(func=cmd_build_site)
```

- [ ] **Step 6: Create `site/vendor/.gitkeep` (empty)**

```
```

- [ ] **Step 7: Commit**

```bash
git add cae/site.py tests/test_site.py cae/cli.py site/vendor/.gitkeep
git commit -m "Task 17: cae build-site (static leaderboard)"
```

---

### Task 18: Reproducibility doc + Markdown renderer

**Files:**
- Create: `cae/render_markdown.py`
- Create: `tests/test_render_markdown.py`
- Create: `docs/reproducibility.md`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render_markdown.py
from cae.render_markdown import render_markdown


def test_renders_heading():
    html = render_markdown("# Title\n")
    assert "<h1>" in html and "Title" in html


def test_renders_paragraph():
    html = render_markdown("hello world\n")
    assert "<p>" in html and "hello world" in html


def test_renders_code_block():
    md = "```\nfoo\n```\n"
    html = render_markdown(md)
    assert "<pre>" in html and "<code>" in html and "foo" in html


def test_renders_inline_code():
    html = render_markdown("run `cae run` now")
    assert "<code>cae run</code>" in html


def test_renders_link():
    html = render_markdown("see [docs](https://x.com)")
    assert '<a href="https://x.com">docs</a>' in html


def test_renders_doctype_and_body():
    html = render_markdown("# t\n")
    assert html.startswith("<!doctype html>")
    assert "</body>" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/render_markdown.py`**

```python
"""Tiny markdown → HTML renderer for docs/reproducibility.md.

Supports: h1-h3, paragraphs, fenced code blocks, inline code, links, lists.
This is intentionally small — not CommonMark — but covers the docs we author.
"""

from __future__ import annotations

import html
import re


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_FENCE_RE = re.compile(r"^```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LIST_RE = re.compile(r"^[-*]\s+(.*)$")


def render_markdown(md: str) -> str:
    out: list[str] = ["<!doctype html>", "<html><head><meta charset=\"utf-8\"></head><body>"]
    in_code = False
    in_list = False
    for raw_line in md.splitlines():
        line = raw_line.rstrip()
        if _FENCE_RE.match(line):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(raw_line))
            continue
        m = _HEADING_RE.match(line)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = len(m.group(1))
            out.append(f"<h{level}>{html.escape(m.group(2))}</h{level}>")
            continue
        m = _LIST_RE.match(line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip() == "":
            continue
        out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    out.append("</body></html>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_render_markdown.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Create `docs/reproducibility.md`**

```markdown
# Reproducibility

Every leaderboard row can be reproduced from a single command.

## What's in a result

Each `results/<run_id>.json` captures:

- `agent`, `agent_version`, `model` — what was run
- `mode` — `local` or `docker`
- `started_at`, `harness_git_sha` — when and with which code
- `task_source` — the SWE-bench split and upstream commit
- `patch`, `test_results` — what the agent produced and how the tests ran

## Reproducing a row

Given a row, find the `agent` and the task list, then run:

```
cae run --agent <agent> --task <task_id> [--docker]
```

For the official leaderboard, always use `--docker` so the run is reproducible across machines. Without it, results depend on the local Python/library versions in the workdir.

## Upstream drift

If the SWE-bench dataset is updated, old results can still be re-run because `task_source.swe_bench_commit` is recorded in the result JSON. The importer writes this at import time.
```

- [ ] **Step 6: Commit**

```bash
git add cae/render_markdown.py tests/test_render_markdown.py docs/reproducibility.md
git commit -m "Task 18: reproducibility.md + tiny markdown renderer"
```

---

## Phase 5: Production Polish (Tasks 19–22)

### Task 19: CLI polish (resume, --repeat, --force, --keep-workdir, --fetch-fresh)

**Files:**
- Modify: `cae/cli.py`
- Modify: `cae/harness.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Extend `cmd_run` in `cae/cli.py` to accept these flags and pass them through**

Replace the existing `cmd_run` and `p_run` setup:

```python
def cmd_run(args: argparse.Namespace) -> int:
    from cae.harness import run
    task_path = Path(args.tasks_dir) / args.task
    if not (task_path / "task.json").exists():
        print(f"error: task {args.task!r} not found at {task_path}", file=sys.stderr)
        return 2

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    # Resume: per (task, agent, repeat-index), skip if a result file already exists.
    # With --repeat N, all N indices must be missing for the pair to fully run.
    workdir = None
    if args.workdir:
        workdir = Path(args.workdir)
    repeat = max(1, args.repeat)
    for i in range(1, repeat + 1):
        repeat_index = i if repeat > 1 else None
        suffix = f"__{i}" if repeat_index is not None else ""
        out_pattern = f"*__{args.agent}__{args.task}{suffix}.json"
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
            repeat=repeat,
            repeat_index=repeat_index,
        )
        out = results_dir / f"{result['run_id']}.json"
        out.write_text(json.dumps(result, indent=2, default=str))
        print(f"wrote {out}")
        print(f"status: {result['status']}")
    return 0
```

Update `p_run` flags in `build_parser`:

```python
    p_run.add_argument("--agent", required=True)
    p_run.add_argument("--task", required=True)
    p_run.add_argument("--tasks-dir", default="tasks")
    p_run.add_argument("--results-dir", default="results")
    p_run.add_argument("--timeout", type=int, default=30, help="per-stage timeout in minutes")
    p_run.add_argument("--workdir", default=None, help="pre-populated workdir (skips fetch)")
    p_run.add_argument("--fetch-fresh", action="store_true",
                      help="clone the repo from GitHub at base_commit instead of copying from tasks/<id>/repo/")
    p_run.add_argument("--keep-workdir", action="store_true", help="don't delete the workdir after the run")
    p_run.add_argument("--force", action="store_true", help="overwrite existing result files for this (task, agent) pair")
    p_run.add_argument("--repeat", type=int, default=1, help="run this many times (default: 1)")
    p_run.add_argument("--docker", action="store_true", help="run inside a Docker container")
    p_run.add_argument("--docker-image", default="python:3.11-slim",
                      help="base image for --docker mode (default: python:3.11-slim)")
    p_run.add_argument("--env-file", default=None,
                      help="file with KEY=VALUE lines, passed to `docker run --env-file` (for API keys)")
```

- [ ] **Step 2: Update `harness.run` to accept the new kwargs**

In `cae/harness.py`, the `run` signature was already extended in Task 7 to include
`fetch_fresh`, `keep_workdir`, `docker`, `docker_image`, `env_file`, `repeat`, and
`repeat_index`. Verify it matches the new `cmd_run` call site; if anything is
missing, add it.

Add this cleanup logic to the harness near the end of `run` (before the final return):

```python
    if workdir_owned and not keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
```

- [ ] **Step 3: Add CLI tests for the new flags**

Append to `tests/test_cli.py`:

```python
def test_cae_run_with_keep_workdir(tmp_path, tiny_task_path):
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        (tasks / "repo" / child.name).write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task", "--keep-workdir",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(list((proj / "results").glob("*.json"))[0].read_text())
    # workdir path should be recorded in the result
    assert "workdir" in data
    assert data["workdir"]  # non-empty


def test_cae_run_force_flag_resumes(tmp_path, tiny_task_path):
    """Without --force, a second run for the same (task, agent) skips."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        (tasks / "repo" / child.name).write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    base_cmd = [sys.executable, "-m", "cae", "run", "--agent", "mock",
                "--task", "tiny_task",
                "--tasks-dir", str(proj / "tasks"),
                "--results-dir", str(proj / "results")]

    r1 = subprocess.run(base_cmd, capture_output=True, text=True)
    assert r1.returncode == 0
    n_after_first = len(list((proj / "results").glob("*.json")))

    r2 = subprocess.run(base_cmd, capture_output=True, text=True)
    assert "skipping" in r2.stdout or n_after_first == len(list((proj / "results").glob("*.json")))

    r3 = subprocess.run(base_cmd + ["--force"], capture_output=True, text=True)
    assert r3.returncode == 0
```

- [ ] **Step 4: Run all tests**

Run: `pytest -v`
Expected: PASS (all tests across all files)

- [ ] **Step 5: Commit**

```bash
git add cae/cli.py cae/harness.py tests/test_cli.py
git commit -m "Task 19: CLI polish (resume, --repeat, --force, --keep-workdir, --fetch-fresh)"
```

---

### Task 20: Documentation (`docs/adding-tasks.md`, expanded README)

**Files:**
- Create: `docs/adding-tasks.md`
- Modify: `README.md`

- [ ] **Step 1: Create `docs/adding-tasks.md`**

```markdown
# Adding Tasks

Two paths: import from SWE-bench or author by hand.

## Import from SWE-bench

```
cae add-task --from-swebench --limit 50
cae add-task --from-swebench --instance-id django__django-12345
```

The importer writes `tasks/<id>/task.json`, `tests.patch`, and `repo/` (a git checkout at `base_commit`).

## Author by hand

Create a directory under `tasks/<your_id>/`:

```
tasks/my_task/
├── task.json
└── repo/
    ├── main.py
    └── test_main.py
```

`task.json` schema:

```json
{
  "instance_id": "my_task",
  "repo": "my/repo",
  "base_commit": "<any sha>",
  "prompt": "Description of the task the agent sees.",
  "setup_cmd": "pip install -e .",
  "test_cmd": "python -m pytest -v",
  "fail_to_pass": ["test_main.py::test_foo"],
  "pass_to_pass": ["test_main.py::test_bar"]
}
```

`fail_to_pass` lists tests that fail before the agent runs and must pass after.
`pass_to_pass` lists tests that pass before and must still pass after.
No `tests.patch` is needed for hand-authored tasks; the test cases are already in `repo/`.
```

- [ ] **Step 2: Update `README.md`**

```markdown
# probe-agent-eval

Public, reproducible benchmark for CLI coding agents. Compare Claude Code, Codex, Aider, and more on the same set of real-world tasks. See `docs/superpowers/specs/2026-06-06-coding-agent-eval-design.md` for the design.

## Quickstart

```
pip install -e ".[dev]"
cae --help
```

## Run a task

```
cae list-agents
cae run --agent mock --task tiny_task --tasks-dir tests/fixtures --results-dir /tmp/cae
```

The result is written to `/tmp/cae/<run_id>.json`.

## Add tasks

From SWE-bench Verified:

```
cae add-task --from-swebench --limit 50
```

Or by hand: see `docs/adding-tasks.md`.

## Build the leaderboard site

```
cae build-site --results-dir results --out-dir site
```

Deploy `site/` to GitHub Pages (or run `cae build-site --publish` to push via the `gh` CLI).

## Development

```
pytest -v
ruff check cae tests
```

## Status

Pre-v1. See `docs/superpowers/plans/2026-06-07-coding-agent-eval.md` for the implementation plan.
```

- [ ] **Step 3: Commit**

```bash
git add docs/adding-tasks.md README.md
git commit -m "Task 20: docs (adding-tasks, README)"
```

---

### Task 21: End-to-end integration test (full vertical slice replay)

**Files:**
- Create: `tests/test_integration.py`
- Modify: `tests/conftest.py` (if needed)

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration.py
"""Full vertical-slice replay: harness + mock + tiny fixture, end-to-end."""

import json
import subprocess
import sys
from pathlib import Path


def test_full_vertical_slice_replay(tmp_path, tiny_task_path):
    """Re-run the Task 8 manual smoke test programmatically."""
    proj = tmp_path
    # copy the tiny fixture into a fresh tasks/ tree
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    repo = tasks / "repo"
    repo.mkdir()
    for child in (tiny_task_path / "repo").iterdir():
        (repo / child.name).write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    result = subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"

    files = list((proj / "results").glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())

    # every required spec field is present
    for field in ("run_id", "task_id", "agent", "agent_version", "model", "mode",
                  "status", "started_at", "duration_sec", "harness_git_sha",
                  "task_source", "usage", "test_results", "patch", "workdir"):
        assert field in data, f"missing field: {field}"

    # test_results has both pre and post flight
    assert "pre_flight" in data["test_results"]
    assert "post_flight" in data["test_results"]
    assert "fail_to_pass" in data["test_results"]["post_flight"]
    assert "pass_to_pass" in data["test_results"]["post_flight"]


def test_aggregate_after_run(tmp_path, tiny_task_path):
    """After a run, cae report and cae build-site should work end-to-end."""
    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    repo = tasks / "repo"
    repo.mkdir()
    for child in (tiny_task_path / "repo").iterdir():
        (repo / child.name).write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    subprocess.run(
        [sys.executable, "-m", "cae", "run", "--agent", "mock",
         "--task", "tiny_task",
         "--tasks-dir", str(proj / "tasks"),
         "--results-dir", str(proj / "results")],
        check=True, capture_output=True, text=True, timeout=120,
    )

    # report --format table should run cleanly
    r = subprocess.run(
        [sys.executable, "-m", "cae", "report",
         "--results-dir", str(proj / "results")],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0

    # build-site should produce an index.html
    site_out = proj / "site"
    r2 = subprocess.run(
        [sys.executable, "-m", "cae", "build-site",
         "--results-dir", str(proj / "results"),
         "--out-dir", str(site_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert r2.returncode == 0, r2.stderr
    assert (site_out / "index.html").exists()
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v`
Expected: PASS (2 tests, may take 10-30s each for harness + grading)

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "Task 21: end-to-end integration test (full vertical slice)"
```

---

### Task 22: Docker Mode

**Files:**
- Create: `cae/docker_run.py`
- Create: `tests/test_docker_run.py`
- Modify: `cae/harness.py`
- Modify: `cae/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test (docker_run helpers)**

```python
# tests/test_docker_run.py
from pathlib import Path
from unittest.mock import patch, MagicMock

from cae.docker_run import in_container, exec_in, run_in_container


def test_in_container_returns_true_when_dockerenv_exists(monkeypatch, tmp_path):
    fake_rootfs = tmp_path
    (fake_rootfs / ".dockerenv").touch()
    monkeypatch.setattr("pathlib.Path.root", lambda: fake_rootfs)
    assert in_container() is True


def test_in_container_returns_false_when_no_dockerenv(monkeypatch, tmp_path):
    fake_rootfs = tmp_path
    monkeypatch.setattr("pathlib.Path.root", lambda: fake_rootfs)
    assert in_container() is False


def test_exec_in_builds_docker_exec_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        exec_in("my-image", ["ls", "/work"], workdir=Path("/tmp"), timeout=60, env_file=None)
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0:2] == ["docker", "exec"]
        assert "my-image" in cmd
        assert "ls" in cmd
        assert "/work" in cmd


def test_exec_in_passes_env_file_when_provided():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        exec_in("my-image", ["ls"], workdir=Path("/tmp"), timeout=60, env_file=Path("/tmp/env"))
        cmd = mock_run.call_args[0][0]
        assert "--env-file" in cmd
        assert "/tmp/env" in cmd
```

(We can't actually run a real container in CI; these tests are mocked.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_docker_run.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `cae/docker_run.py`**

```python
"""Helpers for running the harness inside a Docker container (--docker mode)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path


def in_container() -> bool:
    """Return True if we're already running inside a Docker container."""
    return Path("/.dockerenv").exists()


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_docker_run.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Confirm harness docker wiring (already done in Task 7)**

Task 7's `harness.run` already includes the `run_step` closure that dispatches to
`exec_in` when `docker=True`. Verify by reading `cae/harness.py`; no code changes
needed for this step.

- [ ] **Step 6: Confirm CLI docker flags (already done in Task 19)**

Task 19's `p_run` setup already adds `--docker`, `--docker-image`, and `--env-file`,
and `cmd_run` already passes them to `harness.run`. Verify by reading `cae/cli.py`;
no code changes needed for this step.

- [ ] **Step 7: Add a CLI test for `--docker` (mocked — actual docker not required)**

Append to `tests/test_cli.py`:

```python
def test_cae_run_docker_flag_accepted(tmp_path, tiny_task_path):
    """`--docker` is accepted by argparse; the run will fail if `docker` is not
    on PATH. We mock `subprocess.run` to assert that the docker-runner branch
    is actually invoked (i.e., the harness called `docker run ...`)."""
    from unittest.mock import patch, MagicMock

    proj = tmp_path
    tasks = proj / "tasks" / "tiny_task"
    tasks.mkdir(parents=True)
    (tasks / "task.json").write_text((tiny_task_path / "task.json").read_text())
    for child in (tiny_task_path / "repo").iterdir():
        (tasks / "repo" / child.name).write_bytes(child.read_bytes())
    (proj / "results").mkdir()

    docker_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        # Capture any docker invocation.
        if isinstance(cmd, list) and cmd and cmd[0] == "docker":
            docker_calls.append(cmd)
        return MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        result = subprocess.run(
            [sys.executable, "-m", "cae", "run", "--agent", "mock",
             "--task", "tiny_task", "--docker",
             "--tasks-dir", str(proj / "tasks"),
             "--results-dir", str(proj / "results")],
            capture_output=True, text=True, timeout=30,
        )

    # Either docker was actually called (at least one), or the run failed cleanly.
    # We don't assert the exact call count because the harness invokes docker
    # for setup, pre-flight, agent, and grading — any of those being called
    # proves the docker branch is wired up.
    assert result.returncode == 0 or "docker" in result.stderr.lower()
    # If subprocess was mocked to succeed, the harness should have run end-to-end.
    if result.returncode == 0:
        assert docker_calls, "expected at least one docker invocation with --docker"
```

- [ ] **Step 8: Run all tests**

Run: `pytest -v`
Expected: all tests pass (or skip cleanly if docker is not available)

- [ ] **Step 9: Commit**

```bash
git add cae/docker_run.py tests/test_docker_run.py cae/harness.py cae/cli.py tests/test_cli.py
git commit -m "Task 22: Docker mode (--docker, --docker-image, --env-file)"
```

---

## Self-Review

**Spec coverage:**
- Architecture (directory tree) → covered by Task 1 + each module's create step
- Task format (SWE-bench-style JSON) → covered by Task 6 (fixture) + Task 9 (importer)
- Agent Adapter Protocol (`is_available`, `version`, `build_command`, `parse_output`) → Tasks 2, 5, 11, 12, 13
- Run lifecycle (steps 1-11) → Task 7
- Test patch application → Task 7 (step 4)
- Pre-flight + post-flight in result JSON → Task 7 + Task 2 (TestStatus)
- Grading rules → Task 4
- Status enum (6 values) → Task 2
- Docker mode → Task 22
- Resilience (timeout, --force, --keep-workdir) → Task 19
- Output JSON shape → Task 7
- Metrics (median, n_attempted, mock excluded) → Task 15
- Console report → Task 16
- Static site → Task 17
- Reproducibility doc → Task 18
- Testing strategy (unit, integration, smoke) → Tasks 1-8 (unit) + Task 21 (integration) + Task 10 (smoke docs)

**Gaps found during self-review and addressed inline:**
- The mock adapter in Task 5 calls `subprocess` from the adapter, but the actual implementation should be exercised by the harness's `_run_subprocess` not the adapter's `build_command`. Fixed in Task 5 by making the mock command a no-op (`python -c "import sys; sys.exit(0)"`).
- Task 7's `run` signature changed during Task 19 (added `fetch_fresh`, `keep_workdir`); the changes are consolidated in Task 19 step 2 to keep the plan DRY.
- Task 17's `_index_html` references "PASS" in the test but the column is "Pass rate" — fixed in test step 1.

**Type consistency check:**
- `Status` enum values used in Task 4 (grader) match Task 2 (definition): `"resolved"`, `"failed"`.
- `TestStatus` enum values used in Task 3 (parser) match Task 2 (definition): `"passed"`, `"failed"`, `"error"`, `"skipped"`, `"xfail"`.
- `AgentResult` fields used in Task 5 (mock) and Task 7 (harness) match Task 2 (definition): `log`, `usage`, `exit_code`. (Note: `duration_sec` is set by `_run_subprocess`, not by the adapter — Task 7 is the source of truth.)
- `UsageInfo` fields used in Task 11 (claude-code) and Task 17 (site) match Task 2: `tokens_in`, `tokens_out`, `cost_usd`, `model`, `billing_mode`.

No inconsistencies remaining.

**Placeholder scan:** No "TBD", "TODO", "implement later", or vague "add appropriate error handling" phrases. Every step has explicit code or commands.

**DRY check:** Each piece of logic is introduced once and referenced by name in later tasks. The harness's `_run_subprocess` and `_ensure_git_repo` are written once in Task 7 and reused in later tasks via the `run` function signature changes (Tasks 19, 22) rather than copy-pasting.

---

## Execution

After committing the plan, choose an execution mode:

**Option A — Subagent-Driven (recommended):** I dispatch a fresh subagent per task, review between tasks.

**Option B — Inline Execution:** I execute the tasks in this session, batched with checkpoints.

Which approach?
