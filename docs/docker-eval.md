# Docker-Mode Eval Results

This document records the results of running real agents end-to-end inside
Docker, in order of increasing task difficulty.

## Setup

1. **Docker image:** `pae/eval:linux` (built from `Dockerfile.eval` in the repo root).
   Python 3.11 + Node 20 + Claude Code CLI 2.1.168 + Codex CLI 0.137.0, all
   installed as the `pae` user (uid 1000) so the agents don't refuse to run
   as root.
2. **Auth:** Both agents' config/auth dirs are bind-mounted from the host
   into the container:
   - Claude Code: `ANTHROPIC_AUTH_TOKEN` env var via `--env-file env/auth.env`
   - Codex: `--network=host` (to reach the host's local LLM proxy) +
     bind-mount of `~/.codex/` (so the OAuth token + config.toml travel
     with the container). Codex's `config.toml` is sanitized to drop
     hardcoded `/Users/...` paths that don't exist in the container.

## Invocation

```bash
# Claude Code
pae run --agent claude-code --task <id> \
    --tasks-dir tasks --results-dir results \
    --docker --docker-image pae/eval:linux \
    --env-file env/auth.env

# Codex
pae run --agent codex --task <id> \
    --tasks-dir tasks --results-dir results \
    --docker --docker-image pae/eval:linux \
    --docker-network host \
    --docker-mount /tmp/codex-mount:/home/pae/.codex
```

## Results

| # | Task (bugs) | Agent | Status | Time | Cost | Notes |
|---|---|---|---|---|---|---|
| 1 | simple_tiny__fix-1 (1) | claude-code | ✅ resolved | 14.4s | $0.14 | |
| 2 | medium_strproc__fix-1 (3) | claude-code | ✅ resolved | 18.5s | $0.08 | |
| 3 | handcrafted__inventory-1 (6) | claude-code | ✅ resolved | 38.2s | $0.19 | |
| 4 | simple_tiny__fix-1 (1) | codex | ✅ resolved | 29.2s | — | cost not exposed in codex JSONL |
| 5 | medium_strproc__fix-1 (3) | codex | ✅ resolved | 36.9s | — | |
| 6 | handcrafted__inventory-1 (6) | codex | ✅ resolved | 92.2s | — | All 6 bugs fixed (vs 4/6 in local mode earlier) |

Both agents: **100% pass rate across all 3 difficulty levels in real docker mode.**

## Bugs fixed during this eval

1. **macOS binaries can't run in Linux container** — replaced with npm-installable
   Linux agents (the npm packages download the real Linux binaries).
2. **Claude Code refuses to run as root** — Dockerfile creates a non-root `pae` user.
3. **Auth not passed to container** — `--env-file` for env vars; `--docker-mount`
   for files (e.g. codex's `auth.json`).
4. **Network isolation blocks local proxies** — `--docker-network=host` lets
   codex reach the host's localhost.
5. **Host-specific config paths fail in container** — codex's `config.toml` has
   hardcoded `/Users/sarace/...` paths; sanitized before mounting.

## Files in this directory

- `Dockerfile.eval` — Dockerfile for the eval image
- `pae/eval:linux` — built image (run `docker build -f Dockerfile.eval -t pae/eval:linux .`)
- `pae run --docker*` — the CLI flags added in commit `3389d18`
