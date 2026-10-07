# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-07 15:45 UTC)

- **Served (#409, autoselect, build 20261007T153845309893Z-3dba77be):** m7-nocurves-floorslope-bednoise-
  dayfourier-bedtime-yearnoise + nb3-coded-v2 on the current rules, run
  `…-nb3-coded-v2-rows-39c3c8a-a100-3600k9cb1-gv1006-ul9s`, summary b65c406, 953 s on Modal A100,
  PSIS-LOO 107,490.3. Against the previous selection on shared rows: +725.6 ± 65.8, held-out +53.5 ± 20.3.
- **prevprice removed (Ben, 2026-10-07 14:17Z):** semantically invalid (no time dependence of the
  correction). `autoselect.BLOCKED` refuses every feature set containing `prevprice`, in autoselect and
  latestselect; `manual_removal` in config/main-analysis.json at #403 records it. The elegance brief is
  `elegance-v2`, with semantic validity first.
- **Current rules:** baths-ad-v2, bedrooms-ad-v2, fields-review-v3, quarantine-v5, unit-labels-v9,
  unit-splits-v1. Data tests unit-splits v2 (#400) and v3 (#408) on coded-v2 explorations (GPU now).
- **A100 full-fit frontier** (coded-v2, current rules; paired PSIS-LOO against served, 953 s):
  bedtime12-yearnoise −65.0 ± 11.0 (756 s); dayfourier-yearnoise −193.9 ± 24.9 (539 s); floorslope-
  bednoise-dayfourier −1,008 ± 60 (535 s); floorslope-bednoise −1,102 ± 61 (718 s); floorslope base
  fails the group gate (building 845's bedroom slope, R-hat 1.097). Yearnoise is worth about +814;
  quarterly bedroom curves +194 over none. Exploration fits under prevprice understated bedtime
  (−35 there), so prevprice-era exploration results need rechecking on coded-v2.
- **Year noise (Data, 2026-10-07):** residual sd 4–5% in 2017–19, about 9% Sep 2020–Feb 2021, 5–6% by
  2022; symmetric, same in all neighbourhoods and sources, no data rule. Of +814, 2020–21 give +335 and
  2017–19 +264. Per-row table in /data1/apartments/tmp/suspect/yearnoise/.
- **Running:** bedtime6-yearnoise (#410) full fit on Modal at 2cab155 (18 of today's 20 slots; Ben
  granted +10 for 2026-10-07). GPU: `frontier-coded9-explore` runs sp2, sp3, then bedtime12 and dfyn
  coded-v2 explorations at d8fe0c2.
- **Serving fits not on thelio** (Ben 2026-10-07 14:29Z); exploration fits continue there.
- **text-v1:** back in the backlog as text-v2 (Ben, 2026-10-07); nothing text is queued.

## Next

1. Pair bedtime6 against the served fit when it lands (pairs-ul9s.py).
2. If Data's unit-splits v2 or v3 wins and merges: a serving refit on Modal (2 slots left today).
3. A mean-side pandemic term (2020–21 deviation by price tier or bedroom group), to see how much of
   yearnoise's gain it explains; pooled per-year noise scales (random walk on log sigma) as a smaller fix.
4. Areatime as a full fit (its exploration failed the gate at R-hat 1.045, ESS 46).
5. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes); comments in fit.py
   and ops/modal-fit still say the cap is 10.

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), at most 10 a day (ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
