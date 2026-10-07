# Modeling thread handoff

What the next turn of the modeling thread needs. Updated at each milestone. Scripts and logs are
in `/data1/apartments/tmp/bridge` (thelio).

## State (2026-10-07 08:10 UTC)

- **Served:** m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise + nb3-prevprice-v2, run
  `…-nb3-prevprice-v2-rows-163c6de-a100-3600k9cb1-gv1006` (Modal A100, #392), summary at 86a2578.
  latestselect: latest split +84.2 ± 17.5 over coded-v2, both arms passing. PSIS-LOO 107,649.9 ± 334
  (rows split; inflated for a feature that reads earlier rents). Rules unit-labels-v5, quarantine-v5,
  bedrooms-ad-v2, baths-ad-v2, fields-review-v3. Deployed and published: build
  20261007T060508384451Z-0c374f31; kit has 42,839 units.
- **Serving hardware (#391, Ben 2026-10-07):** serve fits from the thelio RTX 2060 or Modal A100;
  compare fit times only within one hardware class.
- **Text features:** text-v1 is +110.8 ± 32.3 on rows but −1.1 ± 10.0 on the latest split; on top of
  prevprice (prevtext-v1, branch features/prevtext, no PR) about −2.2 in exploration. Not served.
- **unit-labels-v8 (#336, merged; current rule):** prevprice-v2 rows full fit at 4d6e6f7 passes the
  gate, +304.7 ± 34.6 over the served fit on shared rows. Latest arms cannot pair across label rules
  (the held-out rows differ). The test is coded-v2 vs prevprice-v2, both under v8 on the latest split:
  prevprice arm done on Modal (`…-prevprice-v2-latest-4d6e6f7-a100-12000k30cb1-gv1006-ul8-latest`);
  the coded-v2 arm waits for the Modal cap in `frontier-modalq-v8b`. Exploration read: +44.2 ± 19.1.
- **Areatime:** the GPU memory probe was low; the 2060 exploration OOMed copying draws to host (2.30
  GiB). It runs on Modal (`frontier-modalq-areatime`, after v8b) at 56251af, pairing with the thelio
  base `…-nb3-prevprice-v2-rows-56251af-x-2060-100w600d-gv1006`.
- **GPU queue:** `frontier-v9pair` (Data's unit-labels-v9, #394: coded-v2 v8 vs v9 at b50430b; Data
  pairs it), then `frontier-ladder-v8` (floorslope design ladder with prevprice-v2 under v8, for the
  lower fit-time frontier).

## Next

1. When the coded-v2 v8 latest arm lands: latestselect with candidate prevprice v8 latest, reference
   coded-v2 v8 latest, serve `…-prevprice-v2-rows-4d6e6f7-a100-3600k9cb1-gv1006-ul8`; summary, selection
   PR, deploy, publish.
2. Pair the areatime Modal exploration with its thelio base.
3. Ladder: pair the steps, mark the lower fit-time frontier.
4. Backlog: autoselect `why_not` should check the dataset before `scored`; elegance.needed_pairs and
   the site's hardware view still assume TARGET_HARDWARE only (#391 review notes).

## Modal fits (2026-10-06)

Frontier fits can run on Modal with `ops/modal-fit` (docs/model/modal.md), at most 10 a day (ledger
/data1/apartments/modal/ledger.jsonl). The served design on an A100-40GB: fit 822 to 919 s, PSIS-LOO
139 s, identical results to thelio, about $0.80 a full fit. The Modal Volume is deleted after 24 h
unused by apartments-modal-cleanup.timer.
