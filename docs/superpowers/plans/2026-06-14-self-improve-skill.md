# Self-Improve Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a user-level Claude Code skill (`self-improve`) that autonomously scans any project for improvements and applies each as an isolated, verified, reviewed branch, then asks the user whether to merge.

**Architecture:** Skill is developed at `self-improve-skill/` in this repo (clearly separated from `cae/`). Installed to `~/.claude/skills/self-improve/` via symlink. Single `SKILL.md` for MVP (no `references/` split unless it exceeds 400 lines). Python static-check tests under `self-improve-skill/tests/`. Synthetic fixture project at `self-improve-skill/tests/fixtures/sample-project/` (its own git repo, initialized by the test setup) seeded with one issue per category.

**Tech Stack:** Markdown (SKILL.md), Python 3.10 + pytest (static checks, no new deps — frontmatter parsed with regex), Bash (install script), uv (test runner).

---

## File structure

```
self-improve-skill/                              # the deliverable (symlinked to ~/.claude/skills/)
├── SKILL.md                                     # the skill itself
├── README.md                                    # what it is, how to install
├── scripts/
│   └── install.sh                               # symlink to ~/.claude/skills/
└── tests/
    ├── test_static_checks.py                    # CI-able checks on SKILL.md
    ├── test_fixture_project.py                  # checks fixture is seeded correctly
    └── SMOKE_CHECKLIST.md                       # manual end-to-end checklist

tests/fixtures/self-improve-sample-project/      # NOT under self-improve-skill/ — spec §8.2
├── pyproject.toml                               # so it doesn't get symlinked into
├── README.md                                    # ~/.claude/skills/self-improve/tests/
├── src/sample/__init__.py                       # and pollute the user's installed skill
└── tests/test_sample.py
```

