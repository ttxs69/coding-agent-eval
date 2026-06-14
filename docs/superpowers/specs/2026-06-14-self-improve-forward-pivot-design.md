# Self-Improve Skill — Forward Pivot Design

**Date:** 2026-06-14
**Status:** Approved (pending spec review)
**Replaces:** `docs/superpowers/specs/2026-06-14-self-improve-skill-design.md` (v1, reactive mode)
**Deliverable:** a major revision of the existing user-level `self-improve` skill that pivots from **reactive** (scan for issues, fix them) to **forward** (infer next features from project artifacts, implement the one the user picks). Same skill name, same install path, same workflow shape — but the scan phase, candidate category, and approval gates change substantially.

## 1. Problem & purpose

The v1 self-improve skill was purely reactive — it scanned for bugs, missing tests, refactors, doc gaps, and fixed them. On a clean, well-maintained codebase it produces little value (the first real run merged a single docstring commit and stopped).

The user wants the skill to **push the project forward** — implement the next feature, advance the roadmap, do work that grows the project rather than just defends it. Reactive maintenance is a narrow lane; forward progress is where most of the value of an autonomous coding agent actually lies.

This revision pivots the skill. Bug-fixing becomes incidental (a feature implementation can fix bugs along the way), not a separate scan target. The skill's primary job is now: read the project's artifacts, infer what features come next, ask the user to pick, then implement on an isolated branch with verification and a merge gate.

## 2. Architecture

### 2.1 What changes from v1

- **Skill name & location:** unchanged — `self-improve` at `~/.claude/skills/self-improve/`
- **Skill purpose:** reactive → forward. Scan-for-issues → infer-next-features.
- **Bug handling:** no longer a primary candidate category. Incidental fixes during feature implementation are allowed; standalone bug-fix candidates are not generated.
- **Approval:** one gate (merge) → **two gates** (propose-pick + merge). The new pre-implementation gate exists because inferred features are higher-uncertainty than reactive fixes — the user must explicitly pick the feature before any code is written.
- **State file:** same path. Old reactive entries (category `bug`/`docs`/etc.) remain in the file for history but are **ignored** for forward-candidate matching. No migration step.

### 2.2 SKILL.md frontmatter (updated)

```yaml
---
name: self-improve
description: Use when the user wants to proactively push a project forward by implementing its next feature. Reads project artifacts (specs' "future work" sections, README, TODOs, recent commit trajectory, codebase gaps), infers candidate features, asks the user to pick one, then implements it on an isolated branch with verification + review + merge-gate. Triggered by /self-improve or phrases like "implement next feature", "push project forward", "evolve".
---
```

### 2.3 Runtime artifacts (unchanged location)

- `.claude/self-improve-state.md` — tracks proposed / picked / merged features. Old reactive entries preserved but ignored.
- Worktrees under `.claude/worktrees/<slug>/` (same path as v1).
- Branches: `self-improve/feature/<slug>-<ts>` (e.g., `self-improve/feature/gemini-adapter-20260614-110000`). Branch prefix changes from `<category>` to always `feature` since there's only one candidate category now.

### 2.4 File structure (unchanged)

```
~/.claude/skills/self-improve/
├── SKILL.md
└── references/
    └── inference-signals.md   # optional split-out for scan signal detail
```

Single SKILL.md for v2 — same 400-line threshold for splitting as v1.

## 3. Workflow

Same per-iteration shape as v1, with **two gates** instead of one.

### 3.1 Per-run setup (once)

1. Read `.claude/self-improve-state.md`. **Existing reactive entries ignored** for matching — only `feature`-category entries count toward "already tried".
2. Verify working tree is clean: if dirty, refuse to start, tell user to commit/stash.
3. Ensure gitignore entries are present (same as v1 — append `.claude/self-improve-state.md`, `.claude/self-improve-state.md.tmp`, `.claude/worktrees/` if missing).

### 3.2 Per-iteration steps

