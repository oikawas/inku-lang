#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${INKU_REMOTE:-ddl-server@pentala}"
REMOTE_ROOT="${INKU_REMOTE_ROOT:-~/inku-lang}"

rsync -av \
  --exclude='node_modules' \
  --exclude='.svelte-kit' \
  "${ROOT_DIR}/web/src/" \
  "${REMOTE}:${REMOTE_ROOT}/web/src/"

rsync -av \
  "${ROOT_DIR}/web/vite.config.ts" \
  "${ROOT_DIR}/web/BUILD_NUMBER" \
  "${REMOTE}:${REMOTE_ROOT}/web/"

ssh "${REMOTE}" "cd ${REMOTE_ROOT}/web && test ! -e routes && test ! -e lib && test ! -e app.html && test ! -e app.d.ts"
