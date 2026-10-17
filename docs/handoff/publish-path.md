# Handoff: publish path

This thread reorganizes the path from a finished fit to the published site (summary, calibration,
rent map, estimate kit, site build, research data build) around what the pages and the project goal
read. Modeling owns the summary and the fit queue, Website owns the site build, and each OKs a
change to its step before merge.

## State on 2026-10-17

- The column reads log (`reads.jsonl`, #1017) has collected on the running site since 10:45 ET
  Oct 17. Ben's devices are 100.111.61.78 (MacBook Air) and 100.108.123.68 (iPhone); 100.80.84.126
  is thelio.
- Ben has the decision table, a row per output with a keep, compute-on-request or remove
  recommendation. We carry on with the recommendations behind flags until he answers.
- #1028 drops three site columns no page reads. Its merge waits for Website to say the
  all-scraped build is live.
- #1030 is stacked on #1028 and stops the summary writing `fit_units` and the seasonal reference
  rent bounds. A reviewer approved it, and Modeling looks before merge.
- `SITE_DETAIL_ON_REQUEST=1` moves listing parts to `detail.parquet` (docs/site.md, data flow
  step 2). Website turns it on in the publish.

## Next

1. Move the other listing-page-only columns (`fitted*`, `pred_*_95`) and the per-listing
   `inputs` to the detail file. The build's own steps read `inputs` (captures, estimate_build,
   best), so they need another source first.
2. Give each publish step a key from its inputs' hashes and skip unchanged steps. `kit.py` and
   `rentmap.py` rebuild the prepared features that `design.prepared` caches for the summary.
3. Measure each step on nested samples (1%, 4%, 16%) and on the all-scraped run under systemd.

Scratch notes and tools are in `/data1/apartments/tmp/publish-path/`.
