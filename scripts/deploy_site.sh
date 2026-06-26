#!/bin/sh
# Build and deploy the leaderboard site to GitHub Pages, non-destructively.
#
# The site lives on the `gh-pages` branch (separate from main). It's a
# static artifact built by `cae build-site` from results/*.json. The
# deployed data/details/ accumulates over time — old eval runs that no
# longer exist in local results/ SHOULD stay published (otherwise we'd
# silently rewrite leaderboard history every time results/ was cleaned).
#
# This script:
#   1. Builds the site from local results/ into a fresh out-dir.
#   2. Creates a worktree on origin/gh-pages.
#   3. rsyncs the new build INTO the worktree WITHOUT --delete — files
#      already on gh-pages that aren't in this build (e.g. historical
#      result details from previous evals) are preserved.
#   4. Commits + force-pushes-with-lease.
#
# To forcibly remove stale files from gh-pages (e.g. a wrongly-published
# run), edit the worktree manually or pass --delete to rsync locally —
# don't make destructive deploys the default.
#
# Usage:
#   sh scripts/deploy_site.sh                 # build from results/, deploy
#   sh scripts/deploy_site.sh --dry-run       # build + rsync, skip commit/push
#   sh scripts/deploy_site.sh --results-dir /path/to/other/results
#   sh scripts/deploy_site.sh --out-dir /tmp/site  # build only, no deploy
#
# Requires: rsync, git, uv, gh-pages branch on origin.
set -eu

RESULTS_DIR=results
OUT_DIR=site
DRY_RUN=0
WORKTREE_DIR=""

# Parse args.
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)      DRY_RUN=1; shift ;;
    --results-dir)  RESULTS_DIR="$2"; shift 2 ;;
    --out-dir)      OUT_DIR="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "error: unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

cd "$(dirname "$0")/.."

# 1. Build the site. --include-archive pulls every data/details/*.json ever
#    published to origin/gh-pages and merges it with local results/ (local
#    wins on duplicate run_id) so the leaderboard doesn't shrink across
#    deploys. Costs a git fetch per build.
echo "[deploy] building site from $RESULTS_DIR → $OUT_DIR"
uv run cae build-site --results-dir "$RESULTS_DIR" --out-dir "$OUT_DIR" --include-archive

# Out-dir without deploy: stop here.
if [ "$OUT_DIR" != "site" ] && [ "$DRY_RUN" = 1 ]; then
  echo "[deploy] --out-dir + --dry-run: build done, skipping deploy"
  exit 0
fi

# 2. Fetch latest gh-pages + worktree it.
echo "[deploy] fetching origin/gh-pages"
git fetch origin gh-pages --quiet
WORKTREE_DIR=$(mktemp -d /tmp/gh-pages-deploy-XXXX)
trap '[ -n "$WORKTREE_DIR" ] && git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true; rm -rf "$WORKTREE_DIR"' EXIT
echo "[deploy] worktree at $WORKTREE_DIR"
git worktree add --force --detach "$WORKTREE_DIR" origin/gh-pages >/dev/null

# 3. rsync new build into worktree WITHOUT --delete (preserve historical files).
#    Trailing slashes matter: "$OUT_DIR/" means "contents of", not the dir itself.
echo "[deploy] rsync $OUT_DIR/ → $WORKTREE_DIR/ (no --delete; history preserved)"
rsync -a --no-times --omit-dir-times "$OUT_DIR/" "$WORKTREE_DIR/"

# Count what would change.
CHANGED=$(cd "$WORKTREE_DIR" && git status --porcelain | wc -l | tr -d ' ')
if [ "$CHANGED" = "0" ]; then
  echo "[deploy] no changes; gh-pages already up to date"
  exit 0
fi
echo "[deploy] $CHANGED file(s) changed:"
(cd "$WORKTREE_DIR" && git status --short | head -20)

if [ "$DRY_RUN" = "1" ]; then
  echo "[deploy] --dry-run: not committing or pushing"
  exit 0
fi

# 4. Commit + force-with-lease push.
SUBJECT="Deploy site: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
(
  cd "$WORKTREE_DIR"
  git add .
  git commit --quiet -m "$SUBJECT

Built by scripts/deploy_site.sh from $RESULTS_DIR/ ($(ls "$OLDPWD/$RESULTS_DIR"/*.json 2>/dev/null | wc -l | tr -d ' ') result files).
Non-destructive: existing gh-pages files not in this build are preserved.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
  git push --force-with-lease origin HEAD:gh-pages
)

echo "[deploy] pushed → gh-pages"
echo "[deploy] live: https://ttxs69.github.io/coding-agent-eval/"
