#!/usr/bin/env bash
# Publish the served run after an autoselect switch has been merged and the
# site deployed (ops/site-deploy.sh): the rent map, then the estimate kit, then
# the site build, which bundles both and publishes the selection.
#
#   1. rent map    rentfrontier.rentmap  -> /data1/apartments/frontier/maps/<run>-<key>/
#   2. kit         rentfrontier.kit      -> /data1/apartments/frontier/kits/<run>-<key>/
#                  (the /estimate form; the site build finds it by the summary
#                  bundle's sha256, and without it the form says "not available")
#   3. site build  apartments.site build -> /data1/apartments/site/builds/<id>
#
# The run and its summary bundle come from the serving checkout's selection
# (config/main-analysis.json). Steps 1 and 2 run at the master checkout's
# commit (both refuse a dirty tree) as light jobs. Each hashes the run's
# result and draws, the summary bundle, the frontier package's code and its
# own options into a key (rentfrontier.step_key), and keeps an output already
# made for the key, so a step whose inputs are unchanged takes seconds. Both read the design's parts from the
# summary bundle when it has them (rentfrontier.design_parts) and otherwise
# prepare the whole design. Usage: ops/autoselect-publish.sh
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

MASTER=${MASTER:-/data1/apartments/serve/master}
SITE=${SITE_SERVE:-/data1/apartments/serve/site}
SITE_VENV=${SITE_VENV:-/data1/apartments/venvs/serve-site}
export TMPDIR=${TMPDIR:-/data1/apartments/tmp} JAX_PLATFORMS=cpu XLA_PYTHON_CLIENT_PREALLOCATE=false

read -r RUN SUMMARY < <(python3 -c "
import json, sys
c = json.load(open(sys.argv[1]))
print(c['run'], c['summary'])" "$SITE/config/main-analysis.json")
COMMIT=$(git -C "$MASTER" rev-parse HEAD | cut -c1-7)
echo "== $RUN at $COMMIT $(date +%T)"

cd "$MASTER/frontier"
"$MASTER/ops/job" light -m 5G -- uv run --frozen --extra gpu python -m rentfrontier.rentmap "$RUN" --summary "$SUMMARY"
"$MASTER/ops/job" light -m 5G -- uv run --frozen --extra gpu python -m rentfrontier.kit "$RUN" --summary "$SUMMARY"

echo "== site build $(date +%T)"
# The all-scraped publish peaks at about 5.2 GB resident (48:39, 2026-10-17; docs/site.md),
# and its writes fill the page cache besides: cap it at 8 GB.
cd "$SITE"
# The pipeline build (ops/pipeline/build-latest) waits while a site-build-* unit runs, so the
# scope takes such a name. The build holds every light slot while it runs, so waiting for slot 1
# keeps the site build from starting beside a running build. The listings' dollar parts go to
# detail.parquet rather than the listings table, and the estimate form's building draws go to
# kit_buildings.parquet rather than the kit_buildings table (docs/site.md, data flow step 2).
flock /data1/apartments/tmp/locks/light-1.lock systemd-run --user --scope -q --unit="site-build-publish-$(date +%s)-$$" -p MemoryMax=8G env TMPDIR="$TMPDIR" SITE_DETAIL_ON_REQUEST="${SITE_DETAIL_ON_REQUEST:-1}" SITE_KIT_ON_REQUEST="${SITE_KIT_ON_REQUEST:-1}" "$SITE_VENV/bin/python" -m apartments.site build
curl -s -m 10 http://127.0.0.1:8600/healthz || true; echo
