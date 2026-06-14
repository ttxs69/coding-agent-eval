# Self-Improve Forward Pivot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pivot the existing `self-improve` skill from reactive (bug-sweep) to forward (implement next features). Same skill name, same install path, new workflow with two approval gates.

**Architecture:** Modify the existing files in place. Update the static-check tests' category tuple first (TDD Red), then the SKILL.md description (TDD Green). Rewrite SKILL.md body and README with forward-mode content. Repurpose the existing fixture by adding forward signals (spec file, README section, source TODO + codebase gap), with validation tests written first (Red) then seeds added (Green). Rewrite SMOKE_CHECKLIST.md for the two-gate flow.

**Tech Stack:** Markdown (SKILL.md, README, fixture spec, smoke checklist), Python 3.10 + pytest (static checks + fixture validation), Bash (existing install script, unchanged).

---

## File structure

Modified files:
- `self-improve-skill/SKILL.md` — rewrite (description + body)
- `self-improve-skill/README.md` — rewrite for forward mode
- `self-improve-skill/tests/test_static_checks.py` — update category tuple only
- `self-improve-skill/tests/test_fixture_project.py` — add forward-signal validation tests
- `self-improve-skill/tests/SMOKE_CHECKLIST.md` — rewrite for two-gate flow
- `tests/fixtures/self-improve-sample-project/README.md` — add Planned features section
- `tests/fixtures/self-improve-sample-project/src/sample/__init__.py` — add forward TODO + codebase gap

New files:
- `tests/fixtures/self-improve-sample-project/docs/superpowers/specs/2026-06-14-sample-design.md` — fixture's design spec with Future work section

Unchanged:
- `self-improve-skill/scripts/install.sh` — install mechanism unchanged
- `.gitignore` — patterns unchanged
- `tests/fixtures/self-improve-sample-project/pyproject.toml` — package metadata unchanged

---

## Task 1: Update static-check category tuple (TDD Red → Green)

The current `test_description_mentions_categories` checks for `bug`/`test`/`refactor`. The forward-mode description uses `feature`/`next`/`forward` instead. Update the test first (Red), then update the description (Green) — same commit.

**Files:**
- Modify: `self-improve-skill/tests/test_static_checks.py`
- Modify: `self-improve-skill/SKILL.md` (frontmatter only)

- [ ] **Step 1: Update the category tuple in the test**

Edit `self-improve-skill/tests/test_static_checks.py`. Find the `test_description_mentions_categories` function:

```python
def test_description_mentions_categories():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for category in ("bug", "test", "refactor"):
        assert category in desc, (
            f"description missing category {category!r}: {desc!r}"
        )
```

Replace the category tuple:

```python
def test_description_mentions_categories():
    fm = parse_frontmatter(SKILL_MD.read_text())
    desc = fm.get("description", "").lower()
    for category in ("feature", "next", "forward"):
        assert category in desc, (
            f"description missing category {category!r}: {desc!r}"
        )
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py::test_description_mentions_categories -v`

Expected: FAIL with `description missing category 'feature' ...` — the current SKILL.md description contains `bug`/`test`/`refactor` but not `feature`/`next`/`forward`.

- [ ] **Step 3: Update the SKILL.md description (frontmatter only)**

Edit `self-improve-skill/SKILL.md`. Find the description line:

```yaml
description: Use when the user wants to autonomously improve a codebase. Scans for bugs, missing tests, refactors, doc gaps, dependency issues, perf, and security concerns. For each candidate, creates an isolated branch with verification + review, then asks the user whether to merge. Triggered by /self-improve or phrases like "improve this project", "self-evolve", "evolve", "auto-improve".
```

Replace with:

```yaml
description: Use when the user wants to proactively push a project forward by implementing its next feature. Reads project artifacts (specs' "future work" sections, README, TODOs, recent commit trajectory, codebase gaps), infers candidate features, asks the user to pick one, then implements it on an isolated branch with verification + review + merge-gate. Triggered by /self-improve or phrases like "implement next feature", "push project forward", "evolve".
```

