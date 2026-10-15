# Pipeline stack trial, 2026-10-15

The rebuilt pipeline in [the pipeline handoff](../handoff/data-pipeline.md) runs on SQLMesh over
DuckDB, with Python models for the steps SQL handles badly. This file records the trial behind
that choice: latest ask, built three ways from the same inputs and checked against
`rentfrontier.latest_ask`.

## Inputs

- Ad records: an export of the API archive's runs 1 to 4, 1,713,239 records in 2.6 GB of
  Parquet, made from the stored bodies with the columns the scraper thread later adopted in
  `streeteasy_archive/graphql_export.py` (#863). The steps were rerun on #863's own export once
  it was written, with the same result.
- Rows: the four API region tables of Oct 15 (manhattan-below-59th, manhattan-59th-110th,
  brooklyn-prospect-park, brooklyn-north-crown-heights), 1,396,053 rows, frozen to Parquet in the
  order `latest_ask.main` reads them.
- Reference: `/data1/apartments/external/latest-ask/20261015-13f5968-api/latest-ask.parquet`,
  written by `rentfrontier.latest_ask` from the page-capture rewrite of the same records.

## Steps

Each stack ran the same five SQL steps, 121 lines in all, against 259 lines of Python in
`latest_ask.py`:

1. `ad_latest`: each ad's latest record, cut down to its status, market dates, page price and
   price changes. The fields come out of the JSON before the pick. Picking whole records first
   ran DuckDB out of a 5 GB limit.
2. `price_change`: one row per nonzero price change, numbered in date order.
3. `kept_change`: the placeholder check on changes after an ad left the market. It compares
   each change with the last kept one, so it recurses. Ad 2326634 has 799 changes, 7 distinct
   prices over two months, and 1,814 ads have 100 or more. The recursion runs only over the
   108,877 ads with a late change, which cut the step from 72 s to 20 s.
4. `row_latest`: each analysis row's last kept change up to its ad's next row.
5. `latest_ask`: the leave-one-out building median and the four choices that follow it.

## Results

| | plain DuckDB | dbt-duckdb | SQLMesh |
|---|--:|--:|--:|
| lines besides the SQL | 68 (hash-caching runner) | 18 (config) | 15 (config) |
| cold build | 30.5 s, 2.8 GiB | 41.7 s, 4.0 GiB | 42.1 s, 3.4 GiB |
| rebuild after a change to step 3 | 25.5 s | 33.7 s | 31.8 s |
| rebuild after undoing that change | 24.6 s, its first build | 43.9 s | 3.9 s |
| rows unlike the reference | 0 | 0 | 0 |

All three matched the reference on all 1,396,053 rows, in `latest_ask`, `first_ask` and `how`.
The first plain run differed on 12 rows, in the last stage, where a column from an earlier stage
shadowed the one the stage computed. The fix went into the shared SQL before the other two ran.
The 4.0 and 2.8 GiB peaks reflect DuckDB's threads and settings as much as the stacks: dbt ran
with DuckDB's defaults, and the plain runner with 8 threads and insertion order off.

## Choice

SQLMesh fingerprints each model by its normalized SQL and its parents' fingerprints, and keeps
every version it has built. That gives the hash-keyed step cache the pipeline needs without
writing one:

- A change that leaves the query's meaning alone rebuilds nothing. `x < 1.0 / 2` in place of
  `x < 0.5` registered as a metadata change.
- Going back to a version built before takes seconds, as in the table.
- `sqlmesh plan dev` builds the changed steps in a separate environment, and
  `sqlmesh table_diff prod:dev la.latest_ask -o audit_id` lists every row they change. With a
  change to step 3 from 1.2 to 1.25, the two took 9.3 s and found the 4 rows it moves.
- Models can be Python where SQL is awkward, and incremental kinds cover the Friday top-up.

dbt rebuilds whatever a run selects, with no record of what it built before, so undoing a
change costs a full rebuild and seeing a change's effect needs a second copy built by hand.
The plain runner was fastest, but lineage, environments, diffs, audits and incremental builds
would all have to be written for it.

SQLMesh parses SQL with sqlglot before running it, and its optimizer failed on
`SEMI JOIN ... USING`. `WHERE ... IN (SELECT ...)` works in all three and replaced it.

The trial's projects are in `/data1/apartments/tmp/pipeline/compare/` on thelio, with the three
stacks installed in `/data1/apartments/venvs/pipeline-stacks` (DuckDB 1.5.5, SQLMesh 0.236.3,
dbt-core 1.12.6 with dbt-duckdb 1.11.0).
