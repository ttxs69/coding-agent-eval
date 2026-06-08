#!/bin/sh
# Run the eval: tasks in tasks/ x {claude-code, codex}, in local mode.
#
# Usage:
#   sh scripts/run_eval.sh           # all tasks
#   sh scripts/run_eval.sh 1         # first task only (cheap e2e test)
#   sh scripts/run_eval.sh 4         # first 4 tasks
#   sh scripts/run_eval.sh --small   # alias for 4
#
# The harness skips any (task, agent) pair whose result JSON already exists,
# so this is safe to re-run after an interruption. Use --force on the cae
# invocation to overwrite.
#
# Logs to results/eval.log. Each run prints "RUN start" / "RUN done" lines
# with timestamps so you can tail -f to follow progress.
#
# Written for POSIX sh (not bash) so it works regardless of which shell
# the harness invokes. Uses `uv run` so the venv's cae/pytest is on PATH
# without needing a manual `source .venv/bin/activate`.
set -u
cd "$(dirname "$0")/.."

# Make sure deps are installed (idempotent; no-op if already synced).
uv sync --extra dev --extra astropy-build >/dev/null 2>&1

# CFLAGS for old astropy's Cython-generated C: -Wincompatible-function-pointer-types
# was promoted to an error by newer Clang, but the old wcslib wrappers trigger it
# (the C API for tp_traverse/tp_clear changed in Python 3.9+).
CFLAGS="-Wno-incompatible-function-pointer-types -Wno-error=incompatible-function-pointer-types -Wno-implicit-function-declaration"
export CFLAGS

LOG=results/eval.log
mkdir -p results

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" | tee -a "$LOG"
}

# Discover tasks from the tasks/ dir (each subdir is one instance), sorted.
# Capture into a positional-parameter list so we don't need bash arrays.
TASKS_ALL=""
for d in tasks/*/; do
  [ -d "$d" ] || continue
  TASKS_ALL="$TASKS_ALL $(basename "$d")"
done
TOTAL_TASKS=$(echo $TASKS_ALL | wc -w | tr -d ' ')

# Argument parsing: optional count (or --small).
LIMIT=""
case "${1:-}" in
  "")
    LIMIT="$TOTAL_TASKS"
    ;;
  --small)
    LIMIT=4
    ;;
  -h|--help)
    sed -n '2,15p' "$0"
    exit 0
    ;;
  --*)
    echo "error: unknown flag $1" >&2
    exit 2
    ;;
  *)
    if ! [ "$1" -eq "$1" ] 2>/dev/null || [ "$1" -lt 1 ]; then
      echo "error: task count must be a positive integer, got '$1'" >&2
      exit 2
    fi
    LIMIT=$1
    ;;
esac

if [ "$LIMIT" -gt "$TOTAL_TASKS" ]; then
  log "Requested $LIMIT tasks but only $TOTAL_TASKS available; using $TOTAL_TASKS"
  LIMIT=$TOTAL_TASKS
fi

# Take the first $LIMIT tasks (alphabetical order, same as `ls`).
N=0
TASKS=""
for t in $TASKS_ALL; do
  N=$((N + 1))
  if [ "$N" -gt "$LIMIT" ]; then
    break
  fi
  TASKS="$TASKS $t"
done
TASKS=${TASKS# }  # strip leading space

N_TASKS=$(echo $TASKS | wc -w | tr -d ' ')
N_AGENTS=2
log "Starting eval: $N_TASKS task(s) x $N_AGENTS agents = $((N_TASKS * N_AGENTS)) runs"
log "Tasks: $TASKS"

# Run all claude-code first, then all codex. Two-agent ordering means we
# see one agent's cost roll up before the next agent starts (easier to read).
for agent in claude-code codex; do
  for task in $TASKS; do
    log "RUN start: $agent / $task"
    uv run cae run \
        --agent "$agent" \
        --task "$task" \
        --tasks-dir tasks \
        --results-dir results \
        --timeout 30 \
        >> "$LOG" 2>&1
    rc=$?
    log "RUN done:  $agent / $task (rc=$rc)"
  done
done

log "All runs complete"
uv run cae report --results-dir results --format table | tee -a "$LOG"
