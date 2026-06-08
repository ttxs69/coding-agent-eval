# Adding Tasks

Two paths: import from SWE-bench or author by hand.

## Import from SWE-bench

```
cae add-task --from-swebench --limit 50
cae add-task --from-swebench --instance-id django__django-12345
```

The importer writes `tasks/<id>/task.json`, `tests.patch`, and `repo/` (a git checkout at `base_commit`).

## Author by hand

Create a directory under `tasks/<your_id>/`:

```
tasks/my_task/
├── task.json
└── repo/
    ├── main.py
    └── test_main.py
```

`task.json` schema:

```json
{
  "instance_id": "my_task",
  "repo": "my/repo",
  "base_commit": "0000000000000000000000000000000000000000",
  "prompt": "Description of the task the agent sees.",
  "setup_cmd": "pip install -e .",
  "test_cmd": "python -m pytest -v",
  "fail_to_pass": ["test_main.py::test_foo"],
  "pass_to_pass": ["test_main.py::test_bar"]
}
```

`base_commit` is required by the schema but for hand-authored tasks
(any 40-char hex string is fine — the harness doesn't actually `git
checkout` since `repo/` is shipped in-tree). SWE-bench imports use
the real upstream commit here.

`fail_to_pass` lists tests that fail before the agent runs and must pass after.
`pass_to_pass` lists tests that pass before and must still pass after.
No `tests.patch` is needed for hand-authored tasks; the test cases are already in `repo/`.
