#!/usr/bin/env bash
# A sampler rehearsal on the building subsample of `subsample.py`, run on thelio's GPU.
#
#   rehearse.sh MODEL COPY OUT WARMUP DRAWS NAME [WIDTH]
#
# The script runs `rentfrontier.run` as `ops/modal-fit` runs it on Modal, with the full
# fits' chains, thinning, seed and level prior, on the subsample copy COPY (such as
# k100-r8/base under datasets/) with the full data's latest split carried over. The code is
# this checkout's rentfrontier, imported through PYTHONPATH by the Python of serve/master's
# frontier venv, which holds JAX's CUDA plugin. With WIDTH, the run goes through `width.py`
# instead, which sets the slice width of the building spreads to WIDTH for the diagnostic
# runs. The run, its log, the device's memory every 2 s and the run's /usr/bin/time record
# go under /data1/apartments/tmp/rehearsals-2026-11-14/OUT.
# Call it through `ops/job gpu` so it takes the GPU lock.
set -euo pipefail
[ $# -eq 6 ] || [ $# -eq 7 ] || {
	echo "usage: rehearse.sh MODEL COPY OUT WARMUP DRAWS NAME [WIDTH]" >&2
	exit 2
}
model=$1 copy=$2 out=$3 warmup=$4 draws=$5 name=$6
root=/data1/apartments/tmp/rehearsals-2026-11-14
checkout=$(cd "$(dirname "$0")/../../.." && pwd)
entry=(-m rentfrontier.run)
if [ $# -eq 7 ]; then
	entry=("$checkout/docs/notes/rehearsals-2026-11-14/width.py" "$7")
fi
mkdir -p "$root/$out"
nvidia-smi --query-gpu=timestamp,memory.used --format=csv,noheader,nounits -lms 2000 \
	>"$root/$out/gpu-memory.csv" &
smi=$!
trap 'kill "$smi"' EXIT
cd "$checkout"
env PYTHONPATH="$checkout/frontier/src" \
	FRONTIER_DATASET="$root/datasets/$copy" \
	FRONTIER_OUTPUT_ROOT="$root/$out" \
	FRONTIER_COMMIT="$(git rev-parse HEAD)" \
	XLA_PYTHON_CLIENT_PREALLOCATE=false \
	XLA_PYTHON_CLIENT_MEM_FRACTION=0.95 \
	/usr/bin/time -v -o "$root/$out/time.txt" \
	/data1/apartments/serve/master/frontier/.venv/bin/python "${entry[@]}" \
	--split carried --model "$model" --features b0 --chains 2 --chain-batch 2 \
	--warmup "$warmup" --draws "$draws" --keep-every 40 --name "$name" --seed 1 \
	--level-dof 4 >"$root/$out/run.log" 2>&1
