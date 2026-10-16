# Pipeline project

The rebuilt pipeline is a SQLMesh project over DuckDB, in `pipeline/`. So far it builds each
analysis row's latest ask from the API export, as `rentfrontier.latest_ask` does, and a log of
the events the API reported for each ad, with each ad's first ask, its time on the market and
its ending. It also reads each ad's attributes from its records, gives the current chain's
reasons for dropping the ad, and finds each ad's unit. The later
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

The build reads the ads and buildings files listed in the manifest and skips any file still
lacking a line.
`ops/pipeline/analysis_rows.py` wrote the rows file from the four API region datasets of the
latest-ask run of Oct 15, `20261015-13f5968-api`. It stays an input until the event log builds
the rows from API records.

For each input, `config.py` also computes a version: for each export table, a SHA-256 over the
path and hash of each of its listed files, and the rows file's own SHA-256. SQLMesh fingerprints a model by its SQL as
written and by the values of the variables the SQL uses. The raw views use the versions as well
as the paths, so a file written again under its old name also counts as a change, once the
manifest's line for it carries the new hash. A second line for the same path with another hash
stops the build instead, since `config.py` refuses a path with two hashes. A new or
rewritten ads file changes `raw.ads`, and the next plan rebuilds it and every model below it. A
new buildings file changes `raw.buildings`, and the next plan rebuilds it and `ads.identity`.
With unchanged inputs, a plan builds nothing.

`raw.ads` holds every answer, including the API's empty answers, marked `missing`.
`ads.latest_record` reads only answers with a record, so an ad whose latest answer came back
empty keeps its last record, as in `rentfrontier.latest_ask`.

## Models

| model | kind | a row for each |
|---|---|---|
| `raw.ads` | view | exported API answer for an ad |
| `raw.buildings` | view | exported API answer for a building |
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
| `ads.market` | table | ad with a record: its days on the market, its spans on the market and its ending |
| `ads.record_attributes` | table | distinct API record: its attributes and rental flags, as the current chain reads them |
| `ads.attributes` | table | ad with a parsed record: its attributes and rental flags, merged over its records |
| `ads.exclusions` | table | ad with a record: its first day, its first ask and the current chain's reasons for dropping it |
| `ads.identity` | table | ad with a record: its building, its unit page and its unit |

The comments in each model's SQL describe its rules. The audits in the `MODEL` blocks check
keys and nulls: one row per listing in `ads.latest_record`, `ads.first_ask`, `ads.market`,
`ads.attributes`, `ads.exclusions` and `ads.identity`, per record in `ads.record_attributes`, per `(listing_id, response_id)` in
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

A record can list two status changes or two price changes at the same instant, and only the
record's order tells which came last. So each status and price change keeps `list_index`, its
place in its list in the latest answer that reported it, counting from 1. On runs 1 to 5, the
price change last in order of time and then of `list_index` matches the last item of the latest
record's `priceChanges` for every one of the 2,137,997 ads.

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

## Days on market

`ads.market` reads each ad's status changes from the event log and puts them in order of time,
and in the record's order when two share an instant. Each change holds until the next one, and
the last holds until the New York date of the ad's latest answer with a record. The model takes
from them:

- `on_day`, the day of the first change to ACTIVE, which StreetEasy gives as `onMarketAt`;
- `off_day`, the day of the last change from ACTIVE or IN_CONTRACT to another status, given as
  `offMarketAt`. An ad whose last change puts it ACTIVE or IN_CONTRACT has none;
- `active_days`, the days of all the ad's ACTIVE spans together;
- `active_spans`, the number of changes to ACTIVE from another status or from none. An ad put
  back on the market has two or more;
- `ending` and `ending_day`, the last change and its day, when that change is RENTED,
  NO_LONGER_AVAILABLE or DELISTED. An ad still on the market, in contract or paused has none.

It also keeps the status, `daysOnMarket` and `rentedPrice` of the ad's latest record, as the
API wrote them, so a reader can compare StreetEasy's count with the event log's.