- [ ] **Step 4: Run all static-check tests, verify they pass**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py -v`

Expected: 6/6 PASS.

- [ ] **Step 5: Commit**

```bash
git add self-improve-skill/tests/test_static_checks.py self-improve-skill/SKILL.md
git commit -m "refactor(self-improve): pivot description to forward mode

Static-check category tuple shifts from bug/test/refactor to
feature/next/forward. SKILL.md description updated to match the
forward-mode pivot. Body still describes the old reactive workflow —
that gets rewritten in the next commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: Rewrite SKILL.md body with forward-mode workflow

Replace the entire SKILL.md body (everything after the frontmatter) with the new forward-mode workflow. The frontmatter stays as updated in Task 1.

**Files:**
- Modify: `self-improve-skill/SKILL.md` (body only — frontmatter unchanged)

- [ ] **Step 1: Replace the SKILL.md body**

Use the Write tool to overwrite `self-improve-skill/SKILL.md` with this exact content (frontmatter preserved from Task 1, body replaced):

````markdown
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
````

- [ ] **Step 2: Run static checks, verify they pass**

Run: `uv run pytest self-improve-skill/tests/test_static_checks.py -v`

Expected: 6/6 PASS.

- [ ] **Step 3: Run fixture-validation tests (no regression check)**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py -v`

Expected: all currently-passing tests still pass. (No fixture changes yet — those come in Tasks 4–5.)

- [ ] **Step 4: Manual read-through**

Read `self-improve-skill/SKILL.md` end-to-end. Verify:
- Step numbers sequential 1–12
- Two gates (Step 3 = Gate 1, Step 10 = Gate 2) clearly marked
- "Skills used" maps each skill to the right step
- Status enum consistent across Step 11, Error handling, State file format
- Forward-specific safety rails present (no new deps / schema / breaking without explicit pick; LOC + file caps)

Fix any inline issues.

- [ ] **Step 5: Commit**

```bash
git add self-improve-skill/SKILL.md
git commit -m "feat(self-improve): rewrite SKILL.md body for forward mode

Pivot from reactive bug-sweep to forward feature implementation.
New per-iteration loop has 12 steps with two approval gates: pick
(Gate 1, before implement) and merge (Gate 2, after implement).

Inference reads project artifacts (specs' future-work sections,
README, forward-looking TODOs, commit trajectory, codebase gaps,
issues). Each candidate carries title/source/scope/why-now/risk;
risk callouts surface dep/schema/breaking concerns before the user
picks.

Forward-specific safety rails: no new deps, schema changes, or
breaking API/CLI changes without explicit user pick of a candidate
noting the risk. Per-feature LOC cap (500) and per-file cap (8)
auto-abort oversized work as skipped-too-big.

State file gains a 'Proposed but not picked' section to prevent
re-proposing rejected ideas. Legacy reactive entries preserved but
ignored for matching.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Rewrite README for forward mode

The README currently describes the v1 reactive workflow. Rewrite it to describe forward mode, two-gate flow, new safety rails, and stopping criteria.

**Files:**
- Modify: `self-improve-skill/README.md`

- [ ] **Step 1: Replace README.md content**

Use the Write tool to overwrite `self-improve-skill/README.md` with this exact content:

````markdown
# self-improve

A Claude Code skill that proactively pushes a project forward by implementing its next feature. Reads project artifacts, infers candidate features, asks you to pick one, then implements it on an isolated branch — with verification, review, and a merge gate.

## What it does

When you invoke `/self-improve` (or say "implement next feature", "push project forward", "evolve"), the skill:

