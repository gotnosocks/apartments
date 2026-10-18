# Handoff: publish path

This thread reorganizes the path from a finished fit to the published site (summary, calibration,
rent map, estimate kit, site build, research data build) around what the pages and the project goal
read. Modeling owns the summary and the fit queue, Website owns the site build, and each OKs a
change to its step before merge.

## State on 2026-10-18

- The column reads log (`reads.jsonl`, #1017) has collected on the running site since 10:45 ET
  Oct 17. Ben's devices are 100.111.61.78 (MacBook Air) and 100.108.123.68 (iPhone); 100.80.84.126
  is thelio.
- Ben has the decision table, a row per output with a keep, compute-on-request or remove
  recommendation. We carry on with the recommendations behind flags until he answers.
- Merged so far: #1028 and #1030 (columns and summary outputs nobody reads), #1065 and #1066
  (range atoms behind a flag), #1084 (the design prepared on Modal), #1111, #1112 and #1115
  (listing parts in `detail.parquet` and the form's draws in `kit_buildings.parquet`, both on by
  default in `ops/autoselect-publish.sh`). Website moved serve/master to 7243a467 and serve/site
  to 25860f7, so the next publish builds with both files. Before those flags the live site had
  /estimate at 0.19 s, a listing page at 0.87 s and site.sqlite at 10.3 GB; Website times the
  pages again after the next publish.
- The rent map and the kit read the design's parts (`rentfrontier.design_parts`, about 100 MB)
  from the summary bundle in place of the whole design (6.3 GB on all-scraped), after checking
  the dataset hash, the rows hash and the draws' units and buildings against the run.
  Bundles written before that change have no parts, and the two steps then prepare the design
  as before. The all-scraped posterior.npz (13.4 GB, 9 GB of it the walk) still does not load
  on thelio, since `explain.load_run` reads every array as float64; streaming the draws is
  the next proposal to Modeling.
- Ben dropped the 80% range from the lists (12:50 ET Oct 17). The summary's `--range-atoms`
  (#1065, #1066 for Modal) writes 64 atoms per row and `noise.json` in place of the quantile
  solve; on NB9 at 10% it ran in 397 s against 663 s, with a median error of 0.00027 log
  against a Monte Carlo error of 0.0013. The site reads them from `ranges.parquet` when a
  page opens (docs/site.md, data flow step 2). The flag stays off by default, and nobody
  passes it on a publish of the served fit until the site change has merged.
- Before the default flips: check every `estimate_pred_*` reader (coverage, price band, board,
  rent map, site build) against a table mixing atom rows and fallback rows, and compare the
  ranges on Ben's opened pages and a random sample with the exact ones.
- A full thelio summary of the served all-scraped run runs out of memory: 9 GB in the design
  prep (Oct 17), and Modeling asked for no more full all-scraped feature builds on thelio. The
  design is now prepared on Modal (`ops/modal-fit --design-only`, #1084), and summaries on
  thelio load it with `FRONTIER_DESIGN_CACHE=read`. A thelio summary of whole buildings
  (`--rows`) fits under 9 GB up to about 175k rows: RSS sits near 6 GB after the draws load and
  grows about 14 KB a row. A full summary needs the Modal LARGE container.
- On the served all-scraped run (Oct 18, 59,851 rows including Ben's opened listings), the
  ranges the site computes from the atoms came within 0.00025 log of the same run's exact
  intervals at the median and 0.059 at the worst row, against a Monte Carlo error of 0.0011.
  Two summaries of the same fit differ by up to 0.43 log on a few rows, because the summary's
  leave-own-row-out unit levels draw their jitter from per-chunk keys. A row-by-row check of two
  summaries needs that noise in its yardstick. Modeling has the details.

## Next

1. Move the other listing-page-only columns (`fitted*`, `pred_*_95`) and the per-listing
   `inputs` to the detail file. The build's own steps read `inputs` (captures, estimate_build,
   best), so they need another source first.
2. Give each publish step a key from its inputs' hashes and skip unchanged steps. The rent map
   and the kit are keyed by the master commit, so any merge reruns both; key them by the
   posterior's sha, the bundle's sha and their own module sources.
3. Stream the draws in the kit and the rent map, so the all-scraped publish runs on thelio.
4. Measure each step on nested samples (1%, 4%, 16%) and on the all-scraped run under systemd.

Scratch notes and tools are in `/data1/apartments/tmp/publish-path/`.
