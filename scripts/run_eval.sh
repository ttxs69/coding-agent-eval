#!/bin/sh
# Run the full eval: every task in tasks/ x {claude-code, codex}, in local mode.
#
# The harness skips any (task, agent) pair whose result JSON already exists,
# so this is safe to re-run after an interruption. Use --force on the cae
# invocation to overwrite existing results.
#
# Logs to results/eval.log. Each run prints "RUN start" / "RUN done" lines
# with timestamps so you can tail -f to follow progress.
#
# Written for POSIX sh (not bash) so it works regardless of which shell
# the harness invokes.
set -u
cd "$(dirname "$0")/.."
. .venv/bin/activate

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

# Count tasks.
N_TASKS=$(ls -1d tasks/*/ 2>/dev/null | wc -l | tr -d ' ')
N_AGENTS=2

log "Starting eval: $N_TASKS tasks x $N_AGENTS agents = $((N_TASKS * N_AGENTS)) runs"

# Run all claude-code first, then all codex. Two-agent ordering means we
# see one agent's cost roll up before the next agent starts (easier to read).
for agent in claude-code codex; do
  for task_dir in tasks/*/; do
    [ -d "$task_dir" ] || continue
    task=$(basename "$task_dir")
    log "RUN start: $agent / $task"
    cae run \
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
cae report --results-dir results --format table | tee -a "$LOG"
