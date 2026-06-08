"""Build a static leaderboard site from results/*.json.

Output:
  site/index.html           — sortable leaderboard table
  site/data/results.json    — aggregate rows for the table
  site/tasks/<id>.html      — per-task detail (one per (task, agent))
  site/reproducibility.html — copied from docs/reproducibility.md if present
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cae.metrics import aggregate_results


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harness_sha() -> str:
    """Return the harness's git short SHA, walking up from this file to find .git.

    Walks up from cae/site.py looking for the nearest .git directory so this
    works regardless of how many levels deep site.py is nested (e.g. in a
    pip-installed package or in a source tree). Falls back to "unknown" if
    no .git is found.
    """
    import subprocess
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".git").exists():
            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, check=True, cwd=p,
                )
                return proc.stdout.strip()
            except Exception:
                return "unknown"
        p = p.parent
    return "unknown"


def _fmt_cost(v):
    return f"${v:.2f}" if v is not None else "$?"


def _fmt_dur(v):
    return f"{v:.0f}s" if v is not None else "?"


def _fmt_int(v):
    return f"{v:.0f}" if v is not None else "?"


def _fmt_tokens_with_cache(r: dict) -> str:
    """Show median input+output tokens, with cache share appended when known.

    Example: ``250k (60% cached)`` or ``250k``.
    """
    in_t = r.get("median_tokens_in") or 0
    out_t = r.get("median_tokens_out") or 0
    cache_read = r.get("median_cache_read_tokens")
    total_input = (in_t or 0) + (cache_read or 0)
    if total_input and cache_read:
        pct = round(100 * cache_read / total_input)
        return f"{_fmt_int(in_t + out_t)} ({pct}% cached)"
    return _fmt_int(in_t + out_t)


def _index_html(rows: list[dict], harness_sha: str) -> str:
    rows_html = "\n".join(
        f"<tr><td>{html.escape(r['agent'])}</td>"
        f"<td>{html.escape(str(r['model'] or ''))}</td>"
        f"<td>{r['pass_rate']*100:.0f}%</td>"
        f"<td>{r['n_attempted']}</td>"
        f"<td>{r.get('n_skipped_harness', 0)}</td>"
        f"<td>{_fmt_cost(r['median_cost_usd'])}</td>"
        f"<td>{_fmt_dur(r.get('median_duration_sec'))}</td>"
        f"<td>{_fmt_tokens_with_cache(r)}</td>"
        f"<td>{r['last_run']}</td></tr>"
        for r in rows
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>cae leaderboard</title>
<style>
body {{ font: 14px/1.4 system-ui, sans-serif; max-width: 1200px; margin: 2em auto; padding: 0 1em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #f5f5f5; cursor: pointer; }}
tr:hover {{ background: #fafafa; }}
footer {{ margin-top: 2em; color: #888; font-size: 12px; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #1a1a1a; color: #ddd; }}
  th {{ background: #2a2a2a; }}
  tr:hover {{ background: #222; }}
  th, td {{ border-color: #333; }}
}}
</style></head><body>
<h1>cae leaderboard</h1>
<p>Public, reproducible benchmark of CLI coding agents on SWE-bench Verified.</p>
<table id="lb">
<thead><tr>
  <th>Agent</th><th>Model</th><th>Pass rate</th><th># tasks</th><th>Skipped</th>
  <th>Median cost</th><th>Median time</th><th>Median tokens (in+out, % cached)</th>
  <th>Last run</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
<footer>Built {_now_iso()} with harness <code>{html.escape(harness_sha)}</code> &middot; <a href="reproducibility.html">reproducibility</a></footer>
<script>
// minimal sort: click any th to sort the table by that column
document.querySelectorAll('th').forEach((th, i) => {{
  th.addEventListener('click', () => {{
    const tbody = document.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
    th.dataset.dir = dir;
    rows.sort((a, b) => (dir === 'asc' ? 1 : -1) * a.cells[i].textContent.localeCompare(b.cells[i].textContent, undefined, {{numeric: true}}));
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body></html>"""


