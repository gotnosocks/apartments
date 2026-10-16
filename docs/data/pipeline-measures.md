# Data pipeline measures, 2026-10-16

This file records how long the rebuilt pipeline took, and how much memory it used, to turn the
StreetEasy API exports into fit-ready rows on Oct 16, the first day it built after every export.
[The baseline](pipeline-baseline.md) gives the same figures for the steps run by hand on Oct 15, and
the sections below compare the two days.

Times, CPU and memory come from systemd accounting and the Modal ledger. Each build's seconds, row
counts and the script's memory peak come from its line in
`/data1/apartments/pipeline/datasets/catalog.ndjson`, described under [Build
command](pipeline.md#build-command). All times are ET. To regenerate the accounting figures:

```sh
python ops/pipeline/accounting.py journal --since "2026-10-16 00:00" --until "2026-10-16 19:00" \
    --match apartments-pipeline-build
python ops/pipeline/accounting.py modal --last 15
```

## Builds on Oct 16

`apartments-pipeline-build.service` ran eight builds on Oct 16. Its path unit started two of them
when an export changed the manifest, and its timer started the one at 07:15. The other five were
started by hand, each right after a pipeline change merged, so the change went into the rows at once
instead of at the next morning's timer. A ninth start, at 01:23, found the export and the code as
the last build left them and stopped within a second.

Wall and CPU in the table are the unit's, from the journal, so the wall time includes waiting for
the GPU lock and the light slots. Build is the catalog's total, from loading the project to writing
the files. Peak is the script's own resident peak, DuckDB's included. The unit's cgroup peaked at
its 5 GiB cap in six of the eight builds, since the page cache fills whatever the script leaves.

| finished | code | started by | wall | CPU | build | peak MiB | rows file | notes |
|---|---|---|--:|--:|--:|--:|---|---|
| 01:22 | #887 | hand | 9.7 min | 40.8 min | 575 s | 4,143 | `rows-4743b90b`, 1,747,140 rows | the first build, runs 1 to 5 into an empty state; `ads.record_attributes` parsed every record in 410 s |
| 03:21 | #888 | hand | 1.3 min | 1.1 min | 13 s | 3,461 | `rows-09106f48`, 1,746,283 rows | the corrections ledger; 6 of 23 models rebuilt |
| 06:35 | #896 | manifest | 45.5 min | 14.5 min | 193 s | 4,239 | `rows-892481e2`, 1,746,499 rows | the Friday top-up of runs 6 to 10, after 42 min waiting for the GPU lock |
| 07:20 | #901 | timer | 5.2 min | 0.6 min | 7 s | 3,423 | `rows-892481e2` | 11 of 31 models rebuilt, and the same rows file |
| 09:53 | #908 | manifest | 2.9 min | 8.8 min | | | | run 11; `ads.events` and `buildings.latest_record` ran out of DuckDB's 3 GB limit, and the build wrote nothing |
| 11:40 | #910 | hand | 62.4 min | 7.7 min | 124 s | 3,809 | `rows-04fe7ad8`, 1,746,515 rows | run 11 again, after about 60 min waiting for the locks |
| 14:45 | #919 | hand | 3.1 min | 15.4 min | 167 s | 4,126 | `rows-04fe7ad8` | the first ads file, `ads-237af093`, with 2,140,578 ads |
| 16:25 | #925 | hand | 12.2 min | 41.7 min | 722 s | 4,332 | `rows-1c991405`, 1,746,515 rows | #923 changed the record parser, so `ads.record_attributes` parsed every record again, in 643 s; #925's first check of every export file's hash took 31 s |

Each build ran every model's audits before writing its files. From #925 on, a build also checks the
export's new or changed files, and each record in them, against their hashes. The 09:53 build failed
in two models and wrote nothing, so the rows of 06:35 stayed the latest until 11:40.

## From a finished scrape to fit-ready rows

The Friday top-up ran with no step by hand:

1. The collector's runs 6 to 10 made their last API call at 05:48. The export changed the manifest
   at 05:49, and the path unit started the build within seconds.
2. The build waited 42 minutes for the GPU lock, which Modeling's summary of a fit held.
3. It built in 193 s and wrote the rows at 06:35, 47 minutes after the last call.

A check build of the same export and code into an empty scratch state took 713 s at a 4,113 MiB peak
and wrote the same rows file. The top-up took 27% of that time. Most of its 193 s went to
`ads.events` (59 s), `ads.record_attributes` (30 s, parsing the new records and copying the others
from its cache) and `ads.kept_changes` (19 s). Since those models still recompute every ad, I'll
make them incremental under item 5 of step 8 in [the handoff](../handoff/data-pipeline.md).

Run 11 needed a fix. Its last call came at 09:49. The path unit started a build at 09:50, and at
09:53 the build failed when two models ran out of DuckDB's memory. #910 parses each building record
once, and the start by hand at 10:38, nine seconds after #910 merged, waited about 60 minutes for
the locks and wrote the rows at 11:40, 111 minutes after the last call. After `ads.events` failed
the same way in two scratch builds that afternoon, #918 split it into two tables at 14:07. No build
has failed since.

On Oct 15, Manhattan's rows passed the feature build check about 1.7 hours after the collector's
last run. No Brooklyn region had checked rows by 16:30, and two threads ran 18 scripts by hand
between them.

## Memory, CPU and wall time

| | Oct 15 steps | pipeline, runs 1 to 5 from empty | pipeline, Friday top-up |
|---|--:|--:|--:|
| wall time of the work | about 172 min, 82 of them network | 575 s | 193 s |
| CPU | about 103 min in the steps behind that wall time | 40.8 min | 14.5 min |
| highest peak | 8.1 GiB, and two steps out of memory | 4,143 MiB | 4,239 MiB |
| steps by hand | 18 scripts | none | none |
| rows | 1.40M distinct rows in four regions | 1,747,140 | 1,746,499 |

The pipeline builds its rows from every ad of the export, the old page-crawl areas included, and
keeps one row for each unit and month. Its peaks are the script's. The baseline's are the units'
cgroup peaks, page cache included, and the pipeline's cgroup peaks equal the service's 5 GiB cap
with swap off for the reason above. The build runs on all twelve CPUs at nice 10.

The two days don't cover the same work:

- The baseline's building registry made a GeoSearch request for each building, 54 minutes for
  Manhattan. The pipeline reads lots and buildings from the city archive: PAD, MapPLUTO, footprints,
  LPC landmarks and DOB certificates of occupancy. Its first copy, by hand on Oct 16, fetched 62
  files and 4.45 GB in 525 s. `apartments-city-fetch.timer` refreshes it every Friday at 04:00, from
  Oct 23. When a run finds nothing new, it takes 4 s.
- The baseline checked its rows with a feature build (`data.load`, the rules and `features.build`)
  on two Manhattan regions. A pipeline build counts as checked when the export's files and records
  match their hashes and every model's audits pass. No feature build has read a pipeline rows file
  yet, and none will until fits read a rows file by its name and hash, item 3 of step 8 in the
  handoff.
- The pipeline doesn't yet write the descriptions file, the price changes with their kept flag, or a
  few of the listing extras' columns: the lister, the broker's licence, the source type, the outdoor
  space, the room count and the fireplaces.

## Changing a step

| change | how it ran | wall | peak |
|---|---|--:|--:|
| any model or step, on the fixture's 229 records | `diff.py`, both sides from empty | 6.1 s | 350 MB |
| any model or step, on the 1% sample of 19,683 ads | `diff.py --sample` | 18.5 s | 2.2 GB |
| `ads.market` (#935), on the full export | a build on a copy of a built state | 27 s | 4,164 MiB |
| the record parser (#923), on the full export | the service's build at 16:25 | 722 s | 4,332 MiB |

On the fixture and the sample, `diff.py` lists every table's changes within a minute. On the full
export, a change to a model downstream of the parse also takes under a minute, because the build
reuses the parse cache and rebuilds only the models downstream of the change. A change to the parser
parses all 2.1M records again, in about 11 minutes. In the tests, a build of the fixture's export
from an empty state takes about 5 s.

## Data preparation inside a fit

Fits still read the chain's datasets, so the pipeline hasn't changed this step yet. Over the last 15
Modal fits (Oct 13 to 16, all on an A100), preparation took a median of 191 s (92 to 342 s), 6.3% of
the GPU container's time. That comes to about $0.13 a fit, and $1.81 across the
15. The baseline's 15 fits, from Oct 12 to 15, took a median of 153 s and $0.10 a fit.

## Disk

On the evening of Oct 16, after run 11, the export took 3.45 GB and the city archive 4.45 GB. The
city tables' Parquet cache took 3.2 GB for each version of the code to unpack the archive, 6.47 GB
for the two on disk. The build's state took 9.10 GB, its parse cache and older tables included, and
the janitor drops a table after a week with no build using it. Each rows file takes 80 MB, and each
ads file 122 MB. All sizes here are in decimal units. On Oct 15 the granular Parquet took 5.4 GB,
and the API response bodies 11 GB.
