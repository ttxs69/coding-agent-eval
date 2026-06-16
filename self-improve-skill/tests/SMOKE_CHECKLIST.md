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
