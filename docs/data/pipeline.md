# Pipeline project

The rebuilt pipeline is a SQLMesh project over DuckDB, in `pipeline/`. So far it builds each
analysis row's latest ask from the API export, as `rentfrontier.latest_ask` does. The later steps
in [the pipeline handoff](../handoff/data-pipeline.md) add models to it.

The project keeps its own uv environment and lock, as `frontier/` does. SQLMesh 0.236.3 requires
pandas below 3, and the repo's lock holds pandas 3.0.5.

```sh
uv sync --project pipeline --extra dev
uv run --project pipeline sqlmesh -p pipeline plan --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline fetchdf "SELECT how, count(*) FROM analysis.latest_ask GROUP BY 1"
uv run --project pipeline --extra dev pytest pipeline/tests
```

## Inputs

`pipeline/config.py` reads three environment variables:

| variable | default on thelio | holds |
|---|---|---|
| `PIPELINE_EXPORT` | `/data1/apartments/archive/crawls/api/export` | the scraper's export, with its manifest |
| `PIPELINE_ROWS` | `/data1/apartments/pipeline/inputs/analysis-rows-20261015-13f5968-api.parquet` | analysis rows |
| `PIPELINE_STATE` | `/data1/apartments/pipeline/state` | the DuckDB database, spill files and SQLMesh's cache |

The build reads the ads files listed in the manifest and skips any file still lacking a line.
`ops/pipeline/analysis_rows.py` wrote the rows file from the four API region datasets of the
latest-ask run of Oct 15, `20261015-13f5968-api`. It stays an input until the event log builds
the rows from API records.

For each input, `config.py` also computes a version: a SHA-256 over the path and hash of each
listed ads file, and the rows file's own SHA-256. SQLMesh fingerprints a model by its SQL as
written and by the values of the variables the SQL uses. The raw views use the versions as well
as the paths, so a file written again under its old name also counts as a change. A new or
rewritten export file changes `raw.ads`, and the next plan rebuilds it and every model below it.
With unchanged inputs, a plan builds nothing.

`raw.ads` holds every answer, including the API's empty answers, marked `missing`.
`ads.latest_record` reads only answers with a record, so an ad whose latest answer came back
empty keeps its last record, as in `rentfrontier.latest_ask`.

## Models

| model | kind | a row for each |
|---|---|---|
| `raw.ads` | view | exported API answer for an ad |
| `raw.analysis_rows` | view | analysis row |
| `ads.latest_record` | table | ad, from its latest record: status, market days, page price and price changes |
| `ads.price_changes` | table | nonzero price change, numbered in date order within its ad |
| `ads.kept_changes` | table | price change left after the placeholder check |
| `analysis.latest_change` | table | analysis row, with its ad's last kept change while the row stood and its page price |
| `analysis.latest_ask` | table | analysis row, with its first ask, its latest ask and the step behind the latest |

The comments in each model's SQL describe its rules. The audits in the `MODEL` blocks check
keys and nulls: one row per listing in `ads.latest_record`, per `(listing_id, n)` in
`ads.price_changes` and per `ordinal` in the two analysis tables. The `every_row` audit, in
`pipeline/audits/`, checks that `analysis.latest_ask` keeps every analysis row. When an audit
fails, the plan stops, and the tables from the last good plan stay in place.

To try an edit, I build it in a dev environment beside prod and list the rows it changes:

```sh
uv run --project pipeline sqlmesh -p pipeline plan dev --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline table_diff prod:dev -m analysis.latest_ask -o ordinal --show-sample
```

## Tests

`pipeline/tests/fixture/` holds the analysis rows of five buildings, the 229 exported records of
their ads and the latest ask `rentfrontier.latest_ask` gave each row, 187 KB in all.
`pipeline/tests/make_fixture.py` writes it from the full inputs on thelio. The API data lacks
several cases the latest-ask steps handle, as the full build below notes, so
`pipeline/tests/make_cases.py` makes up seven answers and eleven rows for them in
`fixture/cases/`, 17 KB in all, and writes the latest ask `rentfrontier.latest_ask` gives each
row. The tests:

