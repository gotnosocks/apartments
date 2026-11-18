#!/bin/bash
# Reads batches 08 to 197 on Haiku, eight at a time, each once its images are fetched.
# A batch counts as fetched when the fetch log reports a later batch or every fetch unit has ended.
O=/data1/apartments/tmp/deals-photos-2026-11-18
fetched() {
  local last
  last=$(cat $O/fetch.log $O/fetch2.log $O/fetch3.log 2>/dev/null | grep -o 'batch [0-9]*' | awk '{print $2+0}' | sort -n | tail -1)
  if ! systemctl --user -q is-active po-deals-photos && ! systemctl --user -q is-active po-deals-photos-2 && ! systemctl --user -q is-active po-deals-photos-3; then echo 999; else echo $(( ${last:-0} - 1 )); fi
}
done_n() { [ -s $O/reads/haiku/batch_$1.jsonl ] && [ "$(grep -c '^{' $O/reads/haiku/batch_$1.jsonl)" -ge 15 ]; }
declare -A tries
while :; do
  left=0; ready=()
  f=$(fetched)
  for i in $(seq 8 197); do
    n=$(printf %02d $i)
    done_n $n && continue
    [ "${tries[$n]:-0}" -ge 3 ] && continue
    left=$((left+1))
    [ $i -le $f ] && ready+=($n)
  done
  [ $left -eq 0 ] && break
  if [ ${#ready[@]} -eq 0 ]; then sleep 60; continue; fi
  pick=("${ready[@]:0:16}")
  for n in "${pick[@]}"; do tries[$n]=$(( ${tries[$n]:-0} + 1 )); done
  printf '%s\n' "${pick[@]}" | xargs -P 8 -n 1 $O/read_batch.sh
  echo "$(date +%H:%M:%S) read ${pick[*]}; files $(ls $O/reads/haiku | wc -l)" >> $O/read_all.log
done
echo "$(date +%H:%M:%S) finished" >> $O/read_all.log
