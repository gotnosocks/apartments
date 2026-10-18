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
PIPELINE_LEDGER=$PWD/pipeline/ledger uv run --project pipeline sqlmesh -p pipeline plan --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline fetchdf "SELECT how, count(*) FROM analysis.latest_ask GROUP BY 1"
uv run --project pipeline --extra dev pytest pipeline/tests
```

## Inputs

`pipeline/config.py` reads these environment variables, along with `PIPELINE_MEMORY`:

| variable | default on thelio | holds |
|---|---|---|
| `PIPELINE_EXPORT` | `/data1/apartments/archive/crawls/api/export` | the scraper's export, with its manifest |
| `PIPELINE_STATE` | `/data1/apartments/pipeline/state` | the DuckDB database, spill files and SQLMesh's cache |
| `PIPELINE_LEDGER` | `pipeline/ledger` in the checkout | the corrections ledger, and the unit ledger in its `units` folder, as described under [Corrections ledger](#corrections-ledger) and [Unit ledger](#unit-ledger). The ledger models read it again as they run, after SQLMesh has restored the environment it loaded `config.py` in, so a plan needs it set: `build.py` and `diff.py` set it, and a `sqlmesh plan` by hand takes it on its command line |
| `PIPELINE_CITY` | `/data1/apartments/archive/city` | the city archive, as described under [City records](#city-records) |
| `PIPELINE_CITY_CACHE` | `/data1/apartments/pipeline/city` | the city archive's files as Parquet, as described under [City tables](#city-tables) |
| `PIPELINE_INCREMENTAL` | unset, read as 0 | 1 when `ops/pipeline/build.py` asks for a top-up build, as described under [Top-up builds](#top-up-builds) |
| `PIPELINE_STALE_DAYS` | unset, read as 7 | the days after an ad's off-market day past which `ads.kept_changes` counts its price changes as stale, as described under [Latest ask](#latest-ask) |

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

Before the models load, `config.py` checks each listed ads and buildings file. It hashes the
file and compares the hash with the manifest's SHA-256, then has DuckDB hash each record in the
file and compare it with the answer's `record_sha256`. It stops at the first file failing
either check. A record under another record's hash would otherwise take that record's parsed
attributes from `ads.record_attributes`, whose cache goes by the hash. The config keeps each
checked file's hash with the file's size, inode, modification time and change time in
`export-hashes.json` in the state folder, and a later load checks only the new or changed
files. Writing a file back with its old modification time still gives it a new change time.
When a file fails, the record keeps the files checked before it, so the next load starts the
checks again from the failing file. On Oct 16 the 47 ads and buildings files of the export,
3.2 GiB, took 3.2 s to hash from the page cache, and
their 2,232,461 records took 37 s on four threads, with no record differing from its hash. A
stat of all of them took under a millisecond.

SQLMesh also fingerprints a Python model by the text of the values its code reads. The text of
a set of strings changes with the process's hash seed, so the Python models keep such values in
tuples. A test looks for sets in those values and compares every fingerprint under two seeds.

`raw.ads` holds every answer, including the API's empty answers, marked `missing`.
`ads.latest_record` reads only answers with a record, so an ad whose latest answer came back
empty keeps its last record, as in `rentfrontier.latest_ask`.

## City records

`ops/pipeline/city.py` keeps copies of the city's bulk records of lots and buildings in
`/data1/apartments/archive/city`. The identity step and the city-fact step join each API
building to them as of each ad's date.

```sh
python3 ops/pipeline/city.py [--archive DIR] [--source NAME ...] [--verify]
```

| Source | Records | Files | Date |
|---|---|---|---|
| `pad` | City Planning's Property Address Directory | a zip for each quarter, from 23b | the file's Last-Modified |
| `pluto` | City Planning's MapPLUTO | a zip for each release, from 09v1 | `ops/pipeline/pluto_releases.csv`, then Last-Modified after 26v2 |
| `footprints` | building footprints, 5zhs-2jue | all rows, as gzipped CSV | `rowsUpdatedAt` |
| `landmarks` | LPC's designated and calendared buildings and sites, ncre-qhxs | all rows, as gzipped CSV | `rowsUpdatedAt` |
| `dob_now_co` | DOB NOW certificates of occupancy, pkdm-hqz6 | all rows, as gzipped CSV | `rowsUpdatedAt` |
| `dob_co` | DOB's earlier certificates of occupancy, bs8b-p36w | all rows, as gzipped CSV | `rowsUpdatedAt` |

The script asks each source for its files and downloads a file when the manifest lacks it. It
asks City Planning's server for each PAD quarter from 23b to the quarter after the current one,
and for each MapPLUTO name after 26v2 up to the current year. The server answers 404 for a name
with no release. For each Open Data set, the script reads `rowsUpdatedAt`, the time of the last
change to the rows, and downloads all the rows when the manifest has no copy from that time.

The script downloads each file to a `.part` file and checks it:

- a file sent with a Content-Length has that many bytes;
- a zip opens;
- a CSV ends with a newline.

On a server error, a rate limit, a dropped connection or a failed check, it waits and tries
again, up to five tries in all. After a CSV download it reads `rowsUpdatedAt` again and drops
the copy when the time moved. Then it renames the file into place and appends its line to
`manifest.ndjson`, so a reader can take each listed file as whole. Each line gives:

- the source, its release, and the Open Data set's ID for a copy of rows;
- the file's path under the archive and the URL it came from;
- `published`, the date or time the publisher gives the release, and `published_from`, the
  evidence for it;
- `retrieved`, the time the download began, and the file's size and SHA-256.

`pluto_releases.csv` copies frontier's `PLUTO_RELEASES`, with its evidence for each date. On
Oct 16, 29 of the 30 releases before 22v3, all but 21v1, had a Last-Modified date of 2023-10-15,
from a re-upload. For those releases the table takes the date from their own documents: the
README, the data dictionary or the file layout. For 21v1 and for each release from 22v3 on, it
takes the Last-Modified date. Since 22v2 has no dated document, its line leaves the date empty.
A test checks the copy against frontier's table. City Planning's server holds no PAD release
before 23b, so an ad posted before April 2023 has no PAD release from its own time. In the 15v1
zip, `PlutoReadme15v1.pdf` fails its CRC check. The copy matches the server's file, since the
server's ETag gives the copy's MD5. The five borough tables in that zip read whole.

Open Data's export at `/api/views/ID/rows.csv` answers with a Deprecation header and a sunset
date of 2026-12-22, so the script reads `/api/v3/views/ID/query.csv`. That export also gives
Socrata's `:id`, `:version`, `:created_at` and `:updated_at` for each row. The script sends
`NYC_OPEN_DATA_TOKEN` as the app token when the variable is set. It gzips each CSV with a fixed
header time, so two copies of the same rows in the same order have the same SHA-256. The script
sets no order on the query, so two copies of unchanged rows may still differ.

The first run, on Oct 16, copied 62 files and 4.45 GB in 525 s, 352 s of it for the footprints.
The process peaked at 24 MiB. The unit's peak of 1 GiB is page cache. Each Open Data copy holds
as many rows as the set's own `count(*)` gives, with no `:id` repeated: 1,083,059 footprints,
39,363 landmarks, 82,963 DOB NOW certificates and 143,242 earlier ones. A second run found
nothing new in 4 s, and `--verify` checked the 62 files in 7 s. A copy of the footprints takes
214 MB, so a new copy every week adds about 11 GB a year. Weekly copies of the two certificate
sets add about 1.2 GB a year, and four PAD and four MapPLUTO releases about 0.5 GB.

`apartments-city-fetch.timer` starts the script every Friday at 04:05 ET, before the StreetEasy
top-up at 05:35. The service moves `/data1/apartments/serve/master` to master and runs the
script from there on the system's Python, capped at 1 GiB. The dashboard build moves the same
checkout every ten minutes, at :00, :10 and so on, and the Modal cleanup moves it every hour on
the hour. At 04:05 the fetch starts between two dashboard runs, clear of both units' git steps.
While a run holds the script's own `.lock`, a second run exits at once. `--verify` checks each
listed file's size and SHA-256. The units go in once:

```sh
cp /data1/apartments/serve/master/ops/systemd/apartments-city-fetch.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now apartments-city-fetch.timer
```

## City tables

DuckDB can't read a member of a zip, so `pipeline/steps/city.py` unpacks the city archive into
Parquet files for the `city.*` views. `config.py` runs the step as the project loads, with the
archive from `PIPELINE_CITY` and the cache from `PIPELINE_CITY_CACHE`. For each file the
archive's manifest lists, the step

1. picks the folder `<code>/<entry>` in the cache, from the first 16 hex digits of the SHA-256
   of `steps/city.py` with DuckDB's version and of the file's manifest line, and goes on to the
   next file when the folder exists;
2. copies each member a table takes to a scratch file, without the DOS end-of-file byte at the
   end of an old MapPLUTO table. As it copies, it checks the bytes as UTF-8. It takes Latin-1
   for a member with bytes UTF-8 can't decode;
3. reads the copy with DuckDB as CSV, every value as text, with the column names in lower
   case. DuckDB sets aside each row with too few or too many values, and the step writes those
   rows to the folder's `rejects.parquet` with DuckDB's line number, its reason and the row's
   text. PAD's street name dictionary has records of fixed width, and DuckDB reads each record
   whole into the column `line`;
4. writes each member's rows to a Parquet file, adding `release` and `published` from the
   manifest line, the archive's `file` and its `member`, `record`, the row's place among the
   rows DuckDB kept from the member, and the `encoding`;
5. flushes the scratch folder to disk and renames it into place. DuckDB doesn't flush its
   files, and a folder in place counts as unpacked.

| table | source | members |
|---|---|---|
| `pad_addresses` | `pad` | `bobaadr.txt` at the zip's root |
| `pad_lots` | `pad` | `bobabbl.txt` at the zip's root |
| `pad_streets` | `pad` | the street name dictionary, `snd26Ccow.txt` in 26c |
| `pluto` | `pluto` | each `.txt` or `.csv` |
| `footprints`, `landmarks`, `dob_now_co`, `dob_co` | the Open Data set | the gzipped CSV |

PAD's zips from 24c to 25c hold a second copy of each table in a `win11` folder, and the tables
take the copy at the root. MapPLUTO comes as a table for each borough up to 18v1, in `.txt`
files up to 12v2, and as one table for the city from 18v2 on.

`config.py` gives each view its Parquet files as a variable. A file's path holds the hashes of
the code and of the manifest line, so a new file in the archive gives its source's views new
fingerprints, and an edit to `steps/city.py` or a new DuckDB gives every city view new ones. For
a table with no file in the archive, the step gives an empty file with only the added columns,
along with `line` for the street names. A file holding no member for one of its source's tables
stops the load with an error. The step keeps every value as text, and the identity and city-fact
steps cast the values they read.
A `published` date with no time reads as midnight UTC.

`record` counts the kept rows. A refused row's `line` is DuckDB's line number for it, counting
the header. DuckDB counts records rather than lines, so after a value holding a line break, the
numbers fall short of the line in the file. The 13v1 tables end in rows of commas only, and
those come through as rows with every value empty.

The step holds a lock on its code's folder while it works, so two loads never unpack the same
file at once. An unpack stopped partway leaves a `.part` folder, and the next load deletes it
and starts that file again. After each load, the step deletes the folder of each other version
of its code that no load has used for a week. It renames such a folder to `<code>.old` before
deleting it, and a load waiting on that folder's lock starts again in a new folder. Each edit to
`steps/city.py`, comments included, means the next build unpacks the whole archive again, for
about 10 minutes under the build's locks.

On thelio on Oct 16, the step unpacked the archive's 62 files into an empty cache in 597 s, with
a peak of 1,078 MiB, into 3.1 GB of Parquet files. A second unpack from empty, with the build's
venv into `/data1/apartments/pipeline/city`, took 589 s with a peak of 1,454 MiB. A load with
every folder in place took under 0.1 s. Every member read as UTF-8, and DuckDB refused one row
in the whole archive, the row of 13v1's Queens table with 80 values of 82. Across their
releases, the tables hold 18,515,237 PAD address ranges, 12,238,530 PAD lots and 37,806,144
MapPLUTO lots. Each Open Data copy gives as many rows as its set's `count(*)`. The step lets
DuckDB write the rows in the member's order rather than sorting them by `record`: a sort doubled
the memory for MapPLUTO's table of the whole city, and the first try at the full archive ran out
at a 2 GiB cap.

## Build command

`ops/pipeline/build.py` builds the project, saves the fit-ready rows, the ads and the API
records, and records the build:

```sh
uv run --project pipeline python ops/pipeline/build.py [--export DIR] [--state DIR] [--out DIR]
```

It plans and applies `prod`, as the `sqlmesh plan` line above does. Then it writes
`analysis.rows`, sorted by `listing_id`, to a Parquet file in OUT, by default
`/data1/apartments/pipeline/datasets`. The file's name holds the first 16 hex digits of its
SHA-256, as in `rows-4743b90bc5aa49b4.parquet`. It writes `analysis.ads` the same way, to a file
such as `ads-<hash>.parquet`, described under [Ads file](#ads-file). It writes both files with
eight of DuckDB's threads, since with all twelve the sort of the ads file ran out of the 3 GB
limit once the file joined `analysis.ask_check`. Then it writes the records file, such as
`records-<hash>.parquet`, described under [Records file](#records-file). Last, the script appends
a line for the build to `OUT/catalog.ndjson`:

| key | holds |
|---|---|
| `built` | the time the build finished, in UTC |
| `code` | the checkout's commit, and `clean`, false when `pipeline/`, `src/` or `ops/pipeline/` differ from it |
| `export`, `ads`, `buildings` | the export folder, and for each table its version from `config.py` and each file it listed, with the file's SHA-256 |
| `models` | each model's table in the state and its row count, and the seconds its evaluation and audits took, or null when the build left the model as it was |
| `ledger` | the corrections ledger's files by name with their SHA-256, and its entries counted by status and change, with the same for the unit ledger under `units` |
| `city` | the city archive's folder, and each file it lists for a source the city tables read, with the file's SHA-256 |
| `rows` | the rows file's name, SHA-256 and row count |
| `ads_file` | the ads file's name, SHA-256 and row count, under its own key since `ads` lists the export's files |
| `records` | the records file's name, SHA-256 and row count, under `read` the count of records the step read into its cache, and under `reused` whether the step returned a file it had noted for the same export |
| `seconds` | the wall time of loading the project, of the plan, of counting rows, of writing the rows and ads files and of writing the records file, and the total |
| `peak_mib` | the peak resident memory of the script, DuckDB's included, and the peak and name of the script's cgroup |
| `top_up` | true when the build read only the answers missing from the last build's tables, as [Top-up builds](#top-up-builds) describes |

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
and copied the 1,713,239 cached ones into its table again, and the models after it recomputed
every ad. Those full recomputes took most of that top-up's time, and
[Top-up builds](#top-up-builds) describes how a top-up reads fewer ads.

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
   export's manifest, the city archive's manifest and the pipeline's code match the last
   build's, as on most of the timer's runs;
3. waits for room to build, checking that
   - no job holds the GPU lock, so no fit or other GPU job runs on thelio;
   - no unit named `site-build-*`, `frontier-publish*`, `di-*`, `data-*`, `adfills-*` or `bd4-*`
     is active, for the site builds and Data improvements' jobs run outside `ops/job`;
   - 5 GiB of memory is available.

   While a GPU job holds the GPU lock, it queues for the lock as the GPU jobs do and holds it
   through the build. Once the other checks pass, it takes every light slot, so no
   `ops/job light` job runs beside the build, and checks again with the slots held. When a
   check fails, it lets go of every lock and checks again a minute later, logging the reason
   when it changes;
4. logs the locks it took and the memory available, runs `build.py` with `PIPELINE_MEMORY=3GB`
   in the service's own cgroup, which the unit caps at 5 GiB with swap off and keeps on the
   light CPUs, and lets go of its locks after it;
5. builds again when the manifest changed during the build.

Manual exports with `streeteasy_archive.graphql_export` take `export/.lock` and exit when it is
held, so the script waits on `oxylabs.lock` alone. When such an export appends its lines during
a build, step 5 builds again.

When the build starts with the GPU lock free, it leaves the lock free. A GPU job queued after
its start takes the GPU lock and runs beside it, while a `gpu -x` job, as full fits run, also
waits for the light slots and so starts after the build. Ben agreed on 2026-10-16 to let the build skip the GPU lock this
way, on the terms the checks above carry out. The build queues for the lock behind a running GPU
job, as it did before, so a queue of GPU jobs only delays it. The checks run at the build's
start, so a job started during a build still overlaps it. A site build or a Data improvements
job that must not overlap the build runs through `ops/job light`, which waits for the slots the
build holds. A job run outside `ops/job` goes in a service named like the patterns above, so the build
waits for it, started under light slot 1:

```sh
flock /data1/apartments/tmp/locks/light-1.lock \
    systemd-run --user --unit=di-NAME -p MemoryMax=3G -p MemorySwapMax=0 -- COMMAND
```

`flock` waits while a build holds the slots, and lets go of slot 1 only after `systemd-run` has
started the service, so a build that starts later finds the unit active and waits for it. A
scope in place of the service would hold slot 1 for the whole job. `systemctl --user is-active`
doesn't tell whether a build is running: the build's service stays `activating` through its
waits as well as its build. `ops/autoselect-publish.sh` runs its site build under slot 1 the
same way.

A build after an export is a top-up. The 16 models of kind `merge` read the export's new
answers and the ads they change, and the other ads models and the `analysis` tables read every
ad again, as [Top-up builds](#top-up-builds) describes.

After each build, the script writes the hashes of both manifests and the commit's trees to
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

### Top-up builds

When an export adds answers, the build reads those answers and the ads they change, and it keeps
the rows of every other ad from the last build. Before it plans, `build.py` picks the mode:

1. It loads the project with `PIPELINE_INCREMENTAL=1`. `can_top_up` then compares each model of
   kind `merge`, and each model above one, with the prod build's snapshot of it. For `raw.ads`
   it compares the query alone, since a new export file gives the view new variables.
2. It reads `STATE/merge.json`, which the last build wrote with the SHA-256 of
   `pipeline/materializations/merge.py` and `pipeline/models/ads/changes.py`, the value it gave
   the variable and the mode that ran, and checks the hash against the checkout's. `config.py`
   also passes the SHA-256 of `merge.py` to `ads.changes` as the variable `merge_code`, so an
   edit to `merge.py` gives `ads.changes` a new fingerprint, and the plan rebuilds it and every
   model below it.
3. When a check fails, it loads the project again with the variable at 0, and the plan rebuilds
   the models below `ads.changes` from every answer.
4. When `raw.ads` has no new files, it gives the variable the last build's value. The plan then
   leaves the table of `ads.changes` in place and rebuilds only the models below an edit.

To force a full build, I delete `STATE/merge.json`.

In a top-up, `ads.changes` holds the answers of `raw.ads` missing from the prod `ads.answers`.
Before it reads them, the model checks that every previous answer is still in `raw.ads` with
its fetch time, outcome, record hash and region, and that no new answer repeats one. When a
check fails, the table holds every answer with `incremental` false, and `merge.json` and the
catalog line give `top_up` as false. Otherwise `ads.touched` holds the ads of the new answers,
and the ads whose events show up in a unit history of a new answer, since the history adds
another report of those events. The materialization `merge`, in
`pipeline/materializations/merge.py`, starts each model's new table from a copy of the prod
table:

- `ads.answers`, `ads.history_events`, `ads.record_attributes` and `ads.photos` add the rows of
  keys the copy lacks: the new answers, the events of each history no earlier answer held, the
  attributes of each record the table lacks, and the photos an ad shows for the first time.
- The 12 other merge models drop the rows of the ads in `ads.touched` from the copy, then
  compute those ads again from all their answers.

`ads.identity`, `ads.placed`, the ledger models and the `analysis` tables stay full tables
and read every ad on each build:

- `ads.identity` gives an ad a page from its building's latest slug in `buildings.details`, and
  it gives no unit to an ad whose page also comes from a record of an ad with no single page.
  A new building record or a new answer can then change the unit of ads with no new answer. A
  merge would need the previous and new pages of each changed ad and building and every ad on
  them, so I left the model full. In the top-up of 23:38 ET on Oct 16 it took 18.1 s.
- `ads.placed`, the ledger models and the `analysis` tables follow from `ads.identity` for every
  ad. They took about 42 s in that top-up.
- The building and city models depend on no ad, and they rebuild only when their own inputs
  change. The building models took 41.7 s in that top-up.

In that top-up, the 15 models now of kind `merge` took 205 of the 306 s its models took, with
`ads.record_attributes` at 45.7 s and `ads.kept_changes` at 36.9 s. Each top-up still copies
the prod tables of those 15 models, and I have no full-data time for the copies yet.

On the 1% sample, with DuckDB's limit at 1 GB and two workers, I built runs 1 to 9 into an
empty state, copied the state and added run 10's 25 answers:

| build | ads read | total | models | script's peak |
|---|--:|--:|--:|--:|
| runs 1 to 9, from an empty state | 21,593 | 18.8 s | 12.8 s | 1,424 MiB |
| run 10 added, as a top-up | 100 | 7.6 s | 4.2 s | 572 MiB |
| run 10 added on the copy, with `merge.json` deleted | 21,593 | 10.2 s | 5.4 s | 1,466 MiB |

The last build found every record in the attribute cache. The top-up and the full build gave
every model the same rows, apart from `ads.changes` and `ads.touched`. Each of the 33 models
the two builds rebuilt took about 0.1 s even with few rows, so the sample's times say little
about the times on full data.

After a top-up, an edit to a merge model or to a model above one fails the check of step 1,
and the next build rebuilds every ads model from all the answers. The top-up of Oct 16, which
rebuilt the same models in full, took 339 s at a peak of 4,116 MiB. A dev plan reads the variable at its default of
0, so `sqlmesh plan dev` also rebuilds every model below `ads.changes` from all the answers.

## Change diff

`ops/pipeline/diff.py` builds the tables with the base code and with an edit, and lists the
differences:

```sh
uv run --project pipeline python ops/pipeline/diff.py [--base REV] [--export DIR | --sample] \
    [--city DIR] [--ledger DIR] [--rows N] [--json FILE] [--keep DIR]
```

The script writes `pipeline/` and `src/` at REV, HEAD unless given, to a scratch folder. It
builds that code and the checkout's own from empty, each in a process of its own, both at once.
Both builds read the test fixture's export unless `--export` gives another, and the fixture's
city archive unless `--city` gives another. Each side unpacks the city archive into a cache of
its own in the scratch folder. Each build reads its own `pipeline/ledger` unless `--ledger`
gives a folder for both. Each side's process drops the
folders added by the venv's .pth files from its import path, so it imports only that side's
code. Then the script compares the tables model by model:

- a model with a grain: it joins the two tables on the grain and counts the rows only in the
  base, the rows only in the edit and the changed rows, with a count for each changed column.
  When the grain changed, or repeats on a side, it compares the rows as multisets instead and
  notes the reason;
- a model without a grain: it counts the rows of each side missing from the other;
- every model: it lists models and columns present on one side only, and columns with a new
  type. It compares a retyped column by value when both types hold numbers, as text otherwise,
  so 5 and '05' differ.

It prints up to N rows of each kind for each changed model, 5 unless given, and then the names
of the unchanged models. With the size bound of `analysis.candidates` narrowed to 150 to 1,000
square feet, it printed:

```
analysis.candidates: 229 rows in the base, 229 in the edit; 1 changed (square_feet 1)
  listing_id=3120884: square_feet 1200.0 -> null
analysis.kept: 229 rows in the base, 229 in the edit; 1 changed (square_feet 1)
  listing_id=3120884: square_feet 1200.0 -> null
analysis.rows: 229 rows in the base, 229 in the edit; 1 changed (square_feet 1)
  listing_id=3120884: square_feet 1200.0 -> null
