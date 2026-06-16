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
