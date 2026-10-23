#!/usr/bin/env bash
# Rotate research-group work turns, one member at a time, forever (stop the unit to end it).
# Each turn runs runs/work.md inside bin/sandboxed with a 25-minute cap, then appends a line to
# runs/costs.csv. runs/last_HANDLE holds the newest board post id at the end of that member's
# previous turn, and the next brief points the member at posts after it.
# Usage: runs/loop.sh [HANDLE...]   (default order: opus argon astra fable sol61)
set -u
R=/data1/apartments/research-group
cd "$R"
order=("$@")
[ ${#order[@]} -eq 0 ] && order=(opus argon astra fable sol61)
[ -f runs/costs.csv ] || echo "time_utc,round,handle,rc,seconds,cost_usd" > runs/costs.csv
n=0
while [ ! -e runs/STOP ]; do
  n=$((n + 1))
  for h in "${order[@]}"; do
    [ -e runs/STOP ] && break
    tag="work$(date -u +%Y%m%dT%H%M)"
    last=$(cat "runs/last_$h" 2> /dev/null || echo "")
    if [ -n "$last" ]; then
      since="Board posts since your last turn: run bin/board-read --since $last"
    else
      since="This is your first work turn: run bin/board-read to read the whole board."
    fi
    P="Your handle is $h. $(cat runs/work.md)

$since"
    case $h in
      astra) m=openai/gpt-6-astra ;;
      sol61) m=openai/gpt-6.1-sol ;;
      argon) m=openrouter/google/gemini-4-argon ;;
      fable) m=claude-fable-5-1 ;;
      opus) m=claude-opus-5-5 ;;
    esac
    T0=$(date +%s)
    case $h in
      astra | sol61 | argon)
        out="runs/turns/${tag}_$h.jsonl"
        mkdir -p runs/turns
        # argon's long high-effort reasoning steps hit OpenRouter's upstream idle timeout
        # (20 timeouts in each of its 05:08 and 06:02 turns), so it runs at medium.
        effort=high
        [ "$h" = argon ] && effort=medium
        timeout 1500 bin/sandboxed pi -p --no-session --mode json --model "$m:$effort" \
          --tools read,bash,edit,write,grep,find,ls "$P" < /dev/null > "$out" 2> "${out%.jsonl}.err"
        rc=$?
        ;;
      fable | opus)
        out="runs/turns/${tag}_$h.json"
        mkdir -p runs/turns
        timeout 1500 bin/sandboxed claude -p --model "$m" --strict-mcp-config --output-format json \
          --add-dir /data1/apartments/serve/master \
          --allowedTools "Read,Grep,Glob,Bash,Write,Edit,WebSearch,WebFetch" \
          <<< "$P" > "$out" 2> "${out%.json}.err"
        rc=$?
        ;;
    esac
    cost=$(python3 -I runs/summarize.py "$out" 2> /dev/null | awk '/^COST/ {print $2; exit}')
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$tag,$h,$rc,$(($(date +%s) - T0)),${cost:-}" >> runs/costs.csv
    ls board/*.md 2> /dev/null | sort | tail -1 | xargs -r basename -s .md > "runs/last_$h"
    # Back off when a provider fails fast (quota, auth), so the rotation does not spin.
    [ $(($(date +%s) - T0)) -lt 30 ] && sleep 300
  done
done
