# Pipeline project

The rebuilt pipeline is a SQLMesh project over DuckDB, in `pipeline/`. So far it builds each
analysis row's latest ask from the API export, as `rentfrontier.latest_ask` does, and a log of
the events the API reported for each ad, with each ad's first ask. It also reads each ad's
attributes from its records and gives the current chain's reasons for dropping the ad. The later
steps in [the pipeline handoff](../handoff/data-pipeline.md) add models to it.

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
as the paths, so a file written again under its old name also counts as a change, once the
manifest's line for it carries the new hash. A second line for the same path with another hash
stops the build instead, since `config.py` refuses a path with two hashes. A new or
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
| `ads.answers` | table | answer, with the fields the event log reads and a hash of its unit history |
| `ads.history_events` | table | event in a distinct unit history |
| `ads.events` | table | event the API reported for an ad, with the answers that reported it |
| `ads.first_ask` | table | ad with an ACTIVE event in its own history: its first day on the market and its asks that day |
| `ads.record_attributes` | table | distinct API record: its attributes and rental flags, as the current chain reads them |
| `ads.attributes` | table | ad with a parsed record: its attributes and rental flags, merged over its records |
| `ads.exclusions` | table | ad with a record: its first day, its first ask and the current chain's reasons for dropping it |

The comments in each model's SQL describe its rules. The audits in the `MODEL` blocks check
keys and nulls: one row per listing in `ads.latest_record`, `ads.first_ask`, `ads.attributes`
and `ads.exclusions`, per record in `ads.record_attributes`, per `(listing_id, response_id)` in
`ads.answers`, per `(listing_id, n)` in `ads.price_changes`, per event in `ads.events` and per
`ordinal` in the two analysis tables. The `every_row` audit, in
`pipeline/audits/`, checks that `analysis.latest_ask` keeps every analysis row. When an audit
fails, the plan stops, and the tables from the last good plan stay in place.

To try an edit, I build it in a dev environment beside prod and list the rows it changes:

```sh
uv run --project pipeline sqlmesh -p pipeline plan dev --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline table_diff prod:dev -m analysis.latest_ask -o ordinal --show-sample
```

## Event log

`ads.events` gathers what the API reported about each ad. An answer reports events from four
places:

1. the fetch itself, with the ad's status and page price at that moment;
2. the record's status changes;
3. the record's price changes;
4. the unit history, listing the rental events of every ad of the unit.

The model keeps a row for each distinct event, with the fetch times of the first and last
answers that reported it, the number of those answers and the `response_id` of the first. An
event in a unit history may come first from a sibling's answer, so `own_first_seen` and
`own_first_response_id` give the first answer of the ad itself, and `own` marks an event with
such an answer. Through `raw.ads`, an answer's `(listing_id, response_id)` leads back to the
export file and its manifest line.

Each ad's record repeats its unit's whole history, so a unit with n ads holds about n² copies
of each of its events. Parsing every copy and grouping them in one query ran out of a 3 GB
memory limit on thelio. So `ads.answers` parses each record once and keeps an MD5 of its
history's JSON text. `ads.history_events` parses each distinct history once, from the earliest
answer holding it, and `ads.events` joins those events back to the answers through the hash.

`ads.first_ask` reads the ACTIVE events in each ad's own history and keeps the earliest day,
with the distinct prices of that day, whether one of that day's events lacked a price, and the
ad's first answer to report the day. The current chain prices an ad the same way:
`project_advertisement` in `apartments.historical_dataset` takes the earliest own ACTIVE rental
event, sets `price_at` to midnight UTC of its day, and drops an ad with a missing price or with
two. It reads only the answers collected by its cutoff, and `first_seen` gives the time from
which an ad's first day is known. A later answer can add a second price to that day, and
`first_ask` keeps no time for it, so a replay of the cutoff reads each price's `own_first_seen`
in `ads.events`.

## Attributes and exclusions

The current chain reads an ad's attributes in Python, in `apartments.graphql_listing` and
`project_advertisement`. Its rules for features, amenities, floors and exposures run to several
hundred lines. If I rewrote them in SQL, the repo would hold two copies to keep in step, so
`ads.record_attributes` runs the chain's own functions through `pipeline/steps/attributes.py`.
That module copies a few lines from the page parser, since the page parser retires with the
move to API records. Its docstring lists the steps.

`ads.record_attributes` is a Python model. It parses each distinct record once, in worker
processes, and keeps the results in Parquet files in `attributes/<code version>/` beside the
DuckDB database. A later build parses only records missing from those files, so a top-up
parses just its new records. `config.py` computes the code version as a SHA-256 over
`steps/attributes.py` and its six imports from `src/apartments`, and passes it to the model in
the variable `attributes_code`. When any of those files changes, the model writes to a new
folder and gets a new fingerprint. A test compares the list of files with the projection's
imports. `PIPELINE_WORKERS` sets the number of workers, 4 unless set.

