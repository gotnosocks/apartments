# Data pipeline baseline, 2026-10-15

This file records how long the current pipeline took, and how much memory it used, to turn the
Oct 15 four-region API backfill into analysis rows with their outside data. It serves as the
"before" figure for the rebuilt pipeline in [the pipeline handoff](../handoff/data-pipeline.md).

Times, CPU and memory come from systemd accounting and the Modal ledger. Row counts, slice counts
and sizes come from each step's log and from `du`. To regenerate the accounting figures:

```sh
python ops/pipeline/accounting.py journal --since "2026-10-15 11:40" --until "2026-10-15 16:20" \
    --match "data-api|apartments-light"
python ops/pipeline/accounting.py modal --last 15
```

## Scrape to analysis rows

The steps started from a snapshot of the archive taken at 12:43 ET, a minute after a collector
run that reopened boxes stopped early. The collector ran four more times after the snapshot,
until 14:34, and the 404 captures from those runs aren't in the snapshot or in anything built
from it. Two threads ran the steps by hand, each from a script in a scratch folder
(`/data1/apartments/tmp/api-build-20261015` and `/data1/apartments/tmp/suspect/api`, 18 scripts
between them). Times are wall clock. Peak is the unit's memory peak in GiB, with swap in brackets
when the unit used any.

| step | wall | CPU | peak GiB | notes |
|---|--:|--:|--:|---|
| collector rewrites API records as page captures | about 3 h | | | an estimate at about 7 ms an ad, per `docs/data/graphql-collection.md`; it runs inside each region's backfill, so systemd doesn't account it separately |
| snapshot the archive (VACUUM INTO) | 9.2 min | 1.3 min | 2.7 | a first try stopped after 8.0 min at a 3.0 GiB peak, with no out-of-memory record and no logged cause, and was rerun |
| `transform_local` to granular Parquet | 14.7 min | 29.0 min | 4.0 (1.0) | 1.71M ads, 30.6M history events kept as they appear in every capture |
| `collection_audit` | 1.3 min | 0.6 min | 3.0 | |
| `unit_spelling_aliases` | 6.8 min | 6.8 min | 2.5 | |
| `granular_slice` into 16 building slices | 2.3 min | 2.3 min | 3.1 | |
| history and cohort, per slice | 42.2 min | 43.3 min | 6.4 (0.2) | two runs: the first built 13 slices, then DuckDB ran out of its 954 MiB limit 13 s into slice 14, and a second run built the last 3 |
| region tables | 1.8 min | 1.9 min | 8.1 | built four of the eight region tables; `split.py` cut the other four from them at 14:24, outside any accounted unit |
| latest ask | 3.5 min | 3.4 min | 6.4 | |
| building registry, Manhattan | 53.6 min | 1.0 min | 0.1 | one GeoSearch request per building |
| building registry, Brooklyn | 65.0 min | 1.2 min | 0.1 | failed at 15:06; the rerun was still going at 16:30 |
| descriptions | 3.7 min | 5.1 min | 6.0 | a first try died after 0.2 min at 7.0 GiB with 2.6 GiB of swap |
| listing extras | 4.7 min | 2.0 min | 4.5 | |
| outside data, Manhattan (PLUTO, footprints, basemap, LPC, PLUTO releases, HPD) | 13.3 min | 5.8 min | 1.4 | PLUTO, footprints, LPC and HPD failed with HTTP 503 or 500 |
| outside data refetch, Manhattan | 14.8 min | 0.1 min | 0.4 | refetched PLUTO, footprints and LPC; HPD wasn't refetched |
| feature build check, two Manhattan regions | 8.5 and 8.9 min | | 2.3 and 2.8 | `data.load`, rules and `features.build` for manhattan-west-59th-110th (153,551 rows) and manhattan-below-59th (312,388 rows) |

Totals, leaving out the collector's rewrite:

1. Counting each step's successful run once, the steps from the snapshot through the Manhattan
   outside-data refetch took about 172 minutes of wall time if run in order. About 82 of them
   went to network requests: the Manhattan registry and the two outside-data fetches. The
   failed tries added about 8 minutes, the failed Brooklyn registry run another 65, and the
   steps waited on each other and on people between runs.
2. Manhattan's analysis rows passed the feature build check at about 16:15, roughly 3.5 hours
   after the snapshot and 1.7 hours after the collector's last run. The Brooklyn registry rerun
   was still going at 16:30, so no Brooklyn region had a checked, fit-ready dataset by then.
3. The highest peak was 8.1 GiB, in the region tables. History, latest ask and descriptions
   peaked between 6.0 and 7.0 GiB, and two steps failed for lack of memory before a rerun with
   more room or fewer rows.
4. Each step after the collector rereads the whole archive, so processing a Friday top-up takes
   as long as processing the full backfill.

The eight region tables hold 2.28M analysis rows. Four of them are cuts of the other four, which
hold 1.40M distinct rows in about 2.2 GiB of JSON lines. The granular Parquet takes 5.4 GB, and
the API response bodies take 11 GB.

## Data preparation inside a fit

Each fit loads its dataset, applies the data rules and builds the feature matrix before sampling.
The fit records that preparation as `seconds.prepare`. Modal bills the whole container, from
start to exit, at the GPU's hourly rate. Over the last 15 Modal fits (Oct 12 to 15, all on an
A100), preparation took a median of 153 s (111 to 221 s), 5.9% of the billed time. At the A100's
$2.39 an hour, that comes to about $0.10 a fit, and $1.66 across the 15, paid while the GPU
waits.

On thelio, the same preparation for manhattan-below-59th, 312,388 rows, took 8.9 minutes and
2.8 GiB.
