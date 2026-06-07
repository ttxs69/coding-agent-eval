"""Tiny fixture module with one bug and one correct function."""


def add(a: int, b: int) -> int:
    return a - b  # bug: should be a + b


def multiply(a: int, b: int) -> int:
    return a * b
