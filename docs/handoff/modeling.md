# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-06 11:30 UTC)

- **Served:** m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb3-coded-v2,
  run `…-rows-9371a18-gibbs-2060-3600k9cb1-nb3-v5f1u5-gv1005` (#318), the first fit on Chelsea +
  WV + GV to pass the gate: PSIS-LOO 106,764.6 ± 334 (+28,669 over the board baseline), R-hat
  1.0053, min ESS 469, 6,578 s. `data.DATASET` is the GV dataset. Deployed and published (site-deploy,
  autoselect-publish, /estimate checked): build 20261006T110910914042Z-39eb773f. The growth
  decomposition for Website is redone (`r7gv/analyse.py`, `r7gv/out.txt`) and sent to Website.
- **GV data:** `chelsea-wv-gv-analysis-20261005-2d5b3b6`, rules unit-labels-v5, quarantine-v5,
  bedrooms-ad-v2, baths-ad-v2, fields-review-v1. Data's fields-review-v3 (Ben's revert of #167)
  is held until the latest48 pair and latestselect; fits after that use v3.
- **The served design without yearnoise fails the gate on the GV data** within 2 h: refit 1
  group R-hat (unit 1.060, bedroom_slope 1.059); refit 2 (seed 2) R-hat 1.0122 on
  bedroom_time_scale, min ESS 295. Both PSIS-LOO ~106,020.
- **Prevprice latest48:** the 3600-draw pair was +92.5 ± 16.7 but both arms failed on min ESS.
  Rerun at 4800 draws keep 12, at 86184c2: the prevprice arm runs in `frontier-gvlatest48`
  (sampling since 07:30 ET); the coded-v2 arm was OOM-killed at 07:19 (a CPU probe took the swap)
  and reruns next as `frontier-gvlatest48b` (`gvlatest48b.sh`). Then pair_subsets, latestselect,
  and if prevprice wins by > 2 SE with both arms passing, a prevprice rows serving fit within 2 h
  with fields-review-v3.
- **Areatime (#311) runs out of GPU memory** at sampling start (a 2.24 GiB allocation in the
  collect program `jit_run`; warmup runs fine). Both areatime designs in `frontier-gvareatime`
  (`gvareatime.sh`: served, +areatime, +yearnoise+areatime, x-2060-100w600d-u5-gv1005) failed;
  the served-design reference at 29a1c08 completed. `frontier-memprobe` (after latest48b) compiles the sampling
  program on the GPU for the served design and areatime and prints XLA's memory analysis
  (`memprobe/probe-gpu.log`). Never run a full-data CPU job beside a GPU fit: fits sit at the 7G
  slice cap and use swap.

## Next

1. latest48: pair the arms when both land, then latestselect, then tell Data to merge
   fields-review-v3.
2. Areatime: read `memprobe/probe-gpu.log`, fix the memory (or coarser knots under new design
   names), then rerun the `gvareatime.sh` explorations with a served-design reference at the same commit.
3. Backlog: autoselect `why_not` should check the dataset before `scored`.

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), at most 10 a day (ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