unchanged: ads.answer_events, ads.answers, ads.attributes, ads.breaks, ads.events, ...
built the base in 5.5 s and the edit in 5.5 s, 6.1 s in all
```

The run took 6.1 s on thelio and peaked at 350 MB. Each side builds every model from empty, so
an edit to a model, to `pipeline/steps` or to `src` shows in the tables. When a plan stops on
either side, at an audit or an error, the script prints the end of that plan's output and exits
with status 1. `--json` writes the whole comparison to a file, and `--keep` keeps both builds'
tables as Parquet files in a folder.

The fixture's 229 records lack many cases from the full export. `ops/pipeline/sample.py` writes
a sample of the export to `/data1/apartments/pipeline/sample/export`, and `diff.py --sample`
builds both sides from it:

```sh
uv run --project pipeline python ops/pipeline/sample.py [--export DIR] [--out DIR] [--share S]
```

The script picks a building when the MD5 hash of its ID falls in the first S of the hashes'
range, 0.01 unless given. For each ad, it takes every answer when one of the ad's records gives a
picked building or when the ad has a `missing` answer. It also takes every answer of the picked
buildings. When a picked ad's record gives another building, it takes that building's answers
as well. It writes the answers in the export's layout, with a manifest, and stops before writing
when the output folder would replace the export, hold it or lie inside it. On Oct 16 it picked
665 buildings and 19,683 of the export's 2,137,998 ads, the ad with five `missing` answers among
them, and wrote 20 MB in 16 s, at a 1 GB peak. A diff on the sample took 18.5 s and peaked at
2.2 GB. The same buildings fall in the sample on each run. After a top-up, the script takes their
new answers and picks each new building by the same hash test.

`diff.py --export` takes any other export folder. `diff.py` builds both sides in a scratch folder
under TMPDIR, so on thelio a large export calls for TMPDIR under /data1, as /tmp is a small RAM
disk.

## Models

| model | kind | a row for each |
|---|---|---|
| `raw.ads` | view | exported API answer for an ad |
| `raw.buildings` | view | exported API answer for a building |
| `city.pad_addresses` | view | address range of a PAD release |
| `city.pad_lots` | view | lot of a PAD release, with its range of condominium lots and its billing lot |
| `city.pad_streets` | view | name of a street in a PAD release, with the street's code; the view cuts the dictionary's records into fields |
| `city.pluto` | view | lot of a MapPLUTO release |
| `city.pluto_releases` | table | MapPLUTO release: its published date, the first day an ad reads it, and for each field whether any lot of the city has a value in it |
| `city.footprints` | view | building footprint in a copy of the footprints |
| `city.landmarks` | view | landmark building or site in a copy of LPC's set |
| `city.dob_now_co` | view | certificate of occupancy in a copy of the DOB NOW set |
| `city.dob_co` | view | certificate of occupancy in a copy of DOB's earlier set |
| `city.rejects` | view | value missing from, or extra in, a row DuckDB refused as it read the city archive |
| `ads.changes` | table | answer this build reads anew: every answer in a full build, the new ones in a top-up build |
| `ads.answers` | merge | answer, with the fields the event log, the latest-ask steps and the ads file read and a hash of its unit history |
| `ads.history_events` | merge | event in a distinct unit history |
| `ads.touched` | table | ad whose rows this build reads anew: every ad with an answer or a history event in a full build, the ads the new answers change in a top-up build |
| `ads.answer_events` | merge | event an ad's own answers reported in their fetch, status changes or price changes, with those answers |
| `ads.history_reports` | merge | event a unit history listed for an ad, with the answers holding the history |
| `ads.events` | view | event the API reported for an ad, with the answers that reported it: the rows of `ads.answer_events` and `ads.history_reports` |
| `ads.latest_record` | merge | ad, from its latest answer with a record: the answer's ID and fetch time, status, market days, page price and floor plan keys |
| `ads.price_changes` | merge | nonzero price change of an ad's latest record, from the event log, numbered in order of time |
| `ads.kept_changes` | merge | price change left after the stale changes drop out and the placeholder check |
| `ads.first_ask` | merge | ad with an ACTIVE event in its own history: its first day on the market and its asks that day |
| `ads.market` | merge | ad with a record: its days on the market, its spans on the market and its ending |
| `ads.breaks` | merge | ad with a status change in its latest record since that record's first day on the market: its last change, and its latest break when it is ACTIVE and back |
| `ads.regions` | merge | ad with an answer: the export regions of its answers |
| `ads.record_attributes` | merge | distinct API record: its attributes and rental flags, as the current chain reads them, and the elevator and pet policy its description states |
| `ads.attributes` | merge | ad with a parsed record up to its last ACTIVE answer, or with any parsed record when it has no ACTIVE answer: its rental flags, merged over its records, and its attributes, merged over its records up to its last ACTIVE one, with an unknown elevator or pet policy filled from those records' descriptions |
| `ads.exclusions` | merge | ad with a record: its first day, its first ask and the current chain's reasons for dropping it |
| `buildings.details` | table | building with a record: the slug and area of its latest record, and its floor count |
| `buildings.latest_record` | table | building with a record: the slug, address, map point and city facts of its latest record |
| `buildings.pad_link` | table | building whose address matches a range of the latest PAD release: the range's lot and BIN, and the match's rank |
| `buildings.footprint_link` | table | building whose map point lies in or within 10 m of a footprint of the latest copy: the footprint's lot and BIN |
| `buildings.lots` | table | building with a record: its lot and BIN, the link they came from, and how well its facts fit each lot |
| `buildings.lot_releases` | table | lot of `buildings.lots` in a MapPLUTO release: the lot's facts as the release gives them, typed |
| `ads.identity` | table | ad with a record: its building, its unit page and its unit |
| `ledger.unit_entries` | table | line of the unit ledger, checked against the ledger's rules |
| `ledger.unit_status` | table | entry of the unit ledger: its status against the ads and buildings |
| `ads.placed` | table | ad with a record: its building and unit after the live entries of the unit ledger |
| `ads.reported` | merge | ad with a record: the floor its unit labels read, and its full and half bathrooms |
| `ads.photos` | merge | photo an ad shows in any of its answers, by its key |
| `analysis.candidates` | table | ad the current chain accepts before its unit-month check: its fit-ready values and its fate in that check |
| `analysis.kept` | view | candidate kept for its unit and month |
| `ledger.entries` | table | line of the corrections ledger, checked against the ledger's rules |
| `ledger.status` | table | entry of the corrections ledger: its status against the kept rows |
| `analysis.latest_change` | table | kept row, with its ad's last kept change from the row's day on and its page price |
| `analysis.latest_ask` | table | kept row, with its first ask, its latest ask and the step behind the latest |
| `analysis.relist_pairs` | table | pair of kept ads on two unit pages of a lot over its count, where the second ad looks like the first listed again |
| `analysis.relist_links` | table | pair of `analysis.relist_pairs`: the outcome of joining its unit pages, and the relist unit of each page after every pair |
| `analysis.relist_units` | table | unit page the relist step joins with another: its relist unit and the count of pages in it |
| `analysis.ledger_rows` | view | kept row the ledger leaves in, with its latest ask, the values the ledger's live sets give and its relist unit |
| `analysis.history_pairs` | table | pair of units an ad's unit history joins: the history of an ad on one unit lists an ad on the other |
| `analysis.label_units` | table | unit of `analysis.ledger_rows` the label rule joins with another: its label unit, the count of units in it and the layer that joined it |
| `analysis.rows` | view | fit-ready row: a row of `analysis.ledger_rows` with the label unit of its unit |
| `analysis.ask_check` | table | fit-ready row with a latest ask 6 to 16 times, or a sixteenth to a sixth of, the median of its building's other rows with the same bedroom count, for review |
| `analysis.lot_facts` | table | candidate ad: its lot and BIN, the MapPLUTO release it reads, and the lot's facts as of its first day |
| `analysis.lot_landmarks` | table | candidate ad: its lot, and the landmark and historic district designations the LPC had made on the lot by its first day |
| `analysis.building_certificates` | table | candidate ad: its BIN, and the certificates of occupancy DOB had issued on it by its first day |
| `analysis.building_check` | table | fit-ready row whose lot's MapPLUTO record leaves no room for the ad: a floor more than one floor and 30% above the lot's floor count, a nonresidential lot with no apartments, or a lot with no building in any release and no footprint, for review |
| `analysis.ads` | view | ad with a record, kept or dropped: its unit, its latest record's status, dates, ask and floor plans, its merged values, and the reasons it was dropped |

A `merge` model is a table, and a top-up build adds the rows of the new answers to it, as
[Top-up builds](#top-up-builds) describes.

The comments in each model's SQL describe its rules. The audits in the `MODEL` blocks check keys
and nulls: one row per listing in `ads.latest_record`, `ads.first_ask`, `ads.market`, `ads.breaks`,
`ads.regions`, `ads.touched`, `ads.attributes`, `ads.exclusions`, `ads.identity`, `ads.reported`,
`analysis.candidates`, `analysis.latest_change`, `analysis.latest_ask`, `analysis.ask_check`,
`analysis.lot_facts`, `analysis.lot_landmarks`, `analysis.building_certificates` and
`analysis.building_check`, per building
in `buildings.details` and the four building identity models, per lot and release in
`buildings.lot_releases`, per release in `city.pluto_releases`, per record in
`ads.record_attributes`, per `(listing_id, response_id)` in `ads.answers`, per `(listing_id, n)` in
`ads.price_changes`, per `(listing_id, key)` in `ads.photos`, per pair of ads in
`analysis.relist_pairs` and `analysis.relist_links`, per unit page in `analysis.relist_units`,
per unit in `analysis.label_units`, per pair of units in `analysis.history_pairs` and per event in `ads.answer_events` and `ads.history_reports`. The `every_row`
audit, in `pipeline/audits/`, checks that `analysis.latest_ask` keeps every row of `analysis.kept`.
When an audit fails, the plan stops, and the tables from the last good plan stay in place.

To try an edit, I build it in a dev environment beside prod and list the rows it changes:

```sh
PIPELINE_LEDGER=$PWD/pipeline/ledger uv run --project pipeline sqlmesh -p pipeline plan dev --auto-apply --no-prompts
uv run --project pipeline sqlmesh -p pipeline table_diff prod:dev -m analysis.latest_ask -o listing_id --show-sample
```

## Event log

`ads.events` gathers what the API reported about each ad. An answer reports events from four
places:

1. the fetch itself, with the ad's status and page price at that moment;
2. the record's status changes;
3. the record's price changes;
4. the unit history, listing the rental events of every ad of the unit.

The view `ads.events` gives a row for each distinct event, with the fetch times of the first and last
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
answer holding it, and `ads.history_reports` joins those events back to the answers through the
hash.

The event log builds as two tables and a view over them. `ads.answer_events` groups the events of
the fetches and of the records' status and price changes, and `ads.history_reports` groups the
events of the unit histories. `ads.events` lists the rows of both, and their `source` keeps the
two apart. Until Oct 16, `ads.events` grouped both in one query. With DuckDB's limit at 3 GB,
the setting of `build-latest`, that query spilled and took 57 to 68 s on runs 1 to 10, and in
builds it ran out of memory: the service's build at 09:53 ET on Oct 16 stopped there, as did two
scratch builds that afternoon. At a 2 GB limit it ran out of memory on its own as well. Apart, on
the same state, the two tables take 7.6 s and 10.3 s at 3 GB, and 7.7 s and 12.7 s at 2 GB.
Together their rows match the single query's 23,373,166 in count and in the sum of the rows'
hashes. `ads.answer_events` orders an ad's answers by a single HUGEINT key, the fetch's
microseconds above bit 64 and the `response_id` below. With the `(fetched, response_id)` struct
the other models use, the table took 9.7 s at 3 GB and 42 s at 2 GB, since `arg_min` and
`arg_max` hold a struct key as a blob of variable size in each of the 14 million states.

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

`ads.market` reads the status changes of each ad's latest record from the event log, the
events with that record's fetch as their `last_seen`, as `ads.breaks` does. It puts them in
order of time, and in the record's order when two share an instant. Each change holds until
the next one, and the last holds until the New York date of the ad's latest answer with a
record. The model takes from them:

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

I ran the model's query on a scratch build of the export of Oct 16. It took 3.4 s and gave
2,140,578 ads. The 2,117,766 of them with an ACTIVE change each have an `on_day` equal to the
record's `onMarketAt`. Of the 2,109,135 ads with both an `off_day` and an `offMarketAt`,
2,108,863 agree. Of the other 272, 270 pass through a draft or review status, as do all 534 ads
with an `off_day` but no `offMarketAt`, and StreetEasy counts those statuses as on the market.
Another 10,780 ads have an `offMarketAt` and no `off_day`, and 10,773 of them have no ACTIVE
change at all.

On the same build, an earlier record of 53 ads lists 68 status changes, and the ad's latest
record leaves them out. With those changes in, 27 ads would differ:

- 15 would have an `on_day` before the record's `onMarketAt`;
- 10 would have an `off_day` other than its `offMarketAt`, and 4 of those are ACTIVE ads given
  an ending;
- another would gain an ending, and the last would count 6 days on the market in place of 5.

Of the ads on the market, 1,922,278 went on it once, 160,229 twice and 35,259 three times or
more. The median ad spent 14 days on the market, and the middle half spent 6 to 31.
2,118,649 ads have an ending: 1,034,509 rented, 735,234 no longer available and 348,906
delisted. Of the 23,925 ads with a `rentedPrice`, 22,205 end rented.

StreetEasy's `daysOnMarket` equals `active_days` for 1,985,430 of the 2,117,766 ads on the
market, 93.8%, and comes within a day for 2,025,391, 95.6%. So StreetEasy leaves out the days in
contract and the days paused, as `active_days` does. It counts more than a day more for 61,759
ads and more than a day fewer for 30,616. Agreement is lowest for ads first on the market in
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

The module also reads the elevator and pet policy an ad's own text states. The served fit fills
an unknown elevator or pet policy with the chain's rules `elevator-from-ad-v1` and
`pets-from-ad-v2`. These rules read each NB9 row's description with `rentfrontier.adfills` and
keep the readings in files by audit ID, so the rows outside NB9 get no fill. On Oct 17
Modeling agreed that the pipeline takes these rules over, with the rows kept as the chain gives
them on the frozen rows and a row-by-row diff in the PR.

The pipeline's venv has no `rentfrontier`, so `pipeline/steps/adtext.py` holds a copy of
`adfills.elevator` and `adfills.pets`. I copied the patterns unchanged and read one text at a
time in place of a pandas column. `pipeline/tests/test_adtext.py` loads the chain's own module
and checks that both read the same value on its cases and on every description of the
fixture's records. `steps/attributes.py` stores each record's readings as `elevator_text` and
`pet_policy_text`. `ads.attributes` merges them over the same records as the attributes, and
fills the elevator or the pet policy where the merge leaves it unknown, from no record giving
one or from a conflict, as the rules do. Two readings give no fill. A record whose description
StreetEasy stripped gives no reading, so the other records' reading stands. A cut description
still gives a reading of the text left. A cut after "walk-up" and before "elevator" reads as no
elevator, which blocks the fill when another record reads one, and fills the ad wrongly when no
other record gives a reading. Most ads have no ACTIVE answer and merge their closed records
too, as described below. The ads file's `from_text` lists the fields filled this way.

The port replaces a reading of my own from Oct 16, which took any pet fee in the description as
pets allowed. `pets-from-ad-v2` reads a fee the same way, apart from texts it reads otherwise: a
ban, cats and no dogs, or approval beside the fee. In the fixture, ad 4771575 asks for approval
and charges a fee, so it now reads `approval_required`.

I measured the port in a scratch lane on Oct 17, building the export once from master and once
from the branch, with the same records and ledger. The master build took 6 min 51 s at a
4.5 GB peak. The branch build took 16 min 46 s at 4.4 GB, since its new code version makes
`ads.record_attributes` parse all 2,180,406 records again. Later builds parse only new
records. From each build I wrote a folder of the NB9 neighbourhoods and a folder of all scraped
areas with `observations.py`. `ops/pipeline/port_diff.py` loads a pair of such folders, gives
the master folder the two rules' fills as a fit on it would, matches the rows by audit ID and
counts the differences column by column. Its docstring lists the steps. On the folders of all
scraped areas it took 2 min 1 s at a 4.9 GiB peak, in a scope capped at 5 GiB.

In both pairs every row has a match, and only `elevator` and `pets` differ. The NB9 column
counts the rows whose audit ID the served dataset holds:

| | NB9 neighbourhoods | all scraped areas | NB9 |
|---|--:|--:|--:|
| rows | 350,202 | 1,746,770 | 296,718 |
| rows changed | 4,979 (1.42%) | 96,800 (5.54%) | 81 (0.027%) |
| `elevator` unknown to `no` | 1,636 | 21,689 | 0 |
| `elevator` unknown to `yes` | 10 | 821 | 0 |
| `elevator` `no` or `yes` to unknown | 8 | 8 | 8 |
| `pets` unknown to `allowed_restrictions_unknown` | 2,556 | 51,042 | 0 |
| `pets` unknown to `approval_required` | 530 | 20,557 | 0 |
| `pets` unknown to `not_allowed` | 280 | 3,359 | 0 |
| `pets` `allowed_restrictions_unknown` to `approval_required` | 36 | 813 | 34 |
| `pets` `allowed_restrictions_unknown` to `not_allowed` | 2 | 11 | 2 |
| `pets` a value to unknown | 40 | 353 | 40 |

On NB9's rows the port changes 81 rows, under `NEGLIGIBLE_SHARE`. 36 of them carried the pet fee
reading of Oct 16, and the port reads them as the rule does. The other 45 lose a fill, because
the rules' files read the description of the ad's page crawl and the pipeline reads the API
record's. For most of these ads the API record holds an empty or short description. Ad 1707396
has a full one, but only its page says pets are considered case by case. Over all rows the
port changes 1.42% in the NB9 neighbourhoods and 5.54% over all scraped areas, nearly all of
them fills of rows the rules' files never held. That share makes the port a data change of its
own, and Modeling schedules a fit for it. A fit on a folder from this build leaves `elevator-from-ad-v1` and
`pets-from-ad-v2` out of its feature set's rules.

`ads.record_attributes` is a Python model. It parses each distinct record once, in worker
processes, and keeps the results in Parquet files in `attributes/<code version>/` beside the
DuckDB database. A later build parses only records missing from those files. In a top-up the
model reads only the records of the new answers, and the materialization `merge` adds the
ones the previous table lacks. `config.py` hashes `steps/attributes.py`, `steps/adtext.py` and
the six modules of `src/apartments` it imports, and passes each module's SHA-256 to the model in the variable
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

Unlike the chain, `ads.attributes` merges an ad's attributes only over the records fetched up
to its last answer with status ACTIVE, and over all of them when the ad has no ACTIVE answer.
StreetEasy can strip or cut an ad's description once it is rented or delisted. A closed record
read from that text then gave another value, and the merge turned the ACTIVE records' value into
an unknown. The fit's target is the latest ask, so for an ad with an ACTIVE answer the merged
attributes describe the ad as it stood when it last asked. Few ads have one: on the export of
runs 1 to 16, 7,891 of the 2,140,923 ads and 5,850 of the 1,746,791 fit-ready rows, since the
backfill fetched most ads after they closed. The other ads merge all their records, none of
them fetched while ACTIVE. Data improvements sized the pattern on records-b4958178. Of the 469
ads whose latest record was closed and that had an ACTIVE record, 31 had a description different
from their last ACTIVE record's, and 14 had it blanked.

On that export, 875 of the 7,891 ads have records fetched after their last ACTIVE one, and the
cut changes the attributes row of each, 657 of them with a fit-ready row. For most of them only
`records`, the count of records merged, goes down. The merged values
change in 12 ads, one field each: bedrooms in 2 ads, the doorman in 2, laundry in 1, views in 4
and windows in 3. In each of them the conflict between records gives way to the ACTIVE records'
value, and the cut adds no conflict.

The rental flags (furnished, short term and concession) still merge over all of an ad's
records, since they describe the terms behind the ask. Ad 5178211 in Williamsburg shows why.
Its two ACTIVE records, fetched at 10:08 ET Oct 15 and 05:45 ET Oct 16, ask $4,595 and give no
concession or lease term. Its DELISTED record, fetched at 23:26 ET Oct 16, carries the same
description with a price of $5,017, 1.01 months free on a 12-month lease and a price delta of
$422. $5,017 over 10.99 months of 12 comes to $4,595, so the ACTIVE ask was net of the free
month, and only the closed record says so. A cut of the flags at the last ACTIVE record would
take away the ad's concession and its exclusion.

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

Where `ads.identity` puts an ad in the wrong unit or building, an entry of the unit ledger moves
it, as described under [Unit ledger](#unit-ledger).

## Building identity

`buildings.lots` gives each building with a record a lot and a BIN from the city's records. I
link each building two ways and choose between the two lots when they differ:

1. `buildings.latest_record` takes the building's latest answer with a record. It reads the slug,
   the street address, the zip, the city, the community district, the map point (`geoCenter`)
   and the four city facts StreetEasy shows: the building class, the year built, the floor count
   and the count of apartments. A year or a floor count of zero, an empty class and a value of
   the wrong type read as missing, while a count of zero apartments stays a count. It parses
   each record once for all eleven values, as `ads.answers` does, since a parse for each of the
   sixteen reads takes more than the build's 3 GB on 12 threads.
2. `buildings.pad_link` cuts the street address into a house number, a letter and a street name.
   It looks the name up in PAD's street name dictionary, `city.pad_streets`, for the street's
   code, and matches the number against the address ranges of that street in
   `city.pad_addresses`. Both come from the latest PAD release. The model's comment gives the
   parse, the house number keys and the rank of a match, and a condominium's ranges give its
   billing lot.
3. `buildings.footprint_link` tests the map point against the footprints of the latest copy. It
   keeps a footprint holding the point, or else the nearest one within 10 m.
4. `buildings.lots` compares the two lots. Where they differ, and the latest MapPLUTO release gives
   one of them apartments and the other a count of 0, it takes the one with apartments, as [The lot
   with apartments](#the-lot-with-apartments) explains. When the building on the address's lot
   came down, it keeps the address's lot instead, as [A building that came
   down](#a-building-that-came-down) explains. Otherwise, as for a lot missing from
   MapPLUTO or one without a count, it counts the facts the record shares with MapPLUTO's record of
   each lot, in the latest release, and takes the lot with more. `link` says which way the lot
   came:

   | `link` | lot and BIN |
   |---|---|
   | `both` | the address and the map point give the same lot |
   | `address_apartments` | they differ, the address's lot has apartments and the footprint's lot a count of 0 |
   | `footprint_apartments` | they differ, the footprint's lot has apartments and the address's lot a count of 0 |
   | `address_demolished` | as `footprint_apartments`, but the address's last record with apartments, from an earlier release, fits the facts better than the footprint's lot, the map point lies outside the footprint, and every ad of the building ran before the next release |
   | `address` | they differ, and the address's lot fits the facts better |
   | `footprint` | they differ, and the footprint's lot fits better |
   | `tie` | they differ and fit equally, and the step takes the address's lot |
   | `address_only` | the map point lies more than 10 m from any footprint |
   | `footprint_only` | the address matches no PAD range |
   | null | neither |

   The BIN comes with the lot. PAD gives some lots a BIN such as 1000000, which stands for no
   numbered building. When the address's lot has one and the footprint on the same lot gives a
   numbered BIN, I take the footprint's.

`analysis.lot_facts` and `analysis.lot_landmarks`, under [Lot facts by date](#lot-facts-by-date)
and [Landmarks by date](#landmarks-by-date), read MapPLUTO's facts and LPC's designations on each
building's lot as of each ad's date. `analysis.building_certificates`, under
[Certificates of occupancy by date](#certificates-of-occupancy-by-date), reads DOB's certificates
of occupancy on the building's BIN the same way.

### Error rates

On Oct 16 I built the four models over the export of runs 1 to 10, with PAD 26c, MapPLUTO 26v2
and the footprints copy of Oct 11. Of 70,141 buildings, 70,041 have an address link and 69,576 a
footprint link: 61,304 points fall inside a footprint and 8,272 within 10 m of one. Five
buildings have neither.

Reviewer subagents judged a sample of each class, 30 or 40 buildings drawn at random, and split
`both` by whether the lot fits two or more facts. For each building, they read the record's
address, name, type, description and city facts, where the map point falls against the lot's
footprint, and MapPLUTO's record of each lot on offer: its address, class, year, floors,
apartments, floor area, building count and lot area. They answered which lot is the building's,
or whether the single lot is, or said the case was unclear. Their answers and reasons are in
`config/reviews/building-identity-20261016.jsonl`. Three of the buildings have moved to another
class since the draw, as the models changed, and I count each in its class in this build. I
estimate each class's share of wrong lots from the buildings they judged, with a 95% Wilson
interval, and multiply it by the class's size:

| class | buildings | right | wrong | unclear | wrong share | wrong lots |
|---|---:|---:|---:|---:|---|---:|
| `both`, fit 2 or more | 63,905 | 32 | 0 | 0 | 0% (0% to 10.7%) | 0 |
| `both`, fit under 2 | 3,407 | 26 | 2 | 3 | 7.1% (2.0% to 22.6%) | 243 |
| `address` | 1,420 | 33 | 4 | 3 | 10.8% (4.3% to 24.7%) | 154 |
| `footprint` | 271 | 29 | 4 | 4 | 12.1% (4.8% to 27.3%) | 33 |
| `tie` | 478 | 23 | 13 | 4 | 36.1% (22.5% to 52.4%) | 173 |
| `address_only` | 560 | 24 | 2 | 4 | 7.7% (2.1% to 24.1%) | 43 |
| `footprint_only` | 95 | 17 | 7 | 6 | 29.2% (14.9% to 49.2%) | 28 |

The `address` row takes the answers Data improvements gave on Oct 17, when it judged five of its
reviews again, as [The lot with apartments](#the-lot-with-apartments) describes. About 670 lots are
wrong by these estimates, under 1% of the buildings. The build of Oct 16 came before the step took
the lot with apartments, so its `address`, `footprint` and `tie` classes still hold the buildings
that rule now moves, and the same section scores them again. A sample of 30 bounds the largest
class loosely, and Data improvements' registry gives better evidence there: it agrees on 62,932 of
the 63,124 buildings both hold. In the ties the reviewers chose the address's lot 23 times and the
footprint's 13 times. With the point within 10 m of a footprint but outside it, they chose the
address's lot 12 times and the footprint's once.

### Against the registry

Data improvements' lot registry, `/data1/apartments/external/registry/20261016-5f07157-all`,
gives a lot to each building slug by its own address match (`address`), by the lot under the
map point (`reverse`), or by a person's choice (`override`). It matches `buildings.lots` here:

| method | buildings | in the build | same lot | other lot | same lot and BIN |
|---|---:|---:|---:|---:|---:|
| `address` | 64,596 | 64,567 | 64,161 | 405 | 63,411 |
| `reverse` | 4,608 | 4,608 | 4,206 | 398 | 3,886 |
| `override` | 70 | 69 | 69 | 0 | 69 |

The override missing from the build is `the-west-coast-west-wing`, absent from the export. Most
of the other lots fall in the classes where the address and the footprint disagree:

| class | in both | same lot |
|---|---:|---:|
| `both`, fit 2 or more | 63,124 | 62,932 |
| `both`, fit under 2 | 3,355 | 3,328 |
| `address` | 1,396 | 1,196 |
| `address_only` | 546 | 491 |
| `tie` | 463 | 359 |
| `footprint` | 264 | 62 |
| `footprint_only` | 91 | 68 |

Of the 33 reviewed `footprint` buildings with an answer, the reviewers' lot is the step's in 29
and the registry's in 11. In the ties the registry does better, 28 against the step's 23, and in
`address`, with the answers of Oct 17, the step's lot is right in 33 of 37 and the registry's in
25.

### The lot with apartments

StreetEasy lists apartments, so a building's lot ought to have some. Where the address and the
map point give different lots and MapPLUTO gives one of them apartments and the other a count of
0, `buildings.lots` takes the lot with apartments, ahead of the facts. On Oct 17 I built the step
over the export of runs 1 to 10, with PAD 26c, MapPLUTO 26v2 and the footprints copy of
Oct 11. The rule set the lot of 434 buildings: 179 by `address_apartments` and 255 by
`footprint_apartments`. The facts had already chosen the same lot for 209 of them. It moves 225
buildings with 1,931 ads:

| move | buildings | ads | HPD lists only the lot with apartments | only the other | both | neither |
|---|---:|---:|---:|---:|---:|---:|
| to the address's lot | 15 | 924 | 7 | 0 | 8 | 0 |
| to the footprint's lot, no building on the address's lot | 185 | 918 | 98 | 4 | 70 | 13 |
| to the footprint's lot, a building on the address's lot | 25 | 89 | 9 | 0 | 14 | 2 |

I read two independent records against each move:

- HPD's register of the residential buildings under its jurisdiction, fetched on Oct 17. Where
  it lists only one of the two lots, it lists the lot with apartments 114 times and the other
  lot 4 times.
- The city's building footprints, drawn from aerial survey. They show no building on the lot
  without apartments in 185 of the 210 moves to the footprint's lot, and MapPLUTO calls 94 of
  those 185 lots vacant land. DOB's certificates of occupancy give dwelling units on 3 of the
  210 lots.

In 197 of the 210 moves to the footprint's lot, the map point falls outside every footprint,
within 10 m of the footprint's lot. In ties of that kind, the reviewers chose the address's lot
12 times and the footprint's once, as [Error rates](#error-rates) says, and left 3 unclear. Of
those 16 ties the rule moves 2, both unclear, and none with an answer. Among the 197 moves,
HPD lists only the footprint's lot 103 times and only the address's lot 3 times.

The sample of Oct 16 holds 10 buildings now in `footprint_apartments`. The reviewers first
judged the footprint's lot wrong for 5 of them, each time because MapPLUTO's facts for the
address's lot match the StreetEasy record, and the record calls the building vacant land or an
empty lot. StreetEasy copies those facts from the lot it links, so a match shows its link, not
where the apartments are. I read the five again with the footprints and the ads:

- 58 Brooklyn Avenue, 1996 Fulton Street and 356 Vernon Avenue: the address's lot is vacant land
  with no building footprint, and the footprint's lot holds a house of 2 to 4 apartments built
  between 1899 and 1931. The ads of 58 Brooklyn Avenue describe a walk-up with Victorian
  details, and those of 356 Vernon Avenue a pre-war building.
- 310 Broadway in Brooklyn: the address's lot is an 89 sq ft sliver with no footprint. The ads
  describe a boutique rental development, and the footprint's lot holds a 6-floor condominium of
  24 apartments built in 2019.
- 512 West 23rd Street: the address's lot is vacant, with a 12 ft structure on it, and the
  footprint's lot holds a 6-floor building of 30 apartments from 1930. The ad describes a
  doorman building with floor-to-ceiling windows, which matches neither lot.

On Oct 17 Data improvements judged the five again with MapPLUTO's releases from 23v1 on and
HPD's register, and came to the same answers: the footprint's lot for the first four, and
unclear for 512 West 23rd Street. With the rule and those answers, `identity_check.py` scores
`footprint_apartments` 6 right, 0 wrong and 4 unclear, and `address_apartments` 8 right, 0
wrong and 1 unclear. Its estimate of wrong lots in all classes comes to about 490, against
about 670 on the build of Oct 16.

### A building that came down

On some lots the building with the apartments came down after its ads ran, and MapPLUTO now
gives the lot a count of 0. StreetEasy's map point for the old building then falls on open
ground, and the nearest footprint within 10 m belongs to the building next door, so
`footprint_apartments` took the neighbor's lot. Data improvements found the case on Oct 17
among 43 buildings it had moved off empty lots: PAD 26c still puts the address on the lot in
HPD's register for 35 of them.

`buildings.lots` looks for it in MapPLUTO's last record of the address's lot with apartments,
from any release since 09v1 with a published date. 22v2 has none in
`ops/pipeline/pluto_releases.csv`, so the step leaves it out. When that record shares more facts
with the StreetEasy record than the footprint's lot does in the latest release, and the map
point lies outside the footprint, the old building could hold the ads only if they ran before it
came down. MapPLUTO dates that only roughly: the first release after the last record with
apartments comes some months after the building went. The step keeps the address's lot and its
BIN, with `link` set to `address_demolished`, when every ad of the building came on the market
before that release.

Without the date test, 36 buildings with 415 ads would move. I compared their ads with that
release:

| ads | buildings | ads |
|---|---:|---:|
| all listed before | 26 | 340 |
| some before and some after | 2 | 56 |
| all listed after | 8 | 19 |

An ad from after the release can't be for an apartment in the old building. The latest release
classes 8 of those 10 lots as vacant land and the other 2 as a garage and a parking lot, so a
new building on the lot is unlikely to hold the ads, and the step leaves the 10 buildings on the
footprint's lot. One of them, 244 Montrose Avenue in Brooklyn, had 6 ads before MapPLUTO showed
the lot empty in 2022 and 30 after. Data improvements suggested the date test on Oct 17.

On the export of runs 1 to 10 the step moves 26 buildings with 340 ads off
`footprint_apartments`. PAD gives 23 of those lots a placeholder BIN such as 3000000, so a join
by BIN finds no building for them instead of the neighbor. The step reads every MapPLUTO record
of the lots that addresses give, about 2.9 million rows, and on the lane copy it takes 2.3 s
against 0.3 s before.

My first version kept the address's lot whenever an earlier release gave it apartments. That
moved 50 buildings, among them 278 Cooper Street in Brooklyn, which the reviewers of Oct 16
placed on the footprint's lot. There MapPLUTO recorded twin buildings from 1906 with 6
apartments each, at 276 and 278, until the one at 278 came down in 2009, and the ad ran in 2019.
StreetEasy's record fits the two equally, and the step now takes the standing building on a tie.
That costs a little where the twin came down after the ads: the lot's facts come out the same,
but the BIN is the neighbor's. Of the Oct 16 sample, the step moves only 910 Bergen Street, which
the reviewers left unclear. Its record describes a two-family house from 1905, which MapPLUTO
gave the address's lot until 2019, and the footprint's lot holds 12 apartments built in 2016.

Of Data improvements' 43 buildings, 26 were in `footprint_apartments`. The step moves 12 of them
to the lot in HPD's register. It leaves 7 twins whose facts tie, 2 with ads from after the lot
emptied, and 5 where MapPLUTO never gave the address's lot apartments or the map point lies
inside the footprint, mostly new buildings on lots that were vacant.

### Checking a change

`ops/pipeline/identity_check.py` builds `buildings.lots` and the models above it over the export
in a scratch database, prints each class's size, compares the lots with the newest registry and
scores the reviewed sample:

```sh
/data1/apartments/serve/master/ops/job light -m 4G -- \
    pipeline/.venv/bin/python ops/pipeline/identity_check.py --out /data1/apartments/tmp/lots.parquet
