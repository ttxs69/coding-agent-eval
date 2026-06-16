# Sample Package — Design

**Date:** 2026-06-14
**Purpose:** Tiny synthetic package used as a test fixture for the self-improve skill's forward mode.

## Overview

The `sample` package provides basic arithmetic operations. Currently implements `add` and `multiply`. Pair-helper variants (`sum_pair`, `product_pair`) wrap the basic ops for tuple-style callers.

## Future work

In rough priority order:

- **Subtraction (`subtract(a, b)`)** — pairs with `add` and `multiply` but currently missing. Trivial to implement; closes the basic-arithmetic gap.
- **Exponentiation (`power(base, exp)`)** — would require deciding on integer vs float behavior; non-trivial semantics for negative exponents.

## Out of scope

- Arbitrary-precision arithmetic (Python's built-in `int` already handles this)
- Vectorized / batch operations
