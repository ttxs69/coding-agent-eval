import json
from pathlib import Path

import pytest

from cae.importer import import_swebench_instance, SWEbenchRecord


@pytest.fixture
def sample_record() -> SWEbenchRecord:
    return SWEbenchRecord(
        instance_id="django__django-12345",
        repo="django/django",
        base_commit="abc1234",
        prompt="Issue: something is broken",
        test_patch="diff --git a/tests/test_x.py b/tests/test_x.py\n+new test",
        fail_to_pass=["tests/test_x.py::test_y"],
        pass_to_pass=["tests/test_x.py::test_z"],
    )


def test_import_writes_task_json(tmp_path, sample_record):
    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=False)
    out = tmp_path / "django__django-12345" / "task.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["instance_id"] == "django__django-12345"
    assert data["repo"] == "django/django"
    assert data["base_commit"] == "abc1234"
    assert data["fail_to_pass"] == ["tests/test_x.py::test_y"]
    assert data["prompt"] == "Issue: something is broken"
    assert data["source"]["kind"] == "swe-bench"
    assert data["source"]["split"] == "verified"
    assert data["source"]["original_id"] == "django__django-12345"
    # swe_bench_commit may be a real SHA (HF available) or "unknown" (no network)
    assert "swe_bench_commit" in data["source"]


def test_import_writes_test_patch(tmp_path, sample_record):
    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=False)
    out = tmp_path / "django__django-12345" / "tests.patch"
    assert out.exists()
    assert "new test" in out.read_text()


def test_import_fetches_repo_into_repo_dir(tmp_path, sample_record):
    """When fetch_repo is True and a fetcher is provided, the repo state is populated."""
    def fake_fetcher(repo: str, base_commit: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README").write_text(f"fake clone of {repo} at {base_commit}")

    import_swebench_instance(sample_record, tasks_dir=tmp_path, fetch_repo=True, fetcher=fake_fetcher)
    repo_dir = tmp_path / "django__django-12345" / "repo"
    assert repo_dir.exists()
    assert "fake clone of django/django at abc1234" in (repo_dir / "README").read_text()