```

On thelio it takes about 17 s at a 2.7 GB peak: 15 s for the four models, 9 s of it in
`buildings.footprint_link`. A reviewed building whose lot has changed counts as neither right nor
wrong, so a new rule needs reviews of the buildings it moves.

## Lot facts by date

`analysis.lot_facts` gives each candidate ad the lot and BIN of its building, and the lot's
MapPLUTO facts as the city published them before the ad. I build it in three models:

1. `city.pluto_releases` reads every record of `city.pluto`, 37 million across the 44
   releases, and keeps a row for each release: its published date, the day 7 days later when
   ads start to read it, and for each field whether any lot of the city has a value in it. It
   looks at the whole city because the flood zone flags hold values only for lots in the zone,
   and a release can carry a flag that none of the buildings' lots has. The scan takes about
   25 s and 0.8 GB, and SQLMesh runs it again only when the MapPLUTO files change.
2. `buildings.lot_releases` keeps the records of the lots of `buildings.lots` in every release:
   64,478 to 67,440 lots in each release. Releases write the same value in several ways, such
   as `01` and `1` for a land use code or `2.50` and `2.5` for a ratio, so the model casts each
   fact to a whole number, a decimal, a true or false value or trimmed text. A fact then
   compares equal across releases when the city recorded the same value. Three kinds of value
   stop the build: one that isn't a number in a field of numbers, a fraction in a field of
   whole numbers, and an `irrlotcode` other than Y or N. No release in the archive has any of
   them, so a new release's change of spelling stops the build rather than leaving a fact
   blank. A blank reads as missing.
3. `analysis.lot_facts` dates each candidate ad by its first day, in UTC, and picks the latest
   release published at least 7 days before it, or the first release for an ad older than
   that. Release 22v2 has no published date in the archive's manifest, so I skip it. The ad
   reads the lot's facts from that release's record, as the served model's `plutoasof-v3` does,
   with these exceptions:
   - The address, the year built and the coordinates come from the latest release. They place
     the lot rather than describe it, and older releases often give a round guess for the
     year.
   - When the release has no record of the lot, every fact comes from the latest release and
     `pluto_fallback` says `lot_missing`. A lot numbered after the release, such as a new
     condominium's, has no record in it.
   - When the release came out before the year the latest release gives for the building, its
     record describes the lot before the building. Every fact then comes from the latest
     release, and `pluto_fallback` says `before_built`.
   - Older releases leave some fields blank for every lot of the city, as
     `city.pluto_releases` records, and an ad reading such a release takes those fields from
     the latest release. `latest_fields` lists them:

     | releases | fields from the latest release |
     |---|---|
     | 09v1 to 12v2 | `residfar`, `pfirm15_flag`, `firm07_flag` |
     | 13v1 to 16v2 | `pfirm15_flag`, `firm07_flag` |
     | 17v1 on | none |

     Releases before 20v1 also lack coordinates, which come from the latest release anyway.
     The served model works out the fields of a release from the registry's lots in Data
     improvements' releases file instead, and it counts a value of spaces as a value. The two
     would part on a release where only lots outside the registry have a flag, or where the
     registry's lots hold only spaces in a field. No compared row differs this way.

   A blank in a field the release carries stays missing. The served model reads a blank number
   as missing too. For a blank `irrlotcode` it depends on how pandas loads the field in Data
   improvements' file of the latest release. Where the field loads as true or false, as in the
   20260925-3096a62 copy, the served model gives the lot's latest value. Where it holds a null,
   as in 20261016-5f07157-all, it leaves the blank. 109 compared rows in 24 lots read a blank
   `irrlotcode`, 26 of them from lot 3009557506 in 18v2, and none of those lots is in the
   20260925-3096a62 copy.

Each row keeps its release, the release's published date and the fallback, so each value
traces to a record of `buildings.lot_releases` and from there to a file of the city archive.
Nothing reads `analysis.lot_facts` yet. A fit moving to it changes its data, and gets its own
fit under the evaluation framework.

### Against the served model

On Oct 16 I built the three models in a scratch database over the export of runs 1 to 10, with
the 1,746,499 rows of `rows-892481e29edeeb73.parquet` standing in for the candidates. Of those
rows, 532 have no lot. The rest read these records:

| record | rows | lots |
|---|---:|---:|
| the lot's record in the ad's release | 1,715,452 | 64,805 |
| the latest release, `lot_missing` | 27,526 | 1,324 |
| the latest release, `before_built` | 2,989 | 305 |

Of the `lot_missing` rows, 158 in 9 lots have no record in the latest release either and get
no facts. The 479,641 rows dated before 17v1 became usable take the flood zone flags from the
latest release.

I then ran the served model's `released_lots` over each pair of lot and date, with Data
improvements' MapPLUTO files of `20261016-5f07157-all`, once with each row's month as the
served model dates it and once with its first day. I also worked out each row's release,
fallback and fields from the latest release from Data improvements' releases file, the way
`released_lots` does. By first day, each compared row agrees with `analysis.lot_facts` in its
release, its fallback, its fields from the latest release and every fact. I left two kinds of
rows out of the comparison:

- 36,308 rows in 24,800 pairs of lot and date whose lot isn't in Data improvements' file of
  26v2. That file holds the lots of their registry, and `buildings.lots` gives these buildings
  other lots.
- 48 rows in 15 lots whose record in their release is missing from Data improvements'
  releases file, though the city archive has it. The file lacks 22 Queens lots on blocks 3410,
  3442, 3444, 3539 and 3729 in releases 09v1 to 18v1, because its fetch read only the Brooklyn
  file of each release the city split by borough. `released_lots` gives those rows the facts of
  26v2. Data improvements fixed the fetch in #907, and the gap closes when they next rebuild
  their releases file.

By month, 28,366 of the 1,709,611 compared rows read other facts. The served model dates each
row by the first of its month, so a row takes a release only from the first month starting 7 or
more days after the release came out. This step dates each ad by its own first day, and an ad
later in a month can read a release from earlier in that month.

### Checking a change

`ops/pipeline/lot_facts_check.py` builds the three models and those below them over the export
and a rows file, and prints the rows by release and fallback. It gives `analysis.lot_facts` an
empty `ledger.status`, so no `drop_lot` takes a lot away, as none does in `released_lots`. It
compares the release, the fallback, `latest_fields` and every fact with `released_lots`:

```sh
/data1/apartments/serve/master/ops/job light -m 6G -- \
    pipeline/.venv/bin/python ops/pipeline/lot_facts_check.py --out /data1/apartments/tmp/lot-facts.parquet
```

On thelio it takes 4 to 7 minutes, depending on the other jobs, at a 4.3 GB peak, most of both
in `released_lots`. The models take 60 s: 25 s for `city.pluto_releases` and 9 s and 10 s for
`buildings.lot_releases` and `analysis.lot_facts`.

## Landmarks by date

`analysis.lot_landmarks` gives each candidate ad the designations the Landmarks Preservation
Commission had made on its building's lot by the ad's first day. I read the latest copy of LPC's
set in `city.landmarks`, which gives a row for each building of each designation, with its lot,
type, status and date, and keep the rows with the status DESIGNATED. A row of a historic
district puts the lot in the district. A row of an individual, interior or scenic landmark makes
the lot a landmark, as the served model's `lpc_as_of` reads them.

For each ad I take its building's lot from `buildings.lots` and keep the lot's designations
dated on or before the ad's first day in UTC. The row gives the earliest landmark and the
earliest district, each with its date and LP number, and `landmark` and `historic_district` say
whether the lot had one. For an ad whose building has no lot, both flags stay missing, where
`lpc_as_of` gives false. Two kinds of value stop the build: a type outside the four, and a date
that is blank or not written as month, day and four-digit year. The copy of 2026-06-18 has
neither in its 39,363 rows.

The copy holds LPC's designations as of its release. A designation the LPC withdrew before then
is missing from every ad, and an ad after the release misses designations made since, so
`landmarks_release` gives the copy each row read. Of the rows of rows-892481e29edeeb73, 46,705
come after the release. Nothing reads `analysis.lot_landmarks` yet. A fit moving to it changes
its data, and gets its own fit under the evaluation framework.

### Against the served flags

`ops/pipeline/landmarks_check.py` builds `analysis.lot_landmarks` and the models it reads over
the newest rows file in a scratch database, and runs `lpc_as_of` on Data improvements' LPC file
of 20261016-5f07157-all twice: once on each row's building with that folder's lot registry, as
the served model does, and once on the step's lot. The second run reads the same lots as the
step, so it differs from the step only through the copy and the rules, and the first run differs
from the second only through the lot each reads:

```sh
systemd-run --user --unit landmarks-check -p MemoryMax=5G -p MemorySwapMax=0 --wait --pipe \
    pipeline/.venv/bin/python ops/pipeline/landmarks_check.py --out /data1/apartments/tmp/lot-landmarks.parquet
```

On the 1,746,499 rows of rows-892481e29edeeb73 the models take 17 s and the whole check 27 s,
at a peak of 2.6 GB. 532 rows have no lot, 25,416 read a landmark lot and 252,699 a lot in a
historic district. I compared the flags three ways:

- On the 1,697,438 rows whose lot is the registry's lot, the step and `lpc_as_of` agree on both
  flags in every row.
- Data improvements' file keeps the designations of the registry's lots only. The copy holds 80
  designations on 79 other lots of the step's, and these account for every row where the step
  differs from `lpc_as_of` on its own lot: 134 rows for `landmark` and 836 for
  `historic_district`.
- On the building, as served, the flags differ in 2,455 rows for `landmark` and 504 for
  `historic_district`, all of them rows whose lot differs from the registry's. In 2,327 of
  them the registry's lot holds a landmark and the step's lot doesn't. 2,300 of those come from
  six buildings the registry places at the address nearest their map point, 6 to 59 m away, on a
  landmark's lot nearby. The registry puts The Sagamore on the lot of the Claremont Stables, One
  Union Square on the Union Square Savings Bank's lot and Barclay Tower on St. Peter's Church's
  lot, for 789, 784 and 505 rows. In the other 128 rows the step's lot holds a landmark the
  registry's lot lacks, 67 of them in the Belnord. For `historic_district`, 294 rows lose a
  district and 210 gain one.

## Certificates of occupancy by date

`analysis.building_certificates` gives each candidate ad the certificates of occupancy DOB had
issued on its building's BIN by the ad's first day. DOB keeps them in two sets, and I read the
latest copy of each:

- `city.dob_co`, the earlier set, from July 2012, with a row for each certificate of a job;
- `city.dob_now_co`, the DOB NOW set, from March 2021, with renewals of earlier jobs as well.

Both hold only new buildings and major alterations (Alteration Type 1). The copies of
2026-10-15 give 53,351 jobs in the earlier set and 25,312 in DOB NOW, 14,969 of them in both, so
I read each job's certificates from both sets and date the job by its first certificate. DOB
NOW files a building rebuilt behind walls it keeps as a new building with existing elements to
remain, and I count it as a new building, as DOB does. The earlier set has no such type.

For each ad I take its building's BIN from `buildings.lots`, read a BIN such as 1000000 as
none, and keep the BIN's jobs with a first certificate on or before the ad's first day in UTC.
The row gives:

- `new_building_since`, the first certificate of the earliest new building job;
- `altered_since`, the first certificate of the latest major alteration job;
- `units`, the count of apartments on the latest certificate giving one above 0. On a day with
  a certificate in each set, I take the DOB NOW one, and among one set's certificates on a day,
  the one with the greatest ID.

Each comes with the job or certificate behind it. `new_building` and `altered` say whether the
BIN had such a job, and stay missing for an ad without a BIN, or when the archive lacks a copy of
either set. Three kinds of value stop the build: a job type outside the two kinds, a blank issue
date in the earlier set, and an issue date in a form other than its set's. The earlier set
writes a four-digit year, month, day and time, and DOB NOW writes month, day, two-digit year and
time. The copies of 2026-10-15 have none of these in their 143,242 and 82,963 rows. A DOB NOW
certificate without an issue date stays out, and the copy has one. I read a count of apartments
other than a whole number as missing, and a count too large for an INTEGER or a count of 0 as
well: each ad offers an apartment in the building, so a 0 gives no count for it. 6,681
certificates in the earlier set and 7,733 in DOB NOW give 0.

The earlier set begins in July 2012, so a building finished before then has no new building
job, unless DOB issued a certificate on its job later, such as a renewal of a temporary
certificate. For such a building `new_building_since` gives the first of the later
certificates, years after the building went up. An alteration job dates late the same way when
its first certificate in either set is a DOB NOW renewal: of the 5,865 buildings with a major
alteration by their latest ad, 297 take `altered_since` from a renewal, 294 of them with change
and 3 without. Each copy holds DOB's certificates as of its
release, and `dob_co_release` and `dob_now_co_release` give the copies each row read. Nothing
reads `analysis.building_certificates` yet. A fit moving to it changes its data, and gets its
own fit under the evaluation framework.

### Against MapPLUTO and StreetEasy

`ops/pipeline/certificates_check.py` builds `analysis.building_certificates` and the models it
reads over the newest rows file in a scratch database. It then takes each building's latest ad
and compares the year of its first new building certificate and its latest count of apartments
with the year built and `unitsres` of its lot in the latest MapPLUTO release, and with the year
and count StreetEasy gives:

```sh
systemd-run --user --unit certificates-check -p MemoryMax=5G -p MemorySwapMax=0 --wait --pipe \
    pipeline/.venv/bin/python ops/pipeline/certificates_check.py --out /data1/apartments/tmp/building-certificates.parquet
```

On the 1,746,499 rows of rows-892481e29edeeb73 the models take 19 s and the whole check 22 s,
at a peak of 2.6 GB. 4,908 rows have no BIN: 4,376 read a lot with a BIN such as 1000000 and 532
have no lot. Of the others, 1,280,065 rows read no certificate, 233,790 read only major
alterations, 208,660 only a new building and 19,076 both.

2,993 buildings have a new building job by their latest ad. Against MapPLUTO's year built, the
first certificate comes:

| years after MapPLUTO's year | buildings | first certificate 2012 to 2014, MapPLUTO before 2012 | rebuilds with existing elements | StreetEasy's year within 2 |
| --- | ---: | ---: | ---: | ---: |
| -1 | 15 | 0 | 0 | 14 |
| 0 to 2 | 1,755 | 65 | 10 | 1,529 |
| 3 to 5 | 756 | 221 | 0 | 298 |
| 6 to 30 | 342 | 214 | 1 | 45 |
| above 30 | 106 | 8 | 73 | 26 |
| no year | 19 | 0 | 2 | 13 |

I traced the larger gaps to the sets and to the records:

- A gap of 3 to 5 years may come from construction running past the year MapPLUTO gives the
  building. For 221 of the 756 the first certificate falls in 2012 to 2014 on a lot MapPLUTO
  dates before 2012, so an earlier certificate before July 2012 could be missing from the set.
- In 214 of the 342 buildings 6 to 30 years off, the first certificate falls in 2012 to 2014 on
  a lot MapPLUTO dates before 2012. The building went up before the set begins, and the
  certificate is a later one on its job, most often a temporary certificate in the earlier set.
- 73 of the 106 buildings more than 30 years off are rebuilds with existing elements to remain,
  nearly all in Brooklyn, with first certificates in 2023 to 2026 on lots MapPLUTO dates mostly
  1899 to 1931. MapPLUTO keeps the year of the old building.
- Some of MapPLUTO's years are stale. BIN 1014563 has a year built of 1920 in MapPLUTO, 2019 on
  StreetEasy and a first certificate in 2020.

Against StreetEasy's year the first certificate comes a year before to 2 years after in 1,913
buildings, 3 to 5 years after in 469, 6 to 30 in 268, more than 30 in 195 and earlier still in
19. StreetEasy gives no year for 129. Of the 195 more than 30 years off, 63 are rebuilds and in
95 MapPLUTO's year is within 2 years of the certificate, so StreetEasy gives those buildings an
older year than the city does.

8,311 buildings have a count of apartments above 0 on a certificate by their latest ad. The
latest count matches MapPLUTO's `unitsres` in 6,372 and comes within 5% in 468 more, and
matches StreetEasy's count in 5,462 and comes within 5% in 482 more. In 79 more buildings, with
1,710 rows, the latest certificate by the latest ad gives 0. 75 of them have no count, and 4
take an earlier certificate's.

## Fit-ready rows

`analysis.rows` gives a fit its rows, one for each unit and month, with the values of the current
chain's analysis datasets. I build them in eight steps.

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
   their attributes, their reported values and their building. It takes each ad's unit and
   building from `ads.placed`, after the unit ledger. Then it gives each ad a floor:
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
5. `analysis.ledger_rows` applies the corrections ledger to the kept rows, as described under
   [Corrections ledger](#corrections-ledger). It adds each row's latest ask from
   `analysis.latest_ask` as `latest_ask`, after the ledger's ask sets. `asking_rent` stays the
   ad's first ask, as in the chain's datasets. The last column, `relist_unit`, gives the row's
   relist unit, as described under [Relist units](#relist-units).
6. `analysis.label_months` checks each month of each label unit again and lists the rows it
   drops, as described under [Label months](#label-months). `analysis.rows` leaves those rows
   out and adds the label unit of each row's unit as `label_unit`, as described under
   [Label units](#label-units). `analysis.history_splits` cuts label units by their bedroom
   history, and `analysis.rows` adds each row's piece as its last column, `split_unit`, as
   described under [History splits](#history-splits).
7. `analysis.ask_check` lists the rows with a latest ask far from their building's median for
   review, as described under [Ask check](#ask-check).
8. `analysis.building_check` lists the rows whose lot's city record leaves no room for the ad,
   as described under [Building check](#building-check).

The chain checks a unit-month within a slice of one region's dataset, while `analysis.candidates`
checks it over every region. Each row lists the export regions of its ad's answers in `regions`,
so a fit can choose the regions it reads.

## Latest ask

`analysis.latest_ask` gives each kept row the latest ask `rentfrontier.latest_ask` chooses for
it, so a ledger change leaves it as it is. `analysis.rows` takes it as `latest_ask`, with the
asks of the ledger's live ask sets in place of the chosen ones. An ad gives at most one kept row, priced on its first
day. `analysis.latest_change`
takes the ad's last kept change dated on or after that day, or the change in effect on that day
when the ad has no later one and its record came after the row. The steps in
`analysis.latest_ask` then check that ask against the row's first ask, the ad's page price and
the median first ask of the building's other rows with the same bedroom count. The comments in
the model list the steps. The step for a page price within a factor of 2 skips a page price
equal to any of the ad's changes. The step for a tenfold digit skips only one equal to a change
`ads.kept_changes` keeps. An ad correcting a tenfold typo on its last day on the market shows
the correction as its page price, and `ads.kept_changes` drops the correcting change as a late
one, so the digit step weighs the typo against the page price. On the export of Oct 16, this
gives 12 ended ads the page price as their latest ask. Each typo was 9.6 to 10.7 times the page
price and was also the ad's first ask. latest-ask-v6 and earlier keep the typos, and
latest-ask-v7 gives those 12 rows the page price. The medians cover every region in
`analysis.kept`, while the chain takes them over the rows of the datasets it reads. On the full
export the two give the same steps, as the full build below shows.

From latest-ask-v9, `ads.kept_changes` first drops each stale change, as the chain does. A
change counts as stale when its ad is no longer active and the change falls more than 7 days
after the off-market day, unless the ad's latest record goes ACTIVE again after that day or the
change falls on the ad's on-market day. The second exception came with latest-ask-v10 (#983),
and the chain applies it at 7 days as well. Brokers
reuse an old ad's record for a later ad of the same apartment, so a stale change carries the
later ad's ask. In the chain's run of Oct 17, the rule changed the asks of 9,601 of 1,751,152
rows, 6,844 of them in the four API regions. In the fixture, it drops 5 of 385 changes, on two
ads, and moves one row's ask from $2,375 to $2,250.

`PIPELINE_STALE_DAYS` sets the 7 days. At -1, as in latest-ask-v10, every change dated on or
after the off-market day drops out, unless it falls on the on-market day or the ad went ACTIVE
again. The build records the value in its catalog line, and `observations.py` copies it into its
manifest. The served build keeps 7, and a lane at -1 builds into its own state and datasets
folders.

With the 7-day window, 38 changes in the drop-lot lane's state of Oct 17 fall on or after the
off-market day and raise the ask to a price of one repeated digit, such as $3,333 or $9,999,
by 1.2 to 2 times the change before. A late change counts as a placeholder only above twice or
below half the last kept change, or at exactly $10,000 over 1.2 times it, so all 38 stay. All
but three fall on the off-market day itself. For 36 of the 38 ads, the change gives the latest
ask.

For five of these ads, Data improvements found another ad for the same unit with an ask at
least 15% below the repeated-digit ask. #1018 gives those five ads back their ask from before
the takedown, in `pipeline/ledger/2026-10-17-takedown-asks.ndjson`. The other 33 have no such
backing and keep their asks. At -1 none of the 38 changes survive.

The median reads list positions with `list_extract`. SQLMesh renders each model through
sqlglot, and sqlglot 30.8 adds 1 to a computed index in brackets once it knows the list's type,
so a bracket reads the next element of the sorted list.

## Ask check

An error in every record of an ad leaves `analysis.latest_ask` nothing to compare within the ad,
so a tenfold typo in all of an ad's prices passes its steps. `analysis.ask_check` compares each
fit-ready row's latest ask with the median latest ask of the building's other rows with the same
bedroom count. It lists the row for review when:

- at least three other rows share its building and bedroom count;
- its latest ask is 6 to 16 times the median, or a sixteenth to a sixth of it.

`analysis.ads` gives the median, the number of other rows and the ratio in its `ask_check` column.
The check reads the rows after the corrections ledger, so a live bedroom set moves a row in with the
rows of its corrected count, a live ask set gives a row its corrected ask, and the ads the ledger
excludes drop out of every median. A typo of an
extra or a missing digit gives a ratio near 10, but a row's true ask can lie a good way from its
building's median. On the planted sample under [Planted errors](#planted-errors), the tenfold asks
ran from 6.8 to 15.1 times the median, so I set the band at 6 to 16. In both builds of that sample
the check also lists ad 2121710, a studio asking $21,545 whose description gives $2,150 a month.
The ledger excludes it, as described under [Tenfold asks](#tenfold-asks).

On the export of Oct 16 the check lists 40 rows: 31 at 6.1 to 12.5 times the median, and 9 at a
tenth to a sixth of it. Half of them have 45 or more others to compare with. A Sonnet subagent read
each of the 40 ads, with its description, its prices, the unit's other ads and the building's other
rows with its bedroom count:

| the ad | rows |
|---|--:|
| a mistyped price, 21 of them by a digit | 23 |
| a shop or a restaurant space | 5 |
| an apartment with another bedroom count or in another building than the record gives | 4 |
| an income-restricted unit | 3 |
| a real ask | 3 |
| unclear | 2 |

The three real asks are two-bedrooms. One is a walk-up asking $2,695 in 2015, in a building
whose other two-bedrooms ask $7,500 to $18,750 in 2026. The other two are new or renovated units
of 1,522 and 2,025 square feet asking $16,000 and $16,500, in buildings whose other two-bedrooms
were listed from 2015 to 2017 at $2,200 to $3,045. The check compares rows of every year and
size, so a rebuilt building or a much larger unit can fall outside the band.

A drop on the ratio alone would lose the three real asks and the rents of the three
income-restricted units, prices a model should explain or mark, and it would choose rows by the
fit's target. So `analysis.rows` keeps every row the check lists. A listed row leaves the list
through a ledger entry with its evidence, as any other correction does. When another ad of the
unit gives the right ask, an ask set gives the row that ask. When only the ad's own words give
it, an exclude drops the row, since the ledger takes no set on the ad's words alone.
`ops/pipeline/ledger_import.py` imports the quarantine versions of the chain named in its `RULES`,
so a commercial space or a mistyped price leaves the pipeline's rows once Data improvements excludes
it in a quarantine version and `RULES` names that version.

On a copy of a built state, the build rebuilt `analysis.ask_check` in 0.9 s, along with the views
below it. The build took 20.4 s, 12.7 s of it writing the two files, at a peak of 3,863 MiB.

## City check

`ops/pipeline/citycheck.py` compares a built state with the city's records of each building's
lot: the lot itself, the units with ads against the lot's apartments, and each row's floor
against the lot's floors. It reads a copy of the state file and writes `citycheck.json` and
`citycheck.md` to the folder given with `--out`:

```sh
ops/job gpu -x -- cp -a /data1/apartments/pipeline/state/pipeline.duckdb COPY
systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=0 -- \
    env TMPDIR=/data1/apartments/tmp/pipeline/tmp \
    pipeline/.venv/bin/python -I ops/pipeline/citycheck.py COPY --out DIR
