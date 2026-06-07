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


def test_parse_pytest_parametrized_ids_with_special_chars():
    """Parametrized test IDs can contain dots, @, +, etc. — make sure they're preserved."""
    output = """
tests/test_x.py::test_y[0.5] PASSED                          [ 50%]
tests/test_x.py::test_z[a@b.c] FAILED                       [100%]
========================== 1 failed, 1 passed in 0.02s ===========
"""
    result = parse_pytest_output(output)
    assert result == {
        "tests/test_x.py::test_y[0.5]": TestStatus.PASSED,
        "tests/test_x.py::test_z[a@b.c]": TestStatus.FAILED,
    }
