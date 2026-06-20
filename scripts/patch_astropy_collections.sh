#!/bin/sh
# Patch old astropy source for Python 3.10+ compat.
#
# SWE-bench's astropy tasks pin to old astropy commits that import the
# deprecated `collections.MutableSequence` / `Mapping` / etc. aliases.
# These were removed in Python 3.10 (the project's pinned version per
# pyproject.toml's requires-python = ">=3.10,<3.11"), so `pip install
# -e .[test]` fails at setup.py egg_info with `AttributeError: module
# 'collections' has no attribute 'MutableSequence'`.
#
# This script rewrites those imports to the modern `collections.abc.X`
# form across every task under tasks/. Run it once after importing
# SWE-bench astropy tasks (or after `cae add-task`).
#
# Why this lives here instead of in the harness: the harness is supposed
# to be task-source-agnostic. Patching source is a one-shot fix-up for
# a known data-quality issue with old SWE-bench Python tasks; keeping
# it as a script makes the modification visible and reproducible.
#
# Re-run is safe — already-patched files match no patterns.
set -eu

# The six deprecated aliases that were removed in 3.10. Match only the
# dotted form (collections.X), not collections.abc.X. The trailing `\b`
# avoids partial matches like `Mappings` (though those don't appear in
# the affected astropy source).
TASKS_DIR="${1:-tasks}"
PATCHED=0
SKIPPED=0

for task_repo in "$TASKS_DIR"/*/repo; do
    [ -d "$task_repo" ] || continue
    # Find files containing the deprecated patterns.
    matches=$(grep -rlE "collections\.(MutableSequence|MutableMapping|Iterable|Mapping|Sequence|Callable)[^a-zA-Z]" "$task_repo" 2>/dev/null || true)
    if [ -z "$matches" ]; then
        SKIPPED=$((SKIPPED + 1))
        continue
    fi
    # Use find + sed so we don't fight xargs on macOS BSD sed quirks.
    echo "$matches" | while IFS= read -r f; do
        # BSD sed (macOS) needs `-i ''`. Detect GNU vs BSD by --version output.
        if sed --version >/dev/null 2>&1; then
            sed -i -E 's/collections\.(MutableSequence|MutableMapping|Iterable|Mapping|Sequence|Callable)([^a-zA-Z])/collections.abc.\1\2/g' "$f"
        else
            sed -i '' -E 's/collections\.(MutableSequence|MutableMapping|Iterable|Mapping|Sequence|Callable)([^a-zA-Z])/collections.abc.\1\2/g' "$f"
        fi
    done
    PATCHED=$((PATCHED + 1))
    echo "patched: $task_repo"
done

echo "---"
echo "patched: $PATCHED task repo(s), skipped (already done or no match): $SKIPPED"
