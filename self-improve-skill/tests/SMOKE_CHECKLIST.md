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