1. **Scan artifacts for forward signals** — read:
   - `docs/superpowers/specs/*.md` — "future work" / "out of scope" / "open questions" sections
   - `README.md` — planned features / roadmap / "not yet implemented" notes
   - `TODO: implement X` / `FIXME: add Y` comments that look forward (not bug-fix)
   - Recent commit trajectory (last ~20 commits — themes, what's been built → natural next step)
   - Codebase structure gaps (e.g., "agents exist for X/Y/Z but not W" — clear parallel-pattern gap)
   - Issue tracker, if `gh` is available and the project is a GitHub repo (`gh issue list --state open`)

2. **Infer N candidates** (default **3**) — synthesize signals into concrete feature candidates. Each candidate gets:
   - **Title** (one line)
   - **Source** (which artifact(s) motivated it — for traceability)
   - **Scope estimate** (LOC range, "single PR worth" = ~50–300 LOC)
   - **Why-now** (why this is the right next step vs the other candidates)
   - **Risk** (low / medium / high — based on LOC, files touched, blast radius, deps, breaking changes)

3. **Propose + user picks** ← **GATE 1** — use `AskUserQuestion` with the N candidates + a "none of these, re-scan" option + a "stop" option. User picks one or stops.

4. **Isolate** — `superpowers:using-git-worktrees`. Worktree at `.claude/worktrees/<slug>`, branch `self-improve/feature/<slug>-<ts>`.

5. **Draft a brief plan** — write a plan to `docs/superpowers/plans/<YYYY-MM-DD>-<feature-slug>.md` with 5–15 tasks (smaller for small features, larger for big ones). Use `superpowers:writing-plans` skill. **Not a separate approval gate** — the user already picked the feature. If they want to abort after seeing the plan, they interrupt.

6. **Implement** — invoke `superpowers:test-driven-development` for the test+code work. For larger features (>200 LOC estimated), dispatch via `superpowers:subagent-driven-development` against the plan from step 5. May use `superpowers:systematic-debugging` if a bug surfaces during implementation (incidental bug-fixing is allowed).

7. **Verify** — `superpowers:verification-before-completion`. Run affected tests + full suite if cheap + linters. **No claiming success without evidence** — paste actual command output.

8. **Review** — `superpowers:requesting-code-review` (or project's `/code-review` skill if available). Fallback to inline self-review against the 4-point checklist (correctness, regressions, scope creep, security) if neither is available.

9. **Commit** — `superpowers:finishing-a-development-branch` for guidance. Conventional-commit message:

   ```
   feat(<scope>): <summary>

   Self-improve feature: <one-line rationale linking back to source artifact>

   [body explaining the change]

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   ```

10. **Offer merge** ← **GATE 2** — same three options as v1: `merge` (FF if possible, else `--no-ff`, no push without explicit ask, then delete worktree + branch), `defer`, `skip`.

11. **Record** — update `.claude/self-improve-state.md`:
    - All proposed candidates (including unpicked) go to *Proposed but not picked*
    - The picked + implemented candidate goes to *Attempted* with status
    - If user said "never propose this kind", move to *Permanently Rejected*

12. **Loop or stop** — check stopping criteria (§4). If continuing, re-scan from step 1.

### 3.3 End of run

Same summary format as v1 — N iterations, M branches created, X merged, Y deferred, Z skipped. Adds: "P proposals recorded (won't be re-proposed)".

## 4. Stopping criteria, error handling, safety rails

### 4.1 Stopping criteria (any one triggers end-of-run)

1. User picks **"stop"** at the propose gate (Gate 1).
2. **Re-scan loop limit** — user picks "none of these, re-scan" **3 times** consecutively without picking a candidate. Skill is generating things the user doesn't want — stop and surface the issue.
3. **Max iterations** — default **10** (configurable: `self-improve max=20`).
4. **3 consecutive failures** — counts: `skipped-tests-failed`, `skipped-review-rejected` (after retry), `skipped-too-big` (implementation exceeded LOC cap), `skipped-other`. A `merged` or `deferred` resets the counter.
5. **Token budget** — default **500K total** (configurable: `self-improve budget=1M`).
6. **Wall-clock budget** — default **30 min**.
7. **User interrupts** (Ctrl-C / Escape).

### 4.2 Error handling per candidate

| Failure | Action | State status |
|---|---|---|
| Working tree dirty at start | Refuse to start, tell user to commit/stash | (no entry) |
| Inference produces 0 candidates | Tell user, stop the run | (no entry) |
| Plan-writing fails | Log, skip candidate, continue | `skipped-other` |
| Implementation exceeds LOC cap (default **500 added/modified lines in the diff**) | Abort, leave worktree for inspection, record | `skipped-too-big` |
| Implementation exceeds per-file cap (default **8 files touched**) | Abort, leave worktree, record | `skipped-too-big` |
| Implementation violates a safety rail (e.g., needs new dep on a "low risk" candidate, attempts schema change, attempts breaking API change) | Abort, leave worktree, record | `skipped-other` (with policy-violation note in summary) |
| Tests fail after implement | Revert worktree, continue | `skipped-tests-failed` |
| Review rejects (after one retry) | Leave worktree for inspection, continue | `skipped-review-rejected` |
| Merge conflict during merge step | Abort merge, leave branch for manual review | `deferred` |
| State file missing/corrupt | Warn, start fresh | (reset) |

**Interrupt handling:** On Ctrl-C / Escape, clean up current worktree (try/finally), write partial state, print summary.

### 4.3 Safety rails

Inherited from v1:
- **Never touch:** `.git/`, user config under `.claude/` (settings, commands, skills, agents, hooks, plugins) except the skill's own artifacts; `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `dist/`, `build/`, lockfiles (unless candidate is explicitly `deps`).
- **No external-state mutations:** refuse `git push`, `npm publish`, `terraform apply`, `docker push`, etc.
- **Worktree cleanup always runs** (try/finally).

**New for forward mode:**
- **No new dependencies without explicit user approval.** If a feature would require adding a runtime dep, the candidate's `Risk` field notes "adds dependency X". The implement step does NOT edit `pyproject.toml` / `package.json` unless the user explicitly picked that candidate (picking a candidate with a noted dep risk authorizes the dep addition).
- **No schema/migration changes.** Database schemas, file formats, on-disk state — off-limits unless the candidate description explicitly called for one AND the user picked it knowing that.
- **No breaking API/CLI contract changes** for "low risk" candidates. If a feature would change a public API signature, CLI flag, or output format in a backward-incompatible way, that goes in the candidate's `Risk` field as "breaking". The implement step refuses to make breaking changes for a "low risk" candidate.
- **Per-feature LOC cap (default 500 added/modified lines in the diff).** Implementation that exceeds this is auto-aborted as `skipped-too-big` — the feature needs decomposition into smaller milestones, which is out of scope for one iteration.
- **Per-file change cap (default 8 files touched in the diff).** Prevents touching too many files in one feature.

### 4.4 The propose-gate candidate format

Each candidate presented at Gate 1 includes a **risk callout** if any safety rail would apply:

```
Title: Add Gemini CLI adapter
Source: docs/adding-agents.md mentions the pattern; cae/agents/ has 3 adapters but no Gemini
Scope: ~180 LOC (1 new file + 1-line registration)
Why-now: closes a measurable leaderboard gap (Gemini is the only major CLI agent missing)
Risk: medium — adds a new runtime dep (google-generativeai SDK)
```

The user picks knowing the risk. If they pick a "medium — adds dep" candidate, the implement step is authorized to add the dep. If they pick a "low risk" candidate, the implement step refuses to add deps and aborts with `skipped-other` (policy-violation note in summary) if it turns out to need one.

## 5. State file

### 5.1 Location & format

- **Path:** `.claude/self-improve-state.md` (unchanged from v1)
- **Format:** plain markdown (unchanged)
- **Lifecycle:** created on first run; updated at propose-gate AND at record-step; safe to delete.
- **Gitignore:** already gitignored by per-run setup step.

### 5.2 Schema

````markdown
# Self-Improve State

Tracks candidates the workflow has considered, so repeated runs don't redo work.
Safe to delete — workflow will recreate.

## Attempted

One line per attempt: `<iso-ts> | <category> | <branch> | <status> | <summary>`

Categories: `feature` (forward mode). Legacy categories (`bug`, `tests`, `refactor`, `docs`, `deps`, `perf`, `security`) may appear in older entries and are **ignored for matching**.

Statuses: `merged` | `deferred` | `skipped-tests-failed` | `skipped-review-rejected` | `skipped-too-big` | `skipped-other`

- 2026-06-14T11:00:00Z | feature | self-improve/feature/gemini-adapter-20260614-110000 | merged | Added Gemini CLI adapter (cae/agents/gemini.py, 180 LOC, +1 dep)
- 2026-06-14T11:15:00Z | feature | self-improve/feature/per-agent-cost-chart-20260614-111500 | deferred | Per-agent cost chart on site (3 files touched)

## Proposed but not picked

Every candidate surfaced at the propose gate gets recorded here, even if user didn't pick it. Prevents re-proposing the same idea next run.

Format: `<iso-ts> | <summary> | <user-reason-or-empty>`

- 2026-06-14T11:00:00Z | Add Cargo (Rust) agent support | user picked Gemini instead
- 2026-06-14T11:00:00Z | Add per-task perf regression check | (no reason given)

## Permanently Rejected

User explicitly said "never propose this kind of feature". Format: `- <summary> — <reason>. Decided <date>.`

- Pin pytest to <8 — won't fix; conflicts with astropy-build extra. Decided 2026-06-13.
````

### 5.3 How the workflow uses it

- **Start of run:** read state file (missing → treat as empty).
- **At propose gate (Gate 1):** filter out anything in *Attempted* (category=feature only), *Proposed but not picked*, or *Permanently Rejected*. The candidate list is what remains.
- **After user picks:** record ALL proposed candidates to *Proposed but not picked* with the user's reason where given. The picked one stays out of this section — it goes to *Attempted* via the Record step.
- **At Record (Step 11):** append the picked+implemented candidate to *Attempted* with appropriate status. If user said "never propose this kind", move to *Permanently Rejected*.

### 5.4 Legacy entries

Old reactive entries (category `docs`/`bug`/`tests`/etc.) remain in the file for history but are **ignored by the matching logic**. No migration step. If the file becomes cluttered, the user can delete it and start fresh (skill recreates from scratch).

### 5.5 Atomic writes & matching

- **Atomic writes:** write to `.claude/self-improve-state.md.tmp`, then atomic rename. (Unchanged.)
- **Same-candidate matching:** fuzzy. Match on title similarity + file list + intent. Same idea phrased differently = same candidate.

## 6. Testing & verification

The pivot from reactive to forward changes what the fixture needs to validate. Same test scaffolding, different seeds.

### 6.1 Static checks (mostly unchanged)

`self-improve-skill/tests/test_static_checks.py` keeps doing the same 6 checks. Only the description text changes — trigger words like `self-improve` / `improve` / `evolve` stay; the category-words assertion shifts from `bug`/`test`/`refactor` to `feature`/`next`/`forward`.

### 6.2 Fixture project (repurpose, not replace)

Same fixture at `tests/fixtures/self-improve-sample-project/`. **Add forward signals** alongside the existing reactive ones (the reactive seeds become inert — forward mode doesn't scan for them, but they don't hurt).

New forward signals to add:
- **`docs/superpowers/specs/<date>-sample-design.md`** with a `## Future work` section explicitly listing 2 features (e.g., "Add subtraction function", "Add exponentiation")
- **`README.md`** gets a `## Planned features` section listing 1–2 features
- **Forward-looking TODO** in `src/sample/__init__.py` — change one of the existing TODOs to e.g. `TODO: implement divide() — pairs with add/multiply but missing` (forward-looking, parallel-pattern gap)
- **Clear codebase gap** — add a 3rd function that calls a 4th that doesn't exist, or add classes for `Cat`/`Dog`/`Bird` and a docstring referencing a missing `Fish`

The fixture's existing bug in `add()` stays — forward-mode tests don't care about it, but it doesn't hurt. (Removing it would mean updating `test_sample.py` to not fail, which is more churn than it's worth.)

### 6.3 Validation tests (update)

`self-improve-skill/tests/test_fixture_project.py` gets new assertions alongside the existing ones:

- `test_fixture_has_future_work_section` — the design spec at `docs/superpowers/specs/<date>-sample-design.md` exists and mentions "Future work" or equivalent
- `test_fixture_has_planned_features_in_readme` — README's "Planned features" section exists and lists ≥1 feature
- `test_fixture_has_forward_looking_todo` — a `TODO: implement ...` comment exists
- `test_fixture_has_codebase_gap` — the parallel-pattern gap is present (e.g., 3 of something, reference to a missing 4th)

The existing `test_fixture_test_command_fails_on_seeded_bug` is **kept** — forward mode's implement-step still runs tests and needs to detect failures, so the regression-test for that machinery stays useful. Existing bug/duplication/docstring checks can be kept or removed depending on whether the seeds stay in the fixture.

### 6.4 Smoke checklist (rewrite for two-gate flow)

`self-improve-skill/tests/SMOKE_CHECKLIST.md` is rewritten to walk through forward mode:

- **Setup:** install, start session in fixture, `git init`
- **Inference:** invoke `/self-improve`, verify skill reads specs/README/TODOs/commits and surfaces 3 candidates
- **Gate 1 (propose):** verify each candidate has title/source/scope/why-now/risk; user picks one
- **Implementation:** worktree created, brief plan written, TDD followed, tests pass, linter clean, review runs, commit on branch
- **Gate 2 (merge):** three-option prompt (merge/defer/skip) works correctly for each path
- **State file:** updated with feature entry; unpicked candidates in "Proposed but not picked"; gitignored
- **Re-run behavior:** second invocation does NOT re-propose previously-surfaced candidates
- **Edge cases:** dirty tree refuses; re-scan 3× stops; Ctrl-C cleans up; LOC cap aborts as `skipped-too-big`

### 6.5 Out of scope for v2 testing

- Automated testing of inference quality (would require fixture with known "right answer" features — brittle)
- Cross-project inference regression tests (forward mode is inherently fuzzy)
- Plan-file content validation (plans are freeform)

## 7. Migration from v1

### 7.1 Files that change

- `self-improve-skill/SKILL.md` — rewritten end-to-end (new description, new workflow, new safety rails)
- `self-improve-skill/README.md` — updated to describe forward mode
- `self-improve-skill/tests/test_static_checks.py` — `test_description_mentions_categories` updates the category tuple
- `self-improve-skill/tests/test_fixture_project.py` — adds forward-signal validations (existing reactive ones can stay as the seeds stay)
- `self-improve-skill/tests/SMOKE_CHECKLIST.md` — rewritten for two-gate flow
- `tests/fixtures/self-improve-sample-project/` — add forward signals (spec file, README section, forward TODO, codebase gap); existing seeds stay

### 7.2 Files that don't change

- `self-improve-skill/scripts/install.sh` — symlink mechanism unchanged
- `.gitignore` — patterns unchanged
- `tests/fixtures/self-improve-sample-project/pyproject.toml` — fixture's package metadata unchanged

### 7.3 What happens to existing `.claude/self-improve-state.md`

Per the user's "fresh start, ignore old state" decision: existing entries are **ignored** by the matching logic (anything not category=`feature` is skipped), but not migrated or deleted. Old reactive entries sit in the file as history. If the user wants a clean file, they delete it; skill recreates.

## 8. Open questions / future work

- **Plan-file persistence.** Each iteration writes a plan to `docs/superpowers/plans/`. Over time this accumulates. Future: auto-archive plans older than N days, or move them to a `completed/` subdir post-merge.
- **Multi-PR features.** Features that exceed the 500-LOC cap are aborted as `skipped-too-big`. Future: skill could decompose into a milestone (multiple planned iterations) instead of just aborting.
- **Cross-project memory.** Like v1, state is per-project. A user-level "feature patterns I always reject" memory could prevent re-proposing the same kinds of features everywhere.
- **Reactive-mode revival.** Some users may want both modes. Future: an opt-in `/self-improve reactive` subcommand to invoke the old bug-sweep behavior.
- **Cost telemetry.** Track $ spent per run and per feature, surface in end-of-run summary.

## 9. Out of scope for v2

- **Auto-PR creation** via `gh pr create` (unchanged from v1).
- **CI integration** (unchanged from v1).
- **Multi-repo orchestration** (unchanged from v1).
- **Milestone/multi-iteration planning** (deferred to future skill per §8).
- **Judgment-driven inference** beyond artifact signals (Approach B from brainstorming — deferred).
