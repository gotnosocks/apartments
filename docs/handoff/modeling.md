# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-07 14:35 UTC)

- **Served:** m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb3-coded-v2, run
  `…-nb3-coded-v2-rows-9371a18-gibbs-2060-3600k9cb1-nb3-v5f1u5-gv1005`, summary 838e50f, PSIS-LOO
  106,764.6. Restored by hand in #403 (build 20261007T142452981592Z-39eb773f). It is on old rules
  (unit-labels-v5, fields-review-v1), so autoselect will replace it with the first gate-passing full fit
  on the current rules.
- **prevprice removed (Ben, 2026-10-07 14:17Z):** semantically invalid (no time dependence of the
  correction). `autoselect.BLOCKED` refuses every feature set containing `prevprice`, in autoselect and
  latestselect; `manual_removal` in config/main-analysis.json at #403 records it. The elegance brief is
  `elegance-v2`, with semantic validity first.
- **Current rules:** baths-ad-v2, bedrooms-ad-v2, fields-review-v3, quarantine-v5, unit-labels-v9,
  unit-splits-v1 (#394, #397).
- **Serving hardware (#391):** thelio RTX 2060 or Modal A100; compare fit times only within one class.
- **text-v1:** Data reports it fails the selection-bias-free test (WV+GV only: +43.7 ± 23.5, 1.9 SE).
  Not served; a selection block waits for Ben's own word (asked 2026-10-07). Nothing text-v1 is queued.
- **Designs:** dayfourier-yearnoise (#398) and bedtime12-yearnoise (#402) fill the fit-time gap below
  the served design (prevprice-v2 exploration under v9 + splits: served 1,480 s; dfyn 640 s, −34.7 ± 8.5).
- **Modal queue** `frontier-modalq-coded9` (waits for the midnight ET cap reset), all coded-v2 on the
  current rules: served design rows full fit at 39c3c8a (label a100-3600k9cb1-gv1006-ul9s), dfyn full
  fit, areatime exploration at d8fe0c2.
- **GPU queue:** Data's `frontier-splits-v2` (sp1 vs sp2, Data pairs it), then
  `frontier-coded9-explore`: coded-v2 explorations at d8fe0c2 of the served design, bedtime12 and dfyn
  (label x-2060-100w600d-gv1006-ul9s).

## Next

1. When the coded-v2 rows full fit lands: `python -m rentfrontier.autoselect`; on a switch build the
   summary (gpu job), `--write`, selection PR (default-model reviewer), merge, deploy, publish.
2. Pair the coded9 explorations (bedtime12 and dfyn against the served design) and the dfyn full fit
   against the served rows fit, for the fit-time frontier.
3. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes).

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), at most 10 a day (ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
