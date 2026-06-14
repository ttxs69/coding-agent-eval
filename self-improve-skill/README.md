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
