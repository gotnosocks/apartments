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
  default in `ops/autoselect-publish.sh`), #1122 (the kit and rent map read the draws a block at
  a time), #1125 (the all-scraped kit in 4.2 GB), #1126 (the rent map and the kit keyed by
  their inputs' hashes in `rentfrontier.step_key`, kept when the key is current). Website moved serve/master to 7243a467 and serve/site
  to 25860f7, so the next publish builds with both files. Before those flags the live site had
  /estimate at 0.19 s, a listing page at 0.87 s and site.sqlite at 10.3 GB; Website times the
  pages again after the next publish.
- The rent map and the kit read the design's parts (`rentfrontier.design_parts`, 31 MB on
  all-scraped) from the summary bundle in place of the whole design (6.3 GB), after checking
  the run's name, dataset, split, feature set and rules, the held-out audit ids and the draws'
  units and buildings against the run (#1120). Bundles written before that change have no
  parts, and the two steps then prepare the design as before. Modeling agreed to backfill the
  served all-scraped bundle's parts into a copy from the saved design pickle
  (`/data1/apartments/tmp/publish-path/tools/backfill-parts.py`), keeping complete.json and so
  the bundle's sha.
- `data.rows_sha256` depends on the CPU: the design prepared on Modal for the all-scraped run
  holds 8 of 1.75M log rents 1 ulp from thelio's `np.log`, so its rows hash misses the fit's.
  The parts record whether the hash matches and don't require it (Modeling, Oct 18).
- The all-scraped posterior.npz (13.4 GB, 9 GB of it the walk) does not load on thelio
  through `explain.load_run`, which reads every array whole as float64 (about 28 GB). The kit
  and the rent map now read it through `rentfrontier.draws`, a block of draws at a time: the
  kit takes 250 thinned draws and the walk's two last knots, and the rent map averages the walk
  over each year as it reads and keeps 250 draws by default (`--draws 0` keeps all). On NB9 the
  kit came out identical to master's at 2.67 GB peak (5.19 GB before), and so did the map on
  all 1000 draws, at 2.67 GB (6.95 GB before). The 250-draw map's rents differ from the
  1000-draw map's by a median of 0.0046 log, 0.66 Monte Carlo SEs (0.67 for a normal), with
  5.5% of cells past 2 SE against 4.6%, since thinned draws still carry some autocorrelation.
- On the all-scraped run on thelio (Oct 18, 9G unit, design parts from the served bundle):
  - The 250-draw rent map peaked at 4.87 GB in 212 s. Against production's 1000-draw map its
    rents sit a median 0.655 Monte Carlo SEs away (5.4% of cells past 2 SE, 0.52% past 3),
    a median of 0.0049 log, and its overall medians agree within 0.0021 log.
  - The kit first ran out of memory at 9G. It built all 23 feature groups' terms on reference
    rows where they are 0 (3 GB), copied the units through an identity index (0.9 GB) and
    turned fslope into Python lists (3 GB). Without those it peaks at 4.21 GB in 132 s, and
    its parquet columns and kit.json come out identical to production's kit.
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
- Cost on nested samples of the served all-scraped run (Oct 18, thelio, systemd units, cold
  page cache):
  - #1137 reads each draws block into a reused buffer and reuses the map's rent arrays across
    years. Kernel time fell from 39 to 15 s in the kit and from 83 to 92 s down to 22 s in the
    250-draw map, with byte-identical outputs. The full kit takes 98 s at 4.0 GB and the map
    142 s at 4.8 GB. From p16 to full, 6.2x the buildings, the kit's CPU grows 5.7x and the
    map's 3.1x.
  - The site build with `SITE_DETAIL_ON_REQUEST=1` and `SITE_KIT_ON_REQUEST=1` takes 0.55, 0.70,
    0.69 and 0.79 s per 1,000 rows on p01, p04, p16 and the full 1.755M rows, and writes about
    2.5 KB a row. The full build ran in 23:12, peaked at 4.26 GB and wrote 4.47 GB (site.sqlite
    3.14 GB, detail.parquet 817 MB). The Oct 17 build without the flags took 48:39 and wrote
    10.3 GB.

## Next

1. Move the other listing-page-only columns (`fitted*`, `pred_*_95`) and the per-listing
   `inputs` to the detail file. The build's own steps read `inputs` (captures, estimate_build,
   best), so they need another source first.
2. Draw the Student t samples in `estimate.score` with numpy per listing rather than per sample
   in Python. On the full build `random.gammavariate` and `random.gauss` take 30% of the time.
   Website owns the site build, so that change goes through Website.
3. Measure the summary, calibration and research data build on the all-scraped run under
   systemd, and run the whole publish from a downloaded fit.

Scratch notes and tools are in `/data1/apartments/tmp/publish-path/`.
