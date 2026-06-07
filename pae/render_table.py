"""Hand-rolled console table renderer. No external deps."""

from __future__ import annotations


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a fixed-width text table. `rows` are pre-stringified cells. Headers are always emitted."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = []
    lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)