Two top-level locations: `self-improve-skill/` (the deliverable that gets installed) and `tests/fixtures/self-improve-sample-project/` (test fixture, lives in the repo's existing `tests/fixtures/` area alongside `tiny_task/`). The split keeps the fixture out of the installed skill per spec §8.2.

---

## Task 1: Scaffold `self-improve-skill/` + static-check tests (TDD)

**Files:**
- Create: `self-improve-skill/tests/test_static_checks.py`

- [ ] **Step 1: Write the failing tests**

Create `self-improve-skill/tests/test_static_checks.py`:

```python
"""Static checks for the self-improve skill.

Validate that SKILL.md is well-formed and triggerable. Run via:
    uv run pytest self-improve-skill/tests/test_static_checks.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse flat YAML frontmatter (between --- markers) as a dict.

    Handles only `key: value` lines; ignores list/multiline values.
    Sufficient for skill frontmatter, which is flat.
    """
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_skill_md_exists():
    assert SKILL_MD.is_file(), f"Missing: {SKILL_MD}"


def test_frontmatter_has_required_fields():
    fm = parse_frontmatter(SKILL_MD.read_text())
    assert "name" in fm, "frontmatter missing 'name'"
    assert "description" in fm, "frontmatter missing 'description'"


def test_name_is_self_improve():
    fm = parse_frontmatter(SKILL_MD.read_text())
    assert fm.get("name") == "self-improve", (
        f"name should be 'self-improve', got {fm.get('name')!r}"
    )


def test_description_contains_trigger_words():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for trigger in ("self-improve", "improve", "evolve"):
        assert trigger in desc, (
            f"description missing trigger word {trigger!r}: {desc!r}"
        )


def test_description_mentions_categories():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for category in ("bug", "test", "refactor"):
        assert category in desc, (
            f"description missing category {category!r}: {desc!r}"
        )


def test_references_exist():
    """All references/*.md paths mentioned in SKILL.md exist."""
    if not SKILL_MD.exists():
        return
    text = SKILL_MD.read_text()
    refs = re.findall(r"references/([a-z0-9_-]+\.md)", text)
    for ref in refs:
        ref_path = SKILL_DIR / "references" / ref
        assert ref_path.is_file(), f"Referenced file missing: {ref_path}"
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py -v`

Expected: ALL tests FAIL (no SKILL.md exists yet). `test_skill_md_exists` fails with `Missing: .../SKILL.md`; others fail because they try to read the missing file.

- [ ] **Step 3: Commit the failing tests**

```bash
git add self-improve-skill/tests/test_static_checks.py
git commit -m "test: add static-check scaffolding for self-improve skill

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Write minimal valid SKILL.md (passes static checks)

**Files:**
- Create: `self-improve-skill/SKILL.md`

- [ ] **Step 1: Write the minimal SKILL.md**

Create `self-improve-skill/SKILL.md` with this exact content:

```markdown
---
name: self-improve
description: Use when the user wants to autonomously improve a codebase. Scans for bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns. For each candidate, creates an isolated branch with verification + review, then asks the user whether to merge. Triggered by /self-improve or phrases like "improve this project", "self-evolve", "evolve", "auto-improve".
---

# Self-Improve

Full workflow content follows in Task 3.
```

- [ ] **Step 2: Run static checks, verify they pass**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py -v`

Expected: ALL tests PASS.

- [ ] **Step 3: Commit**

```bash
git add self-improve-skill/SKILL.md
git commit -m "feat(self-improve): minimal valid SKILL.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Expand SKILL.md to full content

**Files:**
- Modify: `self-improve-skill/SKILL.md` (replace the placeholder body with the full workflow)

- [ ] **Step 1: Replace the SKILL.md body with the full content**

Overwrite `self-improve-skill/SKILL.md` with this exact content:

````markdown
---
name: self-improve
description: Use when the user wants to autonomously improve a codebase. Scans for bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns. For each candidate, creates an isolated branch with verification + review, then asks the user whether to merge. Triggered by /self-improve or phrases like "improve this project", "self-evolve", "evolve", "auto-improve".
---

# Self-Improve

Autonomously scan a project for improvements and apply each as an isolated, verified, reviewed branch. Asks the user before merging anything.

## When to invoke

- User types `/self-improve`, `evolve`, `self-evolve`, `improve this project`, `auto-improve`, or similar phrases
- User asks for an autonomous code-improvement / bug-sweep / refactor pass

Do **not** invoke for:
- Single targeted edits — just do the edit directly
- Unscoped "make it better" requests when the user is unwilling to merge multiple branches
- Projects with uncommitted changes — refuse and ask the user to commit/stash first

## Auto-detection (run at workflow start)

Detect from project files; do **not** read CLAUDE.md for config:

- **Language/runtime**: `pyproject.toml` → Python+uv; `package.json` → Node; `Cargo.toml` → Rust; `go.mod` → Go
- **Test command**: derive from language (`uv run pytest`, `npm test`, `cargo test`, `go test ./...`). If none detected, the verify step skips test execution and candidates requiring test evidence are deprioritized
- **Linters/type-checkers**: detect from config (`ruff`/`mypy` from pyproject; `eslint`/`tsc` from package.json; `clippy` for Rust)
- **Default branch**: read via `git symbolic-ref refs/remotes/origin/HEAD`; fall back to `main`, then `master`. **Never hardcode** — used as merge target in step 8

## Per-run setup (once)

1. Read `.claude/self-improve-state.md` if it exists (missing → treat as empty)
2. Scan `git log` for already-merged `self-improve/*` branches as a backstop
3. Verify working tree is clean: if dirty, **refuse to start**, tell user to commit/stash

## Workflow (per-iteration loop)

Each iteration produces one branch and asks the user whether to merge. Loop until a stopping criterion fires.

### Step 1: Scan

Gather signals:
- Linter / type-checker output (run them, parse errors/warnings)
- Test failures (run the test command, capture which tests fail)
- `TODO` / `FIXME` / `HACK` / `XXX` comments (grep)
- Missing tests (coverage tool if available; else heuristic: public functions with no test references)
- Dead code (unused imports, unreferenced functions)
- Duplication / complexity hotspots
- Dependency freshness + known CVEs (read lockfile; check against registry if cheap)
- Docs gaps (public APIs without docstrings; missing README sections)
- Recent git churn (files changed in last N commits — regression-prone areas)
- Anything project-specific discovered at runtime

### Step 2: Pick next candidate

Filter out:
- Candidates matching the state file's *Attempted* or *Permanently Rejected* sections (match on category + files + idea similarity)
- Candidates matching already-merged `self-improve/*` branches in git log

Rank remaining by `impact × ease × low-risk`:
- **Impact order**: correctness → security → tests → perf → refactor → deps → docs
- **Ease**: cheaper/faster first
- **Risk**: lower-risk first (smaller diffs, more isolated changes)

Take the top candidate.

### Step 3: Isolate

Use `superpowers:using-git-worktrees`. Create:
- Worktree at `.claude/worktrees/<slug>`
- Branch `self-improve/<category>/<slug>-<ts>` (e.g., `self-improve/bug/pytest-parse-error-20260614-103045`)

### Step 4: Apply

Invoke the matching skill:
- Bug → `superpowers:systematic-debugging`
- Missing test / test-included fix → `superpowers:test-driven-development` (Red-Green-Refactor)
- Refactor → `superpowers:simplify` (or `superpowers:code-review --fix` if available)
- Docs / deps / perf → plain editing

### Step 5: Verify

Use `superpowers:verification-before-completion`:
- Run the affected tests
- Run the full test suite if cheap (under ~30s)
- Run linters/type-checkers
- **No claiming success without evidence** — paste the actual command output

If no test command detected (e.g., docs-only repo), skip test execution, rely on linters, and note in the state record.

### Step 6: Review

Use `superpowers:requesting-code-review` (or the project's `/code-review` skill if available).

If **neither** is available, do an inline self-review against this checklist:
- Correctness: does the change do what it claims?
- Regressions: could this break existing behavior?
- Scope creep: does the diff include unrelated changes?
- Security: any new attack surface?

Note in the state record that no formal review skill ran.

If review finds real issues: fix (one retry), then re-review. If still rejected, skip the candidate.

### Step 7: Commit

Use `superpowers:finishing-a-development-branch` for guidance. Commit to the branch with a conventional-commit message:

```
<type>(<scope>): <summary>

Self-improve: <category>

[body explaining the change]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Do **not** push.

### Step 8: Offer merge

Surface the branch with a one-line summary, then ask the user (use AskUserQuestion):

> Branch `self-improve/<category>/<slug>` ready.
> Change: <one-line summary>
>
> Merge to <default-branch> now, defer, or skip?

- `merge` → switch to the detected default branch, merge (fast-forward if possible, else `--no-ff`). **Do not push** without an explicit ask. After successful merge: delete the worktree and the merged branch.
- `defer` → leave branch and worktree in place, continue to next iteration. Surface again in end-of-run summary.
- `skip` → leave branch for manual review, delete the worktree (branch stays so the user can find it). Mark in state as "left for manual".

### Step 9: Record

Update `.claude/self-improve-state.md` (see format below):
- Append to *Attempted*: `<iso-ts> | <category> | <branch> | <status> | <summary>`
- If user said "never do this kind of change", move to *Permanently Rejected*

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-other`

### Step 10: Loop or stop

Check stopping criteria. If continuing, re-scan from step 1 (applying one improvement may surface or fix others).

## Stopping criteria

Any one triggers end-of-run:
1. No candidates found after scan
2. Max iterations reached — default **10** (configurable: `self-improve max=20`)
3. **3 consecutive failures** — counts as failure: `skipped-tests-failed`, `skipped-review-rejected` (after retry), `skipped-other` from apply-produces-no-change, worktree-creation-failed. `deferred` or `merged` resets the counter
4. Token budget hit — default **500K total** (configurable: `self-improve budget=1M`)
5. Wall-clock budget — default **30 min**
6. User interrupts (Ctrl-C / Escape)

## Error handling

| Failure | Action | State status |
|---|---|---|
| Working tree dirty at start | Refuse to start, tell user to commit/stash | (no entry) |
| Worktree creation fails | Log, skip candidate, continue | `skipped-other` |
| Apply produces no change | Log, skip, continue | `skipped-other` |
| Tests fail after apply | Revert worktree, continue | `skipped-tests-failed` |
| Review rejects (after one retry) | Leave worktree for inspection, continue | `skipped-review-rejected` |
| Merge conflict during merge step | Abort merge, leave branch for manual review | `deferred` |
| State file missing/corrupt | Warn, start fresh | (reset) |

**Interrupt handling:** On Ctrl-C / Escape, clean up current worktree (try/finally), write partial state, print summary of what was completed.

## Safety rails

**Never touch:**
- `.git/`, `.claude/`
- `node_modules/`, `.venv/`, `venv/`
- `__pycache__/`, `dist/`, `build/`
- Lockfiles (`uv.lock`, `package-lock.json`, `Cargo.lock`, `go.sum`) unless the candidate is explicitly a `deps` change

**No external-state mutations** — refuse to run:
- `npm publish`, `pip upload`, `cargo publish`
- `git push`, `git fetch` with rewrite
- `terraform apply`, `kubectl apply`, `docker push`
- Anything else that affects systems beyond the local repo

**Per-file change cap per run:** default 3 — if the same file has been edited 3 times this run, skip further candidates touching it.

**Worktree cleanup always runs** (try/finally), even on failure.

## State file format

Path: `.claude/self-improve-state.md` (gitignored by default — local automation state).

```markdown
# Self-Improve State

Tracks candidates the workflow has considered, so repeated runs don't redo work.
Safe to delete — workflow will recreate.

## Attempted

One line per attempt: `<iso-ts> | <category> | <branch> | <status> | <summary>`

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-other`

- 2026-06-14T10:15:22Z | bug | self-improve/bug/pytest-parse-error-20260614-101522 | merged | Fixed off-by-one in test nodeid parser (cae/parsers.py:42)

## Permanently Rejected

Format: `- <summary> — <reason>. Decided <date>.`

- Pin pytest to <8 — won't fix; conflicts with astropy-build extra. Decided 2026-06-13.
```

**Atomic writes:** write to `.claude/self-improve-state.md.tmp`, then atomic rename. Avoids corruption if interrupted mid-write.

**Same-candidate matching:** same file(s) + same category + semantically similar idea. Fuzzy by design — judge similarity from summary text and file list, not hash matching.

## End of run

Print a summary:

```
Self-improve run complete.
- Iterations: N
- Branches created: M (list names)
- Merged: X
- Deferred: Y (list names for review)
- Skipped: Z (with reasons)

Next steps:
- Review deferred branches: git checkout <branch>
- Re-run anytime: /self-improve
```

## Skills used

- `superpowers:using-git-worktrees` (step 3)
- `superpowers:systematic-debugging` (step 4, bugs)
- `superpowers:test-driven-development` (step 4, tests/fixes)
- `superpowers:simplify` (step 4, refactors)
- `superpowers:verification-before-completion` (step 5)
- `superpowers:requesting-code-review` (step 6)
- `superpowers:finishing-a-development-branch` (step 7)
````

- [ ] **Step 2: Run static checks, verify they pass**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py -v`

Expected: ALL tests PASS.

- [ ] **Step 3: Manual read-through**

Read `self-improve-skill/SKILL.md` end-to-end. Check for:
- Internal contradictions (e.g., wrong step numbers, conflicting rules)
- Missing pieces referenced elsewhere in the doc
- Tone consistency

Fix any issues inline.

- [ ] **Step 4: Run full project test suite (regression check)**

Run: `uv run pytest -v`

Expected: All previously passing tests still pass. New `test_static_checks.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add self-improve-skill/SKILL.md
git commit -m "feat(self-improve): full workflow content

Implements the spec at docs/superpowers/specs/2026-06-14-self-improve-skill-design.md:
scan → pick → isolate → apply → verify → review → commit → merge-ask → record → loop.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Write README.md

**Files:**
- Create: `self-improve-skill/README.md`

- [ ] **Step 1: Write README.md**

Create `self-improve-skill/README.md` with this exact content:

````markdown
# self-improve

A Claude Code skill that autonomously scans a project for improvements and applies each as an isolated, verified, reviewed branch — then asks the user whether to merge.

## What it does

When you invoke `/self-improve` (or say "evolve", "improve this project", etc.), the skill:

1. Scans for bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns
2. Picks the highest-impact candidate
3. Creates an isolated git worktree + branch
4. Applies the fix using the matching skill (systematic-debugging / TDD / simplify)
5. Verifies (tests + linters)
6. Reviews (code-review skill)
7. Commits to the branch
8. **Asks you whether to merge** — `merge` / `defer` / `skip`
9. Records the outcome in `.claude/self-improve-state.md`
10. Loops until stopped (no candidates / max 10 iter / 3 consecutive failures / 500K tokens / 30 min / interrupt)

## Install

```sh
sh self-improve-skill/scripts/install.sh
```

This symlinks `self-improve-skill/` to `~/.claude/skills/self-improve/`. Safe to re-run.

## Invoke

In any project, in a Claude Code session:

```
/self-improve
```

Or type: `evolve`, `improve this project`, `auto-improve`.

## What it won't do

- Touch `.git/`, `.claude/`, `node_modules/`, lockfiles (except `deps` candidates)
- Run external-state mutations (`git push`, `npm publish`, `terraform apply`, etc.)
- Start with a dirty working tree (it'll refuse and ask you to commit/stash)
- Push after merging (local-only by default)

## State

Per-project memory at `.claude/self-improve-state.md` (gitignored). Tracks attempted and permanently-rejected candidates so repeated runs don't redo work. Safe to delete — the skill recreates from scratch.

## Spec & plan

- Spec: `docs/superpowers/specs/2026-06-14-self-improve-skill-design.md`
- Plan: `docs/superpowers/plans/2026-06-14-self-improve-skill.md`
````

- [ ] **Step 2: Commit**

```bash
git add self-improve-skill/README.md
git commit -m "docs(self-improve): add README

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Write install script

**Files:**
- Create: `self-improve-skill/scripts/install.sh`

- [ ] **Step 1: Write install.sh**

Create `self-improve-skill/scripts/install.sh` with this exact content:

```sh
#!/usr/bin/env bash
# Install the self-improve skill by symlinking to ~/.claude/skills/.
# Safe to re-run.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${HOME}/.claude/skills/self-improve"

mkdir -p "${HOME}/.claude/skills"

if [[ -L "${TARGET}" ]]; then
    echo "Removing existing symlink at ${TARGET}"
    rm "${TARGET}"
elif [[ -e "${TARGET}" ]]; then
    echo "ERROR: ${TARGET} exists and is not a symlink." >&2
    echo "       Remove it manually first, then re-run." >&2
    exit 1
fi

ln -s "${SKILL_DIR}" "${TARGET}"
echo "Installed: ${TARGET} -> ${SKILL_DIR}"
echo "Invoke with: /self-improve"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x self-improve-skill/scripts/install.sh`

- [ ] **Step 3: Test install**

Run: `sh self-improve-skill/scripts/install.sh`

Expected output:
```
Installed: /Users/<user>/.claude/skills/self-improve -> /Users/sarace/dev/probe/agent_eval/self-improve-skill
Invoke with: /self-improve
```

- [ ] **Step 4: Verify the symlink resolves to a valid skill**

Run: `ls -la ~/.claude/skills/self-improve/SKILL.md`

Expected: a symlink listing showing `SKILL.md` exists at the target.

- [ ] **Step 5: Commit**

```bash
git add self-improve-skill/scripts/install.sh
git commit -m "feat(self-improve): add install script (symlink to ~/.claude/skills/)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Build fixture project skeleton

The fixture is a synthetic Python project with seeded issues the skill should find. Lives at `tests/fixtures/self-improve-sample-project/` (in the repo's existing `tests/fixtures/` area, NOT under `self-improve-skill/`) per spec §8.2 — so it doesn't get installed into `~/.claude/skills/self-improve/`.

**Files:**
- Create: `tests/fixtures/self-improve-sample-project/pyproject.toml`
- Create: `tests/fixtures/self-improve-sample-project/README.md`
- Create: `tests/fixtures/self-improve-sample-project/src/sample/__init__.py`
- Create: `tests/fixtures/self-improve-sample-project/tests/__init__.py`
- Create: `tests/fixtures/self-improve-sample-project/tests/test_sample.py`
- Create: `self-improve-skill/tests/test_fixture_project.py`

- [ ] **Step 1: Write pyproject.toml**

Create `tests/fixtures/self-improve-sample-project/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "sample"
version = "0.1.0"
description = "Fixture project for testing the self-improve skill."
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.4", "ruff>=0.1"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py310"
```

- [ ] **Step 2: Write README.md**

Create `tests/fixtures/self-improve-sample-project/README.md`:

```markdown
# sample

Fixture project for testing the self-improve skill. Contains intentionally seeded issues — see `self-improve-skill/tests/test_fixture_project.py` for the catalog.
```

- [ ] **Step 3: Write the package `__init__.py` with seeded issues**

Create `tests/fixtures/self-improve-sample-project/src/sample/__init__.py`:

```python
"""Sample package for self-improve skill testing.

This module intentionally contains seeded issues the self-improve skill
should detect. See self-improve-skill/tests/test_fixture_project.py for
the catalog.
"""


def add(a, b):
    # BUG: off-by-one — returns a - b + 1 instead of a + b
    return a - b + 1


def multiply(a, b):
    # No test exists for this function — missing-test candidate
    return a * b


# TODO(low priority): extract this into a shared helper. Both `sum_pair`
# and `product_pair` follow the same unpack-then-call pattern. (seeded
# refactor candidate — duplicate logic)
def sum_pair(pair):
    a, b = pair
    return add(a, b)


def product_pair(pair):
    a, b = pair
    return multiply(a, b)


def public_api_function(x):
    # Missing docstring on a public function (seeded docs-gap candidate)
    return x * 2
```

- [ ] **Step 4: Write the test file with one failing + one passing test**

Create `tests/fixtures/self-improve-sample-project/tests/__init__.py`:

```python
```

Create `tests/fixtures/self-improve-sample-project/tests/test_sample.py`:

```python
"""Tests for sample package.

test_add_basic exposes the seeded bug in `add()`. test_multiply_basic
passes — `multiply()` works correctly. The missing-test candidate is
`public_api_function`, which has no test in this file.
"""

from sample import add, multiply


def test_add_basic():
    # SEEDED BUG: add(2, 3) returns 0 (2 - 3 + 1) instead of 5
    assert add(2, 3) == 5


def test_multiply_basic():
    assert multiply(2, 3) == 6
```

- [ ] **Step 5: Write a fixture-validation test**

Create `self-improve-skill/tests/test_fixture_project.py`:

```python
"""Validate the fixture project is set up correctly.

These tests don't run the skill — they verify the fixture has the
seeded issues the skill is supposed to find. Run via:
    uv run pytest self-improve-skill/tests/test_fixture_project.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "self-improve-sample-project"
)
SRC = FIXTURE / "src" / "sample" / "__init__.py"


def _read_source() -> str:
    return SRC.read_text()


def test_fixture_has_seeded_bug():
    """add() contains the off-by-one (returns a - b + 1 instead of a + b)."""
    src = _read_source()
    assert "return a - b + 1" in src, "seeded bug missing from add()"


def test_fixture_has_seeded_missing_test_target():
    """public_api_function has no test (the missing-test candidate)."""
    test_file = (FIXTURE / "tests" / "test_sample.py").read_text()
    assert "public_api_function" not in test_file, (
        "public_api_function is supposed to be untested"
    )


def test_fixture_has_seeded_todo_comment():
    """A TODO comment exists (refactor/dedup candidate)."""
    src = _read_source()
    assert "TODO" in src, "seeded TODO missing"


def test_fixture_has_seeded_duplication():
    """sum_pair and product_pair both unpack a pair then call — duplication."""
    src = _read_source()
    assert "def sum_pair" in src and "def product_pair" in src


def test_fixture_has_seeded_missing_docstring():
    """public_api_function has no docstring (docs-gap candidate)."""
    src = _read_source()
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "def public_api_function" in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                body = lines[j].strip()
                if body and not body.startswith("#"):
                    assert not body.startswith('"""') and not body.startswith("'''"), (
                        f"public_api_function should have no docstring, found: {body}"
                    )
                    break
            return
    raise AssertionError("public_api_function not found in fixture source")


def test_fixture_test_command_fails_on_seeded_bug():
    """Running pytest in the fixture should fail (because of the seeded bug).

    This validates the fixture is set up correctly for the skill's
    verify step to detect failures.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "--tb=no", "-q"],
        cwd=FIXTURE,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"expected pytest to fail due to seeded bug, but it passed:\n{result.stdout}"
    )
```

- [ ] **Step 6: Run the fixture-validation tests**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py -v`

Expected: ALL tests PASS. If `test_fixture_test_command_fails_on_seeded_bug` fails, the fixture's pytest invocation didn't fail — check that the seeded bug is in place and `pip install -e .` was run inside the fixture (or `pytest` is invoked with `PYTHONPATH=src`).

If pytest can't find the `sample` package, run once inside the fixture:

```sh
cd tests/fixtures/self-improve-sample-project && pip install -e . && cd -
```

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/self-improve-sample-project/ self-improve-skill/tests/test_fixture_project.py
git commit -m "test(self-improve): add fixture project with seeded issues

Fixture has one bug, one missing-test target, one TODO, one duplication,
one missing docstring. Validates that the skill's scan step would find
these. Lives under tests/fixtures/ (not self-improve-skill/) per spec
§8.2 — keeps it out of the installed skill directory.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Document the manual smoke checklist

**Files:**
- Create: `self-improve-skill/tests/SMOKE_CHECKLIST.md`

- [ ] **Step 1: Write the smoke checklist**

Create `self-improve-skill/tests/SMOKE_CHECKLIST.md`:

```markdown
# Self-Improve Skill — Manual Smoke Checklist

Run this after `scripts/install.sh` to verify the skill works end-to-end.
Each item is a manual action — there's no way to automate "invoke skill in a real session".

## Setup

- [ ] Run `sh self-improve-skill/scripts/install.sh`
- [ ] Confirm `~/.claude/skills/self-improve/SKILL.md` exists
- [ ] Start a new Claude Code session in `tests/fixtures/self-improve-sample-project/`
- [ ] Initialize the fixture as a git repo: `git init && git add . && git commit -m initial`

## Invocation

- [ ] Type `/self-improve` — autocompletes or recognized as trigger
- [ ] Skill activates (Claude begins the scan phase)

## First run

- [ ] Scan phase runs: linter/test/TODO scan all execute
- [ ] Picks a candidate (likely the `add()` bug since it's a failing test = highest impact)
- [ ] Creates worktree at `.claude/worktrees/<slug>/`
- [ ] Creates branch `self-improve/bug/<slug>-<ts>`
- [ ] Applies the fix (changes `a - b + 1` → `a + b`)
- [ ] Runs tests in worktree — `test_add_basic` now passes
- [ ] Runs review (uses requesting-code-review or self-review fallback)
- [ ] Commits to branch
- [ ] **Asks the user**: merge / defer / skip

## Merge paths

- [ ] Choosing `merge`: switches to default branch, merges (FF if possible), deletes worktree + branch
- [ ] Choosing `defer`: branch + worktree stay, iteration continues, summary lists the deferred branch
- [ ] Choosing `skip`: branch stays, worktree deleted, marked in state as "left for manual"

## State file

- [ ] `.claude/self-improve-state.md` exists after first iteration
- [ ] Entry appended with correct format: `<ts> | <category> | <branch> | <status> | <summary>`
- [ ] File is gitignored (run `git status` — should not appear)

## Re-run

- [ ] Second `/self-improve` invocation: skips candidates matching state file entries
- [ ] Eventually exits with "no candidates found" or hits max iterations

## Interrupt

- [ ] Start a run, press Ctrl-C (or Escape) mid-iteration
- [ ] Worktree cleaned up
- [ ] Partial state written
- [ ] Summary of completed iterations printed

## Dirty tree

- [ ] Make an uncommitted change in the fixture
- [ ] Invoke `/self-improve`
- [ ] Verify it refuses with a clear "commit or stash first" message
```

- [ ] **Step 2: Commit**

```bash
git add self-improve-skill/tests/SMOKE_CHECKLIST.md
git commit -m "docs(self-improve): manual smoke checklist for first-install verification

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Update .gitignore for skill artifacts

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read current .gitignore**

Run: `cat .gitignore` to see what's there.

- [ ] **Step 2: Append skill-specific ignores if not already present**

If `.claude/self-improve-state.md` and `.claude/worktrees/` are not already ignored, append:

```
# self-improve skill runtime artifacts
.claude/self-improve-state.md
.claude/self-improve-state.md.tmp
.claude/worktrees/
```

Use the Edit tool to add at the end of `.gitignore`. If those patterns are already covered by a broader `.claude/` ignore, skip this step.

- [ ] **Step 3: Verify**

Run: `git check-ignore -v .claude/self-improve-state.md`

Expected: a line like `.gitignore:N:.claude/self-improve-state.md` showing which pattern matches. `git check-ignore` works on paths without the file existing.

If nothing is printed, the path isn't ignored — return to Step 2 and make sure the pattern is in `.gitignore`.

- [ ] **Step 4: Commit (if changed)**

```bash
git add .gitignore
git commit -m "chore: gitignore self-improve skill runtime artifacts

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

If no changes were needed, skip this step.

---

## Task 9: Final verification

- [ ] **Step 1: Run the project's test suite (cae tests)**

Run: `uv run pytest -v`

Expected: All pre-existing tests in `tests/` pass.

- [ ] **Step 2: Run the skill's tests (separate testpaths)**

Run: `uv run pytest self-improve-skill/tests/ -v`

Expected: ALL tests pass, including:
- `self-improve-skill/tests/test_static_checks.py`
- `self-improve-skill/tests/test_fixture_project.py`

(Note: `pyproject.toml` has `testpaths = ["tests"]`, so the skill's tests live in a separate path and must be invoked explicitly. This is intentional — keeps the skill's concerns separate from `cae`'s.)

- [ ] **Step 3: Run linter**

Run: `uv run ruff check self-improve-skill`

Expected: no issues.

- [ ] **Step 4: Verify file structure**

Run: `find self-improve-skill tests/fixtures/self-improve-sample-project -type f | sort`

Expected output (modulo `.pyc` etc.):
```
self-improve-skill/README.md
self-improve-skill/SKILL.md
self-improve-skill/scripts/install.sh
self-improve-skill/tests/SMOKE_CHECKLIST.md
self-improve-skill/tests/test_fixture_project.py
self-improve-skill/tests/test_static_checks.py
tests/fixtures/self-improve-sample-project/README.md
tests/fixtures/self-improve-sample-project/pyproject.toml
tests/fixtures/self-improve-sample-project/src/sample/__init__.py
tests/fixtures/self-improve-sample-project/tests/__init__.py
tests/fixtures/self-improve-sample-project/tests/test_sample.py
```

- [ ] **Step 5: Read SKILL.md end-to-end one more time**

Confirm: workflow makes sense, no contradictions, all referenced skills exist in the user's environment.

- [ ] **Step 6: No commit needed if all green.**

If anything failed, fix it. Otherwise, the implementation is complete.

---

## Self-review notes

**Spec coverage:**
- §1 (problem & purpose) → addressed by SKILL.md "When to invoke" + workflow
- §2 (why a skill) → addressed by deliverable being a skill
- §3 (architecture) → Task 1–2 (scaffold) + Task 5 (install)
- §4 (workflow) → Task 3 (full SKILL.md content covers all 10 steps)
- §5 (state file) → Task 3 (format embedded in SKILL.md)
- §6 (stopping & errors) → Task 3 (tables in SKILL.md)
- §7 (safety rails) → Task 3 (rails in SKILL.md)
- §8 (testing) → Tasks 1, 6, 7 (static checks, fixture, smoke checklist)
- §9 (open questions) → out of scope (deferred)
- §10 (out of scope) → respected (no PR creation, no CI integration, no multi-repo)

**Placeholders:** none. Every step shows the exact content to write.

**Type consistency:** branch naming `self-improve/<category>/<slug>-<ts>` used consistently. State file path `.claude/self-improve-state.md` consistent across SKILL.md and tests.

**Deferred to future work:**
- `references/` split-out (spec says only if SKILL.md > 400 lines; current is well under)
- Multi-language auto-detection beyond Python (spec covers this; current fixture is Python-only, which is fine for v1)
- Behavioral test scripting (spec §8.3 — manual checklist is the pragmatic first cut)