def _task_html(task_id: str, results: list[dict]) -> str:
    # Pull the prompt from the first result that has one (it's the same
    # across all results for a task).
    prompt = ""
    for r in results:
        if r.get("prompt"):
            prompt = r["prompt"]
            break

    sections = []
    for r in results:
        # Defensive: `usage` may be missing or null in some result JSONs.
        usage = r.get("usage") or {}
        cost = usage.get("cost_usd")
        cache_read = usage.get("cache_read_tokens")
        cache_creation = usage.get("cache_creation_tokens")
        cache_info = ""
        if cache_read or cache_creation:
            parts = []
            if cache_creation:
                parts.append(f"{cache_creation:,} cache write")
            if cache_read:
                parts.append(f"{cache_read:,} cache read")
            cache_info = f" &middot; {', '.join(parts)}"

        # For non-resolved statuses, surface the error message — it's the
        # primary signal for diagnosing task_error / agent_error / timeout.
        # Show the first 500 chars inline; the full message is one click
        # away in a <details> block.
        error_block = ""
        if r.get("status") != "resolved" and r.get("error"):
            full_error = r["error"]
            preview = full_error[:500]
            extra = full_error[500:]
            if extra:
                error_block = (
                    f'<p><strong>Error:</strong> <code>{html.escape(preview)}'
                    f'<a href="#" onclick="this.parentNode.querySelector(\'details\').open=true;return false">…</a>'
                    f'</code></p>'
                    f'<details><summary>Full error</summary>'
                    f'<pre><code>{html.escape(full_error)}</code></pre></details>'
                )
            else:
                error_block = (
                    f'<p><strong>Error:</strong> <code>{html.escape(full_error)}</code></p>'
                )

        # Test result tables (pre-flight + post-flight) make it easy to see
        # which tests were expected vs. observed without re-loading the JSON.
        test_block = ""
        tr = r.get("test_results") or {}
        if tr:
            rows = []
            for kind in ("fail_to_pass", "pass_to_pass"):
                for name, status in (tr.get("pre_flight", {}).get(kind) or {}).items():
                    post = (tr.get("post_flight", {}).get(kind) or {}).get(name, "?")
                    rows.append(
                        f"<tr><td>{html.escape(kind)}</td>"
                        f"<td><code>{html.escape(name)}</code></td>"
                        f"<td>{html.escape(status)}</td>"
                        f"<td>{html.escape(post)}</td></tr>"
                    )
            if rows:
                test_block = (
                    "<h4>Test results</h4>"
                    "<table><thead><tr><th>Bucket</th><th>Test</th>"
                    "<th>Pre-flight</th><th>Post-flight</th></tr></thead>"
                    f"<tbody>{''.join(rows)}</tbody></table>"
                )

        # Patch is the agent's actual diff. Wrap in a language-diff class
        # so a future highlight.js integration can pick it up automatically.
        patch = r.get("patch", "") or ""
        patch_block = (
            f'<h4>Patch</h4><pre><code class="language-diff">'
            f'{html.escape(patch)}</code></pre>'
            if patch else ""
        )

        sections.append(f"""<details open>
<summary><strong>{html.escape(r['agent'])}</strong> — {html.escape(r['status'])}</summary>
<p>Model: <code>{html.escape(str(r.get('model') or ''))}</code> &middot;
   Version: <code>{html.escape(str(r.get('agent_version') or ''))}</code> &middot;
   Duration: {r.get('duration_sec', 0):.0f}s &middot;
   Cost: {_fmt_cost(cost)}{cache_info}</p>
{error_block}
{test_block}
{patch_block}
</details>""")
    prompt_block = (
        f'<h2>Prompt</h2><pre>{html.escape(prompt)}</pre>'
        if prompt else ""
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(task_id)}</title>
<style>body{{font:14px/1.4 system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}}
pre{{background:#f5f5f5;padding:1em;overflow-x:auto}}
table{{border-collapse:collapse;margin:1em 0;width:100%;font-size:13px}}
th,td{{padding:4px 8px;text-align:left;border-bottom:1px solid #ddd}}
th{{background:#f5f5f5}}
code{{background:#f0f0f0;padding:1px 4px;border-radius:3px;font-size:90%}}
@media(prefers-color-scheme:dark){{
  body{{background:#1a1a1a;color:#ddd}}
  pre{{background:#222}}
  th{{background:#2a2a2a}}
  th,td{{border-color:#333}}
  code{{background:#2a2a2a;color:#ddd}}
}}
</style></head><body>
<h1>{html.escape(task_id)}</h1>
<p><a href="../index.html">back to leaderboard</a></p>
{prompt_block}
{''.join(sections)}
</body></html>"""


def build_site(results_dir: Path, out_dir: Path, docs_dir: Path | None = None) -> None:
    """Generate the static site under out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(exist_ok=True)
    (out_dir / "tasks").mkdir(exist_ok=True)

    # 1. Aggregate and write data/results.json
    rows = aggregate_results(results_dir)
    (out_dir / "data" / "results.json").write_text(json.dumps(rows, indent=2, default=str))

    # 2. index.html
    (out_dir / "index.html").write_text(_index_html(rows, _harness_sha()))

    # 3. Per-task pages
    by_task: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(results_dir.glob("*.json")):
        data = json.loads(f.read_text())
        if data.get("agent") == "mock":
            continue
        by_task[data["task_id"]].append(data)
    for task_id, results in by_task.items():
        (out_dir / "tasks" / f"{task_id}.html").write_text(_task_html(task_id, results))

    # 4. Per-run detail JSONs (consumed by the per-task pages or external tools)
    details_dir = out_dir / "data" / "details"
    details_dir.mkdir(exist_ok=True)
    for f in sorted(results_dir.glob("*.json")):
        data = json.loads(f.read_text())
        if data.get("agent") == "mock":
            continue
        out_name = f"{data['task_id']}__{data['agent']}.json"
        (details_dir / out_name).write_text(json.dumps(data, indent=2, default=str))

    # 4. Reproducibility doc (if source present)
    if docs_dir and (docs_dir / "reproducibility.md").exists():
        from cae.render_markdown import render_markdown
        md = (docs_dir / "reproducibility.md").read_text()
        (out_dir / "reproducibility.html").write_text(render_markdown(md))
