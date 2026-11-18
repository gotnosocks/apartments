#!/bin/bash
# Reads one batch with a headless Haiku reader and saves its JSON lines.
set -u
N=$1
O=/data1/apartments/tmp/deals-photos-2026-11-18
W=/home/ben/code/apartments/.claude/worktrees/bridge-cse_01BbWN4QhsEVcGXeZVb6cqo3
out=$O/reads/haiku/batch_$N.jsonl
[ -s "$out" ] && [ "$(grep -c '^{' "$out")" -ge 15 ] && exit 0
cd $O
timeout 900 claude -p "Read the brief at $W/docs/notes/deals-photos-2026-11-18/READER.md and follow it exactly.

Your batch file: $O/batches/batch_$N.json
Image folders: $O/rate/<label>/ (find the images with the Glob tool, then open every image with the Read tool).

Work through the labels in order. Open no other files. There is no output file: your final reply is the output. Reply with the JSON lines only, one line for each apartment, no code fence and no other text." --model haiku --allowedTools "Read,Glob" < /dev/null > $O/reads/raw/batch_$N.txt 2> $O/reads/raw/batch_$N.err
grep '^{' $O/reads/raw/batch_$N.txt | python3 -I $O/valid.py > "$out"
