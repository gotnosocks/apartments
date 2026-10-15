# Pipeline stack trial, 2026-10-15

The rebuilt pipeline in [the pipeline handoff](../handoff/data-pipeline.md) runs on SQLMesh over
DuckDB, with Python models wherever a step is awkward in SQL. This file records the trial behind
that choice. I built latest ask three ways from the same inputs and checked each result against
`rentfrontier.latest_ask`.

## Inputs

- Ad records: runs 1 to 4 of the API archive, 1,713,239 records in 2.6 GB of Parquet. I exported
  them from the stored bodies with the columns of `streeteasy_archive/graphql_export.py` (#863).
  Once the scraper thread had written #863's export, I reran the steps on it, with the same
  result.
- Rows: the four API region tables of Oct 15, 1,396,053 rows in all. Two cover Manhattan, below
  59th St and from 59th to 110th St, and two cover Brooklyn, around Prospect Park and from north
  Brooklyn to Crown Heights. I froze them to Parquet in `latest_ask.main`'s reading order.
- Reference: `/data1/apartments/external/latest-ask/20261015-13f5968-api/latest-ask.parquet`.
  `rentfrontier.latest_ask` wrote it from the page-capture rewrite of the same records.

## Steps

Each stack ran the same five SQL steps, 121 lines in all. `latest_ask.py` does the same work in
259 lines of Python. The cold builds of plain and dbt ran step 3 with `SEMI JOIN` and `ANTI JOIN`.
SQLMesh's cold build and the later edit and undo runs of all three used `IN` in their place, as
described under Choice.

1. `ad_latest` picks each ad's latest record and keeps its status, market dates, page price and
   price changes. It pulls those fields out of the JSON before the pick. With whole records in
   the pick, DuckDB ran out of its 5 GB limit.
2. `price_change` keeps one row per nonzero price change and numbers them in date order.
3. `kept_change` applies the placeholder check to changes after an ad left the market. The step
   compares each change with the last kept change, so it recurses. Some ads carry long runs of
   changes: ad 2326634 has 799 changes over two months, cycling through 7 prices, and 1,814 ads
   have 100 or more. With the recursion limited to the 108,877 ads with a late change, the step
   took 20 s instead of 72 s.
4. `row_latest` finds each analysis row's last kept change up to the ad's next row.
5. `latest_ask` computes each row's median among the other rows in its building with its bedroom
   count, leaving the row out, then runs the checks against that median and the page price.

## Results

| | plain DuckDB | dbt-duckdb | SQLMesh |
|---|--:|--:|--:|
| lines besides the step SQL | 68, a hash-caching runner | 18 of settings | 15 of settings, and a `MODEL` line per step |
| cold build | 30.5 s, 2.8 GiB | 41.7 s, 4.0 GiB | 42.1 s, 3.4 GiB |
| rebuild after a change to step 3 | 25.5 s | 33.7 s | 31.8 s |
| rebuild after undoing that change | 0.8 s | 43.9 s | 3.9 s |
| rows unlike the reference | 0 | 0 | 0 |

All three matched the reference on all 1,396,053 rows, in `latest_ask`, `first_ask` and `how`.

The first plain run differed on 12 rows. In the digit check of step 5, the stage's `SELECT *`
carried an earlier stage's `picked` column, and DuckDB read `picked` from it in place of the new
value. I fixed the shared SQL with `EXCLUDE` before the other two stacks ran.

The plain runner's undo first took 24.6 s. Between its cold build and the edit, step 3 had
changed from `SEMI JOIN` to `IN`, as described below, so the undo built that text for the first
time. A rerun with nothing changed read every step from the cache in 0.8 s.

All three ran DuckDB with a 5 GB memory limit. The plain runner also set 8 threads and turned
insertion order off, and the other two kept DuckDB's defaults for both.

## Choice

SQLMesh fingerprints each model by its normalized SQL and its parents' fingerprints. It keeps a
table for each version after building it, so I don't have to write a hash-keyed step cache:

- When an edit leaves a query's meaning alone, SQLMesh rebuilds nothing. It recorded
  `x < 1.0 / 2` in place of `x < 0.5` as a metadata change.
- After an undo, SQLMesh reuses the earlier version's tables, in 3.9 s here.
- `sqlmesh plan dev` builds a change in a separate environment beside the current tables. Then
  `sqlmesh table_diff prod:dev la.latest_ask -o audit_id` lists each row with a different value.
  With step 3's threshold moved from 1.2 to 1.3 for the first time, the build and the diff took
  34.3 s at a 3.2 GiB peak and found 10 changed rows. For 1.25, built earlier in the edit run,
  the plan reused the tables. The plan and the diff took 9.3 s, with only the diff doing work, and
found 4 rows.
- A step can be a Python model wherever SQL is awkward. SQLMesh also has incremental model kinds,
  for the Friday top-up.

dbt keeps no record of earlier builds. Each run rebuilds every selected model, so an undo costs a
full rebuild. A before-and-after comparison needs a second copy of the tables, built by hand. The
plain runner was fastest, but I would have to write its environments, diffs, audits and
incremental builds myself.

On step 3, SQLMesh stopped with a sqlglot error, `Required keyword: 'this' missing for
Coalesce`, while the step used `SEMI JOIN` and `ANTI JOIN` with `USING`. I replaced them with
`IN (SELECT ...)` and `NOT IN (SELECT ...)`, and the step then ran in all three stacks. I haven't
isolated the cause: a minimal `SEMI JOIN ... USING` query passes SQLMesh's optimizer.

The trial's projects are in `/data1/apartments/tmp/pipeline/compare/` on thelio, with the three
stacks installed in `/data1/apartments/venvs/pipeline-stacks` (DuckDB 1.5.5, SQLMesh 0.236.3,
dbt-core 1.12.6 with dbt-duckdb 1.11.0).