I ran the model's query on a scratch build of runs 1 to 5. It took 4.1 s and gave 2,137,997
ads. The 2,117,296 of them with an ACTIVE change each have an `on_day` equal to the record's
`onMarketAt`. Of the 2,108,659 ads with both an `off_day` and an `offMarketAt`, 2,108,387 agree.
The other 272, and 440 ads with an `off_day` but no `offMarketAt`, pass through a draft or
review status, and StreetEasy counts those as on the market. Another 10,780 ads have an
`offMarketAt` and no `off_day`, and 10,773 of them have no ACTIVE change at all.

Of the ads on the market, 1,921,832 went on it once, 160,211 twice and 35,253 three times or
more. The median ad spent 14 days on the market, and the middle half spent 6 to 31.
2,118,172 ads have an ending: 1,034,220 rented, 735,138 no longer available and 348,814
delisted. Of the 23,925 ads with a `rentedPrice`, 22,205 end rented.

StreetEasy's `daysOnMarket` equals `active_days` for 1,984,995 of the 2,117,296 ads on the
market, 93.8%, and comes within a day for 2,024,992, 95.6%. So StreetEasy leaves out the days in
contract and the days paused, as `active_days` does. It counts more than a day more for 61,748
ads and more than a day fewer for 30,556. Agreement is lowest for ads first on the market in
2016 to 2018, with 89% to 90% exact. It reaches 96% to 97% for 2021 to 2024 and about 96% for
2025 and 2026. For the ads with more days in StreetEasy's count, the status changes show
nothing to account for them. Ad 4616858 has 575 days on StreetEasy's count and 92 in its
changes, and ad 4599884 has 65 and 12. The model
keeps both counts, and the fit-ready step picks one.

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
parses just its new records. `config.py` hashes `steps/attributes.py` and its six imports from
`src/apartments`, and passes each module's SHA-256 to the model in the variable
`attributes_code`. The cache folder takes its name from a SHA-256 over that variable. When any
of those files changes, the model writes to a new folder and gets a new fingerprint. A test
compares the list of modules with the projection's imports. `PIPELINE_WORKERS` sets the number
of workers, 4 unless set.

The pipeline's venv installs the project in editable mode, which puts `pipeline/` and the
repo's `src/` on `sys.path` of every process in the venv, the workers included. The model can
then import `steps.attributes` with no paths in its variables, so its fingerprint stays the same
in every checkout. The install holds the paths of the checkout where `uv sync` ran, though, so a
copy of the project, or a venv shared by two checkouts, can load code from another checkout
than the one `config.py` hashed. Before it parses a record, the model hashes the files of the
modules it loaded, and it stops the build when one differs from `attributes_code`. The model
writes each cache file under a temporary name, syncs it to disk and renames it, and it deletes
temporary files left by a build that stopped.

`ads.attributes` merges each ad's records as `project_advertisement` merges its captures: for
each attribute, one known value stands, and two or more give an unknown and put the attribute
in `conflicts`. A rental flag is true when any record sets it. The chain fails to parse a
record without propertyDetails or with another ad's `id`, and gives it a capture without
values, so `ads.attributes` leaves such records out.

`ads.exclusions` repeats `project_advertisement`'s reasons for dropping an ad, from its first
ask, its merged attributes and its rental flags. Its SQL describes each rule. It leaves out
three of the chain's checks. `ads.identity` makes two of them, of the unit's identity and of its
canonical URL, as the next section describes. The check for two ads of one unit in one month
waits for the fit-ready rows. The chain also blanks a size outside 150 to 6,000 square feet without
dropping the ad. The fit-ready rows will apply that rule. The chain flags an own ACTIVE event
later than its as-of time, while `ads.exclusions` flags one later than the day of the ad's last
answer. The chain reads events only from the records it parses, while the event log reads every
record. So an ad without a parsed record gets the chain's reason, `no_dated_own_active_event`,
and an ad with both kinds of record may take its first ask from a record the chain leaves out.
Runs 1 to 5 hold no record the chain fails to parse.

## Unit identity

