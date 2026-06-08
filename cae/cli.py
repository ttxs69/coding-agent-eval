"""Command-line interface for cae."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_run(args: argparse.Namespace) -> int:
    from cae.harness import run
    task_path = Path(args.tasks_dir) / args.task
    if not (task_path / "task.json").exists():
        print(f"error: task {args.task!r} not found at {task_path}", file=sys.stderr)
        return 2

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    # Read the instance_id from task.json so the result-file glob matches by
    # the actual id used in the filename (not the directory name on disk).
    instance_id = json.loads((task_path / "task.json").read_text())["instance_id"]

    # Resume: per (task, agent, repeat-index), skip if a result file already exists.
    # With --repeat N, all N indices must be missing for the pair to fully run.
    workdir = None
    if args.workdir:
        workdir = Path(args.workdir)
    repeat = max(1, args.repeat)
    for i in range(1, repeat + 1):
        repeat_index = i if repeat > 1 else None
        suffix = f"__{i}" if repeat_index is not None else ""
        out_pattern = f"*__{args.agent}__{instance_id}{suffix}.json"
        existing = list(results_dir.glob(out_pattern))
        if existing and not args.force:
            print(f"skipping {out_pattern}: {len(existing)} existing result(s). Use --force to overwrite.")
            continue
        result = run(
            task_path=task_path,
            agent_name=args.agent,
            workdir=workdir,
            timeout_sec=args.timeout * 60,
            fetch_fresh=args.fetch_fresh,
            keep_workdir=args.keep_workdir,
            docker=args.docker,
            docker_image=args.docker_image,
            env_file=Path(args.env_file) if args.env_file else None,
            docker_network=args.docker_network,
            docker_extra_mounts=[tuple(m.split(":", 1)) for m in args.docker_mount.split(",")] if args.docker_mount else None,
            model=args.model,
            repeat=repeat,
            repeat_index=repeat_index,
        )
        out = results_dir / f"{result['run_id']}.json"
        out.write_text(json.dumps(result, indent=2, default=str))
        print(f"wrote {out}")
        print(f"status: {result['status']}")
    return 0


def cmd_add_task(args: argparse.Namespace) -> int:
    if not args.from_swebench:
        print("error: only --from-swebench is supported in v1", file=sys.stderr)
        return 2
    from cae.importer import (
        import_swebench_instance,
        load_swebench_records,
        MalformedTestIdsError,
    )
    records = list(load_swebench_records(
        instance_ids=args.instance_id or None,
        split=args.split,
        limit=args.limit,
        dataset_path=args.dataset_path,
    ))
    n_imported = 0
    n_skipped = 0
    for rec in records:
        try:
            import_swebench_instance(
                rec, tasks_dir=Path(args.tasks_dir),
                fetch_repo=not args.no_fetch_repo, split=args.split,
            )
        except MalformedTestIdsError as e:
            print(f"skipped {rec.instance_id}: {e}", file=sys.stderr)
            n_skipped += 1
            continue
        print(f"imported {rec.instance_id}")
        n_imported += 1
    if n_skipped:
        print(f"imported {n_imported}, skipped {n_skipped} (malformed test IDs in SWE-bench data)",
              file=sys.stderr)
    return 0


def cmd_list_agents(args: argparse.Namespace) -> int:
    from cae.agents import list_adapters
    rows = list_adapters()
    print(f"{'NAME':<20} AVAILABLE")
    for r in rows:
        print(f"{r['name']:<20} {r['available']}")
    return 0


def cmd_list_tasks(args: argparse.Namespace) -> int:
    """List every task under tasks-dir, with status counts from results-dir."""
    from pathlib import Path
    import json
    from collections import Counter

    tasks_dir = Path(args.tasks_dir)
    if not tasks_dir.is_dir():
        print(f"error: tasks dir not found: {tasks_dir}", file=sys.stderr)
        return 2

    results_dir = Path(args.results_dir) if args.results_dir else None
    # status[instance_id] = Counter of statuses across all (agent) results
    statuses: dict[str, Counter] = {}
    if results_dir and results_dir.is_dir():
        for f in sorted(results_dir.glob("*.json")):
            d = json.loads(f.read_text())
            if d.get("agent") == "mock":
                continue
            statuses.setdefault(d["task_id"], Counter())[d["status"]] += 1

    tasks = sorted(t for t in tasks_dir.iterdir() if t.is_dir())
    if not tasks:
        print(f"(no tasks under {tasks_dir})")
        return 0

    print(f"{'INSTANCE_ID':<40} {'REPO':<25} STATUSES")
    for t in tasks:
        try:
            data = json.loads((t / "task.json").read_text())
            instance_id = data.get("instance_id", t.name)
            repo = data.get("repo", "?")
        except Exception:
            instance_id, repo = t.name, "?"
        s = statuses.get(instance_id)
        if s:
            summary = ", ".join(f"{k}:{v}" for k, v in sorted(s.items()))
        else:
            summary = "(no results)"
        print(f"{instance_id:<40} {repo:<25} {summary}")
    return 0


def cmd_build_site(args: argparse.Namespace) -> int:
    from cae.site import build_site
    build_site(
        results_dir=Path(args.results_dir),
        out_dir=Path(args.out_dir),
        docs_dir=Path(args.docs_dir) if args.docs_dir else None,
    )
    print(f"wrote site to {args.out_dir}")
    if args.publish:
        return _publish_site(Path(args.out_dir))
    return 0


def _publish_site(out_dir: Path) -> int:
    """Deploy the built site to GitHub Pages via the `gh` CLI.

    Pushes the contents of `out_dir` to a `gh-pages` branch using `git subtree`
    (works without any extra setup) and then uses `gh` to enable Pages on
    that branch. Returns 0 on success, non-zero on any failure.
    """
    import shutil
    import subprocess

    gh = shutil.which("gh")
    if gh is None:
        print("error: --publish requires the `gh` CLI on PATH", file=sys.stderr)
        return 2

    if not (out_dir / "index.html").exists():
        print(f"error: {out_dir} does not look like a built site (no index.html)", file=sys.stderr)
        return 2

    # Use git subtree push to publish out_dir to gh-pages branch.
    result = subprocess.run(
        ["git", "subtree", "push", "--prefix", str(out_dir), "origin", "gh-pages"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"error: git subtree push failed: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode

    # Enable Pages on the gh-pages branch if not already.
    subprocess.run(
        [gh, "repo", "edit", "--enable-pages", "--pages-source", "gh-pages"],
        capture_output=True, text=True,
    )
    print(f"published {out_dir} to gh-pages branch")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from cae.metrics import aggregate_results
    from cae.render_table import render_table
    rows = aggregate_results(Path(args.results_dir))
    if args.format == "table":
        headers = ["AGENT", "MODEL", "PASS RATE", "N", "SKIPPED", "MEDIAN COST", "MEDIAN DUR (s)", "LAST RUN"]
        def fmt_cost(v):
            return f"${v:.2f}" if v is not None else "$?"
        def fmt_dur(v):
            return f"{v:.0f}" if v is not None else "?"
        out_rows = [
            [r["agent"], str(r["model"] or ""),
             f"{r['pass_rate']*100:.0f}%", str(r["n_attempted"]),
             str(r.get("n_skipped_harness", 0)),
             fmt_cost(r["median_cost_usd"]), fmt_dur(r["median_duration_sec"]),
             r["last_run"]]
            for r in rows
        ]
        print(render_table(headers, out_rows))
    else:
        import json
        print(json.dumps(rows, indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cae",
        description="Evaluate CLI coding agents on SWE-bench tasks.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", required=False)

    p_run = sub.add_parser("run", help="run an agent on a single task")
    p_run.add_argument("--agent", required=True)
    p_run.add_argument("--task", required=True)
    p_run.add_argument("--tasks-dir", default="tasks")
    p_run.add_argument("--results-dir", default="results")
    p_run.add_argument("--timeout", type=int, default=30, help="per-stage timeout in minutes")
    p_run.add_argument("--workdir", default=None, help="pre-populated workdir (skips fetch)")
    p_run.add_argument("--fetch-fresh", action="store_true",
                      help="clone the repo from GitHub at base_commit instead of copying from tasks/<id>/repo/")
    p_run.add_argument("--keep-workdir", action="store_true", help="don't delete the workdir after the run")
    p_run.add_argument("--force", action="store_true", help="overwrite existing result files for this (task, agent) pair")
    p_run.add_argument("--repeat", type=int, default=1, help="run this many times (default: 1)")
    p_run.add_argument("--docker", action="store_true", help="run inside a Docker container")
    p_run.add_argument("--docker-image", default="python:3.11-slim",
                      help="base image for --docker mode (default: python:3.11-slim)")
    p_run.add_argument("--env-file", default=None,
                      help="file with KEY=VALUE lines, passed to `docker run --env-file` (for API keys)")
    p_run.add_argument("--docker-network", default="bridge",
                      help="docker network mode (default: bridge). Use 'host' to give container access to host's localhost (e.g. for local LLM proxies).")
    p_run.add_argument("--docker-mount", default=None,
                      help="comma-separated host_path:container_path pairs to bind-mount read-write, e.g. '~/.codex:/home/cae/.codex,~/.claude:/home/cae/.claude'. Used for agent auth dirs.")
    p_run.add_argument("--model", default=None,
                      help="model name to pass to the agent (e.g. 'claude-sonnet-4-6', 'gpt-5'). "
                           "Overrides whatever the agent's config file / env var would otherwise pick. "
                           "When omitted, the agent uses its configured default.")
    p_run.set_defaults(func=cmd_run)

    p_add = sub.add_parser("add-task", help="add a new task under tasks/")
    p_add.add_argument("--from-swebench", action="store_true",
                      help="import from SWE-bench (default split: verified)")
    p_add.add_argument("--split", default="test",
                      help="SWE-bench split (default: test). Note: for the SWE-bench_Verified dataset, the only split is 'test' — the 'verified' in the dataset name is not a split.")
    p_add.add_argument("--limit", type=int, default=None, help="import at most N instances")
    p_add.add_argument("--instance-id", action="append", default=[],
                      help="specific instance_id to import (repeatable)")
    p_add.add_argument("--dataset-path", default=None,
                      help="path to a local SWE-bench dataset clone (for offline use)")
    p_add.add_argument("--no-fetch-repo", action="store_true",
                      help="skip the git clone (faster import for tests)")
    p_add.add_argument("--tasks-dir", default="tasks", help="where to write tasks (default: tasks)")
    p_add.set_defaults(func=cmd_add_task)

    p_la = sub.add_parser("list-agents", help="list registered agent adapters and availability")
    p_la.set_defaults(func=cmd_list_agents)

    p_lt = sub.add_parser("list-tasks", help="list every task under tasks-dir, with status counts from results-dir")
    p_lt.add_argument("--tasks-dir", default="tasks", help="where to look for tasks (default: tasks)")
    p_lt.add_argument("--results-dir", default="results", help="where to look for result JSONs (default: results)")
    p_lt.set_defaults(func=cmd_list_tasks)

    p_rep = sub.add_parser("report", help="aggregate and display results")
    p_rep.add_argument("--results-dir", default="results", help="where to read result JSONs (default: results)")
    p_rep.add_argument("--format", default="table", choices=["table", "json"], help="output format (default: table)")
    p_rep.set_defaults(func=cmd_report)

    p_bs = sub.add_parser("build-site", help="build the static leaderboard site")
    p_bs.add_argument("--results-dir", default="results", help="where to read result JSONs")
    p_bs.add_argument("--out-dir", default="site", help="where to write the site (default: site)")
    p_bs.add_argument("--docs-dir", default="docs", help="where to find docs (for reproducibility.html)")
    p_bs.add_argument("--publish", action="store_true", help="also push via `gh` CLI (requires `gh` on PATH)")
    p_bs.set_defaults(func=cmd_build_site)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from cae import __version__
        print(__version__)
        return 0
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
