#!/usr/bin/env python3
"""Walk results/*.json and recompute cost_usd from token counts × pricing.

Use case: you've added a model to cae/pricing.py (or via CAE_PRICING_JSON)
and want existing result files to reflect the new rates without re-running
the eval (which would cost API $).

Only touches results whose cost_usd is null — agent-supplied costs (e.g.
claude-code's, which comes from the API envelope) are preserved. Use
--force to overwrite even non-null costs (e.g. if the pricing table
changed and you want to recompute everything).

Usage:
    uv run python scripts/reprice_results.py [--results-dir results] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `cae` importable when running as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cae.pricing import compute_cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="results", type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would change; don't write files")
    parser.add_argument("--force", action="store_true",
                        help="overwrite even non-null cost_usd values "
                             "(default: only fill in null costs)")
    args = parser.parse_args()

    results_dir: Path = args.results_dir
    if not results_dir.is_dir():
        print(f"error: results dir not found: {results_dir}", file=sys.stderr)
        return 2

    files = sorted(results_dir.glob("*.json"))
    if not files:
        print(f"(no result files under {results_dir})")
        return 0

    filled = 0
    overwritten = 0
    skipped_already_set = 0
    skipped_no_pricing = 0
    skipped_no_tokens = 0

    for path in files:
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            print(f"warn: {path.name}: unreadable JSON ({e!r})", file=sys.stderr)
            continue

        # Only touch records that look like cae result dicts.
        if "usage" not in data or "agent" not in data:
            continue

        usage = data["usage"]
        current_cost = usage.get("cost_usd")
        if current_cost is not None and not args.force:
            skipped_already_set += 1
            continue

        tokens_in = usage.get("tokens_in")
        tokens_out = usage.get("tokens_out")
        cache_read = usage.get("cache_read_tokens")
        cache_creation = usage.get("cache_creation_tokens")
        model = data.get("model")

        # Can't compute without at least the input/output token counts.
        if tokens_in is None and tokens_out is None:
            skipped_no_tokens += 1
            continue

        new_cost = compute_cost(model, tokens_in, tokens_out, cache_read, cache_creation)
        if new_cost is None:
            skipped_no_pricing += 1
            continue

        action = "would fill" if args.dry_run else "filled"
        if current_cost is not None:
            action = "would overwrite" if args.dry_run else "overwritten"

        print(f"{action:12s} {path.name}: ${current_cost} → ${new_cost:.4f}  "
              f"(model={model}, in={tokens_in}, out={tokens_out}, cache_read={cache_read})")

        if args.dry_run:
            continue

        usage["cost_usd"] = new_cost
        path.write_text(json.dumps(data, indent=2, default=str))
        if current_cost is None:
            filled += 1
        else:
            overwritten += 1

    print()
    print(f"summary: filled={filled}, overwritten={overwritten}, "
          f"skipped(already_set)={skipped_already_set}, "
          f"skipped(no_pricing)={skipped_no_pricing}, "
          f"skipped(no_tokens)={skipped_no_tokens}")
    if args.dry_run:
        print("(dry-run; no files written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
