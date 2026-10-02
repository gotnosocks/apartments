#!/bin/bash
# Rebuild the rents site's research data (data.json) when something new has
# landed: a fit's run record, LOO or variance result, or a master commit.
# Run by apartments-dashboard-build.service, triggered by its .path unit (new
# results) and its timer (fallback). It only reads records, so it runs without
# heavy.lock at idle CPU and I/O priority (Ben, 2026-10-01: live research
# updates, never blocked by the lock).
set -uo pipefail
# The script lives in the checkout it updates: read it whole before running.
{

FRONTIER=${FRONTIER:-/data1/apartments/frontier}
MASTER=${MASTER:-/data1/apartments/serve/master}
OUT=${OUT:-/data1/apartments/dashboard}
STAMP=${STAMP:-$OUT/.last-build}
DEBOUNCE=${DEBOUNCE:-60}

# A LOO directory appears before its files are written: let a burst settle.
sleep "$DEBOUNCE"

follow_master() {
  # If the fetch fails, rebuild from the current checkout. The checkout is
  # dedicated to serving, so --force discards any stray local change.
  git -C "$MASTER" fetch -q origin master || true
  git -C "$MASTER" checkout -q --force --detach origin/master || true
}

fingerprint() {
  # Every finished record (its files and their times) and the master commit.
  # The board's other input, the PyMC screens under data/model, is frozen.
  {
    git -C "$MASTER" rev-parse HEAD
    find "$FRONTIER/runs" "$FRONTIER/loo" "$FRONTIER/variance" "$FRONTIER/rescores" \
      -mindepth 2 -maxdepth 2 \
      \( -name result.json -o -name pointwise.npz -o -name heldout.npz \) -printf '%p %T@ %s\n' 2>/dev/null | sort
  } | sha256sum | cut -d' ' -f1
}

follow_master
# Results that land during a build are picked up by building again (a path
# trigger during a running build is merged into it, not queued).
for _ in 1 2 3; do
  now=$(fingerprint)
  if [[ -f $STAMP && $(cat "$STAMP") == "$now" ]]; then
    echo "nothing new since the last build"
    exit 0
  fi
  (cd "$MASTER/frontier" && /home/ben/.local/bin/uv run --locked -q python -m rentfrontier.dashboard --out "$OUT") || exit 1
  echo "$now" > "$STAMP.tmp" && mv "$STAMP.tmp" "$STAMP"
  follow_master
done
exit 0
}
