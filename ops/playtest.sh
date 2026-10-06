#!/usr/bin/env bash
# Run website playtester personas, each as its own Claude on Sonnet 5.5.
#
#   ops/playtest.sh ROUND PERSONA... [-- URL]
#
# ROUND names the output folder, /data1/apartments/tmp/playtests/<ROUND>/<persona>/.
# Each PERSONA is a file in docs/playtests/personas/ (without .txt). Every persona runs
# as a systemd --user unit, playtest-<ROUND>-<persona>, so it outlives the session that
# started it. Its report lands in <outdir>/report.md. Its own browser steps go through
# ops/job light, per docs/playtests/brief.md. Watch the units with
# `ops/team/wait-next --unit 'playtest-*'`.
#
# Playtesters run on Sonnet 5.5 (Ben, 2026-10-05). claude -p warns "unrecognized_model" because this CLI's catalog predates it, but the API serves it.
# Reviewers stay on the session's model.
set -euo pipefail
MODEL=${PLAYTEST_MODEL:-claude-sonnet-5-5}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
ROUND=${1:?usage: ops/playtest.sh ROUND PERSONA... [-- URL]}
shift
URL=http://127.0.0.1:8600
PERSONAS=()
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then URL=${2:?missing URL}; break; fi
  PERSONAS+=("$1"); shift
done
[ ${#PERSONAS[@]} -gt 0 ] || { echo "no personas" >&2; exit 2; }
# At most 3 personas a round, with one bundled PR and one review (Ben, 2026-10-05).
[ ${#PERSONAS[@]} -le 3 ] || { echo "at most 3 personas a round" >&2; exit 2; }
# Check every persona before starting any, so a round never half-launches.
for p in "$ROUND" "${PERSONAS[@]}"; do
  [[ $p =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "bad name: $p" >&2; exit 2; }
done
for p in "${PERSONAS[@]}"; do
  [ -f "$ROOT/docs/playtests/personas/$p.txt" ] || { echo "no persona $p" >&2; exit 2; }
  [ ! -e "/data1/apartments/tmp/playtests/$ROUND/$p/report.md" ] \
    || { echo "$ROUND/$p already has a report" >&2; exit 2; }
  ! systemctl --user is-active -q "playtest-$ROUND-$p" && ! systemctl --user is-failed -q "playtest-$ROUND-$p" \
    || { echo "unit playtest-$ROUND-$p is loaded (systemctl --user reset-failed it)" >&2; exit 2; }
done
for p in "${PERSONAS[@]}"; do
  file=$ROOT/docs/playtests/personas/$p.txt
  out=/data1/apartments/tmp/playtests/$ROUND/$p
  mkdir -p "$out"
  python3 - "$ROOT/docs/playtests/brief.md" "$file" "$URL" "$out" > "$out/prompt.md" <<'PY'
import re, sys
brief, persona, url, out = sys.argv[1:]
text = open(persona).read()
def field(name):
    m = re.search(rf"^{name}:\s*(.*?)(?=^\w+:|\Z)", text, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""
print(open(brief).read().format(persona=field("persona"), url=url, outdir=out,
      viewport=field("viewport"), goals=field("goals")))
PY
  # A step queued behind a fit outlasts Bash's 2-minute default; claude -p then moves it to the
  # background and the run ends with no report (round 9, 2026-10-06). Let a step block 10 minutes.
  systemd-run --user -q --unit "playtest-$ROUND-$p" --working-directory "$out" \
    -p MemoryMax=2G -E TMPDIR=/data1/apartments/tmp -E HOME="$HOME" -E PATH="$PATH" \
    -E BASH_DEFAULT_TIMEOUT_MS=600000 -E BASH_MAX_TIMEOUT_MS=600000 \
    bash -c "claude -p --model '$MODEL' --strict-mcp-config --allowedTools=Bash,Read,Write < prompt.md > final.md 2> stderr.log"
  echo "started playtest-$ROUND-$p -> $out"
done
