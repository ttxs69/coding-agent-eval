"""Decide the top-level task Status from pre-flight and post-flight test results.

Per the spec:
  - resolved iff every test in fail_to_pass ended as PASSED
                AND every test in pass_to_pass ended as PASSED
  - failed otherwise (any non-PASSED outcome in either set)
"""

from __future__ import annotations

from pae.agents.base import Status, TestStatus


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