1. Reads project artifacts: specs' "future work" sections, README, forward-looking TODOs, recent commits, codebase gaps, open issues
2. Infers 3 candidate features with title / source / scope / why-now / risk
3. **Asks you to pick one** (or re-scan or stop) — *Gate 1*
4. Creates an isolated git worktree + branch
5. Drafts a brief plan to `docs/superpowers/plans/`
6. Implements via TDD (dispatches subagents for features >200 LOC)
7. Verifies (tests + linters)
8. Reviews (code-review skill or self-review fallback)
9. Commits to the branch
10. **Asks you whether to merge** — merge / defer / skip — *Gate 2*
11. Records the outcome in `.claude/self-improve-state.md` (also records unpicked proposals, so they don't resurface)
12. Loops until stopped

Bug-fixing is incidental — if a feature implementation surfaces a bug, the skill fixes it as part of the feature. Standalone bug-sweep candidates are not generated.

## Install

```sh
sh self-improve-skill/scripts/install.sh
```

Symlinks `self-improve-skill/` to `~/.claude/skills/self-improve/`. Safe to re-run.

## Invoke

```
/self-improve
```

Or type: `implement next feature`, `push project forward`, `evolve`.

## What it won't do

- Touch `.git/`, `node_modules/`, lockfiles (unless a candidate's Risk field notes a dep add AND you picked it)
- Modify your `.claude/` config (settings, commands, skills, hooks) — only its own state file + worktrees
- Run external-state mutations (`git push`, `npm publish`, `terraform apply`, etc.)
- Start with a dirty working tree (it'll refuse and ask you to commit/stash)
- Push after merging (local-only by default)
- Add new dependencies, change schemas, or make breaking API/CLI changes unless the candidate's Risk field noted it AND you picked it
- Implement features >500 LOC or >8 files in one iteration (auto-aborted as `skipped-too-big`)

## State

Per-project memory at `.claude/self-improve-state.md` (gitignored). Three sections:

- **Attempted** — every picked+implemented feature with outcome (`merged` / `deferred` / `skipped-*`)
- **Proposed but not picked** — every candidate ever surfaced at Gate 1, so they don't resurface next run
- **Permanently Rejected** — ideas you've explicitly said "never propose"

On first run (and any run where the entries are missing), the skill appends these paths to the project's `.gitignore`.

Legacy entries from the v1 reactive skill (categories like `bug`, `docs`, etc.) remain in the file for history but are ignored for candidate matching.

## Stopping criteria

- You pick "stop" at Gate 1
- You re-scan 3 times without picking
- Max 10 iterations per run
- 3 consecutive failures (tests-fail / review-reject / too-big / policy-violation)
- 500K token budget
- 30 min wall-clock
- You interrupt (Ctrl-C / Escape)

## Spec & plan

- Spec: `docs/superpowers/specs/2026-06-14-self-improve-forward-pivot-design.md`
- Original v1 spec (reactive mode, replaced): `docs/superpowers/specs/2026-06-14-self-improve-skill-design.md`
- Pivot plan: `docs/superpowers/plans/2026-06-14-self-improve-forward-pivot.md`
````

- [ ] **Step 2: Commit**

```bash
git add self-improve-skill/README.md
git commit -m "docs(self-improve): rewrite README for forward mode

Reflects the pivot: forward-mode workflow with two gates, new safety
rails (no deps/schema/breaking changes without explicit pick), Proposed
but not picked state section, and stopping criteria including the
re-scan loop limit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Add forward-signal validation tests (TDD Red)

Add four new tests to `test_fixture_project.py` that verify the fixture has forward signals. They will fail until Task 5 adds the signals.

**Files:**
- Modify: `self-improve-skill/tests/test_fixture_project.py`

- [ ] **Step 1: Add the four new tests**

Edit `self-improve-skill/tests/test_fixture_project.py`. Add the following tests at the end of the file, before the final blank line (after `test_fixture_test_command_fails_on_seeded_bug`):

```python
def test_fixture_has_future_work_section():
    """Fixture has a design spec with a 'Future work' section."""
    spec_dir = FIXTURE / "docs" / "superpowers" / "specs"
    assert spec_dir.is_dir(), f"no docs/superpowers/specs/ dir in fixture: {spec_dir}"
    spec_files = list(spec_dir.glob("*.md"))
    assert spec_files, "no design spec files in fixture's docs/superpowers/specs/"
    found = False
    for spec_file in spec_files:
        text = spec_file.read_text()
        if "future work" in text.lower():
            found = True
            break
    assert found, "no 'Future work' section in any fixture spec file"


def test_fixture_has_planned_features_in_readme():
    """Fixture README has a 'Planned features' section."""
    readme = (FIXTURE / "README.md").read_text()
    assert "planned features" in readme.lower(), (
        "fixture README missing 'Planned features' section"
    )


def test_fixture_has_forward_looking_todo():
    """A forward-looking TODO (TODO: implement X) exists in the fixture source."""
    src = _read_source()
    forward_todos = re.findall(
        r"TODO[^)]*\bimplement\b\s+\w+", src, re.IGNORECASE
    )
    assert forward_todos, (
        "no forward-looking TODO (TODO: implement X) in fixture source"
    )


def test_fixture_has_codebase_gap():
    """Fixture source references a missing function (parallel-pattern gap)."""
    src = _read_source()
    # The fixture references subtract/divide in docstrings or comments but
    # does not define them — that's the parallel-pattern gap.
    referenced = re.findall(r"\b(subtract|divide|power|exponentiate)\b", src)
    assert referenced, (
        "no codebase gap (reference to a missing function like subtract/divide) "
        "in fixture source"
    )
```

Note: `re` is already imported at the top of the file (used by existing tests). Confirm by reading the file head before adding.

- [ ] **Step 2: Run the new tests, verify they fail**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py::test_fixture_has_future_work_section self-improve-skill/tests/test_fixture_project.py::test_fixture_has_planned_features_in_readme self-improve-skill/tests/test_fixture_project.py::test_fixture_has_forward_looking_todo self-improve-skill/tests/test_fixture_project.py::test_fixture_has_codebase_gap -v`

Expected: ALL 4 FAIL.
- `test_fixture_has_future_work_section` → no `docs/superpowers/specs/` dir
- `test_fixture_has_planned_features_in_readme` → README missing the section
- `test_fixture_has_forward_looking_todo` → no `TODO: implement X` in source
- `test_fixture_has_codebase_gap` → no reference to subtract/divide/etc.

(The existing 6 fixture tests should still pass — they verify reactive seeds that we haven't touched yet.)

- [ ] **Step 3: Verify existing fixture tests still pass**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py -v`

Expected: 6 PASS (existing) + 4 FAIL (new) = 10 collected, 6 passed, 4 failed.

- [ ] **Step 4: Commit the failing tests**

```bash
git add self-improve-skill/tests/test_fixture_project.py
git commit -m "test(self-improve): add forward-signal validation tests (Red)

Four new tests for the forward-mode pivot:
- fixture has a design spec with 'Future work' section
- fixture README has 'Planned features' section
- fixture source has a forward-looking TODO (TODO: implement X)
- fixture source references a missing function (codebase gap)

All four fail against the current fixture (no forward signals yet).
Task 5 adds the signals to make them pass.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Add forward signals to fixture (TDD Green)

Add forward signals to the fixture so the four new tests pass. Touch three places: new spec file, README addition, source-code addition.

**Files:**
- Create: `tests/fixtures/self-improve-sample-project/docs/superpowers/specs/2026-06-14-sample-design.md`
- Modify: `tests/fixtures/self-improve-sample-project/README.md`
- Modify: `tests/fixtures/self-improve-sample-project/src/sample/__init__.py`

- [ ] **Step 1: Create the fixture's design spec**

Create `tests/fixtures/self-improve-sample-project/docs/superpowers/specs/2026-06-14-sample-design.md`:

```markdown
# Sample Package — Design

**Date:** 2026-06-14
**Purpose:** Tiny synthetic package used as a test fixture for the self-improve skill's forward mode.

## Overview

The `sample` package provides basic arithmetic operations. Currently implements `add` and `multiply`. Pair-helper variants (`sum_pair`, `product_pair`) wrap the basic ops for tuple-style callers.

## Future work

In rough priority order:

- **Subtraction (`subtract(a, b)`)** — pairs with `add` and `multiply` but currently missing. Trivial to implement; closes the basic-arithmetic gap.
- **Exponentiation (`power(base, exp)`)** — would require deciding on integer vs float behavior; non-trivial semantics for negative exponents.

## Out of scope

- Arbitrary-precision arithmetic (Python's built-in `int` already handles this)
- Vectorized / batch operations
```

- [ ] **Step 2: Update the fixture README**

Use the Write tool to overwrite `tests/fixtures/self-improve-sample-project/README.md` with:

```markdown
# sample

Fixture project for testing the self-improve skill's forward mode. Contains intentionally seeded forward signals — see `self-improve-skill/tests/test_fixture_project.py` for the catalog.

The fixture also retains its v1 reactive seeds (an off-by-one bug in `add()`, a missing-test target in `public_api_function`, etc.) — those are inert under forward mode but don't hurt.

## Planned features

- **Subtraction (`subtract(a, b)`)** — referenced in source docstring but not yet implemented
- **Division (`divide(a, b)`)** — would parallel `multiply` and complete the basic four arithmetic ops
```

- [ ] **Step 3: Update the fixture source with forward TODO + codebase gap**

Use the Write tool to overwrite `tests/fixtures/self-improve-sample-project/src/sample/__init__.py` with:

```python
"""Sample package for self-improve skill testing.

This module intentionally contains seeded forward signals the self-improve
skill should detect. See self-improve-skill/tests/test_fixture_project.py
for the catalog.
"""


def add(a, b):
    # BUG: off-by-one — returns a - b + 1 instead of a + b
    return a - b + 1


def multiply(a, b):
    """Multiply two numbers.

    Pairs with `add`. The full basic-arithmetic set would also include
    `subtract` and `divide` (not yet implemented — see Future work in
    docs/superpowers/specs/2026-06-14-sample-design.md).
    """
    # Has a test below (test_multiply_basic). Contrast with public_api_function,
    # which is the real "missing test" candidate the self-improve skill should find.
    return a * b


# TODO: implement divide() — pairs with add/multiply but missing. See
# Planned features in README and Future work in the design spec.


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

Note: `multiply` now has a docstring (was just a comment before). The existing `test_fixture_has_seeded_missing_docstring` test only checks `public_api_function`, not `multiply`, so it still passes.

- [ ] **Step 4: Run the new tests, verify they pass**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py::test_fixture_has_future_work_section self-improve-skill/tests/test_fixture_project.py::test_fixture_has_planned_features_in_readme self-improve-skill/tests/test_fixture_project.py::test_fixture_has_forward_looking_todo self-improve-skill/tests/test_fixture_project.py::test_fixture_has_codebase_gap -v`

Expected: ALL 4 PASS.

- [ ] **Step 5: Run the full fixture-validation suite, verify no regression**

Run: `uv run pytest self-improve-skill/tests/test_fixture_project.py -v`

Expected: 10/10 PASS (6 existing + 4 new).

If `test_fixture_has_seeded_missing_docstring` fails, the new docstring on `multiply` accidentally satisfied the docstring-check on the wrong function — re-read the test to confirm it only checks `public_api_function`, then debug.

If `test_fixture_test_command_fails_on_seeded_bug` fails, the fixture's `pip install -e .` may need to be re-run after the source change:

```sh
uv pip install -e tests/fixtures/self-improve-sample-project
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/self-improve-sample-project/docs/ tests/fixtures/self-improve-sample-project/README.md tests/fixtures/self-improve-sample-project/src/sample/__init__.py
git commit -m "test(self-improve): seed fixture with forward signals (Green)

Adds the forward signals the new validation tests check for:
- design spec at docs/superpowers/specs/2026-06-14-sample-design.md
  with a Future work section
- README's Planned features section listing subtract/divide
- Forward-looking TODO in source: 'TODO: implement divide()'
- Codebase gap: multiply's docstring references subtract/divide
  (functions that don't exist)

Existing reactive seeds (the add() bug, public_api_function missing
docstring, sum_pair/product_pair duplication) are preserved — they're
inert under forward mode but don't hurt.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Rewrite SMOKE_CHECKLIST.md for two-gate flow

The smoke checklist currently documents the v1 reactive flow. Rewrite it for the forward-mode two-gate workflow.

**Files:**
- Modify: `self-improve-skill/tests/SMOKE_CHECKLIST.md`

- [ ] **Step 1: Replace SMOKE_CHECKLIST.md content**

Use the Write tool to overwrite `self-improve-skill/tests/SMOKE_CHECKLIST.md` with this exact content:

````markdown
# Self-Improve Skill (Forward Mode) — Manual Smoke Checklist

Run this after `scripts/install.sh` to verify the skill works end-to-end.
Each item is a manual action — there's no way to automate "invoke skill in a real session".

## Setup

- [ ] From the repo root, run `sh self-improve-skill/scripts/install.sh`
- [ ] Confirm `~/.claude/skills/self-improve/SKILL.md` exists
- [ ] Start a new Claude Code session in `tests/fixtures/self-improve-sample-project/`
- [ ] Initialize the fixture as a git repo: `git init && git add . && git commit -m initial`

## Inference

- [ ] Type `/self-improve` — autocompletes or recognized as trigger
- [ ] Skill reads: `docs/superpowers/specs/*.md` (Future work section), README (Planned features), forward-looking TODOs, recent commits, codebase gaps
- [ ] Skill surfaces 3 candidate features at Gate 1

## Gate 1 (propose + pick)

- [ ] Each candidate option shows: title, source, scope, why-now, risk
- [ ] Risk callouts appear when applicable (adds-dep, schema-change, breaking)
- [ ] Two non-candidate options present: "none of these, re-scan" and "stop"
- [ ] User picks one (or re-scan or stop)

## Implementation (after pick)

- [ ] Worktree created at `.claude/worktrees/<slug>/`
- [ ] Branch `self-improve/feature/<slug>-<ts>` created
- [ ] Brief plan written to `docs/superpowers/plans/<date>-<slug>.md` (5–15 tasks)
- [ ] TDD: tests written first, then implementation
- [ ] All affected tests pass
- [ ] Linter clean
- [ ] Code review runs (or inline self-review fallback if no review skill available)
- [ ] Commit on branch with conventional-commit message

## Gate 2 (merge)

- [ ] Three-option prompt appears: merge / defer / skip
- [ ] Choosing `merge`: switches to default branch, FF-merges (or `--no-ff`), deletes worktree + branch, does NOT push
- [ ] Choosing `defer`: branch + worktree stay, iteration continues
- [ ] Choosing `skip`: branch stays, worktree deleted, marked "left for manual" in state

## State file

- [ ] `.claude/self-improve-state.md` exists after first iteration
- [ ] *Attempted* entry: `<ts> | feature | <branch> | <status> | <summary>`
- [ ] *Proposed but not picked* entries: one per candidate surfaced at Gate 1 (including the picked one is NOT in this section — it's in *Attempted*)
- [ ] File is gitignored (run `git status` — should not appear)

## Re-run behavior

- [ ] Second `/self-improve` invocation: candidates previously proposed are NOT re-surfaced
- [ ] Merged features are NOT re-attempted

## Edge cases

- [ ] Dirty tree at start: skill refuses with clear "commit or stash first" message
- [ ] Re-scan 3 times consecutively: skill stops with "couldn't find anything you want"
- [ ] Ctrl-C mid-iteration: worktree cleaned up, partial state written
- [ ] Implementation exceeds 500-LOC or 8-file cap: aborted as `skipped-too-big`
- [ ] Implementation needs a new dep on a "low risk" candidate: aborted as `skipped-other` with policy-violation note
````

- [ ] **Step 2: Commit**

```bash
git add self-improve-skill/tests/SMOKE_CHECKLIST.md
git commit -m "docs(self-improve): rewrite smoke checklist for two-gate flow

Documents the forward-mode end-to-end verification: inference → Gate 1
(propose + pick) → implement → Gate 2 (merge) → state recording →
re-run behavior. Adds edge-case checks for re-scan limit, LOC/file
caps, and policy-violation aborts.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Final verification

Verify the full pivot is consistent and doesn't break anything.

- [ ] **Step 1: Run the project's test suite (cae tests)**

Run: `uv run pytest -v`

Expected: All pre-existing tests in `tests/` pass (91 passed, 2 skipped as before).

- [ ] **Step 2: Run the skill's tests**

Run: `uv run pytest self-improve-skill/tests/ -v`

Expected: ALL tests pass — 6 static checks + 10 fixture-validation tests = 16 total.

- [ ] **Step 3: Run the linter**

Run: `uv run ruff check self-improve-skill`

Expected: no issues.

- [ ] **Step 4: Verify file structure**

Run: `find self-improve-skill tests/fixtures/self-improve-sample-project -type f -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -path '*/.ruff_cache/*' -not -path '*/sample.egg-info/*' -not -name '*.pyc' -not -name 'uv.lock' | sort`

Expected output (modulo cache/egg-info which we excluded):
```
self-improve-skill/README.md
self-improve-skill/SKILL.md
self-improve-skill/scripts/install.sh
self-improve-skill/tests/SMOKE_CHECKLIST.md
self-improve-skill/tests/test_fixture_project.py
self-improve-skill/tests/test_static_checks.py
tests/fixtures/self-improve-sample-project/README.md
tests/fixtures/self-improve-sample-project/docs/superpowers/specs/2026-06-14-sample-design.md
tests/fixtures/self-improve-sample-project/pyproject.toml
tests/fixtures/self-improve-sample-project/src/sample/__init__.py
tests/fixtures/self-improve-sample-project/tests/__init__.py
tests/fixtures/self-improve-sample-project/tests/test_sample.py
```

- [ ] **Step 5: Read SKILL.md end-to-end one final time**

Confirm:
- Two gates clearly marked (Step 3 and Step 10)
- "Skills used" maps each skill to the right step (worktrees=4, writing-plans=5, TDD=6, subagents=6 for large, debugging=6 incidental, verification=7, review=8, finishing=9)
- Status enum consistent across Step 11, Error handling, and State file format
- Forward-specific safety rails present and consistent with the spec
- Description in frontmatter matches the trigger words expected by static-check tests

Fix any inline issues. If anything was fixed, commit:

```bash
git add -A
git commit -m "chore(self-improve): final consistency fixes from forward-pivot verification

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

If nothing needed fixing, no commit — implementation is complete.

---

## Self-review notes

**Spec coverage:**
- §1 (problem & purpose) → addressed by the pivot itself (SKILL.md rewrite in Task 2)
- §2 (architecture) → Tasks 1 (description) + 2 (body)
- §3 (workflow) → Task 2 (full SKILL.md content covers all 12 steps)
- §4 (stopping + safety rails) → Task 2 (tables + rails in SKILL.md)
- §5 (state file) → Task 2 (format embedded in SKILL.md) + Task 3 (README state section)
- §6 (testing) → Tasks 1, 4, 5, 6 (static checks update, fixture validation tests Red→Green, smoke checklist rewrite)
- §7 (migration) → implicit (files modified in place, no migration script needed; legacy state entries ignored)
- §8 (open questions) → out of scope (deferred)
- §9 (out of scope) → respected (no milestone planning, no judgment-driven inference, no PR creation)

**Placeholder scan:** none — every step shows the exact content to write.

**Type consistency:**
- Branch naming `self-improve/feature/<slug>-<ts>` consistent across SKILL.md, README, SMOKE_CHECKLIST.md
- State file path `.claude/self-improve-state.md` consistent
- Status enum `merged | deferred | skipped-tests-failed | skipped-review-rejected | skipped-too-big | skipped-other` consistent across SKILL.md Step 11, Error handling table, State file schema
- Category tuple `("feature", "next", "forward")` in static-check test matches words in the new description (`feature`, `next`, `forward`)
- LOC cap "500 added/modified lines in the diff" and per-file cap "8 files touched in the diff" phrased consistently across SKILL.md Error handling table, Safety rails, and SMOKE_CHECKLIST.md

**Deferred to future work (per spec §8):**
- Plan-file archival strategy
- Multi-PR feature decomposition (vs `skipped-too-big` abort)
- Cross-project memory
- Reactive-mode revival (`/self-improve reactive` subcommand)
- Cost telemetry
