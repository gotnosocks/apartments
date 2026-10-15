# StreetEasy collection through the GraphQL API

Ben asked on Oct 14 2026 (22:23 ET) for a collector that spends fewer requests and dollars, so
that the rest of Manhattan and Brooklyn north and west of Prospect Park could be collected and
the dataset topped up on a schedule. He agreed at 22:57 ET that the collector may read each
unit's history from the API in place of fetching unit pages. `streeteasy_archive.graphql_search`
enumerates an area's ads with StreetEasy's `searchRentals` query, reads hundreds of ads in a
request with `rentalsByListingIds` and reads buildings with `buildingsByIds`, all on
api-v6.streeteasy.com through the Oxylabs Realtime API. It then writes the records into an
archive in the same steps a page crawl follows, so `granular_export` and the collection audit
read the archive as they read a crawl's. The module docstring gives the steps and their limits.

## NoMad, offline against the page crawl (Oct 15)

A probe on Oct 15 between 00:00 and 00:43 ET read NoMad through the API in 122 requests
(`data/probes/graphql-search-20261015/`, local). I then ran the collector offline against a
client answering from the probe's saved responses. It needed 86 requests for NoMad: 10 for
the search, 75 for ad reads and 1 for all 221 buildings. The page crawl of Oct 8 and 9 made
13,504 requests for the same area. The replay's archive, dataset and audit are in
`/data1/apartments/tmp/wt-crawl/nomad-offline/`, and the dataset came from
`models/transform_local.py` with an empty corrections ledger, as the crawl's did.

Compared with `nomad-granular-20261009-canonical-url-v1`:

| | page crawl | API |
|---|---:|---:|
| unit memberships | 10,962 | 13,350 |
| rental units | 3,388 | 4,376 |
| event mentions | 607,881 | 645,887 |
| building observations | 213 | 221 |

- Of the crawl's memberships, 10,957 have the same ad on the same unit in the API dataset and
  none has the ad on a different unit. The crawl's other 5 are ads below the listing-ID cutoff.
  The API dataset adds 2,393 memberships for NoMad ads the page crawl never queued, 905 of them
  at Chelsea Landmark (55 W 25th St).
- 3,384 units are in both datasets, 4 only in the crawl's and 992 only in the API's.
- On the 10,958 ads in both, the fields differ only for 4 ads whose listing ID is also a sale
  listing's ID. Prices and statuses differ where an ad changed during the six days between the
  crawl and the probe. Event counts match for 10,682 ads. The others differ at the old end of
  the history, since StreetEasy shows a fixed number of events and newer events had pushed the
  oldest out.
- StreetEasy renamed one unit's slug from `/04n` to `/4n` (the API gives both ads one
  `propertyId`, 7767153). The crawl and the replay both keep two units and exclude the ads at
  the old spelling as `captured_listing_not_eligible`. Merging units by `propertyId` is a
  possible data improvement.

The collection audit runs on the API archive: 15,230 frontier rows done, 4,069 excluded and
4,151 superseded. The historical exclusions are 3,821 ads below the cutoff, 1,867 not eligible
and 248 with no unit membership.

## Ad and building fields next to the pages (Oct 15)

I compared 400 ad pages from the Midtown West crawl of Oct 13 with 1,051 API records
(scripts in `/data1/apartments/tmp/wt-crawl/fields/`). The API record holds the ad page's
listing object, apart from these fields:

- `listingAddress`, which the address fields rebuild
- `saleType`, null on rentals
- `showingNotes` on upcoming open houses

The record also adds `propertyId` and each history episode's `offMarketAt`. The rest of the ad
page lies outside the listing object, and no code in `src/` reads it:

- the listing agent's name, phone, contact and profile IDs, license type and Pro flag (the API
  record keeps the brokerage under `legacy.license`)
- nearby schools with district and grades, and nearby subway stations with routes and distance
- 25 nearby colleges, museums and parks each, with distances
- the page's building summary: area breadcrumbs and related areas, counts of units for rent and
  for sale, and a documents link
- the price history's display text, the similar-homes carousel and nearby-area links

For each building, the collector also reads these fields of the page's building object from
the API:

- the description, the green, land-lease and waterfront flags, and the complex
- the leasing and sales start dates (`additionalDetails`)
- the hero image key, the photo and floor-plan keys, the video URLs and the 3D tour URL
- the IDs of the building's ads for rent and for sale (the collector can read the rental ads
  with `rentalsByListingIds` like any other ad)
- an owner-data flag, the last-change time and `nearby`

The page splits `nearby` into its 5 transit stations and its 5 colleges, 5 museums and 5
parks, and the API gives the same lists. The API disables introspection, so I couldn't find
the subfields of `displayPreferences` and left it out. In the building object, the page also
holds nearby schools, a documents link and the flags `hasPropertyDocs` and
`hasActiveBuildingShowcase`. Outside it, the page shows similar buildings, the management
company and the cards of the building's ads. The API's `Building` type offers no fields for
the schools, the documents, the two flags, similar buildings or the management company.

