#!/bin/sh
# Run the eval: tasks in tasks/ x {agents}, in local mode.
#
# Usage:
#   sh scripts/run_eval.sh                              # all runnable tasks, all available agents
#   sh scripts/run_eval.sh 1                            # 1 runnable task, all available agents
#   sh scripts/run_eval.sh 4                            # first 4 runnable tasks, all available agents
#   sh scripts/run_eval.sh 1 claude-code                # 1 task, one specific agent
#   sh scripts/run_eval.sh 4 claude-code,codex          # 4 tasks, comma-separated list
#   sh scripts/run_eval.sh --all-broken                 # include tasks with malformed test IDs
#   sh scripts/run_eval.sh --small                      # alias for 4
#   sh scripts/run_eval.sh --help                       # show usage
#
# Tasks with malformed test IDs (a known SWE-bench data quality issue)
# are skipped by default — pre-flight catches them as task_error anyway,
# so excluding them saves API spend. Use `--all-broken` to opt in.
#
# Agent selection: by default, the script auto-detects all installed
# non-mock agents via `cae list-agents`. Pass a comma-separated list
# to override. The mock adapter is always excluded (test-only).
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

# Pre-arg: --all-broken flag (parsed by shifting past it).
INCLUDE_BROKEN=0
while [ "${1:-}" = "--all-broken" ] || [ "${1:-}" = "--all" ]; do
  case "$1" in
    --all-broken|--all) INCLUDE_BROKEN=1 ;;
  esac
  shift
done

# First non-flag arg: task count (or --small / --help).
LIMIT=""
case "${1:-}" in
  "")
    LIMIT=99999  # set later from total count
    ;;
  --small)
    LIMIT=4
    ;;
  -h|--help)
    sed -n '2,29p' "$0"
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

# Discover tasks. We use `cae list-tasks` to enumerate them and pick up
# the broken/runnable status in one pass (saves a separate stat walk).
LIST_OUT=$(uv run cae list-tasks 2>/dev/null)
TASKS_RUNNABLE=$(echo "$LIST_OUT" | awk 'NR > 1 && $1 != "" && !/\[BROKEN\]/ {print $1}')
TASKS_BROKEN=$(echo "$LIST_OUT" | awk 'NR > 1 && $1 != "" && /\[BROKEN\]/ {print $1}')
N_RUNNABLE=$(echo $TASKS_RUNNABLE | wc -w | tr -d ' ')
N_BROKEN=$(echo $TASKS_BROKEN | wc -w | tr -d ' ')

if [ "$INCLUDE_BROKEN" = 1 ]; then
  TASKS_ALL="$TASKS_RUNNABLE $TASKS_BROKEN"
  log "Including $N_BROKEN broken task(s) (use without --all-broken to skip)"
else
  TASKS_ALL="$TASKS_RUNNABLE"
  if [ "$N_BROKEN" -gt 0 ]; then
    log "Skipping $N_BROKEN broken task(s) with malformed test IDs (use --all-broken to include)"
  fi
fi
TOTAL_TASKS=$(echo $TASKS_ALL | wc -w | tr -d ' ')

# Default count = all available.
if [ "$LIMIT" = 99999 ]; then
  LIMIT="$TOTAL_TASKS"
fi

if [ "$LIMIT" -gt "$TOTAL_TASKS" ]; then
  log "Requested $LIMIT tasks but only $TOTAL_TASKS available; using $TOTAL_TASKS"
  LIMIT=$TOTAL_TASKS
fi

# Second arg: comma-separated agent list. Default: auto-detect.
AGENTS_ARG="${2:-}"
if [ -z "$AGENTS_ARG" ]; then
  # `cae list-agents` prints:
  #   NAME                 AVAILABLE
  #   mock                 True
  #   claude-code          True
  #   ...
  # We want every non-mock agent whose AVAILABLE column is True.
  AGENTS=$(uv run cae list-agents 2>/dev/null | awk '
    NR > 1 && $1 != "mock" && $2 == "True" {print $1}
  ')
  if [ -z "$AGENTS" ]; then
    echo "error: no agents available. Run 'cae list-agents' to debug." >&2
    exit 1
  fi
  log "Auto-detected agents: $AGENTS"
else
  AGENTS=$(echo "$AGENTS_ARG" | tr ',' ' ' | tr -s ' ')
  # Validate each agent exists in the registry. We don't enforce
  # availability here — a missing CLI binary will surface as agent_error
  # in the result, which is the right diagnostic.
  for a in $AGENTS; do
    if ! uv run cae list-agents 2>/dev/null | awk -v a="$a" 'NR>1 && $1==a {found=1} END{exit !found}'; then
      echo "error: unknown agent '$a'. Run 'cae list-agents' to see available." >&2
      exit 2
    fi
  done
fi

# Take the first $LIMIT tasks.
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
N_AGENTS=$(echo $AGENTS | wc -w | tr -d ' ')
log "Starting eval: $N_TASKS task(s) x $N_AGENTS agent(s) = $((N_TASKS * N_AGENTS)) runs"
log "Tasks: $TASKS"
log "Agents: $AGENTS"

# Run all tasks for the first agent, then all tasks for the second agent,
# etc. Two-agent (or N-agent) ordering means we see one agent's cost
# roll up before the next agent starts.
for agent in $AGENTS; do
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
