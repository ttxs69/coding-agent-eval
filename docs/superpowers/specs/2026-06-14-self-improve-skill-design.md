# Self-Improve Skill — Design

**Date:** 2026-06-14
**Status:** Approved (pending spec review)
**Deliverable:** a user-level Claude Code skill (`~/.claude/skills/self-improve/`) that autonomously scans a project for improvements and applies each as an isolated, verified, reviewed branch — then asks the user whether to merge.

## 1. Problem & purpose

A "self-evolving" project would let the user invoke one command and have Claude systematically find and apply improvements: bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns. Each improvement should land as its own atomic branch (not a giant mixed PR), with verification and review built in, and a human merge gate before anything reaches `main`.

This needs to be **generic** — work on any project without project-specific configuration — and **on-demand** — not burning context on every conversation.

## 2. Why a skill (not CLAUDE.md)

CLAUDE.md is always-loaded context. A long workflow placed there burns tokens on every conversation, even when the user isn't running it. A skill loads on demand, gets slash-command autocomplete, and is the idiomatic home for a complex workflow.

A skill also gets proper invocation semantics: real `/self-improve` autocomplete plus implicit invocation when the user's phrasing matches the description.

## 3. Architecture

### 3.1 Deliverable layout

```
~/.claude/skills/self-improve/
├── SKILL.md              # frontmatter + workflow + state schema + skill map
└── references/           # optional split-out for long sections
    ├── scan-signals.md   # what to look for during scan
    ├── state-schema.md   # full state file format
    └── merge-policies.md # fast-forward vs --no-ff, when to push
```

Splitting into `references/` only happens if `SKILL.md` would otherwise exceed ~400 lines. Initial implementation can fit in a single SKILL.md.

### 3.2 SKILL.md frontmatter

```yaml
---
name: self-improve
description: Use when the user wants to autonomously improve a codebase. Scans for bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns. For each candidate, creates an isolated branch with verification + review, then asks the user whether to merge. Triggered by /self-improve or phrases like "improve this project", "self-evolve", "evolve", "auto-improve".
---
```

### 3.3 Self-contained, auto-detecting

The skill does **not** read CLAUDE.md for project-specific configuration. It auto-detects from project files:

- **Language/runtime:** `pyproject.toml` → Python+uv; `package.json` → Node; `Cargo.toml` → Rust; `go.mod` → Go; etc.
- **Test command:** derive from language (`uv run pytest`, `npm test`, `cargo test`, `go test ./...`)
- **Linters/type-checkers:** detect from config (`ruff`/`mypy` from pyproject; `eslint`/`tsc` from package.json; `clippy` for Rust)
- **Build system:** derive from language

### 3.4 Runtime artifacts (gitignored)

- `.claude/self-improve-state.md` — memory of tried/rejected/merged candidates
- `.claude/worktrees/<slug>/` — one worktree per in-flight improvement
- Branches named `self-improve/<category>/<slug>-<ts>` (e.g., `self-improve/bug/pytest-parse-error-20260614-103045`)

## 4. Workflow

A loop. Each iteration produces one branch (one improvement), then asks the user whether to merge. Runs until a stopping criterion is met.

### 4.1 Per-run setup (once)

