# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-08 04:45 UTC)

- **Served (autoselect, this PR): five neighbourhoods** (Ben 2026-10-08 02:53Z: Chelsea, West Village,
  Greenwich Village, Flatiron, Gramercy Park; dataset chelsea-wv-gv-flatiron-gramercy-analysis-20261008-0a23057,
  Data's #460). m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb5-coded-v2, run
  `…-nb5-coded-v2-rows-5789d79-a100-4500k9cb1-nb5-ul11r1s4` (2 × (300 + 4500)), summary 65362da,
  1,021 s on Modal A100, R-hat 1.0041, ESS 714, group R-hat 1.029, PSIS-LOO 139,864.1 ± 384.9,
  +33,920.9 against the new board baseline `m0-base-base-v1-rows-5789d79-x-2060-300w1500d-nb-nb5`
  (thelio). Variance: features 73%, building 9%, market and time 7%, R² 0.979. The nb4 fit never ran.
- **Current rules:** baths-ad-v2, bedrooms-ad-v2, fields-review-v3, quarantine-v6, unit-labels-v11,
  unit-reviews-v1, unit-splits-v4.
- **Same rows, same rules (Ben 2026-10-08 02:51Z, #458):** autoselect treats a fit whose rule set
  differs from master's as on the current rules when its rows hash (`rows_sha256`) matches.
- **Modal rule (Ben 2026-10-07 22:27Z, #432):** every data-rule, feature or model-term test is its own
  Modal full fit, 2 × (300 + 4500), no exploration, no thelio pairs, no bundling; autoselect serves the
  best passing fit on master's rules (a rule or feature fit only after its PR merges). Budget (#433):
  $8.80 a day accrual, capped at $8.80; one full fit about every 2.4 h.
- **prevprice removed (Ben, 2026-10-07 14:17Z):** `autoselect.BLOCKED` refuses feature sets containing
  `prevprice`.
- **Queue (nb5, systemd units, scripts in /data1/apartments/tmp/bridge, each waits for the one before):**
  `frontier-modalq-nb5tests`: nb5-stab-v1 (0233ec5), nb5-plutoasof-v1 (8af14dc), bedtime6 (5789d79);
  `frontier-modalq-nb5rules`: unit-labels-v12 (881b345), unit-splits-v5 (d478a5b);
  `frontier-modalq-nb5permit`: nb5-permit-v1 (e935808). Pair each against the served fit; Data merges
  its PR only on a win.
- **Variance:** run `rentfrontier.variance` on every served fit (Website's /research/story reads it);
  regenerate docs/model/cleaning.json with every switch PR.
- **Not on thelio:** serving fits (Ben 2026-10-07 14:29Z); the thelio GPU idles under the all-Modal rule,
  apart from board baselines for a new dataset.

## Next

1. nb5-loc-v1 is not queued yet (needs a Data feature set on nb5).
2. As each queued fit lands: autoselect dry run, pair, report to Ben and Data; switch if it wins.
3. Cut Modal's fixed ~800 s a fit (upload, image, PSIS-LOO), recommended to Ben.
4. A mean-side pandemic term (2020–21 deviation by price tier or bedroom group); pooled per-year noise
   scales as a smaller fix. Areatime as a full fit. Each needs a queue slot under the Modal rule.
5. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes).

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), within a dollar budget accruing 10 full fits a day, $8.80, capped at that balance (Ben 2026-10-07 21:59Z and 22:23Z; ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
