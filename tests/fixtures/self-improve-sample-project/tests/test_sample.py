"""Tests for sample package.

test_add_basic exposes the seeded bug in `add()`. test_multiply_basic
passes — `multiply()` works correctly. One public function in the
package is intentionally left untested (see the fixture catalog).
"""

from sample import add, multiply


def test_add_basic():
    # SEEDED BUG: add(2, 3) returns 0 (2 - 3 + 1) instead of 5
    assert add(2, 3) == 5


def test_multiply_basic():
    assert multiply(2, 3) == 6