```

DuckDB locks a file it opens, even read-only, and a lock held by the check would stop the build
from opening the live state, `/data1/apartments/pipeline/state/pipeline.duckdb`. So I run the
check on a copy, and the script refuses the live path. The first command makes the copy: the
build holds the GPU lock and every light slot while it runs, and `ops/job gpu -x` waits for the
same locks, so `cp -a` reads the file between builds. The script attaches the copy under the
catalog name `pipeline`, as the build's views expect, so any file name works. The city views
read the build's city cache by absolute path, so the cache has to stay in place. DuckDB gets
2 GB unless `--memory` says otherwise, and spills past it to a folder under TMPDIR. Each
section of the JSON report carries the definitions of its measures, and the Markdown summary
gives the counts and the first ten cases of each list.

For lots, I first count the buildings with ads, their ads and their fit-ready rows by the
`link` of `buildings.lots`. Then, as a route apart from the build's PAD address ranges and
footprints, I look up each building's street address among the lot addresses of the latest
MapPLUTO release. I parse both addresses as `buildings.pad_link` parses StreetEasy's,
and on both sides a street name in the PAD street dictionary becomes its street code, so
`6th Avenue` meets AVENUE OF THE AMERICAS. For each building, MapPLUTO's address gives:

- `same`: the build's lot alone;
- `among_several`: several lots, the build's among them;
- `other`: lots without the build's;
- `only_mappluto`: a lot for a building without one;
- `no_match`: no lot;
- `unparsed`: nothing, for an address without a house number or a borough.

MapPLUTO lists one address for each lot, so a corner building or a building on a range of house
numbers often finds no match, and a `no_match` counts nothing against the build's lot. The
report lists the `other` and `only_mappluto` buildings with the lots of their MapPLUTO address.
This route reads the same StreetEasy address as `buildings.pad_link`, through the same parse and
the same street dictionary. For a building linked by its address, `same` mostly repeats PAD's
answer, and a wrong StreetEasy address leads both routes to the same wrong lot. For a building
linked by its footprint, the route gives a more independent test.

For units, I take each lot with ads and count its distinct units in `ads.placed`, over all
time and over the 12 months up to the latest first day of a candidate ad. I compare both counts
with the city's:

- the lot's `unitsres` in `analysis.lot_facts`, from the MapPLUTO release of the lot's latest
  candidate ad, or from the lot's latest release when no candidate ad reads the lot. I take the
  count and its release from the same row;
- the apartments on the latest certificate of occupancy of each BIN of the lot's buildings with
  ads, from `analysis.building_certificates` as of the first day of the BIN's latest candidate
  ad, summed over the BINs. The BINs come from the buildings of the counted units, so a lot
  gets no certificate count when one of those buildings lacks a BIN or a BIN lacks a count.

Each lot falls in a class: no count, a count of 0, within the count, or above it by 1, 2 to 5,
6 to 20 or more than 20. The report lists the lots with the largest excess over either count,
and the lots with a `unitsres` of 0.

When a building's address lot and footprint lot differ, `buildings.lots` picks the one with
apartments in the latest MapPLUTO release when only one has some, and otherwise the one whose
latest building class, year, `numfloors` and `unitsres` best match the StreetEasy record. For a
lot with `link` `address_apartments`, `footprint_apartments`, `address` or `footprint`, the
`unitsres` comparison therefore leans toward agreement, and so does the `numfloors` comparison
below. A lot under `address_demolished` comes from an earlier release's record and has a
`unitsres` of 0 in the latest. The links `both`, `tie`, `address_only` and `footprint_only`
involve no such choice. I split each class tally into lots with a building linked by one of the
first five and the other lots, and print both in the summary.

For floors, I take each fit-ready row's advertised floor, else its physical floor, else its
label floor, and compare it with two counts:

- the `numfloors` of the row's lot, from the latest MapPLUTO release published at least 7 days
  before the row's first day;
- the building's StreetEasy floor count, in `building_floor_count`.

Here the classes add `no_lot` and go above by 1, 2, 3 to 5, 6 to 10 and more than 10 floors. A
row's release can come from before a building's last change, so a floor above the as-of
`numfloors` and within the latest release's count goes to `within_latest`, and the report gives
the latest count beside the as-of one. The build refuses a label floor above StreetEasy's count,
and I compare those refused label floors with `numfloors` too. The report lists the buildings
with the most rows above both MapPLUTO counts, and splits the rows by link as for units.

On a build of the sample from `ops/pipeline/sample.py`, with 673 buildings with ads and 16,080
fit-ready rows, the check took 2.7 s at a peak of 0.79 GB. Every building had a lot. MapPLUTO's
address gave the build's lot alone for 610 buildings, several lots with the build's among them
for 3, another lot for 2 and no lot for 58. All 610 `same` buildings took their lot from PAD's
address ranges, with `link` `both`, `address`, `tie` or `address_only`. The 3 buildings linked
by footprint gave `among_several` once and `other` twice: 903 Broadway reads lot 1008750073,
and MapPLUTO gives its address to lot 1008490010.

Over all time, the units with ads exceed `unitsres` in 246 of 663 lots, and over the last 12
months in 19. A unit here is a unit page, so a unit listed under several pages counts once for
each, unless a join of the [Unit ledger](#unit-ledger) gives the pages one unit. 462 Keap
Street in Brooklyn has 202 units with ads, 19 of them in the last 12 months, on a lot of 29
apartments. Of the 14 lots with a building linked by `address` or `footprint`, 6 exceed
`unitsres` over all time and none over the last 12 months. 18 lots have a `unitsres` of 0, and
1 of them reads it from the lot's latest release. Certificates give a count for 80 lots, and the
units of the last 12 months exceed it in 2.

10,567 rows have a floor. 32 of them, in 3 buildings, lie 1 floor above `numfloors`, both as of
the row and in the latest release, and 1 lies above StreetEasy's count. The Vanguard Chelsea
gives 21 of the 32, with floors up to 30 against 29 in MapPLUTO and 30 on StreetEasy. 57 more
rows, in 7 buildings, lie above the `numfloors` of their own release and within the latest
release's. 21 of those come from 951 Madison Street in Brooklyn: its rows read releases 19v2 to
20v4, which give condominium billing lot 3033577501 1 floor, and from 21v1 on MapPLUTO gives 7,
as StreetEasy does. The 27 rows with a floor in buildings linked by `address` or `footprint` all
lie within `numfloors`. 15 rows read a `numfloors` of 0. Of the 433 rows with a refused label
floor, 425 lie above `numfloors`, and 3 more lie above it as of the row and within the latest
release's count.

## Building check

`analysis.building_check` lists the fit-ready rows whose lot, in MapPLUTO's records, leaves no
room for the ad. In some of the rows the city check above read, the matcher had put the ad on
the wrong building. The check gives a reader those rows to move to the right building through
the [Unit ledger](#unit-ledger), or to exclude or take away their lot through the
[Corrections ledger](#corrections-ledger). `analysis.ads` gives the reasons, the lot and the lot's
facts in its `building_check` column.

The check reads each row's lot from `analysis.lot_facts`, with its facts as of the ad's first
day, and the same lot's record in the latest release from `buildings.lot_releases`. A lot can
gain floors or apartments between releases, so the floor and zero-unit rules need both records
to agree. The check lists a row for these reasons:

- `floor_above_lot`: the ad's floor, from its advertised floor, its physical floor or its unit
  label in that order, lies more than one floor and more than 30% above the lot's floor count.
  The lot holds a single building, and StreetEasy's floor count for the building, when it gives
  one, also lies below the floor.
- `zero_unit_lot`: the lot has no apartments and a land use from industrial to vacant, codes 06
  to 11. The ads place at most three units in the building. By the ad's first day, DOB had
  issued no certificate of occupancy with apartments on the building's BIN, and no certificate
  of a new building. For a building without a BIN, the check has no certificates to read, and
  the lot's records and the ads decide. 289 of the rule's 1,554 rows have no BIN.
- `never_built_lot`: every MapPLUTO release with a record of the lot gives it a building area
  of 0 and no apartments, and the latest copy of the building footprints holds no footprint on
  it. The ads may place any number of units in the building. The check leaves out a lot when any
  release gives it a blank area or apartment count, or a condominium class. As in the zero-unit
  rule, it also leaves out a row with a certificate of occupancy for apartments or for a new
  building.

When the latest release has no record of the lot, the dated record decides alone, as for 2 of
the zero-unit rule's rows. A latest floor count of 0 also leaves the dated count to decide.

I added the never-built rule after a reader in Data improvements found 239 rows on 33 lots of
parks, parking, rail yards and vacant land, in #1024. The zero-unit rule listed only 3 of them,
since the ads place 4 to 50 units in most of those buildings. On the drop-lot lane's state of
Oct 17, the rule lists those 239 rows and no others. The check's query took 2.2 s there.

Recent releases give some lots a blank record. A lot with an area of 0 in its older releases may
hold a new building by the time of the blank one, so the check leaves out any lot with a blank
area or apartment count. On the lane's state, the check leaves out one row this way.

The floor of slack covers a basement, a penthouse or a mezzanine that MapPLUTO counts
differently. MapPLUTO gives the floors of the tallest building on a lot, so lots of several
buildings stay out. I added the 30% after a first read. Without it, the rule listed 115 rows in
47 lots on the export of runs 1 to 16. A Sonnet subagent read each lot's MapPLUTO facts,
StreetEasy's buildings on it and up to three of its listed ads, and gave the lot a cause. Eight
lots were towers that number their floors past their story count, as a tower does when it skips
the 13th floor and its mechanical floors. In the ads the subagent read, those towers' floors lay
6% to 28% above the count, and the lots of the wrong building started at 38%, so I set the cut
at 30%. On whole floors, the 30% changes the cut only on lots of seven floors or more.

The city check's labels of lots with no apartments guided the zero-unit rule. Its sample held 8
such lots with land use 05, commercial and office buildings:

- 5 were the ad's building, an office or store building with apartments its record leaves out,
  one of them an unclear call;
- 2 advertised commercial space;
- 1 was the wrong building.

So the rule leaves out commercial and office buildings, code 05, along with mixed residential
and commercial use and the residential uses, codes 01 to 04. It also leaves out a building where
the ads place four units or more, or where DOB has issued a certificate with apartments, since
there I take the lot for a conversion or a new building that DOB recorded before MapPLUTO did.
On the export of runs 1 to 16, the rule lists 7 of the city check's 8 lots of the wrong
building, all but the one with land use 05. It also lists 4 of the 26 other lots the city check
labeled: two it called the right building in mixed use, both unclear calls, one advertising
commercial space and one converted since its record.

On the export of runs 1 to 16, the check lists 1,638 of the 1,746,791 fit-ready rows, in 1,019
lots and 1,041 buildings:

| reason | rows | lots |
|---|--:|--:|
| `floor_above_lot` | 89 | 40 |
| `zero_unit_lot` | 1,554 | 983 |
| both | 5 | |

Of the floor rule's rows, 43 take an advertised floor and 46 a floor from the unit label. The
zero-unit rule's rows read land use 08, public facilities, in 768 rows, industrial in 235,
parking in 191, vacant in 185, open space in 91 and transportation in 84. 866 of its rows are in
Brooklyn, 687 in Manhattan and 1 in Queens. The query took 0.9 s at a peak of 1.0 GB.

The subagent's labels cover every lot the floor rule lists, and 20 of the zero-unit rule's lots:

| cause | floor lots | rows | zero-unit lots | rows |
|---|--:|--:|--:|--:|
| the wrong building | 29 | 65 | 15 | 30 |
| a floor misread from the ad or its unit label | 8 | 21 | | |
| a lot record that leaves out floors or apartments | 1 | 1 | 3 | 6 |
| a tower's own floor numbering | 1 | 1 | | |
| unclear | 1 | 1 | 2 | 2 |
| all | 40 | 89 | 20 | 38 |

I set the 30% on the same labels, so the floor rule's shares hold only for this sample. The 20
zero-unit lots lie outside the city check's sample. I drew 40 lots at random and kept the first
20 by BBL, so 19 of the 20 are in Manhattan, where 420 of the rule's 983 lots are. The tower
left on the list is 25 Columbus Circle, where ad 2589029 gives the 72nd floor of a lot of 54,
33% above the count.

About a fifth of the labeled lots hold the right building, with a floor misread from the ad or
a lot record behind the building. Dropping every listed row would lose theirs too, so
`analysis.rows` keeps every row the check lists, as it does for the ask check.

## Corrections ledger

The fit-ready rows take their corrections from the ledger in `pipeline/ledger/`, a folder of
NDJSON files. To correct a row, a person or a script writes the decision as a line of a batch
file and merges it through a reviewed PR. The docstring of `pipeline/models/ledger/entries.py`
lists the keys of a line and the rules it must follow. In short, a line:

- excludes an ad's row, gives one field of the row new values, takes the lot away from the
  ad's lot facts with a `drop_lot`, or retracts an earlier entry. A set gives the bedrooms, the
  full and half bathrooms, the size or the latest ask;
- gives the ad's `listing_id`;
- gives in `when` the row's values the decision rests on, such as the recorded bedroom count
  for a bedroom set, the latest ask `analysis.latest_ask` chose for an ask set, the month for
  an exclude, or the lot of the ad's building for a drop_lot;
- lists its evidence. A set needs an item beyond the ad's own words: another ad for the unit, a
  stated size, a floor plan, units of the same line, or Ben's own reading. An ask set needs
  another ad for the unit or Ben's own reading, as a size, a plan or another unit's price says
  nothing of the unit's ask. A drop_lot needs a city record or Ben's own reading;
- gives the day of the decision, and the file and line it came from.

Lines merged to master stay as they are, and a later file retracts a wrong entry.
`tests/test_ledger.py` compares each file with its version at the merge base with master.

Four models read the ledger:

1. `ledger.entries` reads every file and checks each line. A line breaking a rule stops the
   build, and the error gives its file and line.
2. `ledger.status` checks each entry against `analysis.kept`, its recorded latest ask
   against `analysis.latest_ask`, and its lot against the lot `buildings.lots` gives the row's
   building. It gives the entry the first status that fits:

   | status | the entry |
   |---|---|
   | `retract` | undoes another |
   | `retracted` | is undone by a later retract |
   | `absent` | is for an ad with no kept row |
   | `stale` | gives a value in `when` other than the kept row's, its latest ask or its lot, and `differs` lists the values |
   | `superseded` | sets a field a later live set of the row also sets |
   | `live` | applies |

3. `analysis.ledger_rows` drops the rows of the live excludes and gives the values of the live
   sets. A bath set gives the full and half bathrooms and leaves `bathrooms` as recorded, as the
   chain's bath rules do. An ask set gives the row's `latest_ask` and leaves `asking_rent`, the
   first ask, as recorded. `analysis.ask_check` reads the corrected ask from the rows, and the
   ads file keeps the latest ask from before the ledger.
4. `analysis.lot_facts` gives an ad with a live drop_lot no lot, BIN, release or facts, and
   names the entry in `lot_entry`. The building check then leaves the ad's row out, and the
   city check counts it among the rows without a lot. The rows file doesn't read the lot
   facts, so a drop_lot changes no fit input.

I gave the rows a `latest_ask` column for the ask sets instead of setting `asking_rent`. That
column holds the ad's first ask, as the chain's datasets do, and the chain gives a fit the
latest ask in a separate latest-ask file. On the build of Oct 16, 604,211 of the 1,746,515 rows
have a latest ask other than their first.

`analysis.latest_ask` reads `analysis.kept`, as the chain chooses each latest ask before its
correction rules apply. A change to the ledger rebuilds only the two ledger models,
`analysis.ask_check`, `analysis.lot_facts`, `analysis.building_check`, `analysis.label_units`
and the views `analysis.ledger_rows`, `analysis.rows` and `analysis.ads`. The catalog line of each
build lists the ledger's files with their SHA-256, and counts the entries by status and change.

### The chain's corrections

`ops/pipeline/ledger_import.py` writes the corrections of the chain's latest rules into the
ledger as a batch file for each run: `pipeline/ledger/2026-10-16-chain.ndjson` first, then
`2026-10-16-west-56th-studio.ndjson`, `2026-10-17-chain.ndjson` and
`2026-10-17-v35-chain.ndjson`. For each correction, it
finds the row's ad and its recorded values in the dataset of the rule version adding the line. A version's provenance file gives the
dataset of the lines it adds. From `bedrooms-ad-v7` on, a version's file starts with its base
rule's lines, so the importer follows the base rules back to the version adding each line.
Then it gathers the evidence:

- the ad's words from the rule file, or Ben's own reading when the rule's line gives his name
  and the day;
- the reads and floor plans in `config/reviews/` that decided the correction;
- the unit's other ads in the latest analysis dataset. The first two batches read them in the
  dataset of the fit's areas from Oct 15. The batches of Oct 17 read them in the dataset of
  all scraped areas from Oct 16, `all-scraped-analysis-20261016-5f07157`, as the first one
  leaves out buildings outside the fit's areas.

The unit's other ads back a set when more of them give the corrected value than give the recorded one. A size
set rests on the unit's other ads with the same bedroom count and a size within 10% of the
corrected one, or, when the rule decided it from the unit's line, on the other units of the
line with that bedroom count and size.

A size a read found stated for the unit backs a bedroom set when it rules out the recorded
count and each count between it and the corrected one: the size has to lie nearer the corrected
count's median than any of theirs. A size nearest a count past the corrected one still backs
the set, since listers seldom understate bedrooms. The 1,400 sq ft of a studio corrected to two
bedrooms lies nearest the three-bedroom median, and it backs the set. The 800 sq ft of a studio
corrected to two bedrooms lies nearer the one-bedroom median, so the importer keeps it as a
read, and the set needs other backing. The readers compared each size with the medians of an
older dataset, so the importer replaces their comparison with its own, from the medians of the
latest dataset.

A set without backing goes to `config/reviews/ledger-held-2026-10-16-chain.jsonl` instead,
with the counts of the unit's other ads, for a reader to look for backing. A second run of the
importer writes nothing to either file. It leaves out each correction from a rule file and line
already in the ledger, each one repeating the latest entry for its ad and field or a retracted
entry, and each held set an earlier held file lists. A later run thus writes only a new rule
version's new decisions. The table counts the first batch.

| rule | corrections | in the chain batch | backed by a later read | held |
|---|--:|--:|--:|--:|
| `bedrooms-ad-v3` | 148 | 92 | 9 | 47 |
| `bedrooms-ad-v4` | 22 | 22 | 0 | 0 |
| `bedrooms-ad-v5` | 4 | 4 | 0 | 0 |
| `bedrooms-ad-v6` | 13 | 12 | 0 | 1 |
| `bedrooms-ad-v7` | 17, 13 of them from v6 | 2 | 2 | 0 |
| `baths-ad-v3` | 59 | 35 | 1 | 23 |
| `sqft-units-v1` | 12 | 12 | 0 | 0 |
| `quarantine-v32` | 889 | 889 | 0 | 0 |

Of the batch's 179 sets, 158 rest on the unit's other ads, 25 on a stated size, 6 on a floor
plan, 2 on units of the same line and 2 on Ben's own review, some on more than one.

Data improvements read the first list of held sets with Sonnet subagents, looking for backing.
`pipeline/ledger/2026-10-16-held-reads.ndjson` holds the 12 sets they backed, 7 by another ad
for the unit and 5 by units of the same line. The held column counts the 70 sets still without
backing from that list, and a set of v6 from a studio to two bedrooms at 800 sq ft.

`pipeline/ledger/2026-10-16-short-stay.ndjson` excludes three short-stay ads Data improvements
found on Oct 16, in a second regex pass over the reads of the API rows.

`pipeline/ledger/2026-10-16-west-56th-studio.ndjson` holds the three new sets of `bedrooms-ad-v8`,
whose other 17 corrections repeat v7. Ben read the floor plan and photos of 333 W 56th St #3E on
Oct 16 and found a studio with a divider wall. Three of the unit's ads gave one bedroom, and
the fourth, from June 2023, already gave a studio. The rule's
lines give his reading with his name and the day in place of the ad's words, and the importer
takes such a line as a floor plan item when it mentions a floor plan and as an `owner` item
otherwise. The unit's 600 sq ft also matches the building's studios.

`pipeline/ledger/2026-10-17-chain.ndjson` holds the new decisions of `quarantine-v33` and
`bedrooms-ad-v9`, which `RULES` lists in place of v32 and v8. Quarantine-v33 adds nine lines to
v32's 889. Six exclude rows of the ask check's list: five shops or restaurant spaces, and a
two-bedroom asking $33,333, a run of one digit, whose unit last asked $2,556 in 2017. The other
three repeat the excludes of `2026-10-16-short-stay.ndjson`. The new lines give each month as
its first day, and the importer writes it as YYYY-MM. `bedrooms-ad-v9` adds two sets from a
studio to three bedrooms, for ads 4966432 and 5036591 of Trump World Tower, also from the ask
check's list. Each ad describes three bedrooms with three en-suite baths, and the unit's other
ads back the sets, three of them for 4966432 and one for 5036591.

On a copy of the state of the Oct 16 export, the rows file loses the six excluded rows and
has 1,746,509 rows. The ask check lists 32 rows, as the excluded rows leave and the two Trump
World Tower units now compare with the building's three-bedrooms. A second run of the importer
writes nothing.

`pipeline/ledger/2026-10-17-v35-chain.ndjson` holds the new decisions of `quarantine-v34`,
`quarantine-v35` and `bedrooms-ad-v10`, as `RULES` now lists v35 and v10 in place of v33 and
v9. Quarantine-v34 adds 15 lines to v33's 898, and v35 adds one more. Their 16 excludes:

- 8 `nonresidential`: three spaces in Gowanus, two in Red Hook, and one each in Greenpoint,
  Park Slope and East Williamsburg;
- 2 `location_conflict`: 2638365 in Noho, and 4853056, filed under 124 De Kalb Avenue #3 in
  Fort Greene. Its copy offers a two-bedroom in Bushwick, as 4839783 does at 1248 De Kalb
  Avenue #3L;
- 3 `explicit_short_term_offer`, in Lenox Hill;
- 2 `product_scope`, in Williamsburg;
- 1 `malformed_ask`: 2121710, the $21,545 studio at 992 Bedford Avenue. The batch
  `2026-10-17-tenfold-asks.ndjson` already excludes it as `tenfold_ask_unbacked`. I kept both
  excludes, since they drop the same row.

`bedrooms-ad-v10` adds six sets to three bedrooms, for units #4A and #4B of 68 Clinton Street
on the Lower East Side. The six ads offer a "5 room duplex", and their rows give five of them no
bedroom and one a single bedroom. 1287004 offers #4A as a "3 bedroom duplex with private
roofdeck", and 5120120 offers #4B as a "3 bedroom penthouse duplex". Each set rests on the
unit's other ads: for each row, four of #4A's other ads give three bedrooms against two with
the row's count, and two of #4B's give three against at most one.

I built the batch on a copy of the state of a lane build of Oct 17, made with the code of
#985 and the rule of `latest-ask-v10` on the export of Oct 16. The rows file lost the 15
excluded rows that had one and has 1,746,778 rows, and the six rows at 68 Clinton Street gave
three bedrooms. No other value of any row changed. The ask check still lists 27 rows, and each
of the 22 new entries is live. The build took 177 s, as the new ledger folder rebuilt the
models from the unit ledger on, and peaked at 4,219 MiB. A second run of the importer writes
nothing.

A quarantine line's `evidence` holds a note, and `quarantine_evidence` sorts it by the line's
`source`:
  - The first 889 lines of `quarantine-v33` have no `source`, and 858 of their notes give the
    ad's words. The importer files a note of such a line as the ad's words.
  - A line whose `source` starts `regex` comes from Data improvements' regex pass, and its note
    gives the matched words alone. The importer files it as the ad's words too. The three lines
    of that pass in `quarantine-v33` repeat the excludes of `2026-10-16-short-stay.ndjson`.
  - A line with any other `source` comes from a reading pass, and its note is the reader's. A
    note quoting the ad starts `Ad text:`, as the five new notes on shops do, and the importer
    files the words in the quotes as the ad's words. It files any other note of a reading pass
    as a read, as it does the note on the $33,333 ask, which gives the reader's reasoning.

The first batch filed every note as the ad's words, so 13 of its excludes hold a reader's note
as `ad_text`. Seven of those notes give the reader's reasoning: 1544571, 1569812, 1718693, 1725378,
2384625, 3421461 and 3780443. The other six give another listing carrying the same ad: 1404306,
1848216, 1887124, 2678483, 5019133 and 5098585.

The chain's `building-joins-v1` and `west-coast-wings-v1` are in the unit ledger, described
under [Unit ledger](#unit-ledger), with the lines of `unit-reviews-v5`, the latest version of
`unit-reviews-v2`, but for a split held for want of backing.
`analysis.label_units` joins units as `unit-labels-v17` does, as described under
[Label units](#label-units), and `analysis.history_splits` cuts units as `unit-splits-v4` does,
as described under [History splits](#history-splits). The chain's `fields-review-v3` needs no
ledger lines, as it returns the rows unchanged. The rules moving ads to another unit or building
go into the unit ledger.
`ads.attributes` reads the elevator and pet policy from each ad's text in place of
`elevator-from-ad-v1` and `pets-from-ad-v2`, as described under
[Attributes and exclusions](#attributes-and-exclusions).

### Tenfold asks

latest-ask-v8 corrects five tenfold asks from the ask check's list on the export of Oct 16, as
Data improvements read them in `tmp/suspect/askcheck/reads.jsonl`. I wrote them into
`pipeline/ledger/2026-10-17-tenfold-asks.ndjson`. For each one, I read the records of the ad and
of the unit's other ads in the export. Where another ad of the same unit, with the same bedroom
count, asked the corrected figure within a few weeks, the file sets the ask and cites that ad:

| ad | unit | recorded | set | the unit's other ads |
|---|---|--:|--:|---|
| 1472207 | 10 Hanover Square #21P, a studio | $31,025 | $3,100 | 1459327 asked $3,100 until Feb 18, 2015, the day this ad went on the market |
| 2498289 | 234 East 52nd Street #A, a one-bedroom | $28,875 | $3,150 | 2384921 asked $3,150 from Aug 7, 2018 until it rented, and 2485003 asked $3,150 on Aug 10 |
| 2552464 | 335 East 54th Street #4F, a one-bedroom | $28,000 | $2,800 | 2552463 went on the market the same day asking $28,000 and asked $2,800 the next day |
| 1792236 | 1689 First Avenue #2, a three-bedroom | $37,500 | $3,750 | 1568026 asked $3,750 from Apr 28, 2016 until it rented, and 1792235 asked $37,500 and then $3,750 on the same day |

The read of 2498289 cited only its ad's words, "Gross rent $3,150". The unit's other two ads
back the figure, so the file sets the ask. The recorded $28,875 is ten times $2,887.50, the net
effective rent of $3,150 with a month free on a 12-month lease.

Only its own ad gives the right ask of 2121710, a studio at 992 Bedford Avenue #1A asking
$21,545 whose description gives $2,150 a month. The ledger takes no set on the ad's words
alone, so the file excludes the row with the reason `tenfold_ask_unbacked` and quotes the
words in the note. Ad 2139816, unit #1 of the building, gives the same description apart from
its price and asked $2,150 the next day, but it is another unit.

Each entry's `when` gives the row's month and its recorded ask. The rows file and the ads file
of the Oct 16 build give each of the five rows its recorded ask, as both its first and its
latest ask.

### Lots taken away

Data improvements read rows of the building check and wrote its decisions to
`config/reviews/drop-lot-20261017.jsonl`. Each line gives an ad, the lot `buildings.lots` gave
its building, a reason and the evidence. `ops/pipeline/drop_lot_import.py` writes a `drop_lot`
entry for each line into `pipeline/ledger/2026-10-17-wrong-lots.ndjson`:

- `when` gives the review's lot, so the entry goes stale once the ad's building takes another
  lot, as a change to the lot step can give it.
- The building check's flag with the lot's record and the PAD lookup of the ad's address
  become `city_record` items. The ad's words become an `ad_text` quote, and the reader's note
  a `read` naming the reader's labels file.
- `source` gives the review file and line. The importer leaves out a line when an entry from
  the same file and line is already in the ledger.

The file holds 1,274 entries:

| reason | entries | the reader found |
|---|--:|---|
| `wrong_building` | 704 | the ad describes a building other than the lot's |
| `city_record_wrong` | 570 | the ad's building stands on the lot, and the lot's record predates it, as for a new building on a lot recorded as vacant |

Both reasons take the lot away alike, as the frontier's `lots3` feature sets do. Those sets
read the review file by listing ID and don't check the lot, so they keep dropping an ad's lot
after its building takes another one, while its ledger entry goes stale.

I built a copy of the relist lane's Oct 17 state with this file. The build took 4 min 36 s,
and the build script peaked at 4,077 MiB. The ledger then gives these statuses:

| reason | live | stale |
|---|--:|--:|
| `wrong_building` | 667 | 37 |
| `city_record_wrong` | 437 | 133 |

For each of the 170 stale entries, the building's address and its footprint give different
lots. The reader saw one of them, and since #1006 `buildings.lots` takes the other, with
apartments in the latest MapPLUTO release. Only 1 of those 170 ads is still on the building
check's list. The list went from 1,434 rows to 339: live entries took 1,095 flagged rows off it,
and the other 9 live entries belong to ads outside the list on this state.

Data improvements then read the 339 rows left. In #1012 its reader judged 152 more lots wrong,
79 as `wrong_building` and 73 as `city_record_wrong`, and listed them in
`config/reviews/drop-lot-20261017-check2.jsonl`. The importer wrote them to
`pipeline/ledger/2026-10-17-wrong-lots2.ndjson`. I rebuilt the same lane copy with both files.
The build took 4 min 32 s, and the build script peaked at 4,141 MiB. All 152 new entries are
live, and 170 entries stay stale. Ad 2555747 had been the only stale ad left on the list after
the first batch. It now has a live entry on its building's new lot and is off the list. The
list went from 339 rows to 187, with 150 flagged `zero_unit_lot` and 37 flagged
`floor_above_lot`. The reader kept each of those rows' lots and sorted them as 90 unclear, 80
mixed use, 12 ad floor errors and 5 vanity floor numbers.

### Check build

I built a copy of the Oct 15 production state with the ledger, at `PIPELINE_MEMORY=3GB` under a
6 GB cap. The first plan took 591 s, 426 s of it in `ads.record_attributes`, and the build
script peaked at 4.1 GiB. After the ledger changed, the next build, at `PIPELINE_MEMORY=2GB`,
rebuilt the two ledger models and `analysis.rows` in 8.6 s, with a peak of 3.1 GiB. The
ledger's 1,083 lines came out as:

| status | excludes | sets |
|---|--:|--:|
| `live` | 857 | 180 |
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

Of the matched rows, 47 differ in bedrooms, 16 in bathrooms and 3 in size:

- In 44 of the bedroom differences and all 16 bath differences, the reference applies a held
  set of `bedrooms-ad-v3`, `bedrooms-ad-v6` or `baths-ad-v3`, and the fit-ready row keeps the
  recorded value.
- The other 3 bedroom differences and the 3 size differences come from six ads listed from July
  to October 2026. For each of them, the page capture and the latest API record give different
  values, and the reference keeps the page's value.

In the reference's neighbourhoods, `analysis.kept` holds another 58,088 rows with no ledger
exclude. They are API ads missing from the page crawl.

## Unit ledger

`ads.identity` gives each ad a unit and a building from its records alone. A reader may find two
unit pages for one apartment, an apartment's ads filed under another unit's page, or a building
StreetEasy lists under two pages. To fix one, the reader writes an entry in the unit ledger,
`pipeline/ledger/units/`, a folder of NDJSON files inside the corrections ledger's folder. Its
files follow the corrections ledger's rules for names, merges and retracts. The docstring of
`pipeline/models/ledger/entries.py` lists the keys of a line and the rules. An entry does one of
these:

- `join_units` gives the ads of two or more unit pages of a building one unit, the least of
  their unit IDs, as the chain's `unit-reviews-v2` does;
- `split_unit` gives some ads of a unit page a unit of their own, with the ID
  `{unit_id}~review-{first listed ad}` from `unit-reviews-v2`. With an `into`, naming an ad of
  an earlier split of the building, the ads take that split's unit instead, as a line of
  `unit-reviews-v4` does;
- `move_building` gives a building's ads the slug and ID of another building and leaves their
  pages and units alone, as `building-joins-v1` does for 97 Horatio Street;
- `split_building` gives some ads of a building, after the moves, a slug of their own, as a
  wing of the building, and leaves their building ID, pages and units alone. Its `labels`, a
  regular expression, pick the ads by the last part of their unit page, in lower case, as
  `west-coast-wings-v1` picks The West Coast's three-digit units;
- `retract` undoes an earlier entry.

A join, split, move or split_building needs evidence of a backing kind, as a set of the
corrections ledger does, or a city record. Among the entries still in force, a page takes part
in one join at most, an ad in one split, and a building in one move and one split_building, so
each ad meets at most one entry of each change. Each split_building gives a slug of its own. A
building with ads moving to it stays where it is. A split points only into a split in force
with no `into` of its own, and a retract of that split waits until the split pointing into it
is retracted.

Three models read the unit ledger:

1. `ledger.unit_entries` reads every file and checks each line, as `ledger.entries` does.
2. `ledger.unit_status` checks each entry against `ads.identity` and `buildings.details` and
   gives it the first status that fits:

   | status | the entry |
   |---|---|
   | `retract` | undoes another |
   | `retracted` | is undone by a later retract |
   | `absent` | joins fewer than two pages with ads that have a unit, splits none of the ads it lists, moves a building with no ads, or splits a building with no ad, after the live moves, on a page its labels match |
   | `stale` | splits an ad with another page or no unit, with the ads in `differs`, splits into a split that isn't live, with `into` in `differs`, moves to a slug matching no building or several, or splits to a slug some building already holds, with `to` in `differs` |
   | `live` | applies |

3. `ads.placed` applies the live entries to `ads.identity`: the joins, then the splits on the
   joined units, the moves, and then the split_buildings on the moved buildings. The ads of a
   split with an `into` then take the unit of the split it points into, from that split's ads
   with a record, since the `into` ad may have none. `placements` lists the entries applied to
   each ad.

`analysis.candidates` and the ads file take each ad's unit and building from `ads.placed`, so
the unit-month check runs on the placed units. Since an entry can change any ad's unit or
building, a change to the unit ledger rebuilds the two unit ledger models and every step from
`ads.placed` on, 23 models in all. The catalog line lists the unit ledger's files by name with
their SHA-256 under `ledger.units`, and counts its entries by status and change.

With no files in the folder, `ads.placed` gives each ad the building and unit of
`ads.identity`. I imported the chain's `unit-reviews-v2` and `building-joins-v1` into
`2026-10-17-unit-reviews.ndjson`, each imported entry with a `source` pointing at its review
line or rule. For each one I looked for backing beyond the ad's own words in the API records, PLUTO and
the lot registry:

- The two joins at 110 West 26th Street rest on Ben's statement of 2026-10-07, as `owner`
  evidence.
- The join of 21 West 12th Street's 2, 2B, 2F and 2R rests on the sizes the ads state, about
  800 sq ft with a 400 sq ft terrace, and on PLUTO's 8 residential units in 4 floors.
- The splits at 1 Patchin Place and 407 West 39th Street rest on the sizes in the split ads'
  records, 1,800 and 2,500 sq ft, against the unit's 900 to 950 and 350.
- The split of 780 Greenwich Street 6H's 2025 ad rests on the 2022 PH6H ads, which describe
  the same apartment as a two-bedroom duplex after a roof addition.
- The move of 97 Horatio Street to The West Coast rests on the lot registry.

I also joined 43 East 20th Street's units 2, 2A and 2S, a full-floor loft of 2,000 sq ft by its
ads' sizes and PLUTO's floor area. I held the split of 249 West 29th Street 3E's ad 2200772. PAD
gives 249 and 251 West 29th Street a single lot and BIN, so the ad's address points at the same
building, and only the ad itself calls the apartment a studio. A floor plan or a stated size
would back it. On the Oct 16 export every entry comes out `live`, and 25 ads change unit or
building.

I then ran the served fit's rules on its rows twice, once as the chain runs them and once after
the ledger's placements. With the chain's rules all kept, the two runs agree on every row's
unit and building but 43 East 20th Street's. Skipping `building-joins-v1` and `unit-reviews-v2`
after the ledger loses the three splits, as well as the held one: the first step of `unit-labels-v17` gives every row of
a building and label the least unit ID among them, and a split's ads keep their page, so their
`~review-` IDs fall back to the unit's. The joins and the move come out as the chain's either
way.

On Oct 17 I imported Data improvements' reviews of 870 Broadway and 444 West 20th Street, lines
8 to 12 of `config/reviews/unit-reviews-20261017c.jsonl`, into `2026-10-17-unit-reviews2.ndjson`.
StreetEasy files 870 Broadway and 30 East 18th Street as one building with unit pages 1 to 4,
and PLUTO gives the lot 4 floors and 6 apartments. Under the 18th Street address, the ads of
pages 1 to 3 offer one-bedrooms of 625 to 720 sq ft. Four ads give 870 Broadway and larger
apartments:

- 4967090, on page 1, gives 875 sq ft and 4 rooms, against 625 and 715 sq ft and 3 rooms for
  the page's other ads. Its ad calls the size an estimate.
- 2157347, on page 2, and 2238992 and 3874322, on page 3, offer a 1,000 sq ft loft with no
  bedroom, with the same description under different headlines. 2238992 came on the market
  16 days after 2157347 came off.

A split of page 1 gives 4967090 a unit of its own. A split of page 3 does the same for 2238992
and 3874322, and a split of page 2 points 2157347 into it, so the three loft ads share
`unit:b0f45b82-0fb5-523e-bc62-64ee2dd5865a~review-2238992`. Each split rests on the stated
sizes and the PLUTO record. 4756550, a one-bedroom of 722 sq ft on page 2, also gives the 870
Broadway address, so the sizes separate the apartments, and the address doesn't. All four ads
have rows, so four rows change unit.

At 444 West 20th Street, a townhouse PLUTO gives 3 apartments, a join puts the garden page and
page 1 in one unit. The garden page's ad 2312228 offered a duplex of 2 bedrooms and 1.5 baths at
$15,750 until 2018-02-08. Four days later, ad 2314583 on page 1 offered the same layout at the
same ask in the same words. The garden page's ad 3215132 of 2020 repeats them and gives 2,750 sq
ft. Both pages take the garden page's unit ID, the lesser, so 2314583's row changes unit.

On Oct 17 I moved the chain's `west-coast-wings-v1` into `2026-10-17-west-coast-wings.ndjson`, as
a split_building of `the-west-coast`. StreetEasy files The West Coast's nine converted warehouses
as one building, and its units carry two numbering schemes: three-digit labels, such as 620 on
the West Street end, and a floor and letter, such as 9L at the corner of Washington and
Gansevoort Streets. The entry rests on Ben's floor plans of those two units and on the Landmarks
Preservation Commission's 2003 Gansevoort Market report. The report gives the West Street and
Horatio warehouses 6 or 7 stories and the Washington Street end 9, and the three-digit labels
run over floors 1 to 7, the others over floors 2 to 10. With `labels` of `\d{3}`, the entry
gives the three-digit units the slug `the-west-coast-west-wing`, and both slugs keep the lot's
building ID.

On the build of Oct 17, 377 of the building's 617 ads and 321 of its 527 rows take the wing's
slug. `analysis.latest_ask` and `analysis.ask_check` compare an ad's asks with others under its
building slug, so they now look within the wing. The chain's `rentfrontier.latest_ask` reads
each dataset before its rules and takes in the whole of The West Coast, as it leaves 97 Horatio
Street apart from it. On the build of Oct 17 the wing changes no row's ask. The other models
join on the building ID. I
wrote two folders for the served dataset's neighbourhoods with `observations.py`, one from a
build of master and one from a build with the entry, and compared them with
`ops/pipeline/port_diff.py`:

- With the chain's `west-coast-wings-v1` applied to master's folder, the two agree on all
  350,202 rows.
- With the fit's other unit rules on both sides as well, `building-joins-v1`, `unit-labels-v17`,
  `unit-reviews-v2` and `unit-splits-v4`, they agree on all 350,202 rows again.

## Relist units

A broker who lists an apartment again often starts a new unit page under another label, and the
lot then shows more unit pages than MapPLUTO gives it apartments. In those lots I look for the
pages of one apartment and give their rows a shared relist unit. The rows keep their unit page
in `unit_id`, and `analysis.rows` adds the relist unit as its last column, `relist_unit`, so a
fit can choose which of the two it reads. Shared photos and relists aren't backing kinds under
the unit ledger's rules, so these joins stay out of the ledger. I build the relist units in four
steps.

1. `ads.photos` lists the photos each ad shows in any of its answers, by the key StreetEasy gives
   each photo. As a merge model, it reads only the new answers in a top-up build.
2. `analysis.relist_pairs` finds the lots over their count, where the unit pages with an ad on
   the market in the 12 months to the build's as-of day outnumber the apartments of the latest
   MapPLUTO release. An ad counts when it went off the market in those months, or when its
   latest answer falls in them while it is still on or gives no day on or off the market. A lot
   with no apartments in MapPLUTO counts once a single page has such an ad, though
   `ops/pipeline/citycheck.py` leaves those lots out. Within each lot over its count, the step
   pairs a kept ad with a kept ad of another unit page when
   - the second ad comes on the market between 3 days before and 7 days after the first goes off,
   - both give the same bedrooms and bathrooms,
   - their listed floors, advertised floors and label floors agree, where both ads give one,
   - the second ad's first or latest ask lies within 3% of the first ad's latest ask, and
   - the two pages share a rare photo.

   A key counts as rare when it appears on 2 or 3 unit pages, all in one lot. A key on more pages
   usually shows the building's lobby, roof or gym.
3. `analysis.relist_links` starts with each unit page as its own relist unit. It sorts the pairs
   by the gap between the two ads, closest first, then by their IDs, so every build gives the same
   units. For each pair it joins the two pages' relist units under the lesser page ID. It leaves
   them apart, and marks the pair, in these cases:
   - `same`: an earlier pair already joined the two pages.
   - `layout`: a page of either relist unit holds a kept ad with a bedroom count other than the
     pair's.
   - `clash`: two pages of the two relist units had ads on the market together for more than 7
     days. The 7 days allow for a broker who posts the new ad before taking the old one down.
4. `analysis.relist_units` lists each unit page in a relist unit of two or more pages.
   `analysis.rows` gives a row on any other page its own unit page as its relist unit.

`ops/pipeline/observations.py` leaves `relist_unit` out of the observations it writes, so the
frontier fits read the same lines as before.

### The layout check

I added the layout check after the first lane build. Without it, the joins chained apartments
together through pages that already mixed them. At 828 St Johns Place in Brooklyn, a broker posted
each new ad under another label on the 4th floor, from 4A to 4T, and a single relist unit took in
14 pages with ads of 1, 2, 3 and 4 bedrooms. Of the 10,584 pages in pairs, 2,885 held kept ads of
more than one bedroom count, and 1,552 of the 3,885 relist units did. Bathroom counts, which the
check doesn't read, differed within 932 of those units, 24%, against 15.5% of the pages alone.
With the check, they differ within 220 of the 2,603 relist units, 8.5%.

### Reading the joins

Sonnet readers judged 50 relist units of the build below from the ads alone. For each unit they
saw every page with up to 4 of its ads nearest the unit's joins, or 3 in units of 4 pages or
more: the layout, size, dates, asks, photo and plan counts, and the start of each description.
They didn't see the photos or the pairs. I drew 20 units of 2 pages, 15 of 3 pages and 15 of 4
or more by a fixed hash of the relist unit.

| pages | relist units | same | different | unclear | same of decided, 95% interval | pages on another apartment |
|---|---:|---:|---:|---:|---|---:|
| 2 | 1,906 | 15 | 1 | 4 | 94%, 72% to 99% | 1 of 40 |
| 3 | 551 | 12 | 1 | 2 | 92%, 67% to 99% | 1 of 45 |
| 4 or more | 146 | 10 | 5 | 0 | 67%, 42% to 85% | 9 of 66 |

When I weight each size by its number of relist units, 92% of the decided units fall on one
apartment, and about 4% of the joined pages fall on another apartment than the rest of their
unit. In the larger units, most misses come from two pages with ads on the market together for a
week or less at different asks, or from a page of another size or bath count. I tried two
stricter rules on the same 50 units:

- A 3-day clash window moves 3 of the 11 odd pages out of their unit, but splits 2 units the
  readers put on one apartment.
- A check of bathrooms beside bedrooms moves none of the odd pages out, and splits 1 such unit.

Neither helps, so I kept the 7-day window and the bedroom check. A fit reading `relist_unit` can
leave out the units of 4 pages or more. `analysis.relist_units.pages` counts their pages, and
the rows file gives a lower count through the distinct `unit_id` of each `relist_unit`, as it
leaves out pages without fit-ready rows. An earlier sample
of 72 pairs, drawn before I limited the step to lots over their count, holds 6 pairs the step now
joins, and the readers put all 6 on one apartment.

### On the build of Oct 17

I built the step on a lane state from ads runs 1 to 16, where 2,126 lots are over their count.

- `analysis.relist_pairs` gives 8,482 pairs of ads in 1,315 of those lots. The median gap is 0 days, and
  in 831 pairs the second ad comes on the market before the first goes off. 6,477 pairs share
  more than one rare photo.
- `analysis.relist_links` joins 3,533 pairs, refuses 3,878 for layout and 403 for a clash, and
  finds 668 already joined.
- The joins give 2,603 relist units of 6,136 pages, 1,906 of them of 2 pages. The largest, of 11
  pages, holds 25 ads of a 1-bedroom with 2 baths at 554 Gates Avenue in Brooklyn. In the fall of
  2023, and again from September 2025 to January 2026, the broker posted it about weekly under
  labels from 4C to 4T while the ask fell, from $3,349 to $3,150 and from $3,350 to $2,975.
- 7,258 of the 1,746,778 fit-ready rows take a relist unit other than their unit page, and the
  rows' 840,571 unit pages fall to 837,039 relist units.
- The lots over their count drop from 2,126 to 1,923, and their unit pages beyond MapPLUTO's
  count from 12,095 to 10,963.

`ads.photos` took 34 s in the full build, for 20,105,782 pairs of ad and key from 2,184,634
answers, and the build took 6.0 min at a peak of 4.0 GiB. After I changed the relist models, the
rebuild took 2.7 min at 4.2 GiB. The relist models took 6.7 s of that, and writing the rows, ads
and records files most of the rest.

### Description text

In the lots over their count, 47,347 pairs of ads pass every test of `analysis.relist_pairs` but
the shared photo. I tested the ads' descriptions as a second signal on the drop-lot lane's state
of Oct 17, with the scripts in `/data1/apartments/tmp/pipeline/lanes/relist-text/`. For each pair
I took the 4-gram Jaccard: the word 4-grams common to both descriptions, divided by the 4-grams
in either. I also counted the rare 4-grams common to both, as the step does for photo keys. A
rare 4-gram appears on 2 or 3 unit pages, all in one lot. As a reference group, I took pairs of
ads on two unit pages of a lot, with the same bedrooms and baths, on the market together for
more than 14 days at asks 3% or more apart. I take those pairs to fall on two apartments. The
rates are shares of the pairs with a description on both ads.

| pairs | count | with text | 4-gram Jaccard of 0.8 or more | 5 or more rare 4-grams in common |
|---|---:|---:|---:|---:|
| in `analysis.relist_pairs` | 8,482 | 7,879 | 72% | 28% |
| without a shared photo | 47,347 | 42,783 | 56% | 6.5% |
| on two apartments | 13,502 | 13,138 | 26% | 3.0% |

Brokers reuse a description across apartments. Of the pairs on two apartments, 3,351 have a
4-gram Jaccard of 0.8 or more. In 3,175 of those, fewer than 5 of the shared 4-grams are rare, so
most of the shared text also appears on 4 or more unit pages, or in other lots. When I count rare
4-grams alone, 28% of the pairs in `analysis.relist_pairs` hold five or more, against 3.0% of the
pairs on two apartments.

Among the pairs without a shared photo, 2,765 hold five or more rare 4-grams. If all 42,783 of
those pairs with text fell on two apartments, I'd expect 3.0% of them, about 1,280, to hold five
or more. That ceiling comes to nearly half of the 2,765, too many to join on.

Readers judged a sample of 60 pairs of unit pages from a prototype of the relist step, in
`/data1/apartments/tmp/pipeline/lanes/laned/read/`, with the first 1,500 characters of each ad's
description in front of them. Of the 20 pairs without a shared photo, they put 12 on one
apartment. In 2 of those 12, I found no pair of ads, one from each page, with a description on
both. In 6 of the other 10, the closest pair of ads has a 4-gram Jaccard of 0.8 or more. None of
the 12 have 5 rare 4-grams in common. The readers may have matched a broker's template, so I
don't count their verdicts as support for joining on text.

In 161 of the pairs without a shared photo, the two pages have the same unit label. In 12 more,
the labels match once I drop case, spaces, punctuation and leading zeros. Together they make up
0.4% of the pairs.

### Photo hashes

When a broker lists an apartment again, the new ad may carry the same photos uploaded again,
each under a new key. I tested perceptual hashes of the images as a second photo test for
`analysis.relist_pairs`, in a pilot on Oct 17 with the scripts in
`/data1/apartments/tmp/pipeline/lanes/photo-hash/`. Ben approved its cost of about $3.30.

1. `sample.py` read the drop-lot lane's state of Oct 17 along with the pairs of the
   [description-text study](#description-text). It counted a photo as usable when its key
   showed on 3 unit pages or fewer. It counted a pair as testable when both ads showed a usable
   photo. Of the 47,347 pairs without a shared photo, 13,063 (28%) were testable. The script
   drew 140 of those at random. It also drew 100 testable pairs from the reference group on two
   apartments, and it took the 60 pairs of the description-text study's reader sample, 42 of
   them testable. For each ad, it kept up to 10 usable photos, in the order of the ad's latest
   record.
2. `fetch.py` fetched each of the 2,917 photos once, from
   `https://photos.zillowstatic.com/fp/<key>-p_e.webp` through the Oxylabs Realtime API. It held
   `crawls/oxylabs.lock` throughout and sent at most 55 requests a minute. Every request returned
   an image. For each photo, the script wrote its SHA-256 and two 64-bit hashes to
   `hashes.jsonl` before dropping the image. The hashes are dhash, from a 9x8 gradient, and
   phash, from the low 8x8 of a 32x32 DCT. The 2,917 requests cost about $3.33 and ran from 1:19
   to 2:13 PM ET.
