"""Model pricing table for cost computation.

Some agent CLIs (notably codex) emit token counts in their JSONL output
but NOT a ``cost_usd`` field. To produce a cost number for the
leaderboard, we look the model up in this table and compute::

    cost = (tokens_in        * price_input        +
            tokens_out       * price_output       +
            cache_read       * price_cache_read   +
            cache_creation   * price_cache_create) / 1_000_000

The default rates live in ``cae/pricing.json`` (next to this module).
All prices are USD per million tokens, from each provider's public list
pricing. **Gateways and proxies may charge differently** — these are
estimates for cases where the agent CLI doesn't report cost directly.
If your actual cost differs, treat the computed number as an upper bound
on the public-list cost, not a billable amount.

To add a model: append to ``cae/pricing.json``. To override at runtime
without editing the file, set the ``CAE_PRICING_JSON`` env var to a
JSON file mapping model names to ``{input, output, cache_read,
cache_creation}`` dicts — those entries take precedence over the
defaults loaded here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_PRICING_JSON_PATH = Path(__file__).resolve().parent / "pricing.json"


def _load_default_pricing() -> dict[str, dict[str, float]]:
    """Load the default pricing table from cae/pricing.json.

    Crashes loudly if the file is missing or malformed — a broken
    pricing table is a packaging bug, not a runtime fallback case.
    Keys starting with ``_`` (e.g. ``_doc``) are doc-only entries and
    are stripped before returning.
    """
    data = json.loads(_PRICING_JSON_PATH.read_text())
    return {
        model: prices
        for model, prices in data.items()
        if not model.startswith("_") and isinstance(prices, dict)
    }


# Load once at import time. Module-level so callers can `from cae.pricing
# import PRICING` if they want to introspect the defaults (after any
# runtime overrides, callers should use compute_cost() instead).
PRICING: dict[str, dict[str, float]] = _load_default_pricing()


def _load_user_overrides() -> dict[str, dict[str, float]]:
    """Load pricing overrides from $CAE_PRICING_JSON if set. Returns {} if
    the file is missing or unreadable (we don't crash the run for a
    misconfigured pricing file)."""
    path = os.environ.get("CAE_PRICING_JSON")
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text())
        # Strip doc-only keys + light validation, same as defaults.
        return {
            model: prices
            for model, prices in data.items()
            if not model.startswith("_") and isinstance(prices, dict)
        }
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