The collector reads each building once in a generation, so a building read before this change
keeps its older record. The `crawls/api` archive had read no buildings when the change
merged, so every building record in it has these fields.

## Regions

`REGIONS` in the module lists the regions and their StreetEasy area IDs. The projections
scale NoMad's 86 requests for 20,461 all-time search hits by each region's hit count, at about
$1.14 per 1,000 requests.

| region | areas | with unit histories | projected requests |
|---|---|---|---:|
| `manhattan-below-59th` | 21 areas not crawled before | yes | about 2,200 |
| `manhattan-59th-110th` | Upper West Side, Upper East Side, East Harlem | yes | about 2,300 |
| `brooklyn-prospect-park` | 14 areas north and west of Prospect Park | yes | about 1,100 |
| `brooklyn-north-crown-heights` | north Brooklyn and Crown Heights | yes | about 2,900 |
| `manhattan-page-crawl-areas` | the areas page crawls already collected | no | daily only |

Ben approved the backfill of the first four (about 8,500 requests, about $9.70) on Oct 15 at
00:37 ET, with north Brooklyn, Crown Heights and Manhattan up to 110th St. StreetEasy has no
area for East Harlem below 110th St, so the region takes all of it, about $0.17 more. Re-reading
the histories of areas collected by page crawls is not part of the backfill. Writing the
records takes about 16 ms an ad with no requests, so the four regions' 1.5 million or so ads
take about 7 hours to write.

## Running it

`ops/streeteasy-collect` copies `src/` at its checkout's commit into
`/data1/apartments/runtime/graphql-search-COMMIT` once, read-only, and runs the collector from
that copy with the main checkout's venv and `.env`. Every region writes into the same archive,
`/data1/apartments/archive/crawls/api`, with a lock in it, and each run records its region.
Each ad a run reads joins the run's region and stays in it, so an ad in an area two regions
cover belongs to both. When a run picks units, histories and buildings to read, it starts
only from its region's ads, and a daily run of one region leaves the others' units alone.
The script holds `crawls/oxylabs.lock` while it runs, so collections run one at a time at 60
requests a minute.

```sh
ops/streeteasy-collect backfill manhattan-below-59th manhattan-59th-110th
ops/streeteasy-collect daily
```

- `backfill` reads every ad of each region with its units' histories at or above the cutoff.
  It stops at 4,000 requests for a region and at the first region that fails. Running it again
  resumes the region's unfinished run.
- `daily` reads the ACTIVE ads of every region and re-reads each region's ads whose status is
  not RENTED, NO_LONGER_AVAILABLE or DELISTED, with at most 150 requests a region. It goes on
  past a region that fails.
- A run that finishes writes the region's ads with an ACTIVE record fetched since the run
  started, by any region's runs, in the current-listings format under
  `crawls/api/current-listings/REGION/`, and points
  `/data1/apartments/archive/current-listings/api-REGION` at them. An ad gone from the API
  keeps its last record, so the capture goes by when that record arrived. The site's reader
  takes the newest capture of each unit across that folder, for buildings in the served fit,
  on the next site data build.
- Each run's report is in `crawls/api/graphql-search/run-N.json`, and the script logs a line
  for each region in `crawls/streeteasy-collect.log`.

`ops/systemd/apartments-streeteasy-daily.timer` runs `daily` at 05:30 New York time from the
master checkout, in the light slice with 2 GB of memory.

## Backup

`ops/streeteasy-backup` copies the archive to the second disk, and
`ops/systemd/apartments-streeteasy-backup.timer` runs it from the master checkout at 09:00 New
York time, three and a half hours after the daily top-up starts. A collector may still be
writing then, which the steps below allow for. Each run goes through these steps:

1. It copies the database with `VACUUM INTO` over a read-only connection, into
   `/data2/apartments-backup/streeteasy-api/db/archive-STAMP.sqlite3`. The copy holds the
   database at a single moment, and a collector can keep writing meanwhile.
2. It runs `PRAGMA quick_check` on the copy and stops if the check reports a problem.
3. It flushes the copy to disk, gives it its final name and deletes all but the newest 7
   database copies.
4. It copies the bodies, the run reports and the current-listings captures into `files/` with
   rsync, leaving out the database, the collector's lock and partial `.tmp` bodies. A file gone
   from the archive stays in the backup. A capture pruned by a collector during the copy leaves
   rsync with exit 24, which the script accepts.
5. It appends a line to `backup.log` in the backup folder.

It stops before writing anything if the archive's database is missing, or if
`/data2/apartments-backup` is missing, which means the second disk is not mounted.

To restore, with no collector running:

1. Copy `files/` back into `crawls/api`.
2. Delete any `archive.sqlite3-wal` and `archive.sqlite3-shm` left in `crawls/api`. Otherwise
   SQLite replays the old WAL onto the restored database and corrupts it.
3. Copy the newest database copy to `crawls/api/archive.sqlite3`.
4. If the `current-listings/api-REGION` links are gone, point each one at its region's newest
   capture under `crawls/api/current-listings/REGION/`. The backup leaves the links out.
