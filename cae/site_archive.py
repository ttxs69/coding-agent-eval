"""Hydrate `cae build-site` from the gh-pages archive.

By default, `cae build-site` aggregates only from local ``results/``.
Over time, as evals are run on different machines and old result files
are cleaned up locally, the visible leaderboard shrinks even though the
per-task pages on ``gh-pages`` still link to historical runs.

This module lets ``cae build-site --include-archive`` pull every
``data/details/*.json`` ever published to ``gh-pages`` and merge it into
the aggregation pass — local results win on duplicate ``run_id``
(local is newer), archive-only entries fill in the historical gaps.

Failures are non-fatal: if the git fetch or archive extraction fails
(no ``gh-pages`` branch, no network, etc.), we return an empty dict
and the build falls through to local-only. Better to publish a partial
leaderboard than to crash the deploy.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _extract_archive_via_git(remote: str, branch: str, dest: Path) -> Path:
    """Run ``git archive <remote>/<branch> data/details`` and extract into
    ``dest``. Returns the path to the extracted ``data/details`` directory.

    Raises if the git command fails (caller is expected to handle this).
    """
    dest.mkdir(parents=True, exist_ok=True)
    # git archive writes a tar to stdout; pipe through tar -x to extract.
    # GitHub doesn't support --remote for archive, so fetch first then
    # archive from the local remote-tracking ref. Single shell pipe keeps
    # this to one subprocess.
    subprocess.run(["git", "fetch", remote, branch], check=True, capture_output=True)
    subprocess.run(
        f"git archive {remote}/{branch} data/details/ | tar -xC {dest}",
        shell=True, check=True,
    )
    extracted = dest / "data" / "details"
    if not extracted.is_dir():
        return dest  # caller globs; this is just a hint
    return extracted


def _fetch_archive_details(remote: str = "origin", branch: str = "gh-pages") -> dict[str, dict]:
    """Return ``{run_id: result_dict}`` for every detail JSON on
    ``<remote>/<branch>:data/details/``. Empty dict on any failure.

    Empty dict is the safe fallback: callers mix this with local results
    and an empty archive just means "no historical data merged in" —
    same as the flag being off.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="cae-archive-") as td:
            dest = Path(td)
            extracted = _extract_archive_via_git(remote, branch, dest)
            archive: dict[str, dict] = {}
            for f in extracted.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    run_id = data.get("run_id") or f.stem
                    archive[run_id] = data
                except Exception:
                    # Skip unreadable JSON — don't lose the whole archive
                    # over one malformed file.
                    continue
            return archive
    except Exception:
        return {}


def _merge_results(local_dir: Path, archive: dict[str, dict]) -> Path:
    """Return a temp directory containing every local ``*.json`` plus every
    archive entry whose ``run_id`` doesn't collide with a local file.

    Local wins on collision: the user just produced it (or re-ran with
    ``--force``), so it's newer than the historical version on gh-pages.

    The returned Path is a temp dir; the caller should not assume it
    outlives the Python process. ``build_site`` uses it immediately.
    """
    merged = Path(tempfile.mkdtemp(prefix="cae-merged-"))
    # Local first.
    for f in local_dir.glob("*.json"):
        shutil.copy2(f, merged / f.name)
    # Then archive entries — skip if a local file already has that run_id.
    # Match by run_id, not filename: archive filenames are the same shape
    # as local ones (<run_id>.json) but we want to be robust to renames.
    local_run_ids = set()
    for f in merged.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("run_id"):
                local_run_ids.add(data["run_id"])
        except Exception:
            continue
    for run_id, data in archive.items():
        if run_id in local_run_ids:
            continue
        out = merged / f"{run_id}.json"
        out.write_text(json.dumps(data, indent=2, default=str))
    return merged