1. build the fixture and compare each row's first ask, latest ask and step with
   `rentfrontier.latest_ask`;
2. build the made-up cases and compare them the same way. They hold several rows of one ad, a
   record collected before its row, an ad without answers, an empty latest answer, and rows
   without a building or a bedroom count;
3. build runs 2 and 3, then add run 4's file to the manifest. The next plan rebuilds `raw.ads`
   and the five tables below it and gives the full answer, and a further plan finds nothing to
   build;
4. write an export file again under its old name with another compression, and give the
   manifest its new hash. The next plan rebuilds the models below `raw.ads`;
5. add a run 5 file with a newer answer for one ad and an older answer for another. Only the
   first ad's row changes;
6. duplicate an analysis row. The `unique_values` audit on `analysis.latest_change` stops the
   plan, and the tables from the earlier plan stay in place;
7. drop a row from `analysis.latest_ask` in a copy of the project. The `every_row` audit stops
   the plan;
8. read manifests with a cut-off last line, a repeated line, a rewritten file and a file with
   two hashes.

They take about 10 s on thelio. SQLMesh loads models in forked workers, and a fork in a process
with open DuckDB connections can deadlock, so `pipeline/tests/conftest.py` sets
`MAX_FORK_WORKERS=1`.

## Full build

On Oct 15 on thelio, I built the project from runs 1 to 4 of the export and compared
`analysis.latest_ask` with the latest-ask run `20261015-13f5968-api`. All 1,396,053 rows matched
in first ask, latest ask and step. The match covers less than the steps allow. In the API
region datasets each ad has one analysis row and every ad has a record in runs 1 to 4, so each
row is its ad's last, and none takes the own-ask or uncaptured steps. No row lacks a building
or a bedroom count, and `analysis.latest_ask` holds all 1,396,053 rows. The made-up cases in the
tests cover the rest.

```sh
uv run --project pipeline sqlmesh -p pipeline fetchdf "
  SELECT count(*) FROM analysis.latest_ask n
  JOIN '/data1/apartments/external/latest-ask/20261015-13f5968-api/latest-ask.parquet' r USING (audit_id)
  WHERE n.first_ask <> r.first_ask OR n.latest_ask <> r.latest_ask OR n.how <> r.how"
```

Then I added run 5 to the manifest and planned again on the same state, as a top-up would. Run 5
re-reads the old page-crawl areas, so only 18 of its 424,776 ads appear in runs 1 to 4. Ten of
those came back with a changed record, and no row's latest ask changed. Last, I built all five
runs into an empty state. Its five tables equal the topped-up ones row for row: 2,137,997 ads,
5,006,178 price changes, 5,002,252 kept changes and 1,396,053 analysis rows.

| build | plan | peak memory |
|---|--:|--:|
| runs 1 to 4, from an empty state | 45.8 s | 5.9 GB |
| run 5 added to that state | 46.1 s | 4.0 GB |
| runs 1 to 5, from an empty state | 43.8 s | 4.8 GB |

Each build ran as a `systemd-run --user` unit with a 6 GB memory limit and DuckDB's limit at
5 GB. The peaks are the units' cgroup peaks, page cache and the comparison included. In the
first build, `ads.kept_changes` took 20.3 s, `ads.latest_record` 12.6 s, and the other three
tables 5.9 s together.

Every model is a full table, so the top-up rebuilt all five tables and took as long as a build
from nothing. Rebuilding only the ads a top-up touches is part of step 8. The event log of step 4
should also shorten `ads.kept_changes`, whose placeholder check steps through each ad's changes
one at a time.

`ops/pipeline/analysis_rows.py` wrote the rows input again from the run's provenance.json in
15 s at a 2 GB peak, and the result equals the file the build read, row for row.
