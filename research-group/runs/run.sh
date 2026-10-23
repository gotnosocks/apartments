#!/usr/bin/env bash
# Run one research-group member on a round brief inside bin/sandboxed.
# Usage: runs/run.sh ROUND HANDLE   (ROUND names runs/ROUND.md; 25-minute cap)
set -u
R=/data1/apartments/research-group
cd "$R"
round=$1
h=$2
P="Your handle is $h. $(cat "runs/$round.md")"
T0=$(date +%s)
case $h in
  astra) m=openai/gpt-6-astra ;;
  sol61) m=openai/gpt-6.1-sol ;;
  argon) m=openrouter/google/gemini-4-argon ;;
  fable) m=claude-fable-5-1 ;;
  opus) m=claude-opus-5-5 ;;
esac
case $h in
  astra | sol61 | argon)
    timeout 1500 bin/sandboxed pi -p --no-session --mode json --model "$m:xhigh" \
      --tools read,bash,edit,write,grep,find,ls "$P" \
      < /dev/null > "runs/${round}_$h.jsonl" 2> "runs/${round}_$h.err"
    ;;
  fable | opus)
    timeout 1500 bin/sandboxed claude -p --model "$m" --strict-mcp-config --output-format json \
      --add-dir /data1/apartments/serve/master \
      --allowedTools "Read,Grep,Glob,Bash,Write,Edit,WebSearch,WebFetch" \
      <<< "$P" > "runs/${round}_$h.json" 2> "runs/${round}_$h.err"
    ;;
esac
echo "$round $h rc=$? secs=$(($(date +%s) - T0)) $(date -u +%H:%M:%SZ)" | tee -a runs/progress.log
