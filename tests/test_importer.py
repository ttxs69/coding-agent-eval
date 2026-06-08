import json
from pathlib import Path

import pytest

from cae.importer import (
    _narrow_test_cmd,
    import_swebench_instance,
    SWEbenchRecord,
)


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


# ---- test_cmd narrowing --------------------------------------------------

def test_narrow_test_cmd_drops_x_and_scopes_to_files():
    out = _narrow_test_cmd(
        "python -m pytest -xvs",
        [
            "astropy/foo/test_x.py::test_a[1]",
            "astropy/foo/test_x.py::test_b",
            "astropy/bar/test_y.py::test_c",
        ],
    )
    assert out == "python -m pytest -vs astropy/foo/test_x.py astropy/bar/test_y.py"
    assert "-x" not in out


def test_narrow_test_cmd_passthrough_for_non_pytest():
    # cargo test doesn't use pytest node IDs, leave it alone.
    out = _narrow_test_cmd("cargo test", ["a.py::t"])
    assert out == "cargo test"


def test_narrow_test_cmd_passthrough_when_no_nodeids():
    # No `::` in test IDs → can't extract files → leave cmd alone.
    out = _narrow_test_cmd("python -m pytest -xvs", ["no_underscores", "just_words"])
    assert out == "python -m pytest -xvs"


def test_narrow_test_cmd_dedupes_files():
    out = _narrow_test_cmd(
        "python -m pytest -xvs",
        ["a/test.py::t1", "a/test.py::t2", "b/test.py::t3"],
    )
    # Each file only once.
    assert out == "python -m pytest -vs a/test.py b/test.py"


def test_import_astropy_setup_cmd_uses_test_extras(tmp_path):
    """astropy's test suite needs [test] extras (hypothesis, pytest-astropy)."""
    rec = SWEbenchRecord(
        instance_id="astropy__astropy-1",
        repo="astropy/astropy",
        base_commit="abc",
        prompt="x", test_patch="",
        fail_to_pass=["astropy/foo/tests/test_x.py::test_a"],
        pass_to_pass=[],
    )
    import_swebench_instance(rec, tasks_dir=tmp_path, fetch_repo=False)
    data = json.loads((tmp_path / "astropy__astropy-1" / "task.json").read_text())
    assert "[test]" in data["setup_cmd"]


def test_import_test_cmd_drops_x_and_narrows_to_files(tmp_path):
    """Generated test_cmd should not have -x and should be narrowed."""
    rec = SWEbenchRecord(
        instance_id="django__django-1",
        repo="django/django",
        base_commit="abc",
        prompt="x", test_patch="",
        fail_to_pass=["tests/test_x.py::test_y"],
        pass_to_pass=["tests/test_x.py::test_z", "tests/test_w.py::test_q"],
    )
    import_swebench_instance(rec, tasks_dir=tmp_path, fetch_repo=False)
    data = json.loads((tmp_path / "django__django-1" / "task.json").read_text())
    assert "-x" not in data["test_cmd"]
    assert "tests/test_x.py" in data["test_cmd"]
    assert "tests/test_w.py" in data["test_cmd"]


# ---- FAIL_TO_PASS deserialization ---------------------------------------

def test_load_swebench_records_deserializes_json_lists(monkeypatch):
    """SWE-bench stores FAIL_TO_PASS/PASS_TO_PASS as JSON-encoded strings;
    load_swebench_records must yield them as actual lists."""
    from cae.importer import load_swebench_records

    fake_row = {
        "instance_id": "x__x-1",
        "repo": "x/x",
        "base_commit": "abc",
        "problem_statement": "p",
        "test_patch": "",
        "FAIL_TO_PASS": json.dumps(["a.py::t1", "a.py::t2"]),
        "PASS_TO_PASS": json.dumps(["a.py::t3"]),
    }

    class FakeDataset(list):
        def filter(self, fn):
            return FakeDataset([r for r in self if fn(r)])
        def select(self, indices):
            return FakeDataset([self[i] for i in indices])

    # `load_dataset` is imported inside the function, so patch it where
    # it's looked up: the `datasets` module.
    import datasets
    monkeypatch.setattr(
        datasets, "load_dataset", lambda *a, **kw: FakeDataset([fake_row]),
    )
    records = list(load_swebench_records(split="test", limit=1))
    assert records[0].fail_to_pass == ["a.py::t1", "a.py::t2"]
    assert records[0].pass_to_pass == ["a.py::t3"]

