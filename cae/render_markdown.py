"""Tiny markdown → HTML renderer for docs/reproducibility.md.

Supports: h1-h3, paragraphs, fenced code blocks, inline code, links, lists.
This is intentionally small — not CommonMark — but covers the docs we author.
"""

from __future__ import annotations

import html
import re


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_FENCE_RE = re.compile(r"^```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_LIST_RE = re.compile(r"^[-*]\s+(.*)$")


def render_markdown(md: str) -> str:
    out: list[str] = ["<!doctype html>", "<html><head><meta charset=\"utf-8\"></head><body>"]
    in_code = False
    in_list = False
    for raw_line in md.splitlines():
        line = raw_line.rstrip()
        if _FENCE_RE.match(line):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            continue
        if in_code:
            out.append(html.escape(raw_line))
            continue
        m = _HEADING_RE.match(line)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            level = len(m.group(1))
            out.append(f"<h{level}>{html.escape(m.group(2))}</h{level}>")
            continue
        m = _LIST_RE.match(line)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip() == "":
            continue
        out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    out.append("</body></html>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    text = _LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text
