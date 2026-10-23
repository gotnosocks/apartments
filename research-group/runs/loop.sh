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
    # A per-member prompt file replaces work.md for that member's turns while it exists.
    [ -f "runs/prompt_$h" ] && P="Your handle is $h. $(cat "runs/prompt_$h")"
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
        # runs/effort_<handle> overrides the default effort and is read every turn, so a change
        # needs no restart. argon's long reasoning steps stall past OpenRouter's idle limit
        # (about 170 s) at high and at medium, so runs/effort_argon holds low.
        effort=high
        [ -s "runs/effort_$h" ] && effort=$(tr -dc 'a-z' < "runs/effort_$h")
        # A provider error (an aborted request, OpenRouter's upstream idle timeout) ends a pi run
        # with stopReason "error". The turn then resumes its own session with --continue, up to
        # four runs inside the 25-minute cap, appending to the same log.
        sess="runs/sessions/${tag}_$h"
        mkdir -p "$sess"
        : > "$out"
        : > "${out%.jsonl}.err"
        prompt="$P"
        resume=()
        for attempt in 1 2 3 4; do
          left=$((1500 - ($(date +%s) - T0)))
          [ $left -lt 120 ] && break
          timeout $left bin/sandboxed pi -p --session-dir "$sess" "${resume[@]}" --mode json \
            --model "$m:$effort" --tools read,bash,edit,write,grep,find,ls "$prompt" \
            < /dev/null >> "$out" 2>> "${out%.jsonl}.err"
          rc=$?
          last_stop=$(tail -n 3 "$out" | grep -o '"stopReason":"[a-zA-Z]*"' | tail -1)
          [ "$last_stop" = '"stopReason":"error"' ] || break
          echo "loop.sh: run $attempt ended on a provider error; resuming the session" >> "${out%.jsonl}.err"
          resume=(--continue)
          prompt="Your last request failed at the provider before you got a reply, so your turn was cut off. Continue the turn from where you stopped. Save each result to members/$h/ as soon as you have it, and post to the board before any long step."
        done
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
