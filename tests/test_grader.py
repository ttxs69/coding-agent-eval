from pae.agents.base import Status, TestStatus
from pae.grader import grade


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