`ads.identity` gives each ad the unit the current chain gives it, by the chain's rule
`canonical-url-v1`, from `canonical_units.memberships` and `graphql_listing.canonical_link`.
For each record of an ad, I take the API's building ID and unit slug from the record and look up
the building's slug in the export's buildings table, in the building's latest answer with a
record. The two slugs give the record's unit page,
`https://streeteasy.com/building/{building slug}/{unit slug}`. An ad takes a page when all its
records give the same one, and its unit ID is `unit:` and the version 5 UUID of that page, as
`uuid.uuid5(uuid.NAMESPACE_URL, page)` gives it. The SQL computes the UUID from a SHA-1 of the
namespace's bytes and the page.

A record gives no page when either slug is missing or empty, or holds a `/`, `?` or `#`. Where
an ad's records disagree, or one of them gives no page, the ad gets no unit. Its pages then stay
unresolved: an ad giving one of them gets no unit either, so no single ad joins two units. An ad
without a unit carries the chain's two reasons, `unresolved_or_conflicting_identity` and
`unresolved_or_conflicting_canonical_url`. The ad's building is the building of its latest
record.

The chain's `unit_page` differs on one kind of slug. When a unit slug ends in `/`, `?` or `#`, it
drops that character and keeps the page, while `ads.identity` gives none. No slug in runs 1 to 5
ends that way, and every unit slug there holds only lowercase letters, digits, `-` and `_`.

The current chain reads the building from the ad's capture, where the API answer for the ad
carries it. A building answered twice with two slugs would give its older ads the newer slug
here. Runs 1 to 5 hold one answer for each of their 70,137 buildings.

## Tests

`pipeline/tests/fixture/` holds the analysis rows of five buildings, the 229 exported records of
their ads, the five exported records of the buildings, and the latest ask
`rentfrontier.latest_ask` gave each row, 197 KB in all.
`pipeline/tests/make_fixture.py` writes it from the full inputs on thelio. The API data lacks
several cases the latest-ask steps handle, as the full build below notes, so
`pipeline/tests/make_cases.py` makes up seven answers, eleven rows and a building for them in
`fixture/cases/`, 23 KB in all, and writes the latest ask `rentfrontier.latest_ask` gives each
row. Their records hold no unit histories. The tests:

1. build the fixture and compare each row's first ask, latest ask and step with
   `rentfrontier.latest_ask`;
2. build the made-up cases and compare them the same way. They hold several rows of one ad, a
   record collected before its row, an ad without answers, an empty latest answer, and rows
   without a building or a bedroom count;
3. build runs 2 and 3, then add run 4's files to the manifest. The next plan rebuilds `raw.ads`,
   `raw.buildings` and the fourteen tables below them and gives the full answer, and a further
   plan finds nothing to build. `ads.record_attributes` parses only run 4's new records;
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
9. build the fixture and compare each analysis row's price date, asking rent, bedroom count and
   building with its ad's first day, first ask, bedroom count and building. The current chain
   kept each ad of the fixture, and neither `ads.exclusions` nor `ads.identity` gives any of
   them a reason;
10. add an answer that repeats an earlier record eight days later. `ads.events` gains the new
    fetch and nothing else. Each event of the record, its siblings' history events included,
    keeps its first answer and counts one answer more, and the other events stay as they were;
11. add four answers with histories to the made-up cases: an empty history, a history listing an
    event twice, an ACTIVE change without a price and a sibling's episode without a
    `listingId`, a later answer with an added event, and the same history from the sibling.
    The test checks every history event and first ask by value, along with the cases' missing
    answer;
12. add made-up records to the cases: an ad for each reason in `ads.exclusions`, an ad with
    none, a record without propertyDetails and a record with another ad's `id`. It adds ads at
    the edges of the ranges too: asks of $749, $750, $50,000 and $50,001, 0 and 5 bedrooms,
    half a bathroom, and 1.25 bathrooms from `bathroomCount`. Four more ads have two records
    each, with two sizes, two doorman types, leases of 12 and 3 months, or the same values in
    both. The last ad carries a feature code for furnished. The test checks each ad's reasons,
    first ask, bedroom count, conflicts and number of records by value;
13. build run 2 in a copy of the project, then change the copy's `steps/attributes.py` to give
    every record 9 bedrooms. A plan in the test's process stops with the mismatch error, since
    the venv loads the repo's own code. A plan in a new process, with the copy first on
    `PYTHONPATH`, parses the same records into a second cache folder, each with 9 bedrooms;
