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
- `.git/`
- User / system config under `.claude/` — `settings.json`, `settings.local.json`, `commands/`, `skills/`, `agents/`, `hooks/`, `plugins/`. (Exception: this skill's own artifacts at `.claude/self-improve-state.md`, `.claude/self-improve-state.md.tmp`, and `.claude/worktrees/` are managed by the workflow itself.)
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
