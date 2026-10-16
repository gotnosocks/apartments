# Pipeline project

The rebuilt pipeline is a SQLMesh project over DuckDB, in `pipeline/`. So far it reads the API
export and builds a log of the events the API reported for each ad, with each ad's first ask, its
time on the market and its ending. It reads each ad's attributes from its records, gives the
current chain's reasons for dropping the ad, and finds each ad's unit. From those it builds the
fit-ready rows, one for each unit and month, and gives each row its latest ask, as
`rentfrontier.latest_ask` does. The later steps in
[the pipeline handoff](../handoff/data-pipeline.md) add models to it.

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
| `PIPELINE_STATE` | `/data1/apartments/pipeline/state` | the DuckDB database, spill files and SQLMesh's cache |
| `PIPELINE_LEDGER` | `pipeline/ledger` in the checkout | the corrections ledger, as described under [Corrections ledger](#corrections-ledger) |

The build reads the ads and buildings files listed in the manifest and skips any file still
lacking a line.

For each export table, `config.py` also computes a version, a SHA-256 over the path and hash of
each of its listed files. SQLMesh fingerprints
a model by its SQL as written and by the values of the variables the SQL uses. The raw views use
the versions as well as the paths, so a file written again under its old name also counts as a
change, once the manifest's line for it carries the new hash. A second line for the same path
with another hash stops the build instead, since `config.py` refuses a path with two hashes. A new or
rewritten ads file changes `raw.ads`, and the next plan rebuilds it and every model below it. A
new buildings file changes `raw.buildings`, and the next plan rebuilds it, `buildings.details`,
`ads.identity`, the fit-ready rows and their latest asks.
With unchanged inputs, a plan builds nothing.

`raw.ads` holds every answer, including the API's empty answers, marked `missing`.
`ads.latest_record` reads only answers with a record, so an ad whose latest answer came back
empty keeps its last record, as in `rentfrontier.latest_ask`.

## Build command

`ops/pipeline/build.py` builds the project, saves the fit-ready rows and records the build:

```sh
uv run --project pipeline python ops/pipeline/build.py [--export DIR] [--state DIR] [--out DIR]
```

It plans and applies `prod`, as the `sqlmesh plan` line above does. Then it writes
`analysis.rows`, sorted by `listing_id`, to a Parquet file in OUT, by default
`/data1/apartments/pipeline/datasets`. The file's name holds the first 16 hex digits of its
SHA-256, as in `rows-4743b90bc5aa49b4.parquet`. Last, the script appends a line for the build to
`OUT/catalog.ndjson`:

| key | holds |
|---|---|
| `built` | the time the build finished, in UTC |
| `code` | the checkout's commit, and `clean`, false when `pipeline/`, `src/` or `ops/pipeline/` differ from it |
| `export`, `ads`, `buildings` | the export folder, and for each table its version from `config.py` and each file it listed, with the file's SHA-256 |
| `models` | each model's table in the state and its row count, and the seconds its evaluation and audits took, or null when the build left the model as it was |
| `ledger` | the ledger's files with their SHA-256, and its entries counted by status and change |
| `rows` | the rows file's name, SHA-256 and row count |
| `seconds` | the wall time of loading the project, of the plan, of counting rows and of writing the file, and the total |
| `peak_mib` | the peak resident memory of the script, DuckDB's included, and the peak and name of the script's cgroup |

When an audit fails, the script prints the failed models and exits with status 1. It writes
nothing to OUT, and the tables of the last good build stay in place. After a good build, the
script runs SQLMesh's janitor, which drops the tables no environment has used for a week. A
failed janitor prints a warning and leaves the build's status at 0.

DuckDB writes the same bytes for the same table, so a second build from the same export and
code finds its file already in OUT. Late on Oct 15, two builds in a row on that day's full state
wrote the same 80 MB file of 1,747,140 rows, in 2.7 and 3.0 s. A fit can read a rows file by
its name and check the file's SHA-256 against the catalog, though no fit reads one yet.

Early on Oct 16, three builds ran one after another as light jobs with a 4,500 MiB cap and
`PIPELINE_MEMORY=3GB`:

| build | starting state | job's wall time | `ads.record_attributes` | other models | script's peak |
|---|---|---|---|---|---|
| runs 1 to 4, 1,713,244 records | empty | 695 s | 502 s | 178 s | 3,782 MiB |
| run 5 added, 424,776 more | the first build's | 399 s | 154 s | 227 s | 4,021 MiB |
| runs 1 to 5 | empty | 769 s | 562 s | 191 s | 4,053 MiB |

The job's wall time includes about 10 s of imports before the catalog's `seconds` start counting,
so the catalog gives 684, 388 and 759 s. The top-up and the build from empty wrote the same rows
file, `rows-4743b90bc5aa49b4.parquet`, and every model came out with the same row count. The two
builds on the Oct 15 state had written the same file. Each build's cgroup peaked within 40 MiB of
the cap because the page cache fills the cgroup, so the script's own peak gives the memory a
build needs.

In the top-up, `ads.record_attributes` parsed the 424,768 distinct records missing from its cache
and copied the 1,713,239 cached ones into its table again, and the models after it recomputed every ad. Those full recomputes
take most of a top-up's time.

At 01:13 ET on Oct 16, the service in the next section built runs 1 to 5 into the empty default
state in 583 s, 575 s of them in the catalog's count. `ads.record_attributes` took 410 s, and the
script peaked at 4,143 MiB. It wrote the same `rows-4743b90bc5aa49b4.parquet`. The service runs
the build on all twelve CPUs at nice 10, where the light jobs above had six.

### After each export

`apartments-pipeline-build.service` runs `ops/pipeline/build-latest`, which builds into the
default state and OUT. Its path unit starts it whenever the exporter changes
`/data1/apartments/archive/crawls/api/export/manifest.ndjson`, and its timer starts it every day
at 07:15 ET, to catch a missed trigger or a pipeline change merged to master. The script:

1. waits for the collector to let go of `oxylabs.lock`, so the build starts after an export's
   last file;
2. moves its own checkout, `/data1/apartments/pipeline/code`, to master and syncs
   `/data1/apartments/venvs/pipeline` from `pipeline/uv.lock`, and stops there when the
   manifest and the pipeline's code match the last build's, as on most of the timer's runs;
3. takes the GPU lock and every light slot, as `ops/job gpu -x` does, so no GPU fit or light job
   runs beside the build, and checks for 6 GiB of available memory, letting go of the locks and
   trying again every five minutes while less is available;
4. runs `build.py` with `PIPELINE_MEMORY=3GB` in the service's own cgroup, which the unit caps
   at 5 GiB with swap off, and lets go of the locks after it;
5. builds again when the manifest changed during the build.

Manual exports with `streeteasy_archive.graphql_export` take `export/.lock` and exit when it is
held, so the script waits on `oxylabs.lock` alone. When such an export appends its lines during
a build, step 5 builds again.

After each build, the script writes the manifest's hash and the commit's trees to
`/data1/apartments/pipeline/state/last-build`. After a build by hand into the default state and
OUT, delete that file, so the next trigger builds from master again.

A failed build leaves the service failed, with the failed models in its journal:

```sh
systemctl --user status apartments-pipeline-build
journalctl --user -u apartments-pipeline-build -o cat | grep -v pydantic | tail -n 40
```

The checkout and the units go in once. The second line adds the checkout when it is missing,
and the third moves it to master, so the service finds the script:

```sh
C=/data1/apartments/pipeline/code
[ -d $C ] || git -C /data1/apartments/serve/master worktree add --detach $C origin/master
git -C $C fetch -q origin master && git -C $C checkout -q --detach origin/master
cp /data1/apartments/pipeline/code/ops/systemd/apartments-pipeline-build.{path,service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now apartments-pipeline-build.path apartments-pipeline-build.timer
```

## Models

| model | kind | a row for each |
|---|---|---|
| `raw.ads` | view | exported API answer for an ad |
| `raw.buildings` | view | exported API answer for a building |
| `ads.answers` | table | answer, with the fields the event log and the latest-ask steps read and a hash of its unit history |
| `ads.history_events` | table | event in a distinct unit history |
| `ads.events` | table | event the API reported for an ad, with the answers that reported it |
| `ads.latest_record` | table | ad, from its latest answer with a record: the answer's ID, status, market days and page price |
| `ads.price_changes` | table | nonzero price change of an ad's latest record, from the event log, numbered in order of time |
| `ads.kept_changes` | table | price change left after the placeholder check |
| `ads.first_ask` | table | ad with an ACTIVE event in its own history: its first day on the market and its asks that day |
| `ads.market` | table | ad with a record: its days on the market, its spans on the market and its ending |
| `ads.record_attributes` | table | distinct API record: its attributes and rental flags, as the current chain reads them |
| `ads.attributes` | table | ad with a parsed record: its attributes and rental flags, merged over its records |
| `ads.exclusions` | table | ad with a record: its first day, its first ask and the current chain's reasons for dropping it |
| `buildings.details` | table | building with a record: the slug and area of its latest record, and its floor count |
| `ads.identity` | table | ad with a record: its building, its unit page and its unit |
| `ads.reported` | table | ad with a record: the floor its unit labels read, and its full and half bathrooms |
| `analysis.candidates` | table | ad the current chain accepts before its unit-month check: its fit-ready values and its fate in that check |
| `analysis.kept` | view | candidate kept for its unit and month |
| `ledger.entries` | table | line of the corrections ledger, checked against the ledger's rules |
| `ledger.status` | table | entry of the corrections ledger: its status against the kept rows |
| `analysis.rows` | view | fit-ready row: a kept row the ledger leaves in, with the values its live sets give |
| `analysis.latest_change` | table | fit-ready row, with its ad's last kept change from the row's day on and its page price |
| `analysis.latest_ask` | table | fit-ready row, with its first ask, its latest ask and the step behind the latest |

The comments in each model's SQL describe its rules. The audits in the `MODEL` blocks check
keys and nulls: one row per listing in `ads.latest_record`, `ads.first_ask`, `ads.market`,
`ads.attributes`, `ads.exclusions`, `ads.identity`, `ads.reported`, `analysis.candidates`,
`analysis.latest_change` and `analysis.latest_ask`, per building in `buildings.details`, per
record in `ads.record_attributes`, per `(listing_id, response_id)` in `ads.answers`, per
`(listing_id, n)` in `ads.price_changes` and per event in `ads.events`. The `every_row` audit,
in `pipeline/audits/`, checks that `analysis.latest_ask` keeps every fit-ready row. When an
audit fails, the plan stops, and the tables from the last good plan stay in place.

To try an edit, I build it in a dev environment beside prod and list the rows it changes:

```sh
uv run --project pipeline sqlmesh -p pipeline plan dev --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline table_diff prod:dev -m analysis.latest_ask -o listing_id --show-sample
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

`ads.price_changes` takes the price changes of each ad's latest record from the event log: the
price events with `last_seen` at that record's fetch. When a later answer leaves out a
change from an earlier one, the latest asks follow the latest record, as the chain's do. No ad
of runs 1 to 5 has such a change, so all of an ad's price events belong to its latest record.

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
2016 to 2018, with 89% to 90% exact, and rises to 96% to 97% for 2021 to 2024 and about 96% for
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
happens in `analysis.candidates`. The chain also blanks a size outside 150 to 6,000 square feet
without dropping the ad, and `analysis.candidates` applies that rule as well. The chain flags an own ACTIVE event
later than its as-of time, while `ads.exclusions` flags one later than the day of the ad's last
answer. The chain reads events only from the records it parses, while the event log reads every
record. So an ad without a parsed record gets the chain's reason, `no_dated_own_active_event`,
and an ad with both kinds of record may take its first ask from a record the chain leaves out.
Runs 1 to 5 hold no record the chain fails to parse.

## Unit identity

`ads.identity` gives each ad the unit the current chain gives it, by the chain's rule
`canonical-url-v1`, from `canonical_units.memberships` and `graphql_listing.canonical_link`.
For each record of an ad, I take the API's building ID and unit slug from the record and look up
the building's slug in `buildings.details`, which reads it from the building's latest answer with
a record. The two slugs give the record's unit page,
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

The chain's `unit_page` cleans the unit slug before it builds the page. It drops a trailing `/`,
`?`, `#` or `;` and removes tabs and line breaks, while `ads.identity` gives no page for a slug
with one of the first three characters and keeps the others. Every unit slug in runs 1 to 5
holds only lowercase letters, digits, `-` and `_`, so the two agree there.

The collector stores each ad's record with the slug its building had in the same generation
when it stored the ad, and the current chain reads the building slug from that record.
`ads.identity` takes the slug from the building's latest answer instead. With a building
answered twice under two slugs, the chain would keep the older slug for ads stored before the
second answer, while `ads.identity` gives every ad the newer one. Runs 1 to 5 hold one answer
for each of their 70,137 buildings.

## Fit-ready rows

`analysis.rows` gives a fit its rows, one for each unit and month, with the values of the current
chain's analysis datasets. I build them in four steps.

1. `buildings.details` takes each building's slug and area name from its latest record. For the
   floor count, it takes the smallest positive `floorCount` among the building's records and
   rounds it down, as `floor_counts` in `rentfrontier.cohort` does. The chain keys both values on
   the building slug and takes the area most of a building's records give. Runs 1 to 5 answer
   each building once, so the two readings agree on them. The chain also counts a boolean `true`
   as one floor, since Python's `True` is an int. `buildings.details` skips a boolean, the second
   item under [Differences from the chain](#differences-from-the-chain).
   Of the 70,137 building records of runs 1 to 5, 67,811 give a whole number and the other
   2,326 give no count.
2. `ads.reported` reads the unit label in `displayUnit`, `fullBathroomCount` and
   `halfBathroomCount` from each record of an ad. For the label, I follow the chain's
   `label_floor`: strip the whitespace, drop a leading `#`, put the rest in upper case, and try
   five patterns, such as `4D`, `1205` for the 12th floor, and `3RDFL`. An ad gets a label floor
   when each of its records gives a label and all the labels read the same floor. For the
   bathrooms, I follow `consensus`: a count holds when every record gives the same whole number
   of zero or more, and a boolean doesn't count as a number.
3. `analysis.candidates` joins the ads with no reason in `ads.exclusions` or `ads.identity` to
   their attributes, their reported values and their building, and gives each ad a floor:
   - its advertised floor, when it has one, with the status `explicit_source_floor`;
   - otherwise its label floor, with the status `label_proxy`.
   The chain refuses a label floor in three cases, and the status then names the case:
   `unresolved_or_conflicting_capture_labels` when the labels give no floor,
   `above_captured_building_floor_count` when the floor lies above the building's floor count,
   and `two_digit_label_without_building_count` for a floor of 10 or more in a building without
   a count. The model also blanks a size outside 150 to 6,000 square feet. Last, it gives each ad
   a fate in its unit and month of first day:
   - `conflicting_layout_same_unit_month` for every ad of a unit-month whose ads give two bedroom
     counts or two bathroom counts, as in the chain's `historical_dataset`;
   - `kept` for the ad with the latest first day in each other unit-month, and on a tie, for the
     ad with the greatest ID compared as text;
   - `superseded_in_unit_month` for the rest.

   Every candidate has a building and a bedroom count, since `ads.identity` and `ads.exclusions`
   give a reason to an ad lacking either, and an audit on `analysis.candidates` checks it.
4. `analysis.kept` gives the kept candidates as a view.
5. `analysis.rows` applies the corrections ledger to the kept rows, as described under
   [Corrections ledger](#corrections-ledger).

The chain checks a unit-month within a slice of one region's dataset, while `analysis.candidates`
checks it over every region. Each row lists the export regions of its ad's answers in `regions`,
so a fit can choose the regions it reads.

## Latest ask

`analysis.latest_ask` gives each fit-ready row the latest ask `rentfrontier.latest_ask` chooses
for it. An ad gives at most one fit-ready row, priced on its first day. `analysis.latest_change`
takes the ad's last kept change dated on or after that day, or the change in effect on that day
when the ad has no later one and its record came after the row. The steps in
`analysis.latest_ask` then check that ask against the row's first ask, the ad's page price and
the median first ask of the building's other rows with the same bedroom count. The comments in
the model list the steps. The medians cover every region in `analysis.kept`, while the chain
takes them over the rows of the datasets it reads. On the full export the two give the same
steps, as the full build below shows.

The median reads list positions with `list_extract`. SQLMesh renders each model through
sqlglot, and sqlglot 30.8 adds 1 to a computed index in brackets once it knows the list's type,
so a bracket reads the next element of the sorted list.

## Corrections ledger

The fit-ready rows take their corrections from the ledger in `pipeline/ledger/`, a folder of
NDJSON files. To correct a row, a person or a script writes the decision as a line of a batch
file and merges it through a reviewed PR. The docstring of `pipeline/models/ledger/entries.py`
lists the keys of a line and the rules it must follow. In short, a line:

- excludes an ad's row, gives one field of the row new values, or retracts an earlier entry;
- gives the ad's `listing_id`;
- gives in `when` the row's values the decision rests on, such as the recorded bedroom count
  for a bedroom set, or the month for an exclude;
- lists its evidence. A set needs an item beyond the ad's own words: another ad for the unit, a
  stated size, a floor plan, units of the same line, or Ben's own reading;
- gives the day of the decision, and the file and line it came from.

Lines merged to master stay as they are, and a later file retracts a wrong entry.
`tests/test_ledger.py` compares each file with its version at the merge base with master.

Three models read the ledger:

1. `ledger.entries` reads every file and checks each line. A line breaking a rule stops the
   build, and the error gives its file and line.
2. `ledger.status` checks each entry against `analysis.kept` and gives it the first status
   that fits:

   | status | the entry |
   |---|---|
   | `retract` | undoes another |
   | `retracted` | is undone by a later retract |
   | `absent` | is for an ad with no kept row |
   | `stale` | gives a value in `when` other than the kept row's, and `differs` lists the values |
   | `superseded` | sets a field a later live set of the row also sets |
   | `live` | applies |

3. `analysis.rows` drops the rows of the live excludes and gives the values of the live sets.
   A bath set gives the full and half bathrooms and leaves `bathrooms` as recorded, as the
   chain's bath rules do.

`analysis.latest_ask` reads `analysis.kept`, as the chain chooses each latest ask before its
correction rules apply, so a change to the ledger rebuilds only the two ledger models and
`analysis.rows`. The catalog line of each build lists the ledger's files with their SHA-256,
and counts the entries by status and change.

### The chain's corrections

`ops/pipeline/ledger_import.py` wrote the corrections of the chain's latest rules into
`pipeline/ledger/2026-10-16-chain.ndjson`. For each correction, it reads the dataset listed
in the rule's provenance file to find the row's ad and its recorded values. Then it gathers the
evidence: the ad's words from the rule file, the reads and floor plans in `config/reviews/`
that decided the correction, and the unit's other ads in the latest analysis dataset. Those
ads back a set when more of them give the corrected value than give the recorded one. A size
set rests on the unit's other ads with the same bedroom count and a size within 10% of the
corrected one, or, when the rule decided it from the unit's line, on the other units of the
line with that bedroom count and size.

A size a read found stated for the unit backs a bedroom set only when the corrected count's
median size lies nearest to it of all the counts' medians, as 827 sq ft does for a one-bedroom.
The 1,400 sq ft of a studio corrected to two bedrooms lies nearest the three-bedroom median, so
the importer keeps it as a read, and the set needs other backing.

A set without backing goes to `config/reviews/ledger-held-2026-10-16-chain.jsonl` instead,
with the counts of the unit's other ads, for a reader to look for backing. A second run of the
importer leaves out each correction from a rule file and line already in the ledger, and each
one repeating the latest entry for its ad and field, so it writes only a new rule version's new
decisions.

| rule | corrections | in the chain batch | backed by a later read | held |
|---|--:|--:|--:|--:|
| `bedrooms-ad-v3` | 148 | 92 | 9 | 47 |
| `bedrooms-ad-v4` | 22 | 13 | 0 | 9 |
| `bedrooms-ad-v5` | 4 | 4 | 0 | 0 |
| `bedrooms-ad-v6` | 13 | 10 | 0 | 3 |
| `bedrooms-ad-v7` | 17, 13 of them from v6 | 2 | 2 | 0 |
| `baths-ad-v3` | 59 | 35 | 1 | 23 |
| `sqft-units-v1` | 12 | 12 | 0 | 0 |
| `quarantine-v32` | 889 | 889 | 0 | 0 |

Of the batch's 168 sets, 158 rest on the unit's other ads, 12 on a stated size, 6 on a floor
plan, 2 on units of the same line and 2 on Ben's own review, some on more than one.

Data improvements read the first list of held sets with Sonnet subagents, looking for backing.
`pipeline/ledger/2026-10-16-held-reads.ndjson` holds the 12 sets they backed, 7 by another ad
for the unit and 5 by units of the same line. The held column counts the 70 sets still without
backing from that list, and 12 bedroom sets of v4 and v6 whose stated size lies nearest a third
count.

`pipeline/ledger/2026-10-16-short-stay.ndjson` excludes three short-stay ads Data improvements
found on Oct 16, in a second regex pass over the reads of the API rows.

The chain's other rules are not in the ledger yet: `building-joins-v1`, `west-coast-wings-v1`,
`unit-splits-v4`, `unit-labels-v17`, `unit-reviews-v2`, `fields-review-v3`,
`elevator-from-ad-v1` and `pets-from-ad-v1`.

### Check build

I built a copy of the Oct 15 production state with the ledger, at `PIPELINE_MEMORY=3GB` under a
6 GB cap. The first plan took 591 s, 426 s of it in `ads.record_attributes`, and the build
script peaked at 4.1 GiB. After the ledger changed, the next build rebuilt the two ledger models
and `analysis.rows` in 6.3 s, with a peak of 3.3 GiB. The ledger's 1,072 lines came out as:

| status | excludes | sets |
|---|--:|--:|
| `live` | 857 | 169 |
| `absent` | 35 | 11 |

The 46 absent entries are for ads with no API record in runs 1 to 5. Only the page crawl found
them. `analysis.rows` holds 1,746,283 rows, 857 fewer than `analysis.kept`.

No ad of the six API region references has an entry in the ledger. For each of their 1,923,491
rows, `analysis.rows` holds a row with the same ad and price day, and with the same bedrooms,
bathrooms and size.

The queued nine-area fit's frozen rows, `queued-nb9-lots2-9c1055f`, come from the page crawl
through the rules `bedrooms-ad-v6` and `quarantine-v31`. I matched its 296,182 rows to the
fit-ready rows by ad:

| reference rows | count |
|---|--:|
| in `analysis.rows`, priced on the same day | 291,343 |
| in `analysis.rows`, priced on another day | 240 |
| dropped by an exclude of `quarantine-v32`, newer than the reference | 6 |
| of ads with no API record in runs 1 to 5 | 4,515 |
| of ads losing the unit-month check to another ad | 63 |
| of ads dropped by their API record's exclusions | 15 |

Of the matched rows, 58 differ in bedrooms, 16 in bathrooms and 3 in size:

- In 55 of the bedroom differences and all 16 bath differences, the reference applies a held
  set of `bedrooms-ad-v3`, `bedrooms-ad-v4`, `bedrooms-ad-v6` or `baths-ad-v3`, and the
  fit-ready row keeps the recorded value.
- The other 3 bedroom differences and the 3 size differences come from six ads listed from July
  to October 2026. For each of them, the page capture and the latest API record give different
  values, and the reference keeps the page's value.

In the reference's neighbourhoods, `analysis.kept` holds another 58,088 rows with no ledger
exclude. They are API ads missing from the page crawl.

## Differences from the chain

Where the pipeline gives a value other than the current chain's on purpose, I add the
difference to this list. A comparison with the chain counts a differing row as explained only
when an item here or an entry of the corrections ledger accounts for it.

1. An ad from a unit's history, when the unit's latest ad has no unit page. The chain's
   collector finds the unit of a history ad only through the unit page of the unit's latest
   ad, and drops the ad as `missing_canonical_unit_association` when that page is missing.
   `ads.identity` builds each ad's page from the ad's own records. On runs 1 to 5, this gives
   92 more rows in the four regions.
2. A boolean `floorCount`. The chain's `floor_counts` counts `true` as one floor, and
   `buildings.details` skips it. No building record of runs 1 to 5 gives one.
3. The scope of the unit-month check and of the building medians. The chain checks a unit-month
   within a slice of one region's dataset and takes the medians over the datasets it reads.
   `analysis.candidates` checks each unit-month, and `analysis.latest_ask` takes each median,
   over every region. On runs 1 to 5, the two scopes give the same rows and the same latest
   asks.
4. A price change a record lists twice, at the same instant and price. The chain reads the
   record's list as it stands, while `ads.price_changes` takes the change once from the event
   log. Of the 5,006,178 changes the latest records of runs 1 to 5 list, 4,628 repeat an
   earlier item, and no latest ask changes.
5. The order of price changes in the hour after clocks fall back. The chain sorts a record's
   changes by the text of `changedAt`, and `ads.price_changes` sorts them by instant. The two
   orders can differ only when two changes carry different UTC offsets, as in the repeated hour
   of early November. On runs 1 to 5, 124,228 ads list changes with both offsets, and each of
   them gets the same order either way.
6. A correction without backing. The chain applies each correction of its rules, while the
   ledger leaves out a set until it has evidence beyond the ad's words. The 82 sets of the
   chain's latest rules held this way are in `config/reviews/ledger-held-2026-10-16-chain.jsonl`,
   and their rows keep the recorded value.
7. The values of an ad's captured page. The page-crawl chain takes an ad's values from the page
   it captured, and the pipeline takes them from the ad's latest API record. For six ads of the
   nine-area reference, listed from July to October 2026, the two give different bedroom counts
   or sizes.

## Tests

`pipeline/tests/fixture/` holds the 229 exported records of the ads of five buildings, the five
exported records of the buildings, the chain's analysis rows of those ads, and the latest ask
`rentfrontier.latest_ask` gave each row, 199 KB in all. `pipeline/tests/make_fixture.py` writes
it from the full inputs on thelio. The API data lacks several cases the steps handle, so
`pipeline/tests/make_cases.py` makes up seven answers and a building in `fixture/cases/`, 14 KB
in all, and most tests add made-up ads to that export. The tests:

1. build the fixture and compare each fit-ready row's first ask, latest ask and step with the
   latest-ask run's;
2. add made-up ads of a building to the cases, build them, and compare each row's latest ask
   and step with `choose` of `rentfrontier.latest_ask`, run in the test over the same rows and
   each ad's latest record. The ads hold a change after the row's day, a change only before
   it, a page price without changes, a page price equal to one of the ad's changes, an ask
   that more than doubles and one that falls below half, a page price a tenth of the ask and
   one ten times the ask, an empty latest answer, a later record leaving out a change of an
   earlier one, and a placeholder price after the ad left the market;
3. build runs 2 and 3, then add run 4's files to the manifest. The next plan rebuilds `raw.ads`
   and the nineteen models below it and gives the full answer, and a further
   plan finds nothing to build. `ads.record_attributes` parses only run 4's new records;
4. write an export file again under its old name with another compression, and give the
   manifest its new hash. The next plan rebuilds the models below `raw.ads`;
5. add a run 5 file with a newer answer for one ad and an older answer for another. Only the
   first ad's latest ask changes;
6. add an export file repeating an answer. The audit on `ads.answers` stops the plan, and the
   tables from the earlier plan stay in place;
7. drop a row from `analysis.latest_ask` in a copy of the project. The `every_row` audit stops
   the plan;
8. read manifests with a cut-off last line, a repeated line, a rewritten file and a file with
   two hashes;
9. add an answer that repeats an earlier record eight days later. `ads.events` gains the new
   fetch and nothing else. Each event of the record, its siblings' history events included,
   keeps its first answer and counts one answer more, and the other events stay as they were;
10. add four answers with histories to the made-up cases: an empty history, a history listing an
    event twice, an ACTIVE change without a price and a sibling's episode without a
    `listingId`, a later answer with an added event, and the same history from the sibling.
    The test checks every history event and first ask by value, along with the cases' missing
    answer;
11. add made-up records to the cases: an ad for each reason in `ads.exclusions`, an ad with
    none, a record without propertyDetails and a record with another ad's `id`. It adds ads at
    the edges of the ranges too: asks of $749, $750, $50,000 and $50,001, 0 and 5 bedrooms,
    half a bathroom, and 1.25 bathrooms from `bathroomCount`. Four more ads have two records
    each, with two sizes, two doorman types, leases of 12 and 3 months, or the same values in
    both. The last ad carries a feature code for furnished. The test checks each ad's reasons,
    first ask, bedroom count, conflicts and number of records by value;
12. build run 2 in a copy of the project, then change the copy's `steps/attributes.py` to give
    every record 9 bedrooms. A plan in the test's process stops with the mismatch error, since
    the venv loads the repo's own code. A plan in a new process, with the copy first on
    `PYTHONPATH`, parses the same records into a second cache folder, each with 9 bedrooms;
13. import `steps.attributes` in a fresh process and compare the modules it loads from `src`
    with the files of the code version;
14. add made-up ads to the cases: an ad put in contract, back on the market twice in a day and
    rented, an ad paused and back on the market, an ad delisted from a draft, an ad without
    status changes, an ad with two answers, the later of which ends it, and an ad whose record
    lists two pairs of changes at shared instants in an order other than the alphabet's. One
    ad's latest answer has no record, and another's latest record has no `daysOnMarket`. The
    test checks each ad's days, spans, ending and record fields by value;
15. add made-up ads and buildings to the cases: two ads of one unit, an ad giving two pages and
    an ad giving the second of them, ads with an empty unit slug, none or one holding a `/`, an
    ad naming a building missing from the export, an ad in a building whose later answer renames
    it, an ad whose latest answer is missing, a building slug holding a `|`, and an ad whose
    latest record names no building. The test computes each ad's page and unit with the chain's
    `unit_page` and `memberships` and compares them with `ads.identity`, then checks the cases
    by value;
16. build every ads file but only the buildings files of runs 2 and 3, then add run 4's buildings
    file. The next plan rebuilds only `raw.buildings`, `buildings.details`, `ads.identity`,
    `analysis.candidates`, `analysis.kept`, the latest asks, `ledger.status` and
    `analysis.rows`, and the 49 ads of the building in that file gain their pages;
17. build the fixture and compare `analysis.rows` with `fixture/chain-rows.parquet`, which
    `make_fixture.py` copies from the chain's analysis datasets that the latest-ask run's
    provenance lists. Each of the 229 rows agrees in every value the pipeline rebuilds;
18. add made-up ads and buildings to the cases:
    - two ads of a unit in one month, two ads of another unit on the same day, a unit whose ads
      give one bedroom and two bedrooms in a month, and a unit whose ads give one bathroom and
      two bathrooms in a month;
    - a label for each of the chain's five patterns, labels with whitespace and a `#`, and a
      label for each way an ad gets no label floor;
    - bathroom counts that disagree, or that come as a negative number, a fraction, a boolean or
      a whole number written as a decimal;
    - sizes of 149, 150, 6,000 and 6,001 square feet;
    - a building with six floors, a building without a floor count whose area changes between
      its answers, and a building with a count of 0 in one answer and 20.5 in another.

    The test checks each label floor and bathroom count against `label_floor` and `consensus` of
    `rentfrontier.cohort`, and each candidate's floor and status against its `floor_of`. Then it
    checks the fates, floors, floor counts, areas, regions and sizes by value;
19. parse every SQL model as SQLMesh loads it and look for a bracket reading a list at a
    computed index;
20. run `ops/pipeline/build.py` on the fixture twice and check the rows file's name and the
    export files' hashes against their SHA-256. The second build rebuilds nothing, writes the
    same rows file and appends a second catalog line. Then the test builds runs 2 and 3, adds
    run 4 and builds again, and compares that build's rows file with a build of runs 2 to 4 into
    an empty state. The two files hold the same bytes. Last, the test adds an export file
    repeating an answer and checks that the build stops and leaves OUT as it was;
21. parse a line breaking each of the ledger's rules, read files with a repeated line, a
    retract of an unknown, a retracted or a retracting entry, and a line that is not JSON, and
    check that `read` takes files in order of name;
22. write ledger entries for six kept rows of the fixture and an ad without one, retract two of
    them in a later file, and check each entry's status and differing values. The next plan
    rebuilds only the two ledger models and `analysis.rows`, which drops one row and changes
    two, and the latest asks stay as they were;
23. write a set backed only by the ad's words. The plan stops at `ledger.entries`, naming the
    file and line;
24. read the repo's ledger, and check that each of its files on master's side of the merge base
    keeps its lines and only grows.

They take about 70 s on thelio. SQLMesh loads models in forked workers, and a fork in a process
with open DuckDB connections can deadlock, so `pipeline/tests/conftest.py` sets
`MAX_FORK_WORKERS=1`.

## Full build

On Oct 15 on thelio, I built the project from runs 1 to 4 of the export and compared
`analysis.latest_ask` with the latest-ask run `20261015-13f5968-api`. At that point the model
read the run's analysis rows from a file, and all 1,396,053 rows matched in first ask, latest
ask and step. The last section below compares the latest asks of the fit-ready rows.

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

With the event log's four tables, I built runs 1 to 5 into an empty state in 109 s, at the
unit's 5 GB cap with DuckDB's limit at 4 GB. `ads.events` holds 23,340,393 events of 2,372,913
ads. Of those ads, 2,137,998 have answers of their own, and the other 234,915 appear only in the
unit histories of their siblings' records. Of the 8,392,975 history events an ad's own answers
reported, a sibling's answer reported 5,186,434 first. `ads.first_ask` gives 2,117,118 ads a
first day, with one price for 2,116,917 of them and two for 201, and none with a missing price.
Each first ask's `first_response_id` is an answer of its own ad. For each of the 1,396,053
rows of the latest-ask run, `price_at` is its ad's first day at midnight UTC and `asking_rent`
the single price of that day:

```sh
uv run --project pipeline sqlmesh -p pipeline fetchdf "
  SELECT count(*)
  FROM '/data1/apartments/pipeline/inputs/analysis-rows-20261015-13f5968-api.parquet' r
  LEFT JOIN ads.first_ask f ON f.listing_id = r.source_listing_id
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

I built the fit-ready rows from runs 1 to 5 and compared `analysis.rows` with the chain's four
regional analysis datasets of the Oct 15 run, `api-manhattan-below-59th`,
`api-manhattan-59th-110th`, `api-brooklyn-prospect-park` and `api-brooklyn-north-crown-heights`,
each with the suffix `-analysis-20261015-6064263`. They hold 1,396,053 rows. I left out the 101
rows of units with an answer after the chain read the archive at 13:10 ET. Each of the other
1,395,952 rows has a row in `analysis.rows` for the same ad and price date, and the two agree in
unit, page, building, ask, layout, bathroom counts, size, floors, floor status, floor count,
area, amenities and exposures. The script is
`/data1/apartments/tmp/pipeline/step45/compare_full2.py`, and the comparison took 26 s.

`analysis.rows` holds 92 more rows in the four regions. The old collector dropped each of their
ads as `missing_canonical_unit_association`. Each is an ad from a unit's history: a later ad of
the same unit exists in the archive, and the collector gives a history ad a unit only through
the unit page of the unit's latest ad. For 88 of the 92, the latest ad's record has no unit
slug, so the latest ad has no unit page. For the other 4, the collector never read the latest
ad. `ads.identity` builds each ad's page from the ad's own records, so the 92 ads get their
units. They make the first item under [Differences from the chain](#differences-from-the-chain).

Data improvements also built the page-crawl areas dataset from run 5,
`api-manhattan-page-crawl-areas-analysis-20261015-run5`, from the archive as it stood at 16:52
ET. I compared it with `analysis.rows` in the same way and left out the 9 rows of units with a
later answer. The 350,974 rows in both agree in every value above. The dataset holds 2,232 more
rows, all for ads in Noho. The chain picks the dataset's rows by `neighbourhood`, while
`regions` in `analysis.rows` lists the regions of the export's answers for the ad, and the
export gives these ads `manhattan-below-59th`. `analysis.rows` holds all 2,232 under that
region, with the same ask, unit and bedrooms. To read the page-crawl areas from
`analysis.rows`, a fit should select rows by `neighbourhood`. `analysis.rows` also holds 13
rows missing from the dataset.
They belong to the first difference: the snapshot behind the dataset excludes each of their ads
as `missing_canonical_unit_association`, since each unit's latest ad has only a `/rental/`
address. The script is `/data1/apartments/tmp/pipeline/step49/compare_pagecrawl.py`, and the
comparison took 5 s.

I ran the SQL of each new model on the same state, each in a unit of its own with DuckDB's
limit at 5 GB:

| model | query | unit peak |
|---|--:|--:|
| `buildings.details` | 0.4 s | 1.8 GB |
| `ads.identity` | 7.9 s | 2.5 GB |
| `ads.reported` | 7.7 s | 3.4 GB |
| `analysis.candidates` | 2.6 s | 3.4 GB |

`analysis.rows` is a view, so it costs nothing to build.

Last, I moved `analysis.latest_ask` onto `analysis.rows`. I planned the change on a copy of the
state above. The plan rebuilt `ads.attributes`, whose list reads changed, and the five models
below it, in 75 s, with a peak of 5.8 GB for the process. `analysis.latest_ask` holds a latest
ask for each of the 1,747,140 fit-ready rows. I compared it with the latest-ask run's
1,396,053 rows, leaving out units with an answer after 13:10 ET as before. Each of the 1,395,952
shared rows agrees in first ask, latest ask and step, and the 92 rows of the listed difference
above have latest asks too. The script is `/data1/apartments/tmp/pipeline/step46/compare_ask.py`,
and the comparison took 7 s.

Over all fit-ready rows, the steps give:

| step | rows |
|---|--:|
| `latest` | 1,745,605 |
| `page price` | 866 |
| `latest, nearer building` | 413 |
| `first, nearer building` | 243 |
| `page price, digit` | 13 |

No row takes the step for an ask captured before the row, since each fit-ready row's ad has a
kept change dated on or after its first day. Each row's ad also has a record collected after the
row, and every row has a building and a bedroom count.

| model | query | process peak |
|---|--:|--:|
| `analysis.latest_change` | 0.7 s | 1.1 GB |
| `analysis.latest_ask` | 2.1 s | 3.4 GB |
| `ads.attributes` | 70.5 s | 6.0 GB |

Then I moved the price changes onto the event log. I planned the change on a copy of that state.
The plan rebuilt `ads.answers`, which now also reads the record's market days, and the thirteen
models below it, in 186 s, with a peak of 5.9 GB for the process. I compared the new tables with
the old ones using `/data1/apartments/tmp/pipeline/step48/compare_events.py`:

- Each of the 2,137,997 latest records agrees in its fetch, status, market days and page price.
- `ads.price_changes` holds 5,001,550 changes, 4,628 fewer than the records list, since the
  event log keeps a change listed twice in one record once. Without those repeats, the kept
  changes of each of the 2,136,603 ads with changes come in the same order, with the same
  last price and day.
- Each of the 1,747,140 fit-ready rows agrees in its last kept change, page price, first ask,
  latest ask and step.

| model | query | process peak |
|---|--:|--:|
| `ads.answers` | 12.6 s | 3.8 GB |
| `ads.latest_record` | 0.3 s | 0.7 GB |
| `ads.price_changes` | 1.1 s | 1.0 GB |
| `ads.kept_changes` | 16.6 s | 1.1 GB |

On the same state, the master versions of `ads.answers` and `ads.latest_record` took 9.9 s and
7.5 s. `ads.latest_record` now picks from the parsed answers instead of parsing each record
again, so the two take 12.9 s together instead of 17.4 s.

Then I changed how `ads.attributes` finds an ad's conflicting values. It counted the distinct
values of each attribute for each ad, and it now compares each attribute's smallest and largest
values. On the state of the last step, the new query took 3.7 s with a peak of 3.1 GB for the
process, against 89 s and 5.7 GB for the old one. The two give the same row for each of the
2,137,997 ads, as `/data1/apartments/tmp/pipeline/step50/compare_attr.py` found. Only 10 ads
of runs 1 to 5 have two records, and none of them has a conflict, so the tests' made-up ads
check the conflicts. On that state,
the queries of all the SQL models take 97 s:

| model | query | process peak |
|---|--:|--:|
| `ads.answers` | 15.5 s | 3.8 GB |
| `ads.history_events` | 10.0 s | 3.1 GB |
| `ads.events` | 12.0 s | 5.1 GB |
| `ads.latest_record` | 0.4 s | 0.7 GB |
| `ads.price_changes` | 1.2 s | 1.0 GB |
| `ads.kept_changes` | 21.3 s | 1.1 GB |
| `ads.first_ask` | 1.0 s | 1.1 GB |
| `ads.market` | 3.4 s | 1.8 GB |
| `ads.attributes` | 3.7 s | 3.1 GB |
| `ads.exclusions` | 1.0 s | 0.8 GB |
| `ads.identity` | 11.0 s | 2.6 GB |
| `ads.reported` | 9.1 s | 3.1 GB |
| `buildings.details` | 0.6 s | 2.0 GB |
| `analysis.candidates` | 3.9 s | 3.7 GB |
| `analysis.latest_change` | 0.8 s | 1.1 GB |
| `analysis.latest_ask` | 2.4 s | 3.3 GB |

Each ran in a process of its own with DuckDB's limit at 5 GB and 12 threads, through
`/data1/apartments/tmp/pipeline/step45/probe_model.py`. `ads.events` ran through
`/data1/apartments/tmp/pipeline/step50/probe_q.py`, which quotes the query's names first.
`ads.record_attributes` also reads its cache, which takes about 25 s.
