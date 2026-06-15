---
name: self-improve
description: Use when the user wants to proactively push a project forward by implementing its next feature. Reads project artifacts (specs' "future work" sections, README, TODOs, recent commit trajectory, codebase gaps), infers candidate features, asks the user to pick one, then implements it on an isolated branch with verification + review + merge-gate. Triggered by /self-improve or phrases like "implement next feature", "push project forward", "evolve".
---

# Self-Improve (Forward Mode)

Proactively push a project forward by implementing its next feature. Reads project artifacts, infers candidate features, asks the user to pick one, then implements on an isolated branch with verification, review, and a merge gate.

Bug-fixing is incidental — only if a feature implementation surfaces a bug.

## When to invoke

- User types `/self-improve`, "implement next feature", "push project forward", "evolve", or similar phrases
- User asks for proactive / forward / next-feature work (not bug-fixing)

Do **not** invoke for:
- Bug-fix sweeps — the v1 reactive mode is no longer supported. If the user explicitly asks for bug fixes, decline and explain the pivot to forward mode.
- Single targeted edits — just do the edit directly
- Projects with uncommitted changes — refuse and ask the user to commit/stash first

## Auto-detection (run at workflow start)

Detect from project files; do **not** read CLAUDE.md for config:

- **Language/runtime**: `pyproject.toml` → Python+uv; `package.json` → Node; `Cargo.toml` → Rust; `go.mod` → Go
- **Test command**: derive from language (`uv run pytest`, `npm test`, `cargo test`, `go test ./...`). If none detected, the verify step skips test execution.
- **Linters/type-checkers**: detect from config (`ruff`/`mypy` from pyproject; `eslint`/`tsc` from package.json; `clippy` for Rust)
- **Default branch**: read via `git symbolic-ref refs/remotes/origin/HEAD`; fall back to `main`, then `master`. Used as merge target in step 10. **Never hardcode.**
- **Issue tracker**: if `gh` is available AND the project's remote is on GitHub, `gh issue list --state open` is a forward signal

## Per-run setup (once)

1. Read `.claude/self-improve-state.md`. Existing reactive entries (category != `feature`) are ignored for matching.
2. Verify working tree is clean: if dirty, **refuse to start**, tell user to commit/stash.
3. Ensure gitignore entries are present (append `.claude/self-improve-state.md`, `.claude/self-improve-state.md.tmp`, `.claude/worktrees/` if missing).

## Workflow (per-iteration loop)

Each iteration produces ONE feature on its own branch. Two approval gates per iteration: pick (before implement) + merge (after implement).

### Step 1: Scan artifacts for forward signals

Read:
- `docs/superpowers/specs/*.md` — "future work" / "out of scope" / "open questions" sections
- `README.md` — planned features / roadmap / "not yet implemented" notes
- `TODO: implement X` / `FIXME: add Y` comments that look forward (not bug-fix)
- Recent commit trajectory (last ~20 commits — themes, what's been built → natural next step)
- Codebase structure gaps (e.g., "agents exist for X/Y/Z but not W" — clear parallel-pattern gap)
- Issue tracker, if `gh` is available and the project is a GitHub repo

### Step 2: Infer N candidates (default 3)

Synthesize signals into concrete feature candidates. Each candidate has:
- **Title** (one line)
- **Source** (which artifact(s) motivated it — for traceability)
- **Scope estimate** (LOC range, "single PR worth" = ~50–300 LOC)
- **Why-now** (why this is the right next step)
- **Risk** (low / medium / high — based on LOC, files touched, blast radius, deps, breaking changes)

Filter out candidates matching anything in:
- *Attempted* (category=`feature` only — legacy categories ignored)
- *Proposed but not picked*
- *Permanently Rejected*

### Step 3: Propose + user picks  ← GATE 1

Use `AskUserQuestion` with the N candidates + a "none of these, re-scan" option + a "stop" option. Each candidate option's description includes its source / scope / why-now / risk so the user can decide.

Surface a **risk callout** in the option description if any safety rail (§"Safety rails") would apply:
- "adds dependency X"
- "schema/migration change"
- "breaking API/CLI change"

The user picks one. Their pick authorizes anything noted in the risk field.

### Step 4: Isolate

Use `superpowers:using-git-worktrees`. Create:
- Worktree at `.claude/worktrees/<slug>`
- Branch `self-improve/feature/<slug>-<ts>` (e.g., `self-improve/feature/gemini-adapter-20260614-110000`)

### Step 5: Draft a brief plan

Use `superpowers:writing-plans` to write a plan to `docs/superpowers/plans/<YYYY-MM-DD>-<feature-slug>.md` with 5–15 tasks (smaller for small features, larger for big ones). **Not a separate approval gate** — the user already picked the feature. If they want to abort after seeing the plan, they interrupt.

### Step 6: Implement

Use `superpowers:test-driven-development` (Red-Green-Refactor) for the test+code work. For features estimated >200 LOC, dispatch via `superpowers:subagent-driven-development` against the plan from step 5. Use `superpowers:systematic-debugging` if a bug surfaces during implementation (incidental bug-fixing is allowed).

If implementation hits a safety-rail violation that the user's pick didn't authorize (e.g., turns out to need a new dep on a "low risk" candidate), abort as `skipped-other` with a policy-violation note in the state summary.

### Step 7: Verify

Use `superpowers:verification-before-completion`:
- Run the affected tests
- Run the full test suite if cheap (under ~30s)
- Run linters/type-checkers
- **No claiming success without evidence** — paste actual command output

If no test command detected (e.g., docs-only repo), skip test execution, rely on linters, and note in the state record.

### Step 8: Review

Use `superpowers:requesting-code-review` (or the project's `/code-review` skill if available).

If **neither** is available, do an inline self-review against this checklist:
- Correctness: does the change do what it claims?
- Regressions: could this break existing behavior?
- Scope creep: does the diff include unrelated changes?
- Security: any new attack surface?

Note in the state record that no formal review skill ran.

If review finds real issues: fix (one retry), then re-review. If still rejected, skip the candidate.

### Step 9: Commit

Use `superpowers:finishing-a-development-branch` for guidance. Commit to the branch with a conventional-commit message:

```
feat(<scope>): <summary>

Self-improve feature: <one-line rationale linking back to source artifact>

[body explaining the change]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

Do **not** push.

### Step 10: Offer merge  ← GATE 2

Surface the branch with a one-line summary, then ask the user (use AskUserQuestion):

> Branch `self-improve/feature/<slug>` ready.
> Change: <one-line summary>
>
> Merge to <default-branch> now, defer, or skip?

- `merge` → switch to the detected default branch, merge (fast-forward if possible, else `--no-ff`). **Do not push** without an explicit ask. After successful merge: delete the worktree and the merged branch.
- `defer` → leave branch and worktree in place, continue to next iteration. Surface again in end-of-run summary.
- `skip` → leave branch for manual review, delete the worktree (branch stays so the user can find it). Mark in state as "left for manual".

### Step 11: Record

Update `.claude/self-improve-state.md` (see format below):
- All proposed candidates (including unpicked) → *Proposed but not picked* with user reason where given
- The picked + implemented candidate → *Attempted* with category=`feature` and appropriate status
- If user said "never propose this kind of change", move to *Permanently Rejected*

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-too-big` | `skipped-other`

### Step 12: Loop or stop

Check stopping criteria. If continuing, re-scan from step 1 (implementing one feature may surface the next).

## Stopping criteria

Any one triggers end-of-run:
1. User picks **"stop"** at Gate 1
2. **Re-scan loop limit** — user picks "none of these, re-scan" 3 times consecutively without picking a candidate
3. Max iterations reached — default **10** (configurable: `self-improve max=20`)
4. **3 consecutive failures** — counts: `skipped-tests-failed`, `skipped-review-rejected` (after retry), `skipped-too-big`, `skipped-other`. A `merged` or `deferred` resets the counter.
5. Token budget hit — default **500K total** (configurable: `self-improve budget=1M`)
6. Wall-clock budget — default **30 min**
7. User interrupts (Ctrl-C / Escape)

## Error handling

| Failure | Action | State status |
|---|---|---|
| Working tree dirty at start | Refuse to start, tell user to commit/stash | (no entry) |
| Inference produces 0 candidates | Tell user, stop the run | (no entry) |
| Plan-writing fails | Log, skip candidate, continue | `skipped-other` |
| Implementation exceeds LOC cap (default **500 added/modified lines in the diff**) | Abort, leave worktree for inspection, record | `skipped-too-big` |
| Implementation exceeds per-file cap (default **8 files touched in the diff**) | Abort, leave worktree, record | `skipped-too-big` |
| Implementation violates safety rail (dep/schema/breaking on a low-risk candidate) | Abort, leave worktree, record | `skipped-other` (policy-violation note in summary) |
| Tests fail after implement | Revert worktree, continue | `skipped-tests-failed` |
| Review rejects (after one retry) | Leave worktree for inspection, continue | `skipped-review-rejected` |
| Merge conflict during merge step | Abort merge, leave branch for manual review | `deferred` |
| State file missing/corrupt | Warn, start fresh | (reset) |

**Interrupt handling:** On Ctrl-C / Escape, clean up current worktree (try/finally), write partial state, print summary.

## Safety rails

**Never touch:**
- `.git/`
- User / system config under `.claude/` — `settings.json`, `settings.local.json`, `commands/`, `skills/`, `agents/`, `hooks/`, `plugins/`. (Exception: this skill's own artifacts at `.claude/self-improve-state.md`, `.claude/self-improve-state.md.tmp`, and `.claude/worktrees/` are managed by the workflow itself.)
- `node_modules/`, `.venv/`, `venv/`
- `__pycache__/`, `dist/`, `build/`
- Lockfiles (`uv.lock`, `package-lock.json`, `Cargo.lock`, `go.sum`) unless the user explicitly authorized a candidate whose Risk field notes a dep add

**No external-state mutations** — refuse to run:
- `npm publish`, `pip upload`, `cargo publish`
- `git push`, `git fetch` with rewrite
- `terraform apply`, `kubectl apply`, `docker push`
- Anything else that affects systems beyond the local repo

**Forward-mode specific:**
- **No new dependencies** without explicit user pick of a candidate whose Risk field notes the dep.
- **No schema/migration changes** without explicit user pick of a candidate whose description calls for one.
- **No breaking API/CLI contract changes** on "low risk" candidates.
- **Per-feature LOC cap (default 500 added/modified lines in the diff).** Implementation that exceeds this is auto-aborted as `skipped-too-big`.
- **Per-file change cap (default 8 files touched in the diff).** Prevents touching too many files in one feature.

**Worktree cleanup always runs** (try/finally), even on failure.

## State file format

Path: `.claude/self-improve-state.md` (gitignored by default — local automation state).

````markdown
# Self-Improve State

Tracks candidates the workflow has considered, so repeated runs don't redo work.
Safe to delete — workflow will recreate.

## Attempted

One line per attempt: `<iso-ts> | <category> | <branch> | <status> | <summary>`

Categories: `feature` (forward mode). Legacy categories (`bug`, `tests`, `refactor`, `docs`, `deps`, `perf`, `security`) may appear in older entries and are **ignored for matching**.

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-too-big` | `skipped-other`

- 2026-06-14T11:00:00Z | feature | self-improve/feature/gemini-adapter-20260614-110000 | merged | Added Gemini CLI adapter (cae/agents/gemini.py, 180 LOC, +1 dep)

## Proposed but not picked

Every candidate surfaced at the propose gate gets recorded here, even if user didn't pick it. Prevents re-proposing the same idea next run.

Format: `<iso-ts> | <summary> | <user-reason-or-empty>`

- 2026-06-14T11:00:00Z | Add Cargo (Rust) agent support | user picked Gemini instead

## Permanently Rejected

User explicitly said "never propose this kind of change". Format: `- <summary> — <reason>. Decided <date>.`

- Pin pytest to <8 — won't fix; conflicts with astropy-build extra. Decided 2026-06-13.
````

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
- Proposals recorded (won't be re-proposed): P

Next steps:
- Review deferred branches: git checkout <branch>
- Re-run anytime: /self-improve
```

## Skills used

- `superpowers:using-git-worktrees` (step 4)
- `superpowers:writing-plans` (step 5)
- `superpowers:test-driven-development` (step 6)
- `superpowers:subagent-driven-development` (step 6, features >200 LOC)
- `superpowers:systematic-debugging` (step 6, incidental bugs)
- `superpowers:verification-before-completion` (step 7)
- `superpowers:requesting-code-review` (step 8)
- `superpowers:finishing-a-development-branch` (step 9)
