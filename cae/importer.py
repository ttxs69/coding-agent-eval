"""SWE-bench Verified importer: pulls task metadata and (optionally) the repo state.

The importer takes SWE-bench records (a flat dataclass) and writes a task
directory under tasks/. For v1 we use the HuggingFace `datasets` library to load
princeton-nlp/SWE-bench_Verified. The HF dataset is wrapped into our
SWEbenchRecord type so the rest of the importer is decoupled from the source.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class SWEbenchRecord:
    """A flat, source-decoupled view of one SWE-bench instance."""

    instance_id: str
    repo: str
    base_commit: str
    prompt: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]


# A fetcher takes (repo, base_commit, dest) and populates dest with the repo
# state at base_commit. Default implementation: git clone.
Fetcher = Callable[[str, str, Path], None]


# Per-repo setup/test commands for common SWE-bench Verified repos. The importer
# consults this table first; if a repo isn't listed, it falls back to the
# generic Python defaults below.
SWE_BENCH_REPO_DEFAULTS: dict[str, dict[str, str]] = {
    "django/django":       {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "pytest-dev/pytest":   {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "pallets/flask":       {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "psf/requests":        {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
    "scikit-learn/scikit-learn": {"setup_cmd": "pip install -e .",  "test_cmd": "python -m pytest -xvs"},
    "astropy/astropy":     {"setup_cmd": "pip install -e .",       "test_cmd": "python -m pytest -xvs"},
}

GENERIC_PYTHON_DEFAULTS = {"setup_cmd": "pip install -e .", "test_cmd": "python -m pytest -xvs"}


def default_fetcher(repo: str, base_commit: str, dest: Path) -> None:
    """Clone the repo at base_commit into dest. Requires `git` on PATH.

    Uses a fetch of a specific commit (not --depth=1) so the checkout succeeds
    for any base_commit, not just HEAD.
    """
    url = f"https://github.com/{repo}.git"
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "fetch", "--depth=1", "origin", base_commit], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "checkout", base_commit], cwd=dest, check=True, capture_output=True)


def import_swebench_instance(
    record: SWEbenchRecord,
    *,
    tasks_dir: Path,
    fetch_repo: bool = True,
    split: str = "verified",
    fetcher: Fetcher | None = None,
) -> Path:
    """Write one task under tasks_dir. Returns the task directory path."""
    task_dir = Path(tasks_dir) / record.instance_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # task.json — populate setup_cmd/test_cmd from the per-repo defaults table
    # (or the generic Python defaults if the repo isn't in the table).
    defaults = SWE_BENCH_REPO_DEFAULTS.get(record.repo, GENERIC_PYTHON_DEFAULTS)

    task_json = {
        "instance_id": record.instance_id,
        "repo": record.repo,
        "base_commit": record.base_commit,
        "prompt": record.prompt,
        "setup_cmd": defaults["setup_cmd"],
        "test_cmd": defaults["test_cmd"],
        "fail_to_pass": record.fail_to_pass,
        "pass_to_pass": record.pass_to_pass,
        "source": {
            "kind": "swe-bench",
            "split": split,
            "original_id": record.instance_id,
            "swe_bench_commit": get_swe_bench_dataset_version(),
        },
    }
    (task_dir / "task.json").write_text(json.dumps(task_json, indent=2))

    # tests.patch
    if record.test_patch:
        (task_dir / "tests.patch").write_text(record.test_patch)

    # repo/
    if fetch_repo:
        repo_dir = task_dir / "repo"
        repo_dir.mkdir(exist_ok=True)
        if (repo_dir / "README").exists() or any(repo_dir.iterdir()):
            import shutil
            shutil.rmtree(repo_dir)
        repo_dir.mkdir(exist_ok=True)
        (default_fetcher if fetcher is None else fetcher)(
            record.repo, record.base_commit, repo_dir
        )

    return task_dir


def load_swebench_records(
    *,
    instance_ids: list[str] | None = None,
    split: str = "test",
    limit: int | None = None,
    dataset_path: str | None = None,
) -> Iterable[SWEbenchRecord]:
    """Load records from the SWE-bench Verified dataset.

    Uses the HuggingFace `datasets` library. If `dataset_path` is given, loads
    from a local clone (e.g. for offline use); otherwise hits the hub.
    """
    if dataset_path:
        from datasets import load_from_disk
        ds = load_from_disk(dataset_path)
    else:
        from datasets import load_dataset
        ds = load_dataset("princeton-nlp/SWE-bench_Verified", split=split)
    if instance_ids:
        ds = ds.filter(lambda r: r["instance_id"] in set(instance_ids))
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    for row in ds:
        yield SWEbenchRecord(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            prompt=row["problem_statement"],
            test_patch=row["test_patch"],
            fail_to_pass=row["FAIL_TO_PASS"],
            pass_to_pass=row["PASS_TO_PASS"],
        )


_swe_bench_version_cache: str | None = None


def get_swe_bench_dataset_version() -> str:
    """Return the SWE-bench dataset's HuggingFace revision SHA (cached).

    Queried from huggingface_hub on first call; subsequent calls return the
    cached value. Falls back to "unknown" if the network is unavailable.
    """
    global _swe_bench_version_cache
    if _swe_bench_version_cache is not None:
        return _swe_bench_version_cache
    try:
        from huggingface_hub import HfApi
        info = HfApi().dataset_info("princeton-nlp/SWE-bench_Verified")
        sha = getattr(info, "sha", None) or "unknown"
    except Exception:
        sha = "unknown"
    _swe_bench_version_cache = sha
    return sha
