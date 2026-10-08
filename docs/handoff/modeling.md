# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-08 01:30 UTC)

- **Served (autoselect, this PR):** m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise +
  nb3-coded-v2 on the current rules, run `…-nb3-coded-v2-rows-9b6c16d-a100-4500k9cb1-gv1006-ul9r1s4`
  (2 × (300 + 4500) draws), summary 344d260, 1,089 s on Modal A100, PSIS-LOO 108,319.3, R-hat 1.0065,
  ESS 490, group R-hat 1.0095. Against the previous selection (39c3c8a, 3600 draws, older rules) on
  shared rows: +829.5 ± 93.1, held-out +102.1 ± 33.6. The 3600-draw refit on these rules missed ESS
  (bedroom_time_scale 399.9), so served fits now draw 4500.
- **Current rules:** baths-ad-v2, bedrooms-ad-v2, fields-review-v3, quarantine-v6, unit-labels-v9,
  unit-reviews-v1, unit-splits-v4.
- **Modal rule (Ben 2026-10-07 22:27Z, #432):** every data-rule, feature or model-term test is its own
  Modal full fit, 2 × (300 + 4500), no exploration, no thelio pairs, no bundling; autoselect serves the
  best passing fit on master's rules (a rule or feature fit only after its PR merges). Budget (#433):
  $8.80 a day accrual, capped at $8.80; one full fit about every 2.4 h.
- **prevprice removed (Ben, 2026-10-07 14:17Z):** `autoselect.BLOCKED` refuses feature sets containing
  `prevprice`.
- **Queue (systemd units, scripts in /data1/apartments/tmp/bridge, each waits for the one before):**
  `frontier-modalq-all`: unit-labels-v10 (2da098d), nb3-loc-v1, bedtime6, unit-splits-v5 (98a146d);
  then `frontier-modalq-stab` nb3-stab-v1 (#435), `-permit` nb3-permit-v1 (#437), `-pluto`
  nb3-plutoasof-v1 (#439). Pair each against the 4500 served refit; Data merges its PR only on a win.
- **Variance:** run `rentfrontier.variance` on every served fit (Website's /research/story reads it).
- **Not on thelio:** serving fits (Ben 2026-10-07 14:29Z); the thelio GPU idles under the all-Modal rule.
  A solo bedroom_time_scale probe ran out of memory on the 2060; loc-v1 ran out of memory there too.

## Next

1. As each queued fit lands: autoselect dry run, pair, report to Ben and Data; switch if it wins.
2. Cut Modal's fixed ~800 s a fit (upload, image, PSIS-LOO), recommended to Ben.
3. A mean-side pandemic term (2020–21 deviation by price tier or bedroom group); pooled per-year noise
   scales as a smaller fix. Areatime as a full fit. Each needs a queue slot under the Modal rule.
4. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes).

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), within a dollar budget accruing 10 full fits a day, $8.80, capped at that balance (Ben 2026-10-07 21:59Z and 22:23Z; ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