1. Load `.claude/self-improve-state.md` if it exists.
2. Scan `git log` for already-merged `self-improve/*` branches (backstop — don't redo).
3. Verify working tree is clean. If dirty: refuse to start, tell user to commit/stash.

### 4.2 Per-iteration steps

1. **Scan** — gather signals: linter/type-checker output, test failures, `TODO`/`FIXME`/`HACK`/`XXX` comments, missing tests, dead code, duplication/complexity hotspots, dependency freshness + CVEs, docs gaps (missing docstrings on public APIs), recent git churn, plus anything project-specific discovered at runtime.

2. **Pick next candidate** — filter out already-tried (state file) and already-merged (git log). Rank by `impact × ease × low-risk`. Impact order: correctness → security → tests → perf → refactor → deps → docs.

3. **Isolate** — create a worktree at `.claude/worktrees/<slug>` on a new branch `self-improve/<category>/<slug>-<ts>`. Uses `using-git-worktrees`.

4. **Apply** — invoke the matching skill:
   - `systematic-debugging` for bugs
   - `test-driven-development` (Red-Green-Refactor) for fixes / missing tests
   - `simplify` for refactors
   - plain editing for docs / deps / perf

5. **Verify** — run the affected tests + full suite if cheap. Uses `verification-before-completion`: no claiming success without evidence.

6. **Review** — use `requesting-code-review` (or the project's `/code-review` if available). If review finds real issues, fix (one retry) or skip.

7. **Commit** — commit to the branch with a conventional-commit message. Uses `finishing-a-development-branch`. Do **not** push.

8. **Offer merge** — surface the branch with a one-line summary and ask the user:
   - `merge` → switch to main, merge (fast-forward if possible, else `--no-ff`), **do not push** without an explicit ask
   - `defer` → leave branch, continue to next iteration; surface again in end-of-run summary
   - `skip` → leave branch for manual review, mark in state as "left for manual"

9. **Record** — update `.claude/self-improve-state.md` with the candidate, branch name, outcome, and merge decision.

10. **Loop or stop** — check stopping criteria (§6). If continuing, re-scan from step 1 (applying one improvement may surface or fix others).

### 4.3 End of run

Print a summary: N branches created, M merged, K deferred/skipped (with branch names so the user can review/merge manually).

## 5. State file

### 5.1 Location & format

- **Path:** `.claude/self-improve-state.md`
- **Format:** plain markdown — human-readable, easy to edit manually, diffable
- **Lifecycle:** created on first run; updated in step 9 of each iteration; safe to delete (workflow recreates from scratch)
- **Gitignore:** add to `.gitignore` by default — local automation state. (Users can commit it if they want shared state across a team.)

### 5.2 Schema

````markdown
# Self-Improve State

Tracks candidates the workflow has considered, so repeated runs don't redo work.
Safe to delete — workflow will recreate.

## Attempted

One line per attempt: `<iso-ts> | <category> | <branch> | <status> | <summary>`

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-other`

- 2026-06-14T10:15:22Z | bug | self-improve/bug/pytest-parse-error-20260614-101522 | merged | Fixed off-by-one in test nodeid parser (cae/parsers.py:42)
- 2026-06-14T10:25:00Z | tests | self-improve/tests/harness-coverage-20260614-102500 | deferred | Added test for harness._result() serialization (tests/test_harness.py)

## Permanently Rejected

Ideas that shouldn't be re-proposed. Format: `- <summary> — <reason>. Decided <date>.`

- Pin pytest to <8 — won't fix; conflicts with astropy-build extra. Decided 2026-06-13.
````

### 5.3 How the workflow uses it

- **Start of run:** read state file (missing → treat as empty); also scan `git log` for merged `self-improve/*` branches as a backstop.
- **Step 2 (Pick candidate):** for each candidate, match against entries by `(category, files, idea-similarity)`. Skip anything that matches either section.
- **Step 9 (Record):** append to *Attempted* with status. If user explicitly says "never do this kind of change," move to *Permanently Rejected*.

**What counts as "the same candidate":** same file(s) + same category + semantically similar idea. Fuzzy by design — Claude judges similarity from summary text and file list, not hash matching.

### 5.4 Atomic writes

Write to `.claude/self-improve-state.md.tmp`, then atomic rename. Avoids corruption if interrupted mid-write.

## 6. Stopping criteria & error handling

### 6.1 Stopping criteria (any one triggers end-of-run)

1. No candidates found after scan.
2. Max iterations reached — default **10** (configurable: `self-improve max=20`).
3. N consecutive failures — default **3** (something is wrong; surface to user instead of grinding).
4. Token budget hit — default **500K total** (configurable: `self-improve budget=1M`).
5. Wall-clock budget — default **30 min**.
6. User interrupts (Ctrl-C / Escape).

### 6.2 Error handling per candidate

| Failure | Action | State status |
|---|---|---|
| Working tree dirty at start | Refuse to start, tell user to commit/stash | (no entry) |
| Worktree creation fails | Log, skip, continue | `skipped-other` |
| Apply produces no change | Log, skip, continue | `skipped-other` |
| Tests fail after apply | Revert worktree, continue | `skipped-tests-failed` |
| Review rejects (after one retry) | Leave worktree for inspection, continue | `skipped-review-rejected` |
| Merge conflict during merge step | Abort merge, leave branch for manual review | `deferred` |
| State file missing/corrupt | Warn, start fresh | (reset) |

### 6.3 Interrupt handling

On Ctrl-C / Escape: clean up current worktree (try/finally), write partial state, print summary of what was completed.

## 7. Safety rails

- **Never touch:** `.git/`, `.claude/`, `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `dist/`, `build/`, lockfiles (unless candidate is explicitly `deps`).
- **No external-state mutations:** refuse to run `npm publish`, `git push`, `terraform apply`, `docker push`, `kubectl apply`, or anything else that affects systems beyond the local repo.
- **Per-file change cap per run:** default 3 — prevents rewriting the same file N times in one run.
- **Worktree cleanup always runs** (try/finally), even on failure.

## 8. Testing & verification

The skill is a prompt, not code — traditional unit tests don't apply. Verification is a mix of static checks and behavioral tests against a fixture project.

### 8.1 Static checks (CI-able, fast)

- SKILL.md frontmatter parses as valid YAML with required fields (`name`, `description`).
- Description contains trigger words (`self-improve`, "improve", "evolve").
- All `references/*.md` paths mentioned in SKILL.md exist.
- Markdown lints clean (no broken links/tables).

### 8.2 Fixture project (separate repo)

A separate repo (NOT under `~/.claude/skills/self-improve/`) containing a tiny synthetic project with known, seeded issues the skill should find:

- One failing test (bug)
- One passing-but-untested function (missing test)
- One `TODO` comment (tech debt)
- One obvious duplication (refactor)
- One function missing docstring (docs gap)
- One outdated dep with mild issue (deps)
- Working `pytest` + `ruff` config so the verify step can actually run

Each issue is small and unambiguous — the skill's behavior against this fixture is predictable and reviewable.

### 8.3 Behavioral test cases

Manual or scripted runs against the fixture:

1. **Happy path** — invoke `/self-improve` on fixture → produces expected branches for each seeded issue.
2. **Empty** — invoke on a clean fixture (no issues) → exits with "no candidates found".
3. **Dirty tree** — invoke with uncommitted changes → refuses cleanly.
4. **State-aware** — invoke twice in a row → second run skips first run's candidates.
5. **Budget hit** — invoke with `budget=1` → stops after one iteration, partial state preserved.
6. **Merge ask** — at merge step, three-option prompt appears correctly.
7. **Interrupt** — Ctrl-C mid-run → worktree cleaned up, partial state written.

### 8.4 Manual smoke checklist (first-install verification)

- [ ] `/self-improve` autocompletes when typed
- [ ] First run creates `.claude/self-improve-state.md` (gitignored)
- [ ] First run creates a worktree → applies → tests → commits → asks merge
- [ ] Re-run skips previously-merged candidates
- [ ] Ctrl-C cleans up worktree and writes partial state

## 9. Open questions / future work

- **Parallel execution.** Current design is sequential. For large codebases, `dispatching-parallel-agents` could run N improvements concurrently — risk of conflicting changes needs mitigation first.
- **Push automation.** Currently merge is local-only; "push after merge" stays opt-in. Could add a per-project allowlist for branches safe to push.
- **Cross-project memory.** State is per-project today. A user-level "patterns I always reject" memory could prevent re-proposing the same kinds of changes everywhere.
- **Cost telemetry.** Track $ spent per run and per category, surface in the end-of-run summary.

## 10. Out of scope

- **Auto-PR creation** via `gh pr create` — left for the user to do manually after merge to main, or as a future enhancement.
- **CI integration** — skill runs locally in a Claude Code session, not in CI.
- **Multi-repo orchestration** — one project per invocation.
- **Skill distribution** — installation is a separate concern (copy/symlink to `~/.claude/skills/`); packaging as a plugin is a future option.