SQLMesh puts `sys.path` and the environment back after it reads `config.py`, so `config.py`
also passes the folders `pipeline/` and `src/` in the variable `pythonpath`. The model adds them
to `sys.path` before it imports `steps.attributes`.

`ads.attributes` merges each ad's records as `project_advertisement` merges its captures: for
each attribute, one known value stands, and two or more give an unknown and put the attribute
in `conflicts`. A rental flag is true when any record sets it. The chain fails to parse a
record without propertyDetails or with another ad's `id`, and gives it a capture without
values, so `ads.attributes` leaves such records out.

`ads.exclusions` repeats `project_advertisement`'s reasons for dropping an ad, from its first
ask, its merged attributes and its rental flags. Its SQL describes each rule. Three of the chain's checks
wait for later steps: identity, the canonical URL, and the check for two ads of one unit in one
month. The chain also blanks a size outside 150 to 6,000 square feet without dropping the ad.
The fit-ready rows will apply that rule. The chain flags an own ACTIVE event later than its
as-of time, while `ads.exclusions` flags one later than the day of the ad's last answer.

## Tests

`pipeline/tests/fixture/` holds the analysis rows of five buildings, the 229 exported records of
their ads and the latest ask `rentfrontier.latest_ask` gave each row, 187 KB in all.
`pipeline/tests/make_fixture.py` writes it from the full inputs on thelio. The API data lacks
several cases the latest-ask steps handle, as the full build below notes, so
`pipeline/tests/make_cases.py` makes up seven answers and eleven rows for them in
`fixture/cases/`, 17 KB in all, and writes the latest ask `rentfrontier.latest_ask` gives each
row. Their records hold no unit histories. The tests:

1. build the fixture and compare each row's first ask, latest ask and step with
   `rentfrontier.latest_ask`;
2. build the made-up cases and compare them the same way. They hold several rows of one ad, a
   record collected before its row, an ad without answers, an empty latest answer, and rows
   without a building or a bedroom count;
3. build runs 2 and 3, then add run 4's file to the manifest. The next plan rebuilds `raw.ads`
   and the twelve tables below it and gives the full answer, and a further plan finds nothing
   to build. `ads.record_attributes` parses only run 4's new records;
4. write an export file again under its old name with another compression, and give the
   manifest its new hash. The next plan rebuilds the models below `raw.ads`;
5. add a run 5 file with a newer answer for one ad and an older answer for another. Only the
   first ad's row changes;
6. duplicate an analysis row. The `unique_values` audit on `analysis.latest_change` stops the
   plan, and the tables from the earlier plan stay in place;
7. drop a row from `analysis.latest_ask` in a copy of the project. The `every_row` audit stops
   the plan;
8. read manifests with a cut-off last line, a repeated line, a rewritten file and a file with
   two hashes;
9. build the fixture and compare each analysis row's price date, asking rent and bedroom count
   with its ad's first day, first ask and bedroom count. The current chain kept each ad of the
   fixture, and `ads.exclusions` gives none of them a reason;
10. add an answer that repeats an earlier record eight days later. `ads.events` gains the new
    fetch and nothing else. Each event of the record, its siblings' history events included,
    keeps its first answer and counts one answer more, and the other events stay as they were;
11. add four answers with histories to the made-up cases: an empty history, a history listing an
    event twice, an ACTIVE change without a price and a sibling's episode without a
    `listingId`, a later answer with an added event, and the same history from the sibling.
    The test checks every history event and first ask by value, along with the cases' missing
    answer;
12. add made-up records to the cases: an ad for each reason in `ads.exclusions`, an ad with
    none, a record without propertyDetails and a record with another ad's `id`. The test
    checks each ad's reasons, first ask, bedroom count and conflicts by value;
13. import `steps.attributes` in a fresh process and compare the modules it loads from `src`
    with the files of the code version.

They take about 30 s on thelio. SQLMesh loads models in forked workers, and a fork in a process
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

With the event log's four tables, I built runs 1 to 5 into an empty state in 109 s, at the
unit's 5 GB cap with DuckDB's limit at 4 GB. `ads.events` holds 23,340,393 events of 2,372,913
ads. Of those ads, 2,137,998 have answers of their own, and the other 234,915 appear only in the
unit histories of their siblings' records. Of the 8,392,975 history events an ad's own answers
reported, a sibling's answer reported 5,186,434 first. `ads.first_ask` gives 2,117,118 ads a
first day, with one price for 2,116,917 of them and two for 201, and none with a missing price.
Each first ask's `first_response_id` is an answer of its own ad. For each of the 1,396,053
analysis rows, `price_at` is its ad's first day at midnight UTC and `asking_rent` the single
price of that day:

```sh
uv run --project pipeline sqlmesh -p pipeline fetchdf "
  SELECT count(*) FROM raw.analysis_rows r LEFT JOIN ads.first_ask f ON f.listing_id = r.source_listing_id
  WHERE f.listing_id IS NULL OR r.price_at <> f.first_day::TIMESTAMPTZ OR f.prices <> [r.asking_rent]"
```
