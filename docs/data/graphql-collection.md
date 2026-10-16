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

| region | areas | with unit histories | requests |
|---|---|---|---:|
| `manhattan-below-59th` | 21 areas not crawled before | yes | about 2,200 |
| `manhattan-59th-110th` | Upper West Side, Upper East Side, East Harlem | yes | about 2,300 |
| `brooklyn-prospect-park` | 14 areas north and west of Prospect Park | yes | about 1,100 |
| `brooklyn-north-crown-heights` | north Brooklyn and Crown Heights | yes | about 2,900 |
| `manhattan-page-crawl-areas` | the 12 areas page crawls already collected | yes, from Oct 16 | 2,054 in run 5, then weekly top-ups |

Ben approved the backfill of the first four (about 8,500 requests, about $9.70) on Oct 15 at
00:37 ET, with north Brooklyn, Crown Heights and Manhattan up to 110th St. StreetEasy has no
area for East Harlem below 110th St, so the region takes all of it, about $0.17 more. Re-reading
the histories of areas collected by page crawls is not part of the backfill. Ben approved a
re-read of those areas' ads, without unit histories, on Oct 15 at 15:50 ET (run 5, below).
Since Oct 16 the region reads unit histories too, for about 6 more requests
([below](#unit-histories-in-the-page-crawl-areas-oct-16)).
Writing the records sends no requests and takes about 7 ms an ad on thelio, half of it in the
two disk flushes for each ad's body file, so the four regions' 1.5 million or so ads take about
3 hours to write.

## Bands too full to read from both ends (Oct 15)

A `searchRentals` query returns at most 1,000 IDs. The collector reads a band of a single
price and bedroom count from both ends, so it misses the ads between the ends of such a
band holding more than 2,000. The first three backfill runs left these bands:

| run | region | truncated bands | ads between the ends | read through unit histories |
|---|---|---:|---:|---:|
| 1 | `manhattan-below-59th` | 24 | 13,649 | 10,322 |
| 2 | `brooklyn-prospect-park` | 13 | 6,917 | 4,867 |
| 3 | `manhattan-59th-110th` | 50 | 47,520 | 32,807 |

Since some ads match the price filter of more than one band, the middle column overstates
the missing ads. The collector splits such a band into the region's areas, and an area
listed in `SUBAREAS` into its child areas: the Upper West Side into Lincoln Square, the
Upper West Side proper and Manhattan Valley, and the Upper East Side into its own leaf area,
Lenox Hill, Yorkville, Carnegie Hill and Upper Carnegie Hill. I took the children from the
`se.areaId` of the buildings in the archive. When I ran the new collector's band tree
against a copy of the archive's band tables, it found 504, 182 and 150 area bands to count
in runs 1 to 3. Projecting from each region's ads by area, I expect the three reopened
runs to take about 450 requests (about $0.51), most of them for the 59th to 110th St ID
and ad reads, and to leave no band truncated.

The fourth run, `brooklyn-north-crown-heights`, finished after that estimate with 63
truncated bands. I reopened all four runs between 11:18 and 12:06 ET, and the reopens took
598 requests ($0.67):

| run | region | reopen requests | truncated bands left | ads beyond the two ends |
|---|---|---:|---:|---:|
| 1 | `manhattan-below-59th` | 170 | 0 | 0 |
| 2 | `brooklyn-prospect-park` | 65 | 0 | 0 |
| 3 | `manhattan-59th-110th` | 106 | 8 | 3,490 |
| 4 | `brooklyn-north-crown-heights` | 257 | 2 | 258 |

Run 3's bands lie in the leaf areas of the Upper West Side (137) and the Upper East Side
(140), and run 4's in area 310. None of these has child areas, so I tested the search's
`boundingBox` filter with two requests (`bbox1.py` and `bbox2.py` in the probe folder). On a
band of 2,863 ads, the north and south halves of a box held 1,278 and 1,585 ads, and the west
and east halves 1,097 and 1,766. A box covering the whole map counted the same 2,863 ads as
the band without a box.

So the collector now halves a band still too full in a leaf area by map box. Box 1 covers
the whole map, and box k splits into boxes 2k and 2k+1, taking the south and north halves at
an even depth and the west and east halves at an odd one (`box_edges`). The halves share
their edge, so an ad on it can match both. Each round of counts goes one level deeper, and a
band of 2,000 Upper East Side ads needs 25 to 30 levels before its halves come apart, with
the empty halves ending as leaves. When the collector reopens a run, it adds a `box` column
to the band tables of an older archive, and the old bands take the value for no box.

I reopened runs 3 and 4 with the box split (#843) between 12:34 and 12:43 ET. The first
attempt stopped after 10 requests, when Oxylabs answered 6 requests in a row with no status
or content, and the second went through. The two attempts took 80 requests ($0.09) and left
no band truncated in either run. The box halves added up to their bands everywhere, so no ad
fell outside the boxes. The searches found 1,343 more ad IDs in run 3 and 236 in run 4, most
of them already in the archive. Writing the new ones, the collector added 28 ad records,
marked 330 ads as superseded and excluded 5. I count a band's gap as its count minus the sum
of its parts' counts. Positive gaps remain only where a band splits by bedroom count, 35 ads
in run 3 and 15 in run 4. Ads with no bedroom count or more than 7 bedrooms would fall in
these gaps, as would ads that changed between two counts.

I probed two of these bands at 13:24 ET with `beds_gap.py` in the probe folder (3 requests,
one of them an Oxylabs failure). Run 4's $3,000 band counted 17,553 ads, against 17,550 in
its bedroom counts 0 to 7, and run 3's $2,500 band counted 11,251 against 11,248. In both
bands a filter for 8 or more bedrooms counted the missing 3 ads. A `bedrooms` filter with a
lower bound and no upper bound counts the same ads as one with an upper bound of 1,000, and a
filter for 0 or more bedrooms counts the whole band. The dataset below holds 154 ads coded
with 8 to 255 bedrooms and none without a bedroom count. The bedroom split now gives a ninth
band, 8 bedrooms or more, after the bands of 0 to 7, and a reopen counts and reads it.

## Reads from both ends of a band (Oct 15)

The bedroom reopen took 50 requests ($0.06) and left no positive gap in any run. Each
region's count, taken in the run's first request, still stood above the ad IDs its searches
had found:

| run | region | count | IDs found | difference | bands read from both ends |
|---|---|---:|---:|---:|---:|
| 1 | `manhattan-below-59th` | 495,253 | 494,353 | 900 | 112 |
| 2 | `brooklyn-prospect-park` | 264,043 | 263,732 | 311 | 45 |
| 3 | `manhattan-59th-110th` | 555,457 | 553,675 | 1,782 | 227 |
| 4 | `brooklyn-north-crown-heights` | 658,118 | 657,349 | 769 | 205 |

Every ID read of a band of 1,000 ads or fewer gave as many IDs as the band's count. Filters
for a price of 0 or more, a price from 0 to 100 million and 0 or more bedrooms each counted
the same ads as the whole region (`full_vs_hits.py` in the probe folder, 4 requests), so no
ad lacks a price or a bedroom count. That left the bands read from both ends. With
`two_ends.py` (1 request) I read two of run 3's bands in each direction. A $4,300
one-bedroom band of 1,005 ads gave 1,002 IDs between its two reads, and a $1,950 one-bedroom
band of 1,971 ads gave 1,954. The search seems to order ads with the same listing date
differently in each direction, so the two reads miss ads in the middle even in a band of
fewer than 2,000. At 4 to 8 missing ads per band, these bands account for the differences
in the table.

So the collector now splits a band of a single price and bedroom count into areas, child
areas and map boxes until each part holds 1,000 ads or fewer, and reads each part from one
end. It still reads a box a microdegree across from both ends when the box holds more than
1,000 ads, and the report lists that band as truncated.

The first enumeration probe put 4 ID reads in a request, with no test behind the number.
With `packed_slices.py` (1 request), a request carrying 20 ID reads of run 3's bands, 3,838
ads between them, came back whole in 4.9 seconds, with a 7,832-character URL and a 100 KB
answer. Twenty-five such reads would have needed a 9,803-character URL, over the collector's
limit of 8,000. The collector now packs ID reads by their ads: the fullest bands go first,
and a request takes reads of up to 4,000 ads between them, or as many as fit in the URL.
For the four runs' bands of 1,000 ads or fewer, this packing takes 532 requests, against
1,379 at four reads to a request. The 589 bands read from both ends split into 4,682 bands
at the first level below them. I expect the reopen of the four runs to take 500 to 800
requests (about $0.60 to $0.90), and a fresh enumeration of the four regions to take about
1,700 requests, against the 2,374 the backfill runs spent on counts and ID reads.

I reopened the four runs from 13:51 to 14:34 ET. The reopen took 1,081 requests ($1.23),
above my estimate of 500 to 800. ID reads took 321 requests, fewer than the projected 532.
Counts took 753, and my estimate had left them out. In run 3, 3,146 of the 4,504 box counts
went to halving boxes from the whole map down to the size of New York (next section).
Oxylabs answered 55 calls with no status or content, 41 of them in run 3. Bursts of these
stopped run 3's reopen twice, at 14:02 and 14:11 ET, each after six failures in a row. #852
now retries such answers, and a third pass of 234 requests finished run 3 at 14:24. The
reopen found 3,797 more IDs. Each region's IDs now match or pass its count:

| run | region | count | IDs found | new IDs |
|---|---|---:|---:|---:|
| 1 | `manhattan-below-59th` | 495,253 | 495,260 | 907 |
| 2 | `brooklyn-prospect-park` | 264,043 | 264,043 | 311 |
| 3 | `manhattan-59th-110th` | 555,457 | 555,471 | 1,796 |
| 4 | `brooklyn-north-crown-heights` | 658,118 | 658,132 | 783 |

No run has a pending, truncated or unanswered band. The only positive gap left is in run
3's $4,200 one-bedroom band: its count of 1,690 stands 1 above the sum of its areas'
counts, and every ID read gave as many IDs as its count. IDs above a region's count most
likely come from ads posted between the run's first count and its later ID reads. The
collector read 398 of the new IDs' ads in 4 requests. The other new IDs lie below the
listing-ID cutoff, which the collector skips, or belong to ads it had read before. The
collector wrote 70 ad records, marked 319 ads superseded by later ads of their units and
excluded 8. Each run then published its region's current listings again under
`current-listings/api-REGION`.

## Child areas and the start of the box split (Oct 15)

Run 3's last reopen took 234 requests ($0.27) and finished at 14:24 ET with 555,471 IDs
found against a count of 555,457. In its band tree, the Upper West Side's child area 137
counted the same ads as its parent, area 135, in 36 of 37 bands and one more in the last.
The Upper East Side's child area 140 counted the same ads as area 139 in all 57 bands.
StreetEasy's search seems to take these leaf areas for their parents, so the child areas'
counts added up to more than their parents', and the collector counted and read 16,600
Upper West Side ads and 81,436 Upper East Side ads twice. The bands of areas 137 and 140
still went on into map boxes. I removed `SUBAREAS`, and an area band now goes straight into
boxes.

Box 1 covers the whole map, and a band took 18 halvings to get from it down to boxes the
size of New York. Of run 3's 4,504 box counts, 3,146 lay above that depth, about 210
requests at 15 box counts to a request. No band of any run held an ad in a box away from
New York. The box split now starts from the four boxes at depth 18 around the five boroughs
(`root_boxes`), each 0.35 degrees of latitude by 0.70 of longitude. Their numbers match the
tree from box 1, so a reopen reuses a run's counts of these boxes and the boxes below them.
Of run 3's 101 box bands, 36 came apart at depth 13, where a split at latitude 40.78125
crosses Manhattan, and a reopen would count those again from the four boxes. An ad placed
outside the four boxes would show up in the report as a gap of its area band. For a region
the size of run 3, I expect the two changes to save about 250 requests (about $0.29) of an
enumeration.

## The four regions' backfill and dataset (Oct 15)

| run | region | requests | dollars | search hits |
|---|---|---:|---:|---:|
| 1 | `manhattan-below-59th` | 2,265 | 2.58 | 495,260 |
| 2 | `brooklyn-prospect-park` | 1,345 | 1.53 | 264,043 |
| 3 | `manhattan-59th-110th` | 3,240 | 3.69 | 555,471 |
| 4 | `brooklyn-north-crown-heights` | 3,415 | 3.89 | 658,132 |
| | all four | 10,265 | 11.69 | 1,972,906 |

The requests include every reopen through the split of bands down to 1,000 ads, failed
calls among them. Ben's approval of Oct 15 projected about 8,500 requests and $9.70.

I then built a dataset from a snapshot of the archive, with no requests, in the steps used for
Midtown West (`/data1/apartments/tmp/api-build-20261015/build.sh`, code from master at #843):

1. `snapshots/api-20261015/archive.sqlite3` (9.3 GB), copied with `VACUUM INTO` under
   `oxylabs.lock` and checked with `quick_check`, with its SHA-256 beside it.
2. `datasets/api-granular-20261015-canonical-url-v1`, from `models/transform_local.py` with an
   empty corrections ledger, in 15 minutes: 1,706,321 listing observations, 767,445 rental
   units, 1,692,611 unit memberships, 62,122 building observations and 30,640,738 event
   mentions.
3. The collection audit, in `/data1/apartments/tmp/api-build-20261015/audit.json`: 1,773,813
   observations and no capture errors. Of the scoped frontier, 1,768,200 rows are done,
   284,094 excluded and 746,478 superseded. The audit also reads the exclusion log as a
   trail: 269,234 ads below the listing-ID cutoff, 14,860 with no unit membership and 26,270
   captured ads found not eligible. The frontier marks those 26,270 as done, so the 284,094
   excluded rows hold the first two groups.
4. `datasets/api-granular-20261015-unit-spelling-aliases-v2`: 16,524 groups of unit
   spellings (12,150 confirmed by unit histories), joining 34,631 units and 81,091 ads.

For 20,900 of the 26,270 ads not eligible, the unit history listing the ad spells the unit
differently from the ad's own unit slug, such as `/2c` and `/2-c` at 32 W 72nd St or `/8c`
and `/008c` at 101 West End Ave. StreetEasy keeps two records for each such unit. The other
5,370 ads have an API record with no building or unit slug.

The dataset holds the four regions' runs as of the 12:47 ET snapshot, so it lacks the ads
from the reopens after it and from the [weekly top-ups](#the-first-weekly-top-up-oct-16).

## The page-crawl areas' re-read (Oct 15)

Ben approved the re-read on Oct 15 at 15:50 ET, so that the API archive holds the ads of the
12 areas page crawls had collected. I ran `ops/streeteasy-collect backfill
manhattan-page-crawl-areas` from 15:52 to 17:48 ET as run 5, with no unit histories. It took
2,054 requests ($2.34): 232 counts, 239 slices, 1,549 ad reads and 34 building reads.

- The searches found 522,774 ad IDs in 2,663 bands, the same as the areas' count, with no
  pending, truncated or unanswered band and no band whose parts held fewer ads than it.
- The run read 424,776 ads: 226,664 RENTED, 153,622 NO_LONGER_AVAILABLE, 42,608 DELISTED, 1,419
  ACTIVE and 463 with other statuses. Of the IDs it left unread, 93,468 fall below the
  listing-ID cutoff of 1,210,000, and 4,535 were already in the archive with a final status
  from the four regions' runs. Its reads also include 5 ads outside the search hits, as the
  latest ads of units.
- Writing took from 16:53 to 17:48 ET: 266,322 ad records, 157,293 ads marked superseded and
  1,161 excluded, with 160,579 units and 8,003 buildings written. 745 units have no unit page.
  Of the ads in the run's scope with no archive entry, it excluded 91,723 for falling below the
  listing-ID cutoff and left 107 unread.
- The run wrote current-listings files for its 1,419 ACTIVE ads to
  `current-listings/api-manhattan-page-crawl-areas`, with 1,417 candidates and 2 failures.
- I exported the run's replies to `crawls/api/export` by hand at the end, since #864 merged
  while it was running. The export holds 424,776 ad reads in 6 files, 8,003 building reads,
  1,508 stored replies and 1,970 calls, and each table matches the archive. The collector
  records each call's POST count in `attempt`, and over run 5 those counts sum to its 2,054
  requests.

## The first weekly top-up (Oct 16)

The timer started `ops/streeteasy-collect topup` on Friday Oct 16 at 05:30 ET. It ran the five
regions in turn as runs 6 to 10 and finished at 05:49 ET, with every region and the export at
exit 0. The whole top-up took 120 requests ($0.14).

| Run | Region | Requests | Dollars | ACTIVE ads | Ad reads |
|---|---|---|---|---|---|
| 6 | `manhattan-below-59th` | 34 | 0.04 | 1,692 | 4,558 |
| 7 | `manhattan-59th-110th` | 33 | 0.04 | 1,356 | 4,122 |
| 8 | `brooklyn-prospect-park` | 17 | 0.02 | 1,001 | 3,252 |
| 9 | `brooklyn-north-crown-heights` | 28 | 0.03 | 1,551 | 6,327 |
| 10 | `manhattan-page-crawl-areas` | 8 | 0.01 | 1,422 | 1,912 |

- Each region's search found as many ACTIVE ads as its count, with no pending, truncated or
  unanswered band. Across regions the searches found 7,011 distinct ads, since 11 fall in two
  regions.
- Besides the ACTIVE ads, each run re-read its region's ads with a status other than RENTED,
  NO_LONGER_AVAILABLE or DELISTED. The 20,171 reads cover 20,154 distinct ads and returned
  7,022 ACTIVE, 9,488 DRAFT, 1,452 IN_CONTRACT, 1,263 TEMPORARILY_OFF_MARKET, 428
  IN_STREETEASY_REVIEW, 289 RENTED, 108 NO_LONGER_AVAILABLE, 95 DELISTED and 26
  IN_BROKERAGE_REVIEW.
- The runs wrote 670 ad records, 10,179 units and 4 buildings. They marked 9,972 ads superseded
  and excluded 9,529. Of the excluded ads, 9,109 are DRAFT ads with no canonical unit. Earlier
  runs had already excluded all but 3 of them, and the top-up logged 6 new exclusions.
- Every region's `current-listings/api-REGION` link moved to the new run's files, with 7,007
  candidates and 15 failures in all. The 15 failures are ACTIVE ads with no single canonical
  unit, so the collector left them out of the files.
- The export added 20,178 ad reads (20,171 records and 7 'missing' rows), 4 building
  reads, 79 stored replies and 101 calls, in 17 files, and each table matches the archive.
- I left the DRAFT ads in the top-up, since they cost about 5 cents a week, though they took
  nearly half its reads.

## Unit histories in the page-crawl areas (Oct 16)

After the top-up, I looked at the 105 ads that run 10 reported as scoped but unread, at or
above the listing-ID cutoff. Runs 5 and 10 scoped them as members of their units, and all 105
appear in the history of an ad those runs read. No area search returned them. I then counted
the IDs in the histories of all the region's ads, and found 2,261 ads at or above the cutoff
with no entry in the archive. The API never read them, and the page crawls got a 404 for 77 of
them and fetched none of the rest. Their IDs run from 1,221,201 to 5,183,637. The other four
regions read their units' older ads, so their histories hold no unread ad above the cutoff.

Ben asked on Oct 15 at 11:47 ET for the collection to capture every listing, so I set the
page-crawl areas to read unit histories like the other regions. A top-up of the region then
reads the 2,261 ads along with its ACTIVE ads and its ads with a status other than RENTED,
NO_LONGER_AVAILABLE or DELISTED. At about 380 ads to a request, they take about 6 requests, plus
reads of any older ads their own histories list.

After #908 merged, I ran `ops/streeteasy-collect topup manhattan-page-crawl-areas` by hand as
run 11, from 09:46 to 09:50 ET. It took 25 requests ($0.03): 3 counts, 2 slices and 20 ad reads.
Three reads of 378 ads timed out at the API, so the collector split them and lowered its batch
to 283 ads. That accounts for 20 ad reads where run 10 needed 6.

- Run 11 read 4,138 ads, and 2,266 of them were new to the archive: the 2,261 above and 5 more
  that unit histories listed after run 11's re-reads.
- Of the 2,266, 2,222 are DRAFT, 31 IN_STREETEASY_REVIEW, 7 ACTIVE (also among this week's
  search hits), 1 IN_BROKERAGE_REVIEW and 1 RENTED, and 4 came back with no record. 2,153 of
  them have no canonical unit, and the run excluded them. So the dataset gains almost no
  listings from these reads.
- The run wrote 146 ad records and 1,872 units, and it marked 1,836 ads superseded.
- `current-listings/api-manhattan-page-crawl-areas` moved to run 11's files, with 1,423 ACTIVE
  ads, 1,421 candidates and 2 failures.
- The export added 4,138 ad reads (4,134 records and 4 'missing' rows), 17 stored replies and
  22 calls, in 3 files, and each table matches the archive.
- Each Friday top-up now re-reads the DRAFT and review ads among them, for about 6 to 10 more
  requests ($0.01) a week.

## Running it

`ops/streeteasy-collect` copies `src/` at its checkout's commit into
`/data1/apartments/runtime/graphql-search-COMMIT` once, read-only, and runs the collector from
that copy with the main checkout's venv and `.env`. Every region writes into the same archive,
`/data1/apartments/archive/crawls/api`, with a lock in it, and each run records its region.
Each ad a run reads joins the run's region and stays in it, so an ad in an area two regions
cover belongs to both. When a run picks units, histories and buildings to read, it starts
only from its region's ads, and a top-up of one region leaves the others' units alone.
The script holds `crawls/oxylabs.lock` while it runs, so collections run one at a time at 60
requests a minute.

```sh
ops/streeteasy-collect backfill manhattan-below-59th manhattan-59th-110th
ops/streeteasy-collect topup
```

- `backfill` reads every ad of each region with its units' histories at or above the cutoff.
  It stops at 4,000 requests for a region and at the first region that fails. Running it again
  resumes the region's latest run with `--reopen`, even after the run finished. On a finished
  run, it counts and reads the new bands from a newer collector's finer split, reads the ads
  and histories still unread, and publishes the region's current ads again.
- `topup` reads the ACTIVE ads of every region and re-reads each region's ads whose status is
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
- After the last region, still holding the lock, the script runs the [raw export](#raw-export)
  from the same runtime and logs its exit status. A failed export makes the script exit 1. A
  backfill stopped by a failed region exits before the export, and the next invocation exports
  its replies.

`ops/systemd/apartments-streeteasy-topup.timer` runs `topup` every Friday at 05:30 New York
time from the master checkout, in the light slice with 2 GB of memory. Ben asked on Oct 15 for
a weekly top-up in place of a daily one. The service and timer go into `~/.config/systemd/user`
as links into the master checkout, and only the timer is enabled:

```sh
ln -s /data1/apartments/serve/master/ops/systemd/apartments-streeteasy-topup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now apartments-streeteasy-topup.timer
```

A backfill holding `oxylabs.lock` at 05:30 delays the top-up until it finishes, for up to 18
hours.

## Raw export

`python -m streeteasy_archive.graphql_export` writes the collector's stored replies out as
Parquet under `crawls/api/export/`, for pipelines that read the API data with DuckDB or pyarrow
in place of the archive's SQLite tables. The collector's tables keep only the latest record of
each ad and building, so the exporter goes back to each reply's body in `bodies/` and writes a
row for each ID the read asked for:

| Table | A row for |
|---|---|
| `ads` | each listing ID of each ad read, with `outcome` 'record' and the record as JSON with sorted keys, or `outcome` 'missing' |
| `buildings` | each building ID of each building read, the same way |
| `requests` | each stored reply, with its Oxylabs job ID, both status codes and its `bodies/` paths |
| `calls` | each timed call, failures included, by its rowid, with its POST count in `attempt` |

A field the API failed to answer gives no rows, since the collector read its IDs again in a
later request. The `record_sha256` of an exported read matches `graphql_search_ads.record_sha256`
for the same ad and reply. Each table has a folder for each run, such as `ads/run-0005/`, and
each file holds up to 250 replies, named by the first and last of their response IDs. The
exporter appends a line for each finished file to `export/manifest.ndjson`, with its rows and
SHA-256. A later export of a run starts above the highest ID in the names of the run's files and
leaves the finished files as they are. With `--run N` it exports that run alone, and with no
`--run` it exports every run. `ops/streeteasy-collect` runs it with no `--run` at the end of
each invocation, so the weekly top-up and each backfill add their replies. The exporter holds
`export/.lock` while it runs and stops with an error when another export holds it, so an export
by hand during a collection can fail the collection's export step.

A database restored from a backup goes back to the backup's ID counter, so the collector can
give a new reply the ID of an exported one, and the `VACUUM INTO` copy can renumber the rowids
of the call table. Before resuming each table of a run, the exporter compares the archive's row
at the last exported ID with the exported row, and it stops with an error when they differ.
After a restore, deleting `export/` and exporting again writes every run afresh.

## Backup

`ops/streeteasy-backup` copies the archive to the second disk, and
`ops/systemd/apartments-streeteasy-backup.timer` runs it from the master checkout at 09:00 New
York time. On Fridays that is three and a half hours after the top-up starts, and a backfill
can run at any hour, so a collector may still be writing during a backup. The steps below allow
for that. Each run goes through these steps:

1. It copies the database with `VACUUM INTO` over a read-only connection, into
   `/data2/apartments-backup/streeteasy-api/db/archive-STAMP.sqlite3`. The copy holds the
   database at a single moment, and a collector can keep writing meanwhile.
2. It runs `PRAGMA quick_check` on the copy and stops if the check reports a problem.
3. It flushes the copy to disk, gives it its final name and deletes all but the newest 7
   database copies.
4. It copies the bodies, the run reports, the current-listings captures and the raw export into
   `files/` with rsync, leaving out the database, the collector's lock and partial `.tmp` bodies. A file gone
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
