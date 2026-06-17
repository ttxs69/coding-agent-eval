from cae.agents.base import Status, TestStatus


def test_status_values():
    assert Status.RESOLVED.value == "resolved"
    assert Status.FAILED.value == "failed"
    assert Status.AGENT_ERROR.value == "agent_error"
    assert Status.TIMEOUT.value == "timeout"
    assert Status.TASK_ERROR.value == "task_error"
    assert Status.GRADER_ERROR.value == "grader_error"
    assert Status.DRY_RUN.value == "dry_run"


def test_status_is_string_enum():
    assert isinstance(Status.RESOLVED, str)
    assert Status.RESOLVED == "resolved"


def test_test_status_values():
    assert TestStatus.PASSED.value == "passed"
    assert TestStatus.FAILED.value == "failed"
    assert TestStatus.ERROR.value == "error"
    assert TestStatus.SKIPPED.value == "skipped"
    assert TestStatus.XFAIL.value == "xfail"


def test_status_count():
    assert len(list(Status)) == 7
    assert len(list(TestStatus)) == 5
