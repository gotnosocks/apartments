# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-06 03:30 UTC)

- **Served:** m7-nocurves-floorslope-bednoise-dayfourier-bedtime + nb-coded-v1, run
  `…-rows-c82aa9b-gibbs-2060-4500k9cb1-nb-v5f1u3-d1005` (Chelsea + West Village). Unscored on the
  GV board (#310 moved the baseline), so autoselect would pick the top eligible fit unguarded: only
  start it for a fit that passes.
- **GV data:** `chelsea-wv-gv-analysis-20261005-2d5b3b6`, rules unit-labels-v5, quarantine-v5,
  bedrooms-ad-v2, baths-ad-v2, fields-review-v1; feature set nb3-coded-v2 (Data's v2 sets).
- **GV refit** of the served design (3600 draws keep 9, e8191b2): 6,572 s, scalars pass, but group
  R-hat fails (unit 1.0598, bedroom_slope 1.0592 against 1.05). Full m5 bedtime fit passes
  (elpd 101,616.6). Exploration (paired vs m0q base-v1): m7 served +27,946 ± 263, yearnoise
  +745 ± 54 over it.
- **Overnight units** (scripts and logs in the bridge dir): `frontier-gvrefit-v2` latest-split pair
  nb3-coded-v2 vs nb3-prevprice-v2 (3 h cap each); then `frontier-gvrefit-s2` (refit, seed 2) and
  `frontier-gvyearnoise` (full yearnoise fit); then `frontier-gvareatime` (exploration: served,
  areatime, yearnoise-areatime at the areatime commit).
- **Areatime (Ben 03:02 UTC: open to new designs for the new data):** a random-walk curve per
  non-reference neighbourhood × month on 3-month knots (`area_time`), Chelsea the reference.
  Serving code (summary, kit, rent map, projection) refuses it until it wins.

## Next

1. When the GV fits land: check the 15 exploration results and the lineface pair in bulk; send
   Data the lineface number and the coordinator the queue summary.
2. After the GV refit: autoselect (dataset switch), publish, then redo the map's growth
   decomposition (`r7/analyse.py`) for Website's "why the map grows less" note.
3. Backlog: autoselect `why_not` should check the dataset before `scored`.
