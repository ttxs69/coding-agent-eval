"""Command-line interface for pae."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _default_results_dir() -> Path:
    return Path("results")


def cmd_run(args: argparse.Namespace) -> int:
    from pae.harness import run
    task_path = Path(args.tasks_dir) / args.task
    if not (task_path / "task.json").exists():
        print(f"error: task {args.task!r} not found at {task_path}", file=sys.stderr)
        return 2
    result = run(task_path=task_path, agent_name=args.agent, timeout_sec=args.timeout * 60)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out = results_dir / f"{result['run_id']}.json"
    out.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {out}")
    print(f"status: {result['status']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pae",
        description="Evaluate CLI coding agents on SWE-bench tasks.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command", required=False)

    p_run = sub.add_parser("run", help="run an agent on a single task")
    p_run.add_argument("--agent", required=True, help="agent adapter name (e.g. mock, claude-code)")
    p_run.add_argument("--task", required=True, help="task instance_id under --tasks-dir")
    p_run.add_argument("--tasks-dir", default="tasks", help="directory containing task subdirs (default: tasks)")
    p_run.add_argument("--results-dir", default="results", help="where to write result JSON (default: results)")
    p_run.add_argument("--timeout", type=int, default=30, help="per-stage timeout in minutes (default: 30)")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        from pae import __version__
        print(__version__)
        return 0
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
