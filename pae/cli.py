"""Command-line interface for pae."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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


def cmd_add_task(args: argparse.Namespace) -> int:
    if not args.from_swebench:
        print("error: only --from-swebench is supported in v1", file=sys.stderr)
        return 2
    from pae.importer import import_swebench_instance, load_swebench_records
    records = list(load_swebench_records(
        instance_ids=args.instance_id or None,
        split=args.split,
        limit=args.limit,
        dataset_path=args.dataset_path,
    ))
    for rec in records:
        import_swebench_instance(
            rec, tasks_dir=Path(args.tasks_dir),
            fetch_repo=not args.no_fetch_repo, split=args.split,
        )
        print(f"imported {rec.instance_id}")
    return 0


def cmd_list_agents(args: argparse.Namespace) -> int:
    from pae.agents import list_adapters
    rows = list_adapters()
    print(f"{'NAME':<20} AVAILABLE")
    for r in rows:
        print(f"{r['name']:<20} {r['available']}")
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

    p_add = sub.add_parser("add-task", help="add a new task under tasks/")
    p_add.add_argument("--from-swebench", action="store_true",
                      help="import from SWE-bench (default split: verified)")
    p_add.add_argument("--split", default="test", help="SWE-bench split (default: test)")
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
