# Data pipeline baseline, 2026-10-15

This file records how long the current pipeline took, and how much memory it used, to turn the
Oct 15 four-region API backfill into analysis rows with their outside data. It serves as the
"before" figure for the rebuilt pipeline in [the pipeline handoff](../handoff/data-pipeline.md).

Every figure comes from systemd accounting or from the Modal ledger. To regenerate them:

```sh
python ops/pipeline/accounting.py journal --since "2026-10-15 11:40" --until "2026-10-15 16:20" \
    --match "data-api|apartments-light"
python ops/pipeline/accounting.py modal --last 15
```

## Scrape to analysis rows

The backfill finished at 11:18 ET. From there, two threads ran the steps below by hand, each from
a script in a scratch folder (`/data1/apartments/tmp/api-build-20261015` and
`/data1/apartments/tmp/suspect/api`, 18 scripts between them). Times are wall clock. Peak is the
unit's memory peak in GiB, with swap in brackets when the unit used any.

| step | wall | CPU | peak GiB | notes |
|---|--:|--:|--:|---|
| collector rewrites API records as page captures | about 3 h | | | inside each region's backfill run at about 7 ms an ad, per `docs/data/graphql-collection.md`; systemd doesn't account it separately |
| snapshot the archive (VACUUM INTO) | 9.2 min | 1.3 min | 2.7 | a first try stopped at 3.0 GiB, its cap, after 8.0 min and was rerun |
| `transform_local` to granular Parquet | 14.7 min | 29.0 min | 4.0 (1.0) | 1.71M ads, 30.6M history events kept as they appear in every capture |
| `collection_audit` | 1.3 min | 0.6 min | 3.0 | |
| `unit_spelling_aliases` | 6.8 min | 6.8 min | 2.5 | |
| `granular_slice` into 17 building slices | 2.3 min | 2.3 min | 3.1 | |
| history and cohort, per slice | 42.2 min | 43.3 min | 6.4 (0.2) | two runs: DuckDB ran out of its 954 MiB limit on slice 14 after 34.8 min, and a second run built the last 4 slices in 7.4 min |
| split rows into the eight regions | 1.8 min | 1.9 min | 8.1 | |
| latest ask | 3.5 min | 3.4 min | 6.4 | |
| building registry, Manhattan | 53.6 min | 1.0 min | 0.1 | one GeoSearch request per building |
| building registry, Brooklyn | 65.0 min | 1.2 min | 0.1 | failed; the rerun was still going at 16:30 |
| descriptions | 3.7 min | 5.1 min | 6.0 | a first try died after 0.2 min at 7.0 GiB with 2.6 GiB of swap |
| listing extras | 4.7 min | 2.0 min | 4.5 | |
| outside data, Manhattan (PLUTO, footprints, basemap, LPC, PLUTO releases, HPD) | 13.3 min | 5.8 min | 1.4 | |
| outside data refetch, Manhattan | 14.8 min | 0.1 min | 0.4 | network |
| feature build check, one region each | 8.5 and 8.9 min | | 2.3 and 2.8 | `data.load`, rules and `features.build` for 312,388 rows |

Totals, leaving out the collector's rewrite:

1. The local steps took about 104 minutes of wall time when each ran once and in order. The
   failed tries added about 43 minutes, and the steps waited on each other and on people between
   runs.
2. The Brooklyn registry was still unfinished five hours after the backfill ended, so no
   Brooklyn region had a checked, fit-ready dataset by then. Manhattan's became ready at about
   16:15, close to five hours after the scrape.
3. The highest peak was 8.1 GiB, in the region split. Three steps went over 6 GiB, and two
   steps failed for lack of memory before a rerun with more room or fewer rows.
4. Each step after the collector rereads the whole archive, so processing a Friday top-up takes
   as long as processing the full backfill.

The eight region tables hold 2.28M analysis rows and take 3.6 GB as JSON lines. The granular
Parquet takes 5.4 GB, and the API response bodies take 11 GB.

## Data preparation inside a fit

Each fit loads its dataset, applies the data rules and builds the feature matrix before sampling.
Over the last 15 Modal fits (Oct 12 to 15, all on an A100), that preparation took a median of
153 s (111 to 221 s), 9.5% of the fit's wall time. At the median settled cost of $2.00 a fit, that
comes to about $0.20 a fit, and $2.98 across the 15, paid at the A100's rate while the GPU waits.

On thelio, the same preparation for one API region of 312,388 rows took 8.5 minutes and 2.3 GiB.
