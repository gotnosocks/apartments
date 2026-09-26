#!/usr/bin/env bash
# Deploy the listings site's code: move the serving worktree to a commit
# (default origin/master), sync its venv, restart the service and check
# /healthz. If any step fails (checkout, uv sync, restart or the health
# check), roll back to the previous commit the same way. Data is published
# separately (python -m apartments.site build). The first deploy follows the
# bootstrap in docs/site.md: the unit and a published build must exist first.
set -euo pipefail

REPO=${REPO:-/home/ben/code/apartments}
SERVE=${SITE_SERVE:-/data1/apartments/serve/site}
VENV=${SITE_VENV:-/data1/apartments/venvs/serve-site}
UNIT=apartments-site.service
HEALTH=${SITE_HEALTH_URL:-http://127.0.0.1:8600/healthz}
REF=${1:-origin/master}

git -C "$REPO" fetch -q origin master
if [ ! -e "$SERVE/.git" ]; then
  echo "no serving worktree at $SERVE; bootstrap first (docs/site.md)" >&2
  exit 1
fi
previous=$(git -C "$SERVE" rev-parse HEAD)
target=$(git -C "$REPO" rev-parse --verify "$REF^{commit}")

# Each step is chained with &&: set -e is suspended inside a function called
# from an if, so a failure has to be passed on explicitly to reach the rollback.
install() {
  git -C "$SERVE" checkout -q --force --detach "$1" &&
    # --locked: never rewrite uv.lock in the serving worktree; base dependencies only.
    (cd "$SERVE" && UV_PROJECT_ENVIRONMENT="$VENV" uv sync --locked -q) &&
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

if install "$target" && healthy; then
  echo "deployed ${target:0:7}: $(curl -fsS "$HEALTH")"
  exit 0
fi
echo "deploy of ${target:0:7} failed; rolling back to ${previous:0:7}" >&2
journalctl --user -u "$UNIT" -n 20 --no-pager >&2 || true
if install "$previous" && healthy; then
  echo "rolled back to ${previous:0:7}" >&2
else
  echo "ROLLBACK FAILED: the site is down at ${previous:0:7}; see journalctl --user -u $UNIT" >&2
fi
exit 1
