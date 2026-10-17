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
- Ben dropped the 80% range from the lists (12:50 ET Oct 17). The summary's `--range-atoms`
  (#1065, #1066 for Modal) writes 64 atoms per row and `noise.json` in place of the quantile
  solve; on NB9 at 10% it ran in 397 s against 663 s, with a median error of 0.00027 log
  against a Monte Carlo error of 0.0013. The site reads them from `ranges.parquet` when a
  page opens (docs/site.md, data flow step 2). The flag stays off by default, and nobody
  passes it on a publish of the served fit until the site change has merged.
- Before the default flips: check every `estimate_pred_*` reader (coverage, price band, board,
  rent map, site build) against a table mixing atom rows and fallback rows, and compare the
  ranges on Ben's opened pages and a random sample with the exact ones.
- A thelio summary of the served all-scraped run died of OOM at 9 GB in the design prep after 11
  minutes (Oct 17). Modeling asked for no more full all-scraped feature builds on thelio, so the
  design gets prepared on Modal (`ops/modal-fit --design-only`, #1084) and the summary loads it
  with `FRONTIER_DESIGN_CACHE=read`. The unit `publish-path-launch-design` launches the prep at
  bc06303d from the pinned clone `/data1/apartments/tmp/publish-path/clone`, once P1 has launched
  and the budget covers $0.70 (log: `/data1/apartments/tmp/publish-path/logs/launch-design.log`).
- Once the design lands in `frontier/designs`, I compute its key on thelio with
  `tools/design_key.py` in a 3G scope, at the clone commit and in the summary's env, and compare
  it with the key in `design.json`. The 9G summary (`--range-atoms --with-exact`) starts only if
  the two keys match. On an OOM or a mismatch I stop and report to Modeling without a retry.

## Next

1. Move the other listing-page-only columns (`fitted*`, `pred_*_95`) and the per-listing
   `inputs` to the detail file. The build's own steps read `inputs` (captures, estimate_build,
   best), so they need another source first.
2. Give each publish step a key from its inputs' hashes and skip unchanged steps. `kit.py` and
   `rentmap.py` rebuild the prepared features that `design.prepared` caches for the summary.
3. Measure each step on nested samples (1%, 4%, 16%) and on the all-scraped run under systemd.

Scratch notes and tools are in `/data1/apartments/tmp/publish-path/`.
