#!/usr/bin/env bash
# Deploy the listings site's code: move the serving worktree to a commit
# (default origin/master), sync its venv, restart the service, and roll back
# to the previous commit if the health check fails. Data is published
# separately (python -m apartments.site build); see docs/site.md.
set -euo pipefail

REPO=${REPO:-/home/ben/code/apartments}
SERVE=${SITE_SERVE:-/data1/apartments/serve/site}
VENV=${SITE_VENV:-/data1/apartments/venvs/serve-site}
UNIT=apartments-site.service
HEALTH=${SITE_HEALTH_URL:-http://127.0.0.1:8600/healthz}
REF=${1:-origin/master}

git -C "$REPO" fetch -q origin master
if [ ! -e "$SERVE/.git" ]; then
  git -C "$REPO" worktree add -q --detach "$SERVE" "$REF"
fi
previous=$(git -C "$SERVE" rev-parse HEAD)

install() {
  git -C "$SERVE" checkout -q --force --detach "$1"
  # --locked: never rewrite uv.lock in the serving worktree; base dependencies only.
  (cd "$SERVE" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --locked -q)
  systemctl --user restart "$UNIT"
}

healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS -m 2 "$HEALTH" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

install "$REF"
if healthy; then
  echo "deployed $(git -C "$SERVE" rev-parse --short HEAD): $(curl -fsS "$HEALTH")"
  exit 0
fi
echo "health check failed at $(git -C "$SERVE" rev-parse --short HEAD); rolling back to ${previous:0:7}" >&2
journalctl --user -u "$UNIT" -n 20 --no-pager >&2 || true
install "$previous"
healthy && echo "rolled back to ${previous:0:7}" >&2
exit 1
