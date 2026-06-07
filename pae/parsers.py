"""Per-runner parsers: map a test runner's output to {test_name: TestStatus}.

v1 ships with pytest. New runners = new function in this module. The contract
is: a parser takes the runner's full output (stdout+stderr) and returns a dict
mapping fully-qualified test names to TestStatus. Unknown lines are ignored.
"""

from __future__ import annotations

import re

from pae.agents.base import TestStatus

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
