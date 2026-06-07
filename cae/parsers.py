"""Per-runner parsers: map a test runner's output to {test_name: TestStatus}.

v1 ships with pytest. New runners = new function in this module. The contract
is: a parser takes the runner's full output (stdout+stderr) and returns a dict
mapping fully-qualified test names to TestStatus. Unknown lines are ignored.
"""

from __future__ import annotations

import re

from cae.agents.base import TestStatus

# pytest's verbose-mode line pattern: nodeid STATUS [percent]
# Use a permissive non-whitespace match for the nodeid so parametrize IDs with
# dots, @, +, :, etc. (e.g. `test_y[0.5]`, `test_x[email protected]`) are preserved.
_PYTEST_LINE_RE = re.compile(
    r"^(?P<nodeid>\S+::\S+)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL)\b"
)


def parse_pytest_output(output: str) -> dict[str, TestStatus]:
    """Parse pytest's verbose output into {nodeid: TestStatus}.

    A "nodeid" is pytest's fully-qualified test identifier, e.g.
    "tests/test_main.py::test_add" or "tests/test_x.py::test_y[1]".
    """
    results: dict[str, TestStatus] = {}
    for line in output.splitlines():
        stripped = line.strip()
        m = _PYTEST_LINE_RE.search(stripped)
        if not m:
            continue
        results[m.group("nodeid")] = TestStatus(m.group("status").lower())
    return results