14. import `steps.attributes` in a fresh process and compare the modules it loads from `src`
    with the files of the code version;
15. add made-up ads to the cases: an ad put in contract, back on the market twice in a day and
    rented, an ad paused and back on the market, an ad delisted from a draft, an ad without
    status changes, an ad with two answers, the later of which ends it, and an ad whose record
    lists two pairs of changes at shared instants in an order other than the alphabet's. One
    ad's latest answer has no record, and another's latest record has no `daysOnMarket`. The
    test checks each ad's days, spans, ending and record fields by value;
16. add made-up ads and buildings to the cases: two ads of one unit, an ad giving two pages and
    an ad giving the second of them, ads with an empty unit slug, none or one holding a `/`, an
    ad naming a building missing from the export, an ad in a building whose later answer renames
    it, an ad whose latest answer is missing, a building slug holding a `|`, and an ad whose
    latest record names no building. The test computes each ad's page and unit with the chain's
    `unit_page` and `memberships` and compares them with `ads.identity`, then checks the cases
    by value;
17. build every ads file but only the buildings files of runs 2 and 3, then add run 4's buildings
    file. The next plan rebuilds only `raw.buildings` and `ads.identity`, and the 49 ads of the
    building in that file gain their pages.

They take about 40 s on thelio. SQLMesh loads models in forked workers, and a fork in a process
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

With the attributes and exclusions, I built runs 1 to 5 into an empty state in 640 s, in a unit
with a 6 GB limit and DuckDB's limit at 4 GB. `ads.record_attributes` spent 451 s of that on
the 2,138,007 distinct records, parsed in four workers, and `ads.attributes` took 67 s. The unit's
peak hit its 6 GB limit with page cache included, and no process was killed. A second plan on
the same state found nothing to do in 3.5 s. Then I built the same runs into another empty state
holding a copy of the first build's parse cache, as a build after a change elsewhere would.
`ads.record_attributes` read every record from the cache in 25 s, the plan took 199 s, and
anonymous memory peaked at 5.1 GB. The eight tables from `ads.answers` to `analysis.latest_ask`
have the same row counts and the same sums of row hashes in both states.

The chain's audit of the four regions, in `/data1/apartments/tmp/pipeline/audit/audit.parquet`,
holds the reasons and captures of 1,692,611 ads. I compared the 1,692,593 of them with no answer
after the audit ran at 13:10 ET. Leaving out the three checks of later steps, `ads.exclusions`
gives each of them the same reasons as the audit, and 1,466,352 have no reason in either. The
counts per reason:

| reason | ads |
|---|--:|
| `excluded_concession` | 135,408 |
| `excluded_furnished` | 66,964 |
| `invalid_or_missing_layout` | 11,032 |
| `invalid_or_extreme_initial_ask` | 8,868 |
| `no_dated_own_active_event` | 8,230 |
| `conflicting_or_missing_initial_prices` | 163 |
| `excluded_short_term` | 23 |
| `outside_date_window` | 2 |

The audit keeps no captures for the 8,230 ads without a dated own ACTIVE event. For the other
1,684,363, I merged the audit's projections as `ads.attributes` merges records, and all sixteen
attributes and flags equal the built ones. The script is
`/data1/apartments/tmp/pipeline/attr/parity.py`.

I ran `ads.identity`'s SQL on runs 1 to 5 in 10.7 s, with a 1.9 GB peak for the unit. It gives
2,123,148 of the 2,137,997 ads with a record a page and a unit, in 930,879 units. The other
14,849 ads have a record without a unit slug: 14,741 lack the field, and 108 leave it empty. No
ad has records giving two pages, so no page stays unresolved. Of the eight regional analysis
datasets of the Oct 15 chain run, `api-*-analysis-20261015-6064263`, I left out
`api-manhattan-59th-110th`, which overlaps the east and west datasets. On each of the other
seven's 1,923,491 rows, the row's unit, canonical page and building equal its ad's in
`ads.identity`. Each of the 1,692,611 ads in the chain's audit has a unit here, and none of the
14,849 ads without one appears in the audit. The script is
`/data1/apartments/tmp/pipeline/step4d/identity_model.py`.
