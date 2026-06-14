"""Validate the fixture project is set up correctly.

These tests don't run the skill — they verify the fixture has the
seeded issues the skill is supposed to find. Run via:
    uv run pytest self-improve-skill/tests/test_fixture_project.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "self-improve-sample-project"
)
SRC = FIXTURE / "src" / "sample" / "__init__.py"


def _read_source() -> str:
    return SRC.read_text()


def test_fixture_has_seeded_bug():
    """add() contains the off-by-one (returns a - b + 1 instead of a + b)."""
    src = _read_source()
    assert "return a - b + 1" in src, "seeded bug missing from add()"


def test_fixture_has_seeded_missing_test_target():
    """public_api_function has no test (the missing-test candidate)."""
    test_file = (FIXTURE / "tests" / "test_sample.py").read_text()
    assert "public_api_function" not in test_file, (
        "public_api_function is supposed to be untested"
    )


def test_fixture_has_seeded_todo_comment():
    """A TODO comment exists (refactor/dedup candidate)."""
    src = _read_source()
    assert "TODO" in src, "seeded TODO missing"


def test_fixture_has_seeded_duplication():
    """sum_pair and product_pair both unpack a pair then call — duplication."""
    src = _read_source()
    assert "def sum_pair" in src and "def product_pair" in src


def test_fixture_has_seeded_missing_docstring():
    """public_api_function has no docstring (docs-gap candidate)."""
    src = _read_source()
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "def public_api_function" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                body = lines[j].strip()
                if body and not body.startswith("#"):
                    assert not body.startswith('"""') and not body.startswith("'''"), (
                        f"public_api_function should have no docstring, found: {body}"
                    )
                    break
            return
    raise AssertionError("public_api_function not found in fixture source")


def test_fixture_test_command_fails_on_seeded_bug():
    """Running pytest in the fixture should fail on the seeded bug.

    Validates the fixture is set up correctly for the skill's verify step.
    Sets PYTHONPATH so the test doesn't depend on an editable install of
    `sample` — works on a fresh `git clone && uv sync` with no manual setup.
    """
    env = {"PYTHONPATH": str(FIXTURE / "src"), **os.environ}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "--tb=no", "-q"],
        cwd=FIXTURE,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"expected pytest to fail with exit 1 (test failure) on seeded bug;\n"
        f"got exit {result.returncode}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "test_add_basic" in result.stdout, (
        f"expected failure to mention test_add_basic (the seeded bug);\n"
        f"stdout:\n{result.stdout}"
    )
