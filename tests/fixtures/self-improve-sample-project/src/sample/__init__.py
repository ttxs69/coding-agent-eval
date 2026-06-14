"""Sample package for self-improve skill testing.

This module intentionally contains seeded issues the self-improve skill
should detect. See self-improve-skill/tests/test_fixture_project.py for
the catalog.
"""


def add(a, b):
    # BUG: off-by-one — returns a - b + 1 instead of a + b
    return a - b + 1


def multiply(a, b):
    # Has a test below (test_multiply_basic). Contrast with public_api_function,
    # which is the real "missing test" candidate the self-improve skill should find.
    return a * b


# TODO(low priority): extract this into a shared helper. Both `sum_pair`
# and `product_pair` follow the same unpack-then-call pattern. (seeded
# refactor candidate — duplicate logic)
def sum_pair(pair):
    a, b = pair
    return add(a, b)


def product_pair(pair):
    a, b = pair
    return multiply(a, b)


def public_api_function(x):
    # Missing docstring on a public function (seeded docs-gap candidate)
    return x * 2
