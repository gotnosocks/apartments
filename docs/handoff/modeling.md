# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-06 11:00 UTC)

- **Served (this PR):** m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb3-coded-v2,
  run `…-rows-9371a18-gibbs-2060-3600k9cb1-nb3-v5f1u5-gv1005`, the first fit on Chelsea + WV + GV
  to pass the gate: PSIS-LOO 106,764.6 ± 334 (+28,669 over the board baseline), R-hat 1.0053,
  min ESS 469, every group under 1.05, 6,578 s. `data.DATASET` is now the GV dataset.
- **GV data:** `chelsea-wv-gv-analysis-20261005-2d5b3b6`, rules unit-labels-v5, quarantine-v5,
  bedrooms-ad-v2, baths-ad-v2, fields-review-v1. Data's fields-review-v3 (a no-op that drops 16
  ad-only fixes, Ben's revert of #167) is held until the latest48 pair and latestselect; fits
  after that use v3.
- **The served design without yearnoise fails the gate on the GV data** within 2 h: refit 1 group
  R-hat (unit 1.060, bedroom_slope 1.059), refit 2 (seed 2) R-hat 1.0122 on bedroom_time_scale,
  min ESS 295. Both PSIS-LOO ~106,020.
- **Prevprice:** latest-split pair nb3-prevprice-v2 vs nb3-coded-v2 is +92.5 ± 16.7 (5.5 SE), but
  both arms fail on min ESS (334, 380; beta[label:lower_level]). Rerun at 4800 draws keep 12 as
  `frontier-gvlatest48` (`gvlatest48.sh`), about 07:15–12:15 ET; then pair_subsets, latestselect,
  and if it wins a prevprice rows serving fit within 2 h (rules with fields-review-v3).
- **Areatime (#311):** a random-walk curve per non-reference neighbourhood × month on 3-month
  knots, Chelsea the reference. Exploration fits `frontier-gvareatime` (served, +areatime,
  +yearnoise+areatime, x-2060-100w600d-u5-gv1005). Serving code refuses it until it wins.

## Next

1. After the switch merges: `ops/site-deploy.sh`, `ops/autoselect-publish.sh`, check `/estimate`,
   then redo the map's growth decomposition (`r7/analyse.py`) for Website (#300 shows it only for
   the d1005 run).
2. Areatime exploration results: pair each against the served design at the same commit; if
   areatime wins clearly, a full fit (yearnoise + areatime) within 2 h, with fields-review-v3.
3. latest48 pair: as above.
4. Backlog: autoselect `why_not` should check the dataset before `scored`.
