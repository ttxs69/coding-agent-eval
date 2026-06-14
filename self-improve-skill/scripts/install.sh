#!/usr/bin/env bash
# Install the self-improve skill by symlinking to ~/.claude/skills/.
# Safe to re-run.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${HOME}/.claude/skills/self-improve"

mkdir -p "${HOME}/.claude/skills"

if [[ -L "${TARGET}" ]]; then
    echo "Removing existing symlink at ${TARGET}"
    rm "${TARGET}"
elif [[ -e "${TARGET}" ]]; then
    echo "ERROR: ${TARGET} exists and is not a symlink." >&2
    echo "       Remove it manually first, then re-run." >&2
    exit 1
fi

ln -s "${SKILL_DIR}" "${TARGET}"
echo "Installed: ${TARGET} -> ${SKILL_DIR}"
echo "Invoke with: /self-improve"
