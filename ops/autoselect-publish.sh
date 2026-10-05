#!/usr/bin/env bash
# Publish the served run after an autoselect switch has been merged and the
# site deployed (ops/site-deploy.sh): the rent map, then the estimate kit, then
# the site build, which bundles both and publishes the selection.
#
#   1. rent map    rentfrontier.rentmap  -> /data1/apartments/frontier/maps/<run>-<commit>/
#   2. kit         rentfrontier.kit      -> /data1/apartments/frontier/kits/<run>-<commit>/
#                  (the /estimate form; the site build finds it by the summary
#                  bundle's sha256, and without it the form says "not available")
#   3. site build  apartments.site build -> /data1/apartments/site/builds/<id>
#
# The run and its summary bundle come from the serving checkout's selection
# (config/main-analysis.json). Steps 1 and 2 run at the master checkout's
# commit (both refuse a dirty tree) as light jobs; an output that already
# exists for this run and commit is kept. Usage: ops/autoselect-publish.sh
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

MASTER=${MASTER:-/data1/apartments/serve/master}
SITE=${SITE_SERVE:-/data1/apartments/serve/site}
SITE_VENV=${SITE_VENV:-/data1/apartments/venvs/serve-site}
FRONTIER=${FRONTIER:-/data1/apartments/frontier}
export TMPDIR=${TMPDIR:-/data1/apartments/tmp} JAX_PLATFORMS=cpu XLA_PYTHON_CLIENT_PREALLOCATE=false

read -r RUN SUMMARY < <(python3 -c "
import json, sys
c = json.load(open(sys.argv[1]))
print(c['run'], c['summary'])" "$SITE/config/main-analysis.json")
COMMIT=$(git -C "$MASTER" rev-parse HEAD | cut -c1-7)
echo "== $RUN at $COMMIT $(date +%T)"

cd "$MASTER/frontier"
if [ -e "$FRONTIER/maps/$RUN-$COMMIT/map.json" ]; then
  echo "rent map exists"
else
  "$MASTER/ops/job" light -m 5G -- uv run --frozen --extra gpu python -m rentfrontier.rentmap "$RUN"
fi
if [ -e "$FRONTIER/kits/$RUN-$COMMIT/complete.json" ]; then
  echo "kit exists"
else
  "$MASTER/ops/job" light -m 5G -- uv run --frozen --extra gpu python -m rentfrontier.kit "$RUN" --summary "$SUMMARY"
fi

echo "== site build $(date +%T)"
# A combined publish peaks at about 1.9 GB (docs/site.md): cap it at 3 GB.
cd "$SITE"
systemd-run --user --scope -q -p MemoryMax=3G env TMPDIR="$TMPDIR" "$SITE_VENV/bin/python" -m apartments.site build
curl -s -m 10 http://127.0.0.1:8600/healthz || true; echo
