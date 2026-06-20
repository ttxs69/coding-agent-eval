"""Model pricing table for cost computation.

Some agent CLIs (notably codex) emit token counts in their JSONL output
but NOT a ``cost_usd`` field. To produce a cost number for the
leaderboard, we look the model up in this table and compute::

    cost = (tokens_in        * price_input        +
            tokens_out       * price_output       +
            cache_read       * price_cache_read   +
            cache_creation   * price_cache_create) / 1_000_000

All prices are USD per million tokens, from each provider's public list
pricing. **Gateways and proxies may charge differently** — these are
estimates for cases where the agent CLI doesn't report cost directly.
If your actual cost differs, treat the computed number as an upper bound
on the public-list cost, not a billable amount.

To add a model: append to :data:`PRICING`. To override at runtime,
set the ``CAE_PRICING_JSON`` env var to a JSON file mapping model names
to ``{input, output, cache_read, cache_creation}`` dicts (those entries
take precedence over the defaults here).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# USD per million tokens. cache_read is typically 10% of input for
# providers that support prompt caching (Anthropic, OpenAI). cache_creation
# is typically 1.25× input (Anthropic's write surcharge). Fields default
# to 0 if missing — e.g. a model with no caching support just has input +
# output entries.
PRICING: dict[str, dict[str, float]] = {
    # Anthropic — public list pricing as of mid-2026.
    "claude-opus-4-7":    {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_creation": 18.75},
    "claude-sonnet-4-6":  {"input":  3.0, "output": 15.0, "cache_read": 0.30, "cache_creation":  3.75},
    "claude-haiku-4-5":   {"input":  1.0, "output":  5.0, "cache_read": 0.10, "cache_creation":  1.25},
    # OpenAI — approximate; OpenAI has tiered pricing and we list the
    # standard tier. Cache read is 50% of input for OpenAI's automatic
    # prompt caching (different discount than Anthropic's).
    "gpt-5":              {"input":  5.0, "output": 15.0, "cache_read": 2.50},
    "gpt-4o":             {"input":  2.50, "output": 10.0, "cache_read": 1.25},
    "gpt-4o-mini":        {"input":  0.15, "output":  0.60, "cache_read": 0.075},
}


def _load_user_overrides() -> dict[str, dict[str, float]]:
    """Load pricing overrides from $CAE_PRICING_JSON if set. Returns {} if
    the file is missing or unreadable (we don't crash the run for a
    misconfigured pricing file)."""
    path = os.environ.get("CAE_PRICING_JSON")
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text())
        # Light validation: each value must be a dict of floats.
        for model, prices in data.items():
            if not isinstance(prices, dict):
                raise ValueError(f"{model}: expected dict, got {type(prices).__name__}")
        return data
    except Exception:
        return {}


def compute_cost(
    model: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    cache_read: int | None = None,
    cache_creation: int | None = None,
) -> float | None:
    """Compute cost in USD from token counts × model pricing.

    Returns ``None`` if ``model`` isn't in the (possibly-overridden)
    pricing table — we don't guess. Token fields that are ``None`` count
    as 0.
    """
    if model is None:
        return None
    prices = _load_user_overrides().get(model) or PRICING.get(model)
    if prices is None:
        return None
    tin = tokens_in or 0
    tout = tokens_out or 0
    tcr = cache_read or 0
    tcc = cache_creation or 0
    return (
        tin  * prices.get("input", 0.0)
        + tout * prices.get("output", 0.0)
        + tcr  * prices.get("cache_read", 0.0)
        + tcc  * prices.get("cache_creation", 0.0)
    ) / 1_000_000