3. I scored the pairs with `match.py` and counted them with `split.py`. A pair has a hash match
   when one photo from each ad, under two different keys, comes within 4 bits on both phash and
   dhash.

Of the 140 sampled pairs without a shared photo, 52 have a hash match at 4 bits or fewer, 40 of
them at 0 bits. The next closest are 2 pairs at 6 bits.

| pairs | testable | key in common | hash match, no key in common |
|---|---:|---:|---:|
| without a shared photo | 140 | 5 | 52 |
| on two apartments | 100 | 8 | 4 |
| readers' same apartment | 27 | 22 | 2 |
| readers' two apartments | 10 | 7 | 1 |
| readers unsure | 5 | 2 | 0 |

In 5 of the 140 sampled pairs, the two ads do show a key in common. Each of those
keys also shows on a third unit page, in another lot on the same block. `analysis.relist_pairs`
counts a key as rare only when its pages all lie in one lot.

Setting aside the pairs with a key in common, 52 of 135 pairs without a shared photo have a hash
match (38.5%), against 4 of 92 pairs on two apartments (4.3%). With 4 matches in 92 pairs, the
control rate's 95% interval runs from 1.2% to 10.8%. The control pairs came from across the
city, though, and the pilot hashed only photos with a rare key. The [second
pilot](#photo-hashes-over-whole-lots) hashed every photo of every ad on a set of lots, and inside
a lot it found most hash matches on photos of the building itself.

The readers' pairs are too few to judge by. Of their 5 same-apartment pairs without a key in
common, 2 have a hash match. Of their 3 two-apartment pairs without one, 1 has a match. They
judged without the photos, from the ads' fields and descriptions. They also called 7 pairs two
apartments even though the two ads share a key.

In 31 of the 52 matching pairs, the match shows on the first photo of both ads. In 44 it shows
within the first 3. From these rates I put three full runs over the 13,063 testable pairs
(16,491 ads) to Ben: about 37,200 requests at 3 photos per ad ($42), 48,517 with the 6,396
testable pairs on two apartments as controls, or about 85,500 at 10 photos per ad ($97). After
the second pilot I withdrew them. Joining on hashes would also make the pipeline read images
fetched from StreetEasy's photo host as well as API records.

#### Photo hashes over whole lots

Inside a building, the same lobby, roof deck or street view shows up on the ads of many
apartments, often uploaded again under a new key. Ben asked how the photo test would hold up
against such photos, and on Oct 17 he approved about $10 for a second pilot over whole lots.
Its scripts are in `/data1/apartments/tmp/pipeline/lanes/photo-hash-lots/`.

1. `select.py` drew lots at random from the drop-lot lane's state in two strata: lots of 300
   photo keys or fewer, and lots of 301 to 1,200 keys, where the larger buildings with amenity
   photos fall. In each stratum it drew lots until the keys left to fetch came to 3,650. On the
   29 lots it took, it kept all 1,505 placed ads and each ad's first 25 photos, in the order of
   the ad's latest record. It took the lots' pairs from the description-text study and split
   the pairs on two apartments three ways:
   - pairs whose unit labels read the same once cleaned, which may be one apartment on two pages;
   - stacked pairs, with the same line on different floors, as in 4N and 6N;
   - the rest, on different lines.
2. `fetch.py` fetched each photo and floor plan once, skipping those the first pilot had
   hashed, and wrote the hashes as before. It worked in 20-minute turns on `crawls/oxylabs.lock`
   with 90 s pauses between them, at 55 requests a minute. All 7,087 requests (6,886 photos and
   201 floor plans) returned an image. They cost $8.08 and ran from 5:11 to 7:32 PM ET.
3. `score.py` scored each pair on both pilots' hashes. Inside each ad it grouped matching photos
   into images, so a photo uploaded twice counts once. It flagged a matching image as a building
   photo when it showed on more than 3 unit pages, on 2 or more lots, or on both apartments of
   another pair known to differ. It flagged it as a floor plan when it matched a floor plan of
   an ad in the lot. `split.py` splits the scores by lot size and by whether the two ads share a
   key.

The table gives each rule's share of the testable pairs with an exact 95% interval. The 3 pairs
with the same label matched under no rule (0 to 70.8%).

| rule | unjoined (415) | different lines (119) | stacked (29) | sharing a rare key (91) |
|---|---:|---:|---:|---:|
| 1. any matching image | 74.2% (69.7 to 78.4) | 73.9% (65.1 to 81.6) | 55.2% (35.7 to 73.6) | 93.4% (86.2 to 97.5) |
| 2. after dropping building photos | 7.0% (4.7 to 9.9) | 3.4% (0.9 to 8.4) | 6.9% (0.8 to 22.8) | 47.3% (36.7 to 58.0) |
| 3. 2 or more matching images | 62.2% (57.3 to 66.9) | 68.9% (59.8 to 77.1) | 48.3% (29.4 to 67.5) | 84.6% (75.5 to 91.3) |
| 4. after dropping floor plans | as rule 1 | as rule 1 | as rule 1 | as rule 1 |
| 5. rule 3 after dropping building photos | 5.1% (3.2 to 7.6) | 2.5% (0.5 to 7.2) | 0% (0 to 11.9) | 33.0% (23.5 to 43.6) |

No matching image was a floor plan, so rule 4 matches the same pairs as rule 1. In 84 of the 88
matching pairs on different lines, every matching image is a building photo. Without the
building flag, then, a hash match says little more inside a lot than that two ads come from the
same building.

A full run would add joins only for pairs with no key in common:

| pairs with no key in common | pairs | lots | rule 2 | rule 5 |
|---|---:|---:|---:|---:|
| unjoined | 220 | 27 | 11.4% (7.5 to 16.3) | 7.7% (4.6 to 12.1) |
| on two apartments | 62 | 25 | 4.8% (1.0 to 13.5) | 0% (0 to 5.8) |

Lots of either size give about the same rates. The intervals treat pairs as independent, but
pairs in a lot share photos. The 17 unjoined pairs matched by rule 5 come from 7 lots, 6 of them
from a single lot, so the real intervals are wider.

Rule 5 separates the groups best, and it still falls short. It finds a third of the pairs
sharing a rare key, mostly one apartment. At the control group's upper bound of 5.8%, up to
three quarters of its 7.7% on unjoined pairs could be pairs on two apartments. The building
flag also drops images of the apartment itself: in 35 of the 85 matching pairs sharing a rare
key, a matching image also shows on two apartments known to differ, as it would when a broker
uses one unit's photos for another. `analysis.relist_pairs` leaves photo hashes out.

## Label units

StreetEasy sometimes files one apartment under several unit pages of a building, with its label
spelled another way on each: "4-B" and "4B", "ph04" and "ph4", "four" and "4", "C7" and "7C".
The chain joins such pages in the fit with `unit-labels-v17`. I make the same joins from the API
records in two models, and `analysis.rows` adds each row's label unit as `label_unit`.
`ops/pipeline/observations.py` writes the row's piece of its label unit as its `unit_id`, as
described under [History splits](#history-splits), so a fit on the folders leaves the rule out.

1. `analysis.history_pairs` lists the pairs of units an ad's history joins. Each answer carries
   the history of the ad's unit page, and the history lists every ad StreetEasy files under
   that page. When a listed ad lies on another unit in `ads.placed`, the two units likely hold
   one apartment under two spellings of its label, or a broker filed an ad on the wrong page.
   Each pair puts the lesser unit ID first and counts the links behind it.
2. `analysis.label_units` reads the rows of `analysis.ledger_rows` and joins their units in
   seven layers, in the order v17 takes them, each layer starting from the units of the one
   before:
   1. `labels` gives the unit pages of a building whose labels are one label written another
      way ("APT-4B", "4-B", "04B") the least unit ID among them.
   2. `aliases` joins the units of an alias group. I group each building's unit pages in
      `ads.placed` by their label with case, punctuation and the leading zeros of every number
      dropped, a bare floor ("2nd-floor", "fl-2") read as its number, and a leading apt, unit,
      suite or residence word dropped, as `unit-spelling-alias-v2` does. A group of two or more
      pages counts when a pair of `analysis.history_pairs` joins two of them.
   3. `words` joins a unit labelled with a number word ("four", "third-fl") to the building's
      unit labelled with that number.
   4. `history` joins the two units of each pair of `analysis.history_pairs` in one building.
   5. `swapped` joins a unit labelled letter first ("C7") to the building's unit labelled digit
      first ("7C").
   6. `word_letters` joins a unit labelled with a number word and a letter ("fourb") to the
      unit labelled with that number and letter.
   7. `spelled` joins units whose labels are one label spelled out and short ("3RDFL" and "3",
      "PENTHOUSEA" and "PHA").

   Layers 3 to 7 join two units only when the median bedroom counts of their rows agree. A
   joined unit takes the least unit ID among its members. The model lists each page unit joined
   with another, with its label unit, the count of page units with rows in that label unit and
   the first layer to join it.

The model reads the rows after the unit-month check, as the fit applies v17, so a unit-month can
still hold two rows of one label unit. Moving the joins ahead of the check would change the rows
the check keeps, and I'll measure that as a change of its own.

The fit runs v17 before `unit-reviews-v5` splits units, so the model runs the layers on each
row's page unit: the unit of its ad after the unit ledger's joins and before its splits, which
`ads.placed` keeps as `page_unit`. The rows of a split count toward their page unit's bedrooms
there, and `analysis.rows` then leaves them in their split, as no label unit carries a
`~review-` ID. At 870 Broadway, the split of #3 holds an ad of #2's page. The layers count that
ad under #2, so #2 and #3 stay apart, as in the served fit on the chain's rows.
`analysis.history_pairs` reads page units as well, so the ads of a unit and of its own split
form no pair. The first version of the model read each row's unit after the splits. Its first
layer then gave a split's rows their page's unit back, and at 870 Broadway it joined #2 and #3
through the split, as the chain's v17 does on a folder holding the ledger's splits. The unit
ledger holds the joins of `unit-reviews-v5` as well, so the layers run after those joins, while
the fit applies them after v17.

v17 reads its history pairs and alias groups from files built from crawled unit pages, in the
neighbourhoods of the served dataset. I build both from the API records for every building, so
the model also joins units in the other neighbourhoods. On the test fixture, it joins two Park
Slope units the chain's files leave out: "4th-floor" with "4", and "2nd-floor" with "2".

The model works on integer codes for the units, with the least code for the least unit ID, and
reads each distinct label once: 50,183 labels over the 1,746,770 rows. I first wrote it over the
unit IDs as strings, and pandas then took 89 s for the build's step, most of it in a
group-by minimum over strings. The coded model took 13.9 s in the lane's latest build.

### The port's diff

I built the export of Oct 16 in the lane `tmp/pipeline/lanes/labels-port`, from master and
from the branch, and compared their folders with `ops/pipeline/port_diff.py`:

- Master took 16:26 from empty, at a peak of 4.42 GiB. Rebuilding `ads.placed` and the models
  after it on the branch then took 3:06, at 4.05 GiB, with 5.7 s for `ads.placed`, 13.9 s for
  `label_units` and 1.8 s for `history_pairs`. The branch's rows file matches master's row for
  row, apart from its new `label_unit` column.
- All 350,202 rows match by audit ID. With v17 given to master's folder alone, 669 rows change
  unit, a share of 0.191%, 506 of them within NB9. With `building-joins-v1`, `sqft-units-v1`,
  `unit-reviews-v5` and `unit-splits-v4` given to both folders as well, as a fit applies them,
  734 rows change, a share of 0.210%, 525 of them within NB9. Both shares come out under
  `NEGLIGIBLE_SHARE`, so the move needs no refit.
- Of the 734 rows, 599 keep the same rows per unit under another ID. Both sides name a joined
  unit after its least member, but they count different members. The chain counts the units
  with rows and the units of its alias table, while the model counts every unit of
  `ads.placed`, with rows or without. With v17 alone, 175 units differ only in their ID, and
  the chain's ID is the lesser in 97 of them, as at 281 Avenue C.
- The other 135 rows sit in units the two sides group differently, 243 rows in all. The
  model's extra joins hold 227 of them. At 154 8th Avenue and 97 East 7th Street,
  `unit-splits-v4` cuts a unit the model joins in other places than it cuts the chain's
  smaller units. At 870 Broadway, the chain's v17 joins #2 and #3.

The model joins 88 units the chain leaves apart, 39 of them within NB9: 24 in the West Village,
13 in Chelsea and 2 elsewhere. The aliases layer makes 70 of them, the history layer 14 and the
labels layer 4. Nearly all join a floor word with a number, such as "3fl" or "third-fl" with
"3". The chain's alias table follows `unit-spelling-alias-v1` in the West Village, which keeps
floor words apart from numbers, has no Chelsea groups at all, and follows v2 in the other six
neighbourhoods. The model follows v2 in every building.

The chain joins 6 units the model leaves apart, moving 8 rows, and each of those joins
undoes a split of the unit ledger. Its labels layer gives a split's ads back to the unit of
their page, at 1 Patchin Place, 407 West 39th Street, 780 Greenwich Street and 870 Broadway.
`unit-reviews-v5` then splits the first three again, as the fit still applies it. At 870
Broadway, though, the chain's labels layer also joins #2 and #3 through the ad of #2's page in
the split of #3. After the fit's rules, the chain's side files four ads of #3's page with #2's
ad, and the split of #3 keeps only the ad of #2's page, against the review's lines. The model's
side gives each of the three units the ads the review assigns it.

I drew 40 of the 88 joins at random, 30 within NB9 and 10 outside it. Two Sonnet readers read
each pair's ads for bedrooms, size, floor and layout:

| | same apartment | different | unclear |
| --- | ---: | ---: | ---: |
| within NB9 | 14 | 12 | 4 |
| outside | 8 | 2 | 0 |
| all | 22 | 14 | 4 |

At that rate, about 26 of the 88 joins are false, 16 of them within NB9. A history pair doesn't
confirm a floor-word group. At 44 Ninth Avenue, the history of the page "fl2" lists the ad of
the page "2ndfl", although the two ads went up on the same day, a studio and a one-bedroom.
Requiring equal bedroom medians wouldn't separate them either. The words and spelled layers
already join floor-word pairs whose medians agree. The aliases layer's 70 joins fall in 68 label
units, and the bedroom medians of the members disagree in 63 of them, as in 17 of the 22 pairs
read as the same apartment. Modeling and I left the floor-folded groups in every neighbourhood
to a measured change of their own; 4 of the 14 false joins hold two ads on the market at once.

## Label months

The chain checks each unit-month on the unit pages, before `unit-labels-v17` joins pages into
label units. When two pages of an apartment each keep a row in a month, often as the ads of two
brokers, a fit on the chain's datasets counts the apartment twice in that month.
`analysis.label_months` runs the check again on label units, after the corrections ledger, and
lists the rows it drops with their label unit, month and fate. `analysis.rows` and
`analysis.history_splits` leave those rows out, and the ads file gives each one's fate as
`label_fate`.

The model gives each row of `analysis.ledger_rows` the label unit `analysis.rows` gives it: the
unit `analysis.label_units` joins the row's unit into, or else the unit itself. In each month of
each label unit, it then takes the chain's two steps:

1. When the month's rows give two bedroom counts or two bathroom counts, every row of the month
   drops with the fate `conflicting_layout_same_label_month`. A bedroom set of the ledger counts
   here. A bath set leaves `bathrooms` as recorded, so it changes nothing in this step.
2. Otherwise the row with the latest first day stays, and on a tie the one with the greatest ad
   ID compared as text. The other rows drop with the fate `superseded_in_label_month`.

A split of the unit ledger keeps its own unit ID, which no label unit joins, so its rows form
months of their own. In the fixture, the check drops three rows. Ad 2426687 shares June 2018
with ad 2425161, a later ad on another page of the same three-bedroom. Ads 3946929 and 3959881
share September 2022 in a label unit as a two-bedroom and a one-bedroom.

### The check on the export of runs 1 to 16

I built master and the branch on the state of the lane `tmp/pipeline/lanes/records-reuse`, in
the lane `tmp/pipeline/lanes/label-check`. The branch rebuilt `analysis.label_months` and the
models after it in 3:21, at a peak of 4.24 GiB. I wrote an observations folder from each build
and compared them with `ops/pipeline/port_diff.py`. A row changes when the check drops it, or
when a dropped row had started its piece in `analysis.history_splits`, so the row takes another
piece:

| fate | all scraped areas | NB9's neighbourhoods | NB9 |
| --- | ---: | ---: | ---: |
| rows | 1,746,763 | 350,195 | 296,953 |
| `conflicting_layout_same_label_month` | 1,243 (0.071%) | 165 (0.047%) | 143 (0.048%) |
| `superseded_in_label_month` | 9,187 (0.526%) | 1,059 (0.302%) | 873 (0.294%) |
| another piece | 263 (0.015%) | 43 (0.012%) | 34 (0.011%) |
| all changes | 10,693 (0.612%) | 1,267 (0.362%) | 1,050 (0.354%) |

All three shares come out over `NEGLIGIBLE_SHARE` (0.25%), so the check counts as a data change,
and a fit on it needs its own run. The NB9 column counts the rows of NB9's dataset holding the
folder's audit IDs: 291,312 of its rows.

The conflicting rows come from 605 label-months: 381 with two bedroom counts and 780 rows, and
224 with two bathroom counts alone and 463 rows. Sonnet readers read 30 of the 381, drawn at
random, each with every page's ads in the month and up to four other ads per page:

- 18 one apartment with a flex room or a changed layout, such as a "1BR with home office" coded
  once as 1 and once as 2, or an open loft "walls allowed for 2/3 bedrooms";
- 5 one apartment with a miscoded ad, such as ad 2367837, coded as a one-bedroom while its text
  opens "2 Bed / 2 Bath", beside a two-bedroom ad at the same $3,000 ask;
- 6 different apartments under a false join, such as page `5` with a two-bedroom at $2,450 and
  page `5th` with a 350 sq ft studio at $1,895;
- 1 unclear.

With 23 of 30 reads judged one apartment, the check keeps dropping every row of a month with two
layouts, as the chain's check on unit pages does. Keeping both rows would count those apartments
twice. A false join loses both rows of its month, about a fifth of the 780.

The superseded step keeps the ad posted last in its month. Its row carries that ad's latest ask,
the fit's target, and the dropped ads' asks leave with their rows. In 8,347 of the 8,915
label-months with a superseded row, no dropped ad changed its price after the kept ad's last
change. In the other 568, the dropped ad's last change came a median of 11 days later, usually
as a cut: 327 of those asks lie below the kept ask, 110 above it and 131 at it, and the two asks
differ by a median of 2.2%. Across all 9,187 superseded rows, 4,563 ask the same as the kept row.

## History splits

A unit page sometimes collects the ads of apartments of different sizes, after a combination, a
rebuild or a miscoded ad: a one-bedroom at $3,395 and a four-bedroom at $14,999 under one page.
The chain cuts such units in the fit with `unit-splits-v4`, after every other rule.
`analysis.history_splits` makes the same cuts on the pipeline's rows, and `analysis.rows` gives
each row its piece as `split_unit`, which `ops/pipeline/observations.py` writes as the row's
`unit_id`.

The model takes each row's label unit from `analysis.label_units`, or its unit from
`analysis.ledger_rows` where no label unit joins it, after the unit ledger's splits. It walks
each label unit's rows by price date, then by listing ID as a string, as v4 does, and starts a
new piece at an ad whose bedroom count differs from the last ad with a count:

1. An ad with no bedroom count stays in the piece of the ad before it.
2. An ad with a bedroom count the unit has had before goes back to that count's latest piece,
   so a convertible apartment coded 1, 2, 1 keeps its one-bedroom ads together.
3. A change of one bedroom keeps the piece when the last ad with a count gave no size and this
   ad gives one. At 110 West 26th Street, lofts of 1,400 to 1,650 sq ft go out as anything from
   a studio to a three-bedroom, and size-less one-bedroom ads would otherwise split away from
   the lofts' full listings.

The first piece keeps the unit's ID, and later pieces add "~1", "~2" and so on. Each step looks
only at earlier ads, so a row's piece depends on its own ad and the ads before it. The model
walks only the units with two or more bedroom counts, since a unit with one count keeps a single
piece, and it lists the rows of the later pieces with their label unit and piece. The walk runs
in Python over the rows sorted in DuckDB.

### The port's diff

I built the branch in the lane `tmp/pipeline/lanes/splits-port`, on the state of the labels lane.
That lane's last folder, `out/b3`, came from code with master's models, and I compared it with the
branch's folder using `ops/pipeline/port_diff.py`:

- The worktree's ledger path changed with the same files, so the ledger models built again, and
  with them `ads.placed` and every model after it. The build took 3:03, at a peak of 4.06 GiB,
  and `analysis.history_splits` took 1.1 s of it.
- With v4 given to master's folder alone, all 350,202 rows match, 23,248 of them in a later
  piece.
- With `building-joins-v1`, `unit-reviews-v5` and `unit-splits-v4` given to master's folder,
  as a fit on it applies them, 4 rows change unit, all at 249 West 29th Street 3E within NB9.
  I gave `sqft-units-v1` to both folders as well, as in the labels port. It replaces one size
  with another, so it changes no footage hold. The share is 0.0011%, under
  `NEGLIGIBLE_SHARE`, so the move needs no refit.

At 249 West 29th Street 3E, StreetEasy lists two one-bedroom ads of 2015 without a size, a
studio of 2017 at $2,000 without a size or a floor plan, and one-bedroom ads of 2020, 2022 and
2026 stating 900 to 1,000 sq ft. `unit-reviews-v5` splits the studio ad off, and the unit ledger
holds that split back for want of backing. On master's folder, the review's split leaves the
one-bedrooms in a single piece. On the branch's, v4 starts a piece at the studio, and the
footage hold keeps the sized one-bedroom ads after it in that piece, as the studio gave no size.

Across all scraped areas, the rows file of the build puts 130,553 of its 1,746,770 rows in a
later piece: 77,585 pieces of 71,981 units.

## Ads file

The rows file holds the fit-ready rows only. Each build also writes `analysis.ads` to a file
such as `ads-<hash>.parquet` in OUT, with a row for every ad with a record, kept or dropped, and
adds the file's name, SHA-256 and row count to its catalog line under `ads_file`. I wrote it for
these readers:

- the site build, which takes the website's current listings and their days on the market from
  it, as the section [The website's current listings](#the-websites-current-listings) describes;
- Data improvements, which reads a unit's other ads when it looks for the evidence behind a
  correction.

The comment at the top of `pipeline/models/analysis/ads.sql` lists the columns and the step each
comes from. These columns need more than a line:

- `page_price` is the latest record's price, the ask an ad shows on its page now. `first_ask`
  is the ask on the ad's first day, from `ads.exclusions`, and `latest_ask` is the latest ask
  of the ad's kept row, from `analysis.latest_ask`, before the ledger. An ad without a kept row
  has no `latest_ask`. The rows file's `latest_ask` gives the ask after the ledger's ask sets.
- `status` and `days_on_market` are the latest record's own, as the API wrote them.
- `floor_plans` lists the keys of the latest record's floor plan images. Data improvements
  fetches a plan from `https://photos.zillowstatic.com/fp/<key>-p_e.webp`. An empty list means
  the record lists no plans, and a missing one means it has no `media`.
- `last_change`, `break_status`, `break_day` and `back_day` come from `ads.breaks`, which reads
  the six statuses the unit's history lists. The website shows an ad back on the market with the
  status and day of its latest break, from these columns. An ad gets a break only when its
  status and its last change are both ACTIVE. On runs 1 to 10, 6 ads with another status have a
  return as their last change: 3 drafts, 2 ads in review and ad 2101233, which is
  NO_LONGER_AVAILABLE and lists a return two minutes after its ending on 2017-05-30. Rebuilding
  `ads.breaks` and the files for this change took 20 s.
- `regions` lists the export regions of the ad's answers, from `ads.regions`.
- `ledger_entries` lists the ledger's live entries for the ad.
- `ask_check` holds, for a row `analysis.ask_check` lists for review, the median latest ask of
  the other rows of its building with its bedroom count, their number and the row's ratio to the
  median.
- `building_check` holds, for a row `analysis.building_check` lists for review, its reasons, the
  lot and the MapPLUTO release it read, the ad's floor and the lot's floor count, apartments and
  land use.
- `label_fate` gives the fate `analysis.label_months` gives a row it drops, as described under
  [Label months](#label-months).
- `in_rows` says whether the ad has a fit-ready row.

The file leaves out the ad's description and its other text. A reader takes them from the
answer `response_id` in the export, as `ops/pipeline/ads_check.py` does for the histories.

The breaks and the regions are tables of their own. When the view worked them out itself, the
build's sorted copy of the view went past the 3 GB of memory build-latest gives DuckDB.

StreetEasy rewrites an ad's status changes between answers. Answers of Oct 15 listed changes off
the market at 03:11 on Oct 14 and Oct 15 for some ads, and answers of Oct 16 listed the same ads
back on the market without them. The event log keeps every change any answer listed, so
`ads.breaks` reads only the changes of the ad's latest record: the events with that record's fetch
as their `last_seen`. Before I added that filter, the check below found 7 ACTIVE ads with a last
change or break other than the one in their latest record's history.

I check a build's file with

```sh
pipeline/.venv/bin/python ops/pipeline/ads_check.py [--ads FILE]
```

The script checks the file against the histories of the ads' latest records, and its docstring
lists the steps. Until #1127 it also compared the file with the collector's last API captures,
those of Oct 16, and the first two items below come from that comparison. I built runs 1 to 10
from empty in a scratch state at 14:08 ET on Oct 16. The build took 229 s at a 4,199 MiB peak, against 199 s for the same
build without the ads file, with 2.7 s in `ads.breaks`, 1.3 s in `ads.regions` and 14 s writing
both files. The ads file holds 2,140,578 ads in 117 MiB, 7,013 of them ACTIVE. The check took
5 s at a 493 MiB peak:

- Each of the 7,008 ads in the website's five captures of Oct 16 has a row. For 6,997 of them,
  the file's latest record is the captured answer, and the other 11 have a later answer.
- On those 6,997 ads, the status, page price, building, unit page, elevator and doorman type
  agree for every ad, and no field gives two different values. A field can still have a value
  on one side only:
  - In 19 cases the capture has a value and the file has none. The ad's two records disagree,
    so the merge leaves the field unknown and lists it in `conflicts`, while the capture reads
    the latest record alone. They are 13 bedroom counts, 3 bath counts, a size and 2 laundry
    types.
  - In 9 cases the file has a value from the ad's earlier record, and the capture has none
    because the latest record leaves the field out. They are 5 short-term flags, 2 laundry
    types, a size and a furnished flag.

  A reader who needs the latest record's own value for such an ad takes it from the export.
- All 7,013 ACTIVE ads have the same last change and latest break as the history in their latest
  record, and 644 of them are back on the market after a break.

### The website's current listings

The site build (`python -m apartments.site build`) reads
`/data1/apartments/pipeline/datasets/catalog.ndjson` and takes its newest line from a build of a
checkout with no changes (`code.clean`). It passes over a last line without its newline, which
a pipeline build may still be writing. A clean checkout of a branch counts as well, so I build
from a branch into a folder of its own with `--out`. The site build checks the SHA-256 of the
ads file and the rows file against that line before it reads either. A line without both files
stops the build, as a file with another SHA-256 does. `src/apartments/site/captures.py` then
picks the listings on the market:

1. It reads the ads with a unit whose latest answer says ACTIVE and came in the 9 days before
   the build (`CURRENT_DAYS`), and joins each to its fit-ready row by listing id.
2. When two of a unit's ads differ on the ask, the bedrooms, the baths or the size the ads file
   gives, a missing size included, it takes none of them, with a fit-ready row or without. It
   takes none either when the served dataset dropped one of them, since the others repeat the
   values the dataset dropped.
3. Otherwise it leaves out the ads without a fit-ready row and takes the one with the latest
   answer of the others.
4. It leaves out that ad when its layout or ask lies outside the ones the dataset prices, or
   when the dataset prices its unit as current from an answer as new as the ad's or newer.

Step 2 compares the four values alone. A furnished, short-stay or concession copy of an ad with
the same ask and layout has no fit-ready row, so the unit shows the other ad, unless the served
dataset dropped the copy. A listing the served dataset dropped hides its whole unit, whichever
of the dataset's rules dropped it, since step 2 rests on the values the dropped ad shares with
the others. On the files of Oct 16 no unit had both a dropped ad and another ad on the market.

The values come from the fit-ready row, after the corrections ledger, and the ask from
`page_price`, since a row's `asking_rent` follows the chain's latest-ask rule and can be an
earlier price. Each listing's `audit_id` is `api:<response_id>:<listing_id>`, which leads back
to its answer in the export. Under `stats.current_ads` the build's `build.json` gives the two
files with their SHA-256, the number of ads priced, and the reason for each ad on the market it
left out.

`src/apartments/site/ad_dates.py` dates each current listing by its listing id, whether the kit
or the served fit priced it, from the ad's `on_day`, `days_on_market` and break columns. It
dates an ad only when the ad is ACTIVE and its `on_day` falls on or before the New York day of
its latest answer.

On the evening of Oct 16 I built the site twice from the export of Oct 16 and the served fit,
once with this reader and once with the code it replaced, and compared the listings on the
market. The reader showed 1,099 against 1,159, every one of them on the old list too. It left
out 60:

- 57 ads whose answers from the top-ups of Oct 15 and 16 say RENTED (26), IN_CONTRACT (15),
  DELISTED (9), NO_LONGER_AVAILABLE (4) or TEMPORARILY_OFF_MARKET (3). The old reader showed
  them from captures of Oct 10, inside its 9-day window. 30 of them are in the East Village.
- 3 ACTIVE ads without a fit-ready row:
  - 5128314, a four-bedroom at 536 East 5th Street, offers a month free in its record's
    `pricing`. The old reader's rule left out concession ads too, but the capture of Oct 10
    had no concession field.
  - 5183409 at 43 East 20th Street gives 2 bedrooms in its first record and 3 in the two
    records of Oct 16, and the pipeline drops an ad whose records disagree on its layout. The
    old reader showed it as a three-bedroom. Its text describes two bedrooms and a home office in
    2,000 square feet, as do three other ads at the address under units 2 and 2S. One of them,
    5178940, was posted the same day at the same $17,500 and delisted.
  - 5154603 shares its unit and ask with 5164886, a later ad of the month whose row the rows
    keep and whose answer says RENTED on Oct 13.

On the 1,099 listings of both builds the values agreed, apart from these:

- The ledger sets 5163731 at 333 West 56th Street to a studio from its floor plan, so its
  estimate fell from $5,339 to $3,841 against a $3,800 ask.
- 74 listings gained a pet policy from the API record's amenities.
- The 150 other listings without a unit level from the fit draw their unit levels with the
  `audit_id` as seed. The id took its new form, so their estimates moved by at most 0.11%.

Both builds took about 4 minutes at a 7.45 GiB peak RSS and 8.5 GB in their cgroup. Under a
7 GB cap with no swap the build was killed for memory, so the comparison ran under 9 GB.

That comparison ran before the reader compared every ad of a unit on the market and hid a unit
with a dropped ad. I ran both versions of `current_ads` again on the same files, with the skip
sets the build had computed from the served dataset. They choose the same ads but two:
5114623 at 161 Prospect Park West in Brooklyn, whose newer ad without a row gives 4 bedrooms
against 5, and 5182171 at the Towne House, whose newer ad without a row gives no size against
400 square feet. Neither building is in the served fit, so the site's 1,099 listings stay the
same.

## Records file

The frontier builders `latest_ask`, `descriptions`, `listing_extras`, `lister` and
`listing_outcomes` read each API record from the granular export's `listing_observations`, in
the column `raw_listing_json`, beside `collected_at`, `snapshot_id` and `listing_type`. The
granular export takes those rows from the page parser, after the capture rewrite has turned
each record into a page. Both of those go away, so each build also writes a records file, such as
`records-<hash>.parquet`, in OUT. The build adds the file's name, SHA-256 and row count to its
catalog line under `records`, with the count of records the step read under `read`.
`pipeline/steps/records.py` writes the file, and its docstring lists the step's stages and the
file's columns.

The file has a row for each distinct record of each listing, keyed by the listing and the
record's SHA-256, with the times of the record's first and last answers. I chose that over a
row for each answer. `latest_ask` and `listing_outcomes` read the last time an ad was seen, so
each row carries its record's last time as well, and the file still comes out 0.1% smaller. In
the Oct 16 export, the 2,162,320 answers with a record hold 2,159,897 distinct records of
2,140,578 listings. Their file takes 3,399,451,975 bytes, close to the 3.3 GB of
`listing_observations` in the granular export of runs 1 to 5.

To give the builders the same text, the step reads each record the way
`apartments.graphql_listing` reads it:

1. It drops `__typename` keys and writes each float with an integral value as an integer, as
   `normalize` does, so a price of 3050.0 becomes 3050 and one of 3050.5 stays.
2. It serializes the record with sorted keys, no spaces and non-ASCII characters as they are.
3. It gives each row the `listing_type` 'rental'.

The granular export's `collected_at` holds the collector's time for the answer, a float, and
the export keeps that time in microseconds. The step gives the first answer's time in
microseconds divided by a million, so the two times can differ by less than a microsecond. The
collector stores `time.time()` as a float in its archive, and `graphql_export` writes
`round(seconds * 1_000_000)`, so the export no longer has the float, and a builder that writes
the time out, such as `listing_extras`, gives it to the microsecond. The export has no archive
snapshot IDs, so the step gives the first answer's `response_id` in their place, the lower one
when two answers share the first microsecond. In the Oct 16 export no record has two answers at
its first microsecond. The builders used snapshot IDs only to order two rows of a listing with
the same time, and in the granular export of runs 1 to 5 no listing has two records with the
same time.

The step keeps each record it has serialized in Parquet files under `STATE/records/`, so any
build, a top-up or a full one, serializes only the records missing from them. A change to
`steps/records.py` starts a new cache folder, and once the step has written the file, it deletes
the folders of other versions, about 3 GB each on the Oct 16 export. While it runs, the step
holds a lock on `STATE/records/.lock`, and a second records step stops at once, such as a run of
the script beside a build.

The build gives the step the export's version, its SHA-256 over the list of ads files and their
hashes. After writing a file, the step notes it in the cache folder, in `written.ndjson`, with
the version, OUT, and the file's size and modification time. On the next build, if the notes
give a file under the same version for the same OUT, and the file still has its noted size and
modification time, the step returns the noted line without reading the export, and the build
writes `reused: true` in its catalog line. Without the notes, each build of the Oct 17 export
rewrote and hashed the same 3.4 GB file, in about 90 s of a 185 s build after a code change.
New ads files change the version, so after a top-up with new answers the step writes a new file
as before.

### Against the granular export

On Oct 16 I ran the step on its own on that day's export, runs 1 to 11, and compared its file
with `api-granular-20261015-run5-canonical-url-v1`, the granular export of runs 1 to 5. The
builders read that folder for their latest API outputs.

- Each of the granular export's 2,130,435 rows has a row in the records file with the same
  listing and the same `raw_listing_json`. The rows hold 2,113,441 distinct records, as the
  collector wrote the latest ad's record again at its unit's page, with the same time.
- Each row's `collected_at` comes from its record's first answer. It lies within 0.72 µs of
  that answer's time, and 514,547 of the times are equal.
- For each of the granular export's 2,113,431 listings, I took the latest record by time and
  then by snapshot ID, and in the records file of runs 1 to 5, the latest by first answer and
  then by SHA-256. All of them match.
- Runs 1 to 5 give the records file 24,566 more listings. The granular export lists 8,539 of
  them as rentals without a unit page. The other 16,027 have the state `excluded` in its
  frontier, which the collector sets before it writes a page, and 17,364 of their 24,686
  records are drafts.
- Runs 6 to 11 add 21,890 records, 2,593 of them for 2,581 new listings, and they change the
  latest record of 10,094 of the granular export's listings.

The run took 262 s in a scope capped at 5 GiB with swap off, with DuckDB's limit at 5 GB. The
main process peaked at 2,393 MiB resident, and the page cache filled the scope to its cap. On
run 2 alone, 238,532 records, with DuckDB's limit at 3 GB, the step took 35 s and the scope's
anonymous memory peaked at 1,904 MiB.

### Reading it in the builders

The frontier builders read the file through `rentfrontier.api_records`. It takes the newest
complete line of `catalog.ndjson` from a clean checkout, as the site does for the ads and rows
files, and stops when that line lists no records file or no ads file, or when either file's
SHA-256 differs from the line's. `PIPELINE_DATASETS` points it at another folder, such as a build's OUT. It reads the
file a row group at a time and hands each row over under the granular export's column names:

- `listing_id` as text;
- `collected_at` from `last_collected_at`;
- `snapshot_id` from `response_id`;
- `listing_type` and `raw_listing_json` as they are.

It passes over each listing the same line's ads file marks with `no_dated_own_active_event`,
whose own history holds no dated ACTIVE event. The rows leave out those ads for the same reason,
so the builders, the ads file and the rows work from one set of listings. In the ads file of
Oct 16, 22,990 of the records file's 2,140,578 listings carry the mark:

| latest status | listings |
|---|---:|
| DRAFT | 11,238 |
| RENTED | 7,436 |
| DELISTED | 1,958 |
| NO_LONGER_AVAILABLE | 1,924 |
| IN_STREETEASY_REVIEW | 404 |
| IN_BROKERAGE_REVIEW | 26 |
| TEMPORARILY_OFF_MARKET | 4 |

The other 477 drafts and 57 ads under review have an ACTIVE event of their own and stay in.
The rows hold 284 of them. A listing missing from the ads file is skipped too, though the
Oct 16 ads file holds every listing in the records file.

Its `observations` reads whichever crawl a builder names: a granular export's folder, a Parquet
file at a time as the builders read them, or the word `records` for the records file.

A builder takes a listing's last capture as its row with the latest `collected_at`. With each
record's last answer in that column, the builder gets the record the collector fetched last, at
the time of that fetch. In the Oct 16 export, every listing's record with the latest first
answer is also its record with the latest last answer, so only the time moves: the granular
export dated a record seen again in a later run to its first answer.

`latest_ask` reads the file with `--crawl records`, beside `--crawl page` for the page crawls,
and lists the file's name and SHA-256 in its provenance under `records`.

`descriptions` reads the file with `--records` in place of `--granular`. It keeps only the
records of the cohort's listings, so one run covers every region, where the granular export
took a run for each slice. Its provenance names the file under `records`.

From the records, `descriptions` takes each listing's ACTIVE record fetched last, and its
record fetched last when it has no ACTIVE record. StreetEasy can strip or cut an ad's
description once it is rented or delisted, so the last ACTIVE record holds the text of the ad
that asked the rent. When that record has no description, the listing gets no evidence line,
even if another of its records has text. Each evidence line records its choice under
`description_record`, as `last_active` or `latest`, and the provenance counts the rows of each
under `rows_by_description_record`. A run from a granular export keeps the record captured last
and marks every line `latest`.

The pipeline's `ads.attributes` cuts each ad's records at the same point, merging the attributes
over the records up to the last ACTIVE one.

`listing_extras` reads the file with `--crawl records`, and its provenance gives the file's path
and SHA-256 under `sources`, with the ads file of the same catalog line under `ads_file`, since
that file decides which listings the reader keeps. With `--base`, the base file's listings keep
their rows, as they do beside a granular crawl.

`lister` reads the file with `--crawl records`, beside `--crawl page` for the page crawls. The
records lack the building slug of the granular rows, so it takes each listing's building from
the ads file on the same catalog line, after checking that file's SHA-256 too. That slug comes
from the building's latest answer, as `ads.identity` gives it. For the day a listing was first
listed, it reads the rental history in each of the listing's records, where the granular export
read its event mentions, and keeps the earliest ACTIVE event of the listing's own episodes. Its
provenance lists both files under `sources`.

`listing_outcomes` reads the file with `--crawl records`, beside `--crawl page` for the page
crawls, and its provenance gives the file under `records`, with the ads file of the same catalog
line under `records.ads`. A listing still on the market has its days counted to its record's last
fetch, where the granular export stopped them at the record's first answer.

## Datasets for the frontier fits

The frontier fits read the chain's analysis datasets, each a folder holding `observations.jsonl`
with a line for each row. To fit on the pipeline's rows, I write such a folder from a build's
rows file with `ops/pipeline/observations.py`, and the fit reads it with `FRONTIER_DATASET` set
to the folder. `rentfrontier.data.load` reads it with no change to its code. For the newest
build from a clean checkout, in the served dataset's neighbourhoods, I run in a checkout `$T`:

```sh
/data1/apartments/venvs/pipeline/bin/python -I $T/ops/pipeline/observations.py OUT
```

The script's docstring gives its steps and options. It writes both files under a hidden name
beside OUT and renames the folder at the end, and it stops if OUT is already there. Each line
holds the row's values under the chain's names and JSON types:

- `source_listing_id` comes from `listing_id`, `canonical_unit_url` from `page`, and
  `reported_full_bathrooms` and `reported_half_bathrooms` from `full_baths` and `half_baths`.
  `floor_status` and `building_floor_count` go into `floor_label_provenance` as `status` and
  `building_floor_count`.
- `unit_id` comes from the row's `split_unit`: its piece of the unit `analysis.label_units`
  joins the row's unit into, as `analysis.history_splits` cuts it. The script stops on a rows
  file without that column.
- `asking_rent` comes from the row's `latest_ask`, after the ledger's ask sets, so the fit's
  `log_rent` follows the latest ask. A rows file from a build before that column holds only the
  first asks, and the script stops on it.
- `audit_id` repeats the chain's ID for the ad, from the chain's dataset of all scraped areas,
  so rows of the two datasets pair up by ID. An ad missing from that dataset gets `api:` and
  its listing ID.
- `analysis_price_basis` reads `historical_initial_own_advertisement_ask` on every row, and
  `description_interpreted_at` is null, so `has_description` comes out false. No frontier code
  reads `has_description` beyond `_flatten`.

`manifest.json` records the build's files with their SHA-256, its catalog line, the
neighbourhoods with their row counts, the chain's datasets read for audit IDs, and the SHA-256
of `observations.jsonl`. It also lists the ads the served dataset gives another audit ID than
the dataset of all scraped areas, and on the build of Oct 16 there were none.

The rows already carry the corrections ledger and the latest asks, so a fit on such a folder
leaves out the chain's `bedrooms-ad`, `baths-ad`, `sqft-units`, `quarantine`, `fields-review`
and `latest-ask` rules. `fields-review-v3`, the latest of its family, changes nothing, and
`pipeline/ledger/2026-10-17-tenfold-asks.ndjson` holds the tenfold typos of `latest-ask-v8`.
Since the rows read the elevator and pet policy from each ad's text, the fit leaves out
`elevator-from-ad-v1` and `pets-from-ad-v2` as well. The unit ledger splits The West Coast as
`west-coast-wings-v1` does, so the fit leaves that rule out too. The observations take each
row's piece of its label unit as its `unit_id`, so the fit leaves out `unit-labels-v17` and
`unit-splits-v4` as well. It leaves out `unit-reviews-v5` too, as the unit ledger holds each of
its lines but the held split of 249 West 29th Street, and `building-joins-v1`, which changes
nothing on the folder since the rows already carry its move.

The served dataset files West Chelsea's ads under Chelsea, while the rows file gives West
Chelsea a neighbourhood of its own. The default neighbourhoods come from the served dataset, so
a folder written with them leaves out West Chelsea's 14,272 rows on the build of Oct 16. To keep
them, I add West Chelsea to `--neighbourhoods`. A fit compared with the served fit needs the same
neighbourhood levels, so for it I pass `--rename "West Chelsea=Chelsea"` instead. The script adds
West Chelsea to the neighbourhoods itself, and the folder gives those rows the served dataset's
name. The manifest lists each rename with the rows it moved.

### Against the served dataset

With `--check-against DATASET`, the script compares a folder with a chain dataset field by
field, and its docstring lists the causes it assigns. On Oct 16, I wrote a folder from the build
of 23:02 ET. That build came before the `latest_ask` column, so I added the column to a copy of
its rows file, from the ads file's latest asks and the ledger's ask sets. None of the ask sets
falls in the served dataset's neighbourhoods. I compared the folder with the served dataset
under `latest-ask-v8`, taking the API chain's dataset of the same areas as the reference for
the values of API records:

```sh
F=/data1/apartments/frontier/datasets
/home/ben/code/apartments/.venv/bin/python -I $T/ops/pipeline/observations.py OUT \
    --check-against $F/chelsea-wv-gv-flatiron-gramercy-stuy-nomad-ev-mw-analysis-20261014-cd891c8 \
    --api-reference $F/api-manhattan-page-crawl-areas-analysis-20261015-run5
```

Writing the folder took 48 s at a 1.1 GiB peak. The check peaked at 3.9 GiB, so I run it in a
scope capped at 5 GiB with swap off, once at least 6 GiB is available. It took 71 s there. The
folder holds 335,886 rows, the served dataset holds 296,718 rows priced at the first ask, and
277,633 ads have a row in both. Every difference on those ads has a cause, by the check's field
names:

| field | rows | cause |
|---|--:|---|
| `bedrooms` | 136 | 133 ledger sets, 3 item 7 |
| `full_baths` | 16 | ledger sets |
| `half_baths` | 10 | 9 ledger sets, 1 item 7 |
| `square_feet` | 11 | 10 ledger sets, 1 item 7 |
| `asking_rent` | 47 | 25 item 11, 22 item 9 |
| `pets` | 3,126 | 3,107 item 10, 19 item 7 |
| `floor_status` | 4,575 | item 7 |
| `label_derived_floor` | 4,271 | item 7 |
| `listed_floor` | 671 | item 7 |
| `advertised_floor` | 41 | item 7 |
| `has_description` | 7,900 | item 7 |
| `doorman` | 1,258 | item 7 |
| `laundry` | 609 | item 7 |
| `elevator` | 21 | item 7 |
| `hvac` | 5 | item 7 |
| views and windows | 24 | item 7 |
| `price_at` | 9 | item 7 |
| `period` | 2 | item 7 |
| `unit_id` and `canonical_unit_url` | 1 each | item 7 |
| `first_ask` | 8 | item 7 |

The table comes from a check before the history splits. The check now gives `unit-splits-v4`
to the served dataset's own bedroom counts, so where the ledger sets another count, the two
sides can cut a unit in different places, and the `unit_id` differences follow the `bedrooms`
row.

The items are those of [Differences from the chain](#differences-from-the-chain). For item 7,
the API chain's dataset gives the folder's value. `audit_id`, `building`, `bathrooms`,
`neighbourhood`, `building_floor_count`, `physical_floor` and `floors_above_ground` match on
every ad. The rows of one side alone:

| side | cause | rows |
|---|---|--:|
| folder | the chain's row for the ad lies outside the served dataset | 58,023 |
| folder | the chain has no row for the ad | 230 |
| served | the ad lies in West Chelsea | 13,691 |
| served | the ad has no API record | 4,550 |
| served | a ledger exclude | 742 |
| served | the row prices the ad's current page | 235 |
| served | `superseded_in_unit_month` | 75 |
| served | `conflicting_layout_same_unit_month` | 14 |
| served | excluded as a concession | 12 |
| served | excluded as furnished | 1 |

The folder is `/data1/apartments/tmp/pipeline/lanes/loader/out/nb9-pipeline-rows-beb8748d`, and
the SHA-256 of its `observations.jsonl` starts `77b07cbe02a3b790`. With West Chelsea added, the
folder beside it, `nb9-west-chelsea-pipeline-rows-beb8748d`, holds 350,158 rows.

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
   ledger leaves out a set until it has evidence beyond the ad's words. The 71 sets of the
   chain's latest rules held this way are in `config/reviews/ledger-held-2026-10-16-chain.jsonl`,
   and their rows keep the recorded value.
7. The values of an ad's captured page. The page-crawl chain takes an ad's values from the page
   it captured, and the pipeline takes them from the ad's latest API record. For six ads of the
   nine-area reference, listed from July to October 2026, the two give different bedroom counts
   or sizes. Against the served dataset, the API chain's dataset of the same areas gives the
   pipeline's value for each difference of a floor, amenity, view, window, date, unit or
   description field, as listed under [Against the served dataset](#against-the-served-dataset).
8. The step at which units and buildings change. The chain's `building-joins-v1` and
   `unit-reviews-v2` change the units and buildings of the dataset's rows, after the unit-month
   check, so a join can leave a unit two rows in a month. `ads.placed` applies the unit ledger
   before the check, which then keeps one row of the joined unit's month, or none when its ads
   give two layouts. `building-joins-v1` changes only a row's `building`, while a move also
   gives the ads the other building's ID.
9. An ask from an API record newer than the chain's. The chain's latest asks read the export up
   to run 5, fetched by 4:52 pm ET on Oct 15, and `analysis.latest_ask` reads every run. On the
   build of Oct 16, 22 rows in the served dataset's neighbourhoods take a later price from runs
   10 and 11. The check counts a row here only if the ad's latest record came after run 5, its
   price differs from the last price up to run 5, and the folder's ask equals it.
10. The elevator and pet policy read from an ad's text. As described under
    [Attributes and exclusions](#attributes-and-exclusions), `ads.attributes` fills these
    fields from the descriptions of every ad's API records. The chain's rules
    `elevator-from-ad-v1` and `pets-from-ad-v2` fill the NB9 rows alone, from the descriptions
    of page crawls, and its analysis datasets leave the fields unknown. `--check-against` gives
    the served dataset the rules' fills before it compares. In the check of Oct 16, before the
    port, 3,107 rows in the served dataset's neighbourhoods differed by a pet fee read as pets
    allowed. In the check of Oct 17, on the branch's folder of the NB9 neighbourhoods, a single
    elevator differed this way. The API chain's dataset gave the folder's value for the other
    24 elevators and all 25 pet policies apart from the served dataset.
11. The latest ask of an ad the chain also prices at its current page. The chain gives such an
    ad a second row, priced at the page under an ID starting `capture:refresh:`, and the latest
    ask of its first-ask row ends at the price on that page. The rows file gives each ad a
    single row, and its latest ask counts every later change. In the served dataset, 25 rows
    differ this way. The check counts a row here only if the served row's ask equals the price
    of the ad's page row.
12. A second unit-month check, on label units. The chain checks unit-months on the unit pages
    alone, and `unit-labels-v17` can then leave a label unit two rows in a month.
    `analysis.label_months` checks each label unit's months after the ledger and drops rows as
    described under [Label months](#label-months). No chain rule makes this check, so a
    comparison with the chain's datasets counts each row of `analysis.label_months` here.

## Planted errors

To learn which errors in StreetEasy's answers stop at a check and which pass into the rows, I
plant errors of known kinds in a copy of an export and build both copies with
`ops/pipeline/plant.py`. Its docstring gives the steps. The script writes each error as
StreetEasy could give it:

- in a later answer, an hour after the ad's latest one, for a price change to ten times or a
  tenth of the page price (`ask_x10_latest`, `ask_div10_latest`), another bedroom count
  (`beds_flip_latest`) or an ACTIVE event in the ad's own history 30 days after the fetch
  (`future_active`). I date the price change halfway from the ad's last change to its
  off-market day, or to the fetch for an ad still on the market, so `ads.kept_changes` takes
  it as a change made while the ad was on the market. When the last change came on or after
  the off-market day, I date it a minute after that change;
- in every record of the ad, for prices at ten or a hundred times (`ask_x10_all`,
  `ask_x100_all`) and another bedroom count (`beds_flip_all`). Every other ad's history gives
  the ad's events at the same prices.

On Oct 16 I planted 50 errors of each kind in a 3% sample of runs 1 to 10, 65,283 ads, which
`ops/pipeline/sample.py --share 0.03` wrote to
`/data1/apartments/tmp/pipeline/evmem/plant/sample/export`. Each planted ad had a fit-ready
row, a page price, a latest ask, 0 to 4 bedrooms and no ledger entry. From an empty state the
clean build took 96 s and the planted build 77 s, at 1500MB for DuckDB and two workers. After
a change to the planted export, rebuilding the planted copy from its state took 20 s.

| kind | result |
|---|---|
| `ask_x10_latest` | 47 take their first ask in `analysis.latest_ask`, and 27 of those first asks equal the clean latest ask; 3 keep the clean latest ask |
| `ask_div10_latest` | 46 take their first ask, and 35 of those equal the clean latest ask; 4 keep the clean latest ask |
| `beds_flip_latest` | all 50 dropped for a layout conflict within the ad |
| `future_active` | all 50 dropped for the future event |
| `ask_x100_all` | all 50 dropped for an initial ask over $50,000 |
| `ask_x10_all` | **43 pass into the rows at ten times the ask**, and the ask check lists 41 of them for review; 7 dropped for an initial ask over $50,000 |
| `beds_flip_all` | **49 pass into the rows with the other bedroom count**, and one dropped for a layout conflict in its unit's month |

None of the 100 planted price changes passes into the rows. For the 7 ads keeping their clean
latest ask, the last change came on or after the off-market day, so the script dated the
planted change a minute after it, and `ads.kept_changes` dropped it as a late placeholder.
In 92 of the 93 ads taking their first ask, `analysis.latest_ask` takes it as nearer the
building's median. The other ad has no row sharing its building and bedroom count, and the
step takes its first ask by default. Either way it drops the ad's earlier changes along with
the typo. In the 31 ads where the first ask differs from the clean latest ask, it differs by a
median of 4.8%, and lies between 0.55 and 1.22 times the clean ask.

Five ads without an error gained a row in the planted build. A planted ad had superseded each
of them in its unit's month, and the planted build drops that ad.

An error in every record of an ad leaves the build nothing to compare within the ad, so 43 of the
tenfold asks in every record pass into the rows. The ask check compares each row's latest ask with
its building's other rows, as described under [Ask check](#ask-check), and lists 41 of the 43 for
review. The other 2 ads have fewer than three other rows with their building and bedroom count in
the sample. A listed row keeps its ask until a ledger entry sets it or excludes the row.

A bedroom count in every record still passes. It needs a size, a floor plan or the unit's other
ads. On the production rows of Oct 16, 36,273 kept rows give a count none of their unit's other
ads give, where at least two other ads agree on another count. Many of those are real changes or
ads of another unit, so a count against the unit can't stand as a check alone. I then flagged a
row only when two sources agreed on another count. For the sources I took the unit's other ads,
other units of the same line and other units of the building within 5% of the row's size. Each
pairing caught 12 to 19 of the 49 planted counts and flagged hundreds of rows without a planted
error.

On the production rows, two sources agree on another count for 14,933 rows. A Sonnet subagent
read 30 of them, drawn at random, with each ad's description, the unit's other ads and the
matching units:

| the row | rows |
|---|--:|
| a flex layout, or an ad unclear about its count | 14 |
| a wrong count | 6 |
| a real change to the unit | 4 |
| the right count | 4 |
| an ad of another unit | 2 |

A rule dropping the flagged rows would drop about four other rows for each wrong count, so I
added no bedroom check. A wrong count goes into the ledger with its evidence, row by row.

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
   earlier one, and a placeholder price after the ad left the market. A last ad corrects a
   tenfold typo on the day it left the market, and both give it the page price;
3. build runs 2 and 3, then add run 4's files to the manifest. The next plan rebuilds `raw.ads`
   and the 44 models below it and gives the full answer, and a further plan finds nothing to
   build. They include `buildings.lots`, which reads the days the ads came on the market, and
   `buildings.lot_releases` below it: about 12 s on the full export. A top-up also brings new
   building records, which rebuild both anyway. `ads.record_attributes` parses only run 4's new
   records;
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
    both. Another ad carries a feature code for furnished. Three ads cover the cut at an ad's
    last ACTIVE answer: a RENTED record after the ACTIVE one, a record off the market between
    two ACTIVE ones, and two DELISTED records with no ACTIVE one. The last ad's DELISTED record
    states a concession and two bedrooms after its ACTIVE record. The test checks each ad's
    reasons, first ask, bedroom count, conflicts and number of records by value;
12. build run 2 in a copy of the project, then change the copy's `steps/attributes.py` to give
    every record 9 bedrooms. A plan in the test's process stops with the mismatch error, since
    the venv loads the repo's own code. A plan in a new process, with the copy first on
    `PYTHONPATH`, parses the same records into a second cache folder, each with 9 bedrooms;
13. import `steps.attributes` in a fresh process and compare the modules it loads from `src`
    with the files of the code version;
14. add made-up ads to the cases: an ad put in contract, back on the market twice in a day and
    rented, an ad paused and back on the market, an ad delisted from a draft, an ad without
    status changes, an ad with two answers, the later of which ends it, and an ad whose record
    lists two pairs of changes at shared instants in an order other than the alphabet's. Another
    ad has two answers, and the later one leaves out the earlier one's ending, so the ad stays
    on the market. One ad's latest answer has no record, and another's latest record has no
    `daysOnMarket`. The test checks each ad's days, spans, ending and record fields by value;
15. add made-up ads and buildings to the cases: two ads of one unit, an ad giving two pages and
    an ad giving the second of them, ads with an empty unit slug, none or one holding a `/`, an
    ad naming a building missing from the export, an ad in a building whose later answer renames
    it, an ad whose latest answer is missing, a building slug holding a `|`, and an ad whose
    latest record names no building. The test computes each ad's page and unit with the chain's
    `unit_page` and `memberships` and compares them with `ads.identity`, then checks the cases
    by value;
16. build every ads file but only the buildings files of runs 2 and 3, then add run 4's buildings
    file. The next plan rebuilds only `raw.buildings`, `buildings.details`, the four building
    identity models, `buildings.lot_releases`, `analysis.lot_facts`, `analysis.lot_landmarks`,
    `analysis.building_certificates`, `ads.identity`, `ads.placed`, `ledger.unit_status`,
    `analysis.candidates`, `analysis.kept`, the latest asks, `ledger.status`, `analysis.rows`,
    `analysis.ask_check` and `analysis.ads`, and the 49 ads of the building in that file gain
    their pages;
17. build the fixture and compare `analysis.rows` with `fixture/chain-rows.parquet`, which
    `make_fixture.py` copies from the chain's analysis datasets that the latest-ask run's
    provenance lists. `analysis.label_months` drops 3 of the 229 rows, the ads of
    `LABEL_MONTH_DROPS` in `test_pipeline.py`, and each of the other 226 agrees in every value
    the pipeline rebuilds;
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
20. run `ops/pipeline/build.py` on the fixture twice and check the names of the rows file, the
    ads file and the records file and the export files' and city files' hashes against their
    SHA-256. The ads file holds each ad once, and its ads with `in_rows` are the rows file's
    ads. The records file holds each of the 229 records once, sorted by listing. The second
    build rebuilds nothing, reads no record, writes the same rows and ads files, returns the
    noted records file and appends a second catalog line. Last, the test adds an export file
    repeating an answer and checks that the build stops and leaves OUT as it was. Item 74
    describes the test of a top-up build;
21. parse a line breaking each of the ledger's rules, the details each evidence kind needs
    among them, an ask set of 0, an ask set without its recorded ask and an ask set backed only
    by a stated size and units of the same line. Then read files with a repeated line, a retract
    of an unknown, a retracted or a retracting entry, and a line that is not JSON, and check
    that `read` takes files in order of name;
22. write ledger entries for ten kept rows of the fixture and an ad without one, retract two of
    them in a later file, and check each entry's status and differing values. Among them, an
    exclude made on a row's latest ask applies, and one made on ten times the latest ask goes
    stale. The next plan rebuilds only the two ledger models, `analysis.ask_check`,
    `analysis.lot_facts`, `analysis.building_check`, `analysis.label_units`,
    `analysis.label_months`, `analysis.history_splits` and the views `analysis.ledger_rows`,
    `analysis.rows` and `analysis.ads`. `analysis.rows` drops two rows, beside the three rows of
    `analysis.label_months`, and changes four. Each row's `latest_ask` equals its ask in
    `analysis.latest_ask`, and the latest asks stay as they were;
23. write a set backed only by the ad's words. The plan stops at `ledger.entries`, naming the
    file and line;
24. read the repo's corrections ledger and unit ledger, and check that each of their files at
    the merge base with master stays as it was and that each new file sorts after master's files
    in its folder;
25. run `ops/pipeline/diff.py` on a copy of the checkout with a narrower size bound in
    `analysis.candidates`, a new column in `analysis.latest_ask` and a new model. The test checks
    the changed rows of `analysis.candidates`, `analysis.kept` and `analysis.rows` against the
    base's sizes above the bound. Without those sizes, `analysis.history_splits` holds fewer ads
    in their piece, and the test checks that the rows it moves take another piece in
    `analysis.rows`. It finds the new column and the new model, and finds no other model
    changed. A second copy drops the price events of
    `ads.history_events`, a model without a grain, and the test checks the count of rows only in the
    base. A third copy drops sizes in `pipeline/steps/attributes.py` and spaces the JSON of
    `canonical` in `src`, and the test finds both changes in `ads.record_attributes`. In a fourth
    copy, `analysis.rows` repeats a row. Its audit then fails, and the script exits with status 1.
    Then the test checks that a side's process imports `steps` from that side alone, and that
    `archive` writes `pipeline/` and `src/` at HEAD. Last, it compares small tables directly:
    retyped grain and value columns, a repeated grain, a changed grain, columns named like the
    join's markers, and tables with no column in common.
26. write a sample of the fixture's export with a share of one half. The fixture has none of
    the following cases, so the test first adds a run with them to a copy of the export:
    - a later record of a picked ad, with a building outside the picked ones;
    - `missing` answers, for an ad outside the sample and for an ad without any record;
    - an answer for a picked building, with no ad giving it.

    It checks the sample against the same rules worked out in Python, along with the records'
    bytes and each manifest line's SHA-256. A second run writes the same manifest and leaves
    only the export folder. Last, the script refuses an output folder over the export, and its
    manifest reader reads a repeated line once and stops at a path with two hashes.
27. fetch city records from a local server, in place of City Planning's and NYC Open Data's.
    The server holds three PAD quarters with a gap between them, two MapPLUTO releases from a
    short release table along with a later one, and the rows of a dataset. The test checks each
    file's manifest line: its date, the source of that date, its size and its SHA-256. It checks
    the gzip header of the copy of rows for an empty file name and a time of 0. A second run asks
    only for the absent names and the dataset's time. When the server adds a quarter and moves
    the rows' time, the next run takes the quarter and a new copy of the rows, with the same
    bytes as the first copy. The test also checks that a run
    - drops a copy when the rows change during its download;
    - downloads a file again after a dropped connection or a short download, and lists the
      whole copy;
    - lists no file after five short downloads, nor a page sent in place of a zip;
    - goes on after a file fails five times, and that the next run takes that file;
    - goes on with the other sources when a dataset's `rowsUpdatedAt` fails;
    - deletes a `.part` file, cuts a manifest line with no newline, and downloads an unlisted
      file again over the old one;
    - exits when another run holds the lock.

    Then it checks that PAD's quarters go on from 24d to 25a, that `--verify` finds a changed
    file and a missing one, and that `ops/pipeline/pluto_releases.csv` matches frontier's
    `PLUTO_RELEASES`.
28. unpack the city fixture and read each member a table takes with Python's `csv` module. Each
    row with as many values as the header matches a Parquet row, in order, and each other row
    has a line in `city.rejects`. Each line of a street name dictionary matches a row's `line`.
    Then the test checks the fixture's forms: the PAD tables come from the zip's root in 24c and
    26c, each MapPLUTO release holds lots, and the Queens table of 13v1 has a row refused for
    missing values. With small archives of its own, it checks
    - the order of the columns and the added values;
    - a dictionary's records kept whole, with their quotes, commas and trailing spaces, a blank
      line read as a null, and a record holding the byte 0x01 refused;
    - a member read as Latin-1;
    - a refused row's line, reason and text, and the `record` of the rows after it;
    - a second unpack writing nothing, and a new manifest line unpacking only its file;
    - new folders for a new version of the code, with the same rows;
    - a stopped unpack, whose `.part` folder the next unpack replaces;
    - a manifest line with no newline, whose file the unpack leaves out;
    - a source no table takes;
    - the sweep, which deletes a week-old folder and keeps a recent one and one a load holds;
    - a sweep after another sweep has moved a folder and a load has made a new one in its
      place, which keeps the new folder.
29. build the fixture with an archive lacking the landmarks file, and check that
    `city.landmarks` holds the added columns and no rows. With the file back in the manifest,
    the next plan rebuilds `city.landmarks`, `city.rejects` and `analysis.lot_landmarks` alone,
    from a new folder holding the landmarks' Parquet file and the rejects.
30. render `city.pad_streets` over the fixture and read 26c's 276 names, none of type S, with
    the fields of BROADWAY's record. The 20-character name is blank in every record of 26c.
31. parse the text of each Python value a model reads, and find no set and no text Python can't
    parse. Then load the project in two processes at once, with hash seeds 1 and 2 and a state
    each, and compare each model's fingerprint.
32. add made-up buildings to the cases, each with a record of its own, and check the lot, BIN,
    link, rank and footprint test `buildings.lots` gives each one:
    - an address written with `W.` and `St.`, and by the street's other name in PAD's
      dictionary;
    - an address and a map point on neighbouring lots, once with the facts of each lot and once
      with facts fitting both;
    - a map point far from any footprint, and one in the street 4 m from a footprint;
    - a record without a house number, and one with neither a house number nor a map point;
    - a lot whose PAD range gives the BIN 3000000 while its footprint gives a numbered one;
    - Broadway addresses with an attached letter, a letter after a space and no letter,
      against the ranges 2441-2449 and 2449A, and a hyphenated address on a condominium's
      range, which gives the billing lot;
    - a Brooklyn address with a letter and no community district.
33. write made-up records of five lots in five releases to `city.pluto` as text, one release
    without a published date, and made-up ads to `analysis.candidates`, then render
    `city.pluto_releases`, `buildings.lot_releases` and `analysis.lot_facts` in a DuckDB
    session set to New York time. Two pairs of ads fall the day before and the day the first
    two releases become usable, and two others come after the undated release and after the
    latest one. One lot is missing from the first release, and another's building postdates
    it. A later release writes a year as 1900.00 and leaves a lot's `irrlotcode` blank, which
    stays blank for the ad reading it. A third lot's building dates from the year of a release
    published on Jan 1 at midnight UTC, which is Dec 31 in New York. The first release leaves
    out the flood zone flags, and a later release carries `firm07_flag` only for a lot without
    a building. The first release also writes a lot number with decimals, a land use code with
    a leading zero, a ratio with a space and a trailing zero, and `irrlotcode` in lower case.
    The test checks each release's dates and flags, the cast facts of a lot, the lots
    `buildings.lot_releases` keeps, and each ad's release, fallback, fields from the latest
    release, year built, floor count and flood zone flags, with ads without a lot or without a
    building in `buildings.lots`;
34. write a record with a floor count that isn't a number, then one with a fractional year
    built, then one with an `irrlotcode` other than Y or N, and check that each stops
    `buildings.lot_releases` with an error giving the value, the lot and the release;
35. write made-up LPC designations, lots and ads to a DuckDB database, render
    `analysis.lot_landmarks` over them, and check each ad's flags, dates and LP numbers. The
    ads come the day before and the day of a lot's landmark and district designations, and
    after both. One lot has two landmarks designated the same day, a designation in an older
    copy and dates padded with spaces, and another has a designation with a status other than
    DESIGNATED. Further ads read a lot without designations, a building without a lot, a
    building missing from `buildings.lots`, a lot with only a scenic landmark and a lot with
    only an interior landmark. A type outside the four, a blank date, a date written as
    `1989-07-11` and a two-digit year each stop the step, and with no copy in the archive an ad
    with a lot reads both flags as missing.
36. write made-up certificates of both sets, lots and ads to a DuckDB database, render
    `analysis.building_certificates` over them in a session set to New York time, and check each
    ad's flags, dates, jobs and count of apartments. The ads come the day before and the day of
    a building's first certificate, and after two alterations, one with a certificate in each
    set on the same day. The certificates include a second new building job, a date of 2105, a
    DOB NOW renewal of an earlier job, a job found only in an older copy, padded values, counts
    of 0 and counts too large for an INTEGER in both sets, a count reading `NON5`, a rebuild
    with existing elements to remain whose count reads `..208`, and a DOB NOW certificate with a
    blank issue date. Further ads read a BIN without certificates, a building without a BIN, a
    building missing from `buildings.lots` and buildings with BINs 1000000 and 3000000. A job
    type outside the two kinds, a blank issue date in the earlier set and a date in another form
    in either set each stop the step, and with no copy of either set an ad with a BIN reads both
    flags as missing and keeps the other set's certificates.
37. add seven made-up ads to the cases and check their rows of `analysis.ads`. The first goes
    off the market and comes back, and its record has two floor plans. The second goes from a
    draft through StreetEasy's review to ACTIVE, and later through a brokerage review, which
    `ads.breaks` doesn't count as a break. The third goes into contract, comes back and rents,
    so it has no break. The fourth had its break before its first day on the market, and the
    fifth goes into contract and comes back at the same instant, in that order in its record.
    The last two have an earlier answer listing changes their later answer leaves out: the
    sixth's lists two more changes off the market after it rents, and the seventh's ends it.
    The row takes the break and the last change from the later answer. Then the test checks
    that each ad with a record has one row;
38. write an export file again under its old manifest line with another compression, and put
    back its modification time. The next load stops at the file;
39. add an answer giving a record with another record's hash, and in a second run with the hash
    of no record. The next load stops at the answer;
40. run `check_files` on two made-up export files. A second check hashes neither. The same
    bytes written back with the old modification time get a file hashed again, and it passes.
    A new hash in the manifest fails a file, and the next check hashes only that file again. A
    second table listing the file with another hash stops the check. A record differing from
    its answer's hash fails its file on each check, as does an answer with no record and no
    hash. After the record of the checks is cut short, the next check hashes every file again.
41. plant two errors of each kind in the fixture export with `ops/pipeline/plant.py`, building
    both copies in the test's process. The planted export passes the config's checks, the
    tenfold asks and tenths of the later answers pass `ads.kept_changes`, and
    `analysis.latest_ask` takes the ads' first asks, nearer the building's median, equal to
    their clean latest asks. The bedroom counts of the later answers, the future events and
    the hundredfold asks drop their ads. The tenfold asks and the bedroom counts in every
    record pass into the rows, and `analysis.ask_check` lists the tenfold asks for review;
42. add made-up ads of a building to the cases, with asks at ten times, a little over five
    times and a tenth of the median of the building's other rows with the same bedroom count,
    and two studios at 20 and 13 times the median of the other studios. A ledger set makes the
    second studio a three-bedroom, at 2.2 times the median of the three-bedrooms.
    `analysis.ask_check` lists the ads at ten times and a tenth for review, and `analysis.ads`
    gives them their median, the count of other rows and the ratio. The check passes over the ad
    at a little over five times, an ad at ten times with only two other rows and both studios.
    Every ad of the building keeps its row. Then a second ledger file gives the ad at ten times
    an ask set made on its recorded ask, and the ad at a tenth an ask set made on another ask.
    The next plan rebuilds the same models as in item 22. The first set applies: the row's
    `latest_ask` takes the set's ask, its `asking_rent` and its ask in the ads file stay as
    recorded, and the check stops listing it. The second goes stale, and its row keeps its ask
    and its place on the list;
43. parse a unit ledger line breaking each of its rules, and read files with a repeated line, a
    page in two joins, an ad in two splits, a building moved twice, a move to a moved building,
    a move of a building other ads move to, a retract of an unknown or a retracted entry, and a
    split backed only by the ad's words. After a retract, a later file takes the retracted
    entries' pages, ad and building. Reading also stops for a split pointing into another
    building's split, a later split, a retracted split, a split with an `into` of its own or an
    ad of no split, and for a retract of a split another points into. A split pointing into an
    earlier one gives that split's entry, and the two can be retracted in turn;
44. build the fixture without a unit ledger, and check that `ads.placed` repeats `ads.identity`.
    Then write two joins, five splits and three moves, each live, absent or stale, a split
    pointing into a live split's ad with no record and one into an absent split, a join
    retracted in a later file, and a later join taking one of its pages. The test checks each
    entry's status and differing values and each ad's building, building ID, unit, page unit and
    placements by value. The plan rebuilds the two unit ledger models, `ledger.status`,
    `ads.placed` and the 19 models after it. `analysis.candidates` and `analysis.ads` give each ad
    the unit and building of `ads.placed`, `analysis.history_pairs` and `analysis.label_units`
    name no split, and `analysis.rows` gives each split's rows the split as their label unit;
45. read the repo's unit ledger and check that it holds a join, a split and a move;
46. write a dataset folder with `ops/pipeline/observations.py` from the fixture build's rows
    file, with a made-up latest ask for an ad, after giving the catalog a line from a checkout
    with changes and a line cut short. `rentfrontier.data.load` reads the folder to the frame it
    gives the chain's rows of the fixture with their latest asks and the made-up one, after the
    chain's `unit-labels-v17` and `unit-splits-v4`, and the floor fields `_flatten` leaves out
    match too. Between the two rules, the chain's side drops the rows of `LABEL_MONTH_DROPS`, as
    `analysis.label_months` drops them after the label units. The chain's
    alias table and history pairs leave out Park Slope, so the test gives two Park Slope units
    the label units the pipeline joins them into. An ad missing from the chain's audit IDs gets
    an `api:` ID, and the manifest lists an ad the served dataset gives another audit ID. The
    script refuses to write the folder again, and it stops on a rows file without `latest_ask`.
    A second folder renames a neighbourhood to another, and its lines and manifest counts follow
    the rename. A third asks only for the new name, and the rename brings in the old one's rows.
    A rename of a neighbourhood with no rows stops the script;
47. run `ops/pipeline/build-latest --room` with a made-up `systemctl` and `git`, as thelio's
    locks are laid out, with the GPU lock linked to `heavy.lock`. The check lets the build start
    with the GPU lock free, with no pattern of units to avoid, and with the lock held by the build
    itself, and it creates no temporary folder and calls no `git` on the way. It gives the reason
    to wait while another job holds the lock, while a unit to avoid is active, when `systemctl`
    fails and when less memory is available than asked for, and it stops on a memory size it
    can't read;
48. add seven made-up buildings and 29 ads to the cases, build them, copy the state under another
    name, and run `ops/pipeline/citycheck.py` on the copy. The script refuses the state the build
    wrote, and the copy's hash stays the same over the run. The first building gets lot 12 of
    block 1220 from its address and its map point, with 15 apartments and 5 floors in MapPLUTO
    and 8 floors on StreetEasy. 15 of its units have ads in September 2026 and 2 more in June
    2025. Unit 7a reads floor 7 from its label, unit 9b's description gives the ninth floor, and
    unit 10c's label floor of 10 lies above StreetEasy's count, so its row has no floor. The
    second building has its map point on lot 12 and the address of lot 10, and it takes lot 12
    from the footprint. Its unit 2d brings lot 12 to 18 units over all time and 16 in the last 12
    months. The third has no map point and takes lot 9 of block 1238 from its address, and its 7
    units with ads lie within MapPLUTO's 9 apartments and above the 4 on its latest certificate
    of occupancy. The fourth gets no lot. The fifth takes condominium lot 7502 of block 1238 from
    its address, which MapPLUTO gives to two lots. Its one ad asks $600, so no candidate ad reads
    the lot, which takes its `unitsres` of 0 from the latest release and gets no certificate
    count. The sixth takes lot 7503 from a PAD address that MapPLUTO lists under no lot, and its
    June 2025 ad puts unit 8a on floor 8, above the 6 floors of release 16v2 and within the 11 of
    the latest release. The seventh, in Queens, gets no lot, and MapPLUTO gives its address one.
    The report counts the buildings and rows of each link and each MapPLUTO address class, lists
    the second and seventh buildings against MapPLUTO's address, puts lot 12 above `unitsres`
    among the lots linked by `address` or `footprint`, lot 9 above the certificate and lot 7502
    at a `unitsres` of 0, and counts floors 7 and 9 above `numfloors`, floor 8 within the latest
    release's count, floor 9 above StreetEasy's count and the refused floor 10 above
    `numfloors`. A second copy gives the second building the BIN of lot 13's building, which has
    no certificate, and gives the first building's BIN a certificate of 20 apartments. Lot 12
    then lists both BINs and gets no certificate count;
49. write the records file of the fixture export and compare each row with its answer: the
    listing, the response ID and SHA-256, the record as `serialize` gives it, and the answer's
    time in seconds as both the first and the last time. A second run reads nothing into the
    cache, leaves one file of the same bytes and deletes another version's cache folder. With
    an export version, a second call returns the noted file without opening the export and
    leaves its modification time alone. Another version, or a new modification time, makes the
    step write the file again, and a version with no note reads the export;
50. write the records file of a made-up record with integral and fractional floats in its
    price, price changes and sizes, `__typename` keys at each depth and non-ASCII text, and
    compare its `raw_listing_json` with the expected text;
51. write the records file of a made-up listing answered four times with a record, twice at
    the first time, and then once with a changed one, beside an answer without a record. The
    file gives the first record with its first and last times and the lower ID of its two first
    answers, then the changed record, and nothing for the answer without a record;
52. copy a cache file of the records step, and check that the step stops on the repeated
    records and leaves OUT empty. Then check that it also stops while another process holds
    the cache's lock, on an export without records and on an empty list of export files.

pytest-xdist runs the tests in three worker processes, as set in `pipeline/pyproject.toml`, and a
worker with an empty queue takes tests queued for another. The fixture comes to under 500 KB, and
nearly all of a test's time goes to SQLMesh: it loads the project in about 2 s and plans the
fixture in about 4 s of CPU. `pipeline/tests/conftest.py` keeps in each worker, for the whole
session:

- a context on the fixture export and an empty state, for the tests rendering models or reading
  their definitions (items 19, 30, 31 and 33 to 36). No test plans on its state, so SQLMesh
  renders models under their own names rather than as the tables of a build;
- a folder for SQLMesh's optimized model queries, shared by every context of the worker.
  SQLMesh keys each entry on a hash of the model's query, macros and parents' columns, so it
  reuses an entry in a later context only for a model with the same text and inputs;
- the list of the venv's packages, which SQLMesh otherwise reads on each plan.

On thelio, with other jobs keeping the load average between 4 and 10, the tests take about 125 s
at three workers and 135 s at two, and use 300 to 350 s of CPU. With item 74's top-up test, a
run at two workers on Oct 17 took 184 s, and that test took 41 s, the longest of them. SQLMesh
loads models in forked workers, and a fork in a process with open DuckDB connections can
deadlock, so `conftest.py` also sets `MAX_FORK_WORKERS=1`.

The repository's own tests hold `tests/test_pipeline_records.py`, since the pipeline's venv lacks
the page parser's dependencies. It compares `serialize` with the parser of
`apartments.graphql_listing` on each of the fixture's 229 records and on the made-up record of
item 50.

The frontier's `frontier/tests/test_api_records.py` checks the builders' reader on a records file
and catalog it writes in a temporary folder:

53. after a clean build's line, append a dirty build's line and a partial last line, and check
    that the reader takes the clean line's file;
54. add a byte to the records file, and check that the reader stops;
55. append a clean line without a records file, and check that the reader stops;
    then a line without an ads file, and check that it stops again;
56. read a row back, and check its granular names: the listing ID as text, the last answer's
    time as `collected_at` and the response ID as `snapshot_id`;
57. read a granular folder of two Parquet files and the records file through `observations`,
    and check that the folder's rows come in file name order;
58. write five listings, and an ads file that marks a draft and a rented ad with
    `no_dated_own_active_event`, gives another ad a different reason, gives one no reason and
    leaves out the fifth. `captures` and `observations` give only the two ads without the mark.
    Then look up six IDs in a sorted array of three, finding the first, middle and last and
    missing one below, one between and one past the end, and look up two IDs in an empty array.

The frontier's `frontier/tests/test_latest_ask.py` checks `latest_ask` on a records file:

59. give `latest_ask.listings` a page crawl's capture of a listing and two of its records, and
    check that it takes the record with the latest last fetch, at that fetch, over a record
    first fetched later;
60. run `latest_ask.main` with `--crawl records`, and check that it hands the checked file to
    `listings` and names it in its provenance.

The frontier's `frontier/tests/test_descriptions.py` checks `descriptions` on a records file:

61. build a cohort's description evidence from a records file with two records of a listing,
    and check that each row takes the text of the record fetched last and that the build skips
    listings outside the cohort. A second build reads four listings: a RENTED record after an
    ACTIVE one, two ACTIVE records before a DELISTED one, a draft and a record in contract with
    no ACTIVE one, and an ACTIVE record without a description before a DELISTED one with a
    description. It checks that each row takes its last ACTIVE record's text, or the latest
    record's without one, and that the last listing gets no evidence line;
62. run `descriptions.main` with `--records` and with `--granular`, and check that it takes
    either and stops on both.

The frontier's `frontier/tests/test_listing_extras.py` checks `listing_extras` on a records file:

63. build the extras of a page crawl and a records file with two records of a listing, and check
    that each listing takes its capture with the latest time, which for a record is its last
    fetch;
64. run `listing_extras.main` with `--crawl records`, and check that its provenance gives the
    file's path and SHA-256, and those of the ads file on the same catalog line.

The frontier's `frontier/tests/test_lister.py` checks `lister` on a records file:

65. parse made-up records whose histories hold episodes named by `listingId`, by `id` or by
    neither, events of other statuses, without a day or not a dict, and histories of the wrong
    type. For each, check that `record_first_listed` gives the earliest day of the own ACTIVE
    rental events `apartments.graphql_listing` parses from it;
66. build the lister table from a records file and an ads file with two records of a listing
    and an earlier listing in its building, and check the lister of the record fetched last, the
    ads file's building, the earliest listed day over both records and the earlier counts;
67. run `lister.main` with `--crawl records`, and check that its provenance gives both files'
    paths and SHA-256 and that a tag without a crawl stops;
68. parse `--crawl page --crawl records`, and build the lister table from a page crawl and a
    records file. A listing fetched last in the records file takes its lister and the ads file's
    building, and keeps the earlier listed day of the page crawl's event mentions. A listing
    captured last in the page crawl keeps the page crawl's lister and building.

The frontier's `frontier/tests/test_listing_outcomes.py` checks `listing_outcomes` on a records
file:

69. build the outcomes of a records file with a listing still on the market and one that left
    it, each first fetched a day after listing and last fetched ten days after, and check that
    the first counts ten days and the second stops at its day off the market;
70. run `listing_outcomes.main` with `--crawl records`, and check that its provenance gives the
    file under `records` and the ads file under `records.ads`, that `--crawl page` adds the page
    crawls and that a tag without a crawl stops.
71. build the outcomes of a page crawl and a records file together, and check that a record
    fetched after a listing's page capture gives its outcome, that a page capture after the
    record stands, and that a listing the ads file marks `no_dated_own_active_event` keeps its
    earlier page capture.

The repo's `tests/test_graphql_listing.py` checks that `graphql_listing` parses API ads without
the page parser:

72. give `apartments.graphql_listing`'s number, text, JSON and event-key helpers a dozen values
    of every kind, and check that each gives the page parser's result for each value.
73. import the API collector, its export and `graphql_listing`'s `parse_capture` in a fresh
    process, parse an API ad, and check that no `apartments.granular_*` module loaded.

The pipeline's `tests/test_build.py` also checks a top-up build against a build from empty:

74. build runs 2 and 3 with `ops/pipeline/build.py`, then add run 4 and three made-up answers and
    build again as a top-up. One answer puts an ad of a unit back on the market at a new price, one
    adds an ad to another unit of the same building, whose ads all came in run 2, and one adds an
    ad in a new unit of the building. The test builds the same export into an empty state and
    compares every model's table with a hash over its rows, and fails with the names of the tables
    that differ. Only `ads.changes` and `ads.touched` differ, holding fewer answers and ads in the
    top-up. The rows, ads and records files and the catalog's export and building lists match, and
    the top-up reads only the records of run 4 and of the three made-up answers. A further build
    finds nothing to rebuild, and a build after deleting `STATE/merge.json` reads every answer and
    gives every table of the build into an empty state. Then the test writes run 4's file again
    with another region. The build asks for a top-up, `ads.changes` finds the previous answers
    changed and reads every answer, `merge.json` and the catalog line give `top_up` as false, and
    `ads.regions` gives the new region. A second test copies the project, edits
    `materializations/merge.py` in the copy, and checks that only `ads.changes` gets new data and
    that all 16 models of kind `merge` get new fingerprints.

The pipeline's `tests/test_building_check.py` checks the building check on made-up rows:

75. write a row for each of 23 made-up ads, each on its own lot, and render
    `analysis.building_check` over them. The check lists an ad advertising floor 8 of a lot of 5
    floors, one on physical floor 8 of a lot of 5, one on floor 38 of a lot of 25, an ad whose
    unit label reads floor 12 on a lot of 4, two ads on floor 8 of a lot of 5 that the latest
    release leaves out or gives 0 floors, an industrial lot with no apartments, and a parking lot
    of one floor with an ad on floor 5, which gets both reasons. It leaves out the rest: an ad on
    floor 4 of a lot of 3, one floor above the count, floor 21 of a tower of 19 floors, a lot that
    gained floors in the latest release, a lot of two buildings in either release, a building
    StreetEasy gives 10 floors, an ad that advertises floor 3 under a label reading 12, a lot
    with a floor count of 0, lots with land use 04 and 05, lots with apartments or land use 04 in
    the latest release, a building where the ads place four units, and lots with a certificate
    of occupancy with apartments or of a new building;
76. read two dozen unit labels with `alias_key` of `analysis.label_units` and with
    `normalize_label` under `unit-spelling-alias-v2`, and get the same keys. Group made-up unit
    pages of a building into alias groups: only the group a history pair confirms comes out;
77. run each layer of `analysis.label_units` on 35 made-up rows of three buildings, and compare
    each layer's units with the units the chain's own steps of `unit-labels-v17` give the same
    rows, pairs and alias groups. Then render the model over the rows, three of them in splits
    of the unit ledger, and check each joined page unit's label unit, count and layer. A split
    holding ads of two pages joins neither page's unit, and no split appears in the table;
78. walk 16 made-up ads of five units with `pieces` of `analysis.history_splits`, and compare
    each ad's piece with the unit the chain's `unit-splits-v4` gives it. The ads hold a split and
    a return to the first piece, a change of one bedroom, an ad with no bedroom count, a third
    piece, a change of one held by a stated size, a change of two, two ads of one day and a unit
    with one bedroom count. Then render the model over the ads with a sixth unit joined into the
    first by `analysis.label_units` and an ad listed in `analysis.label_months`, and check the
    rows it lists with their units and pieces;
79. render `analysis.label_months` over 12 made-up rows of nine unit pages in five label units,
    and check each row's fate. The rows hold two pages of a label unit in a month, a ledger
    split in the same month, a month with two bedroom counts and one with two bathroom counts, a
    month where a row with no bedroom count meets a counted one, and two ads of one day with the
    IDs "999" and "1000".

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

In that build every model was a full table, so the top-up rebuilt all five tables and took as
long as a build from nothing. [Top-up builds](#top-up-builds) describes the models a top-up
now extends with the ads it changes. The event log of step 4 should also shorten
`ads.kept_changes`, whose placeholder check steps through each ad's changes one at a time.

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
