# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-05 22:00 UTC)

- **Served:** m7-nocurves-floorslope-bednoise-dayfourier-bedtime + nb-coded-v1, run
  `…-rows-c82aa9b-gibbs-2060-4500k9cb1-nb-v5f1u3-d1005` (PSIS-LOO 89,284; Chelsea + West Village).
- **GV frontier refit (Ben, 18:32 UTC: refit every design on both frontiers on the new data,
  smallest first).** Dataset `chelsea-wv-gv-analysis-20261005-2d5b3b6`, rules unit-labels-v5,
  quarantine-v5, bedrooms-ad-v2, baths-ad-v2, fields-review-v1. Units, in order:
  - `frontier-gvfit`: baseline m0-base + base-v1 (done 16:11 ET); then waits for 03:00, and is
    stopped by `frontier-gvrefit-early` when that takes over.
  - `frontier-gvfrontier` (`gvfrontier.sh`): 15 exploration fits (2×(100+600), label
    `x-2060-100w600d-u5-gv1005`, master 579d7f3), old frontier designs on nb3-coded-v1, plus the
    yearnoise design and nb3-lineface-v1; then the full m5 bedtime fit (3600 draws, keep 6).
  - `frontier-gvrefit-early` (`gvrefit-early.sh`): the served design's full refit as soon as the
    queue drains (3600 draws, keep 9: 4500 would overrun the 2 h cap on 21% more rows; expected
    min ESS ~440 against 400), then the latest-split pair nb3-coded-v1 vs nb3-prevprice-v1 (3 h cap
    each).
- **Prevprice (Ben, 13:57 UTC: serve nb-prevprice-v1 if it wins the latest-split pair by > 2 SE).**
  It won on the Oct 5 data (+75.5 ± 15.7), but its rows serving fit overran the 2 h cap (exit 124),
  so it was not served. Redo on GV: pair the latest-split arms with `pair_subsets.py`; if > 2 SE and
  passing, run its rows serving fit (it samples slower than the served design: may need fewer
  draws to fit 2 h), then `rentfrontier.latestselect`, selection PR, deploy, publish, check
  `/estimate` (FORM_GROUPS).
- **Noise by year (#295, merged 6420e65).** Residual scale by bedroom group × calendar year, for
  the 2010 and 2021 under-coverage. Exploration point is in the GV queue. Year cells with no
  training rows take the prior scale, so not for latest-split selection as is.

## Next

1. When the GV fits land: check the 15 exploration results and the lineface pair in bulk; send
   Data the lineface number and the coordinator the queue summary.
2. After the GV refit: autoselect (dataset switch), publish, then redo the map's growth
   decomposition (`r7/analyse.py`) for Website's "why the map grows less" note.
3. Backlog: autoselect `why_not` should check the dataset before `scored`.
