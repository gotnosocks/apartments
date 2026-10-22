# Past rentals without browser rendering (probe, 2026-10-13)

Question: can we get each building's past rentals (today: Oxylabs render='html' plus
browser_instructions that click "View unavailable units") without browser jobs?

Answer: yes. One plain (no-render) Oxylabs GET to StreetEasy's GraphQL API returns the list,
in 1 to 4 s instead of ~21 s typical / 141 s p90 for the browser job.

## What the modal calls

GraphQL at https://api-v6.streeteasy.com/ (Apollo Router behind CloudFront, client
"bdp-frontend-service"). Query text lives in JS chunk bdp-2022/_next/static/chunks/8079-*.js
(module 37015). Clicking "View unavailable units" fires:

- `GetBuildingUnavailableRentals($buildingSlug)`: `buildingBySlug(slug).rentalInventorySummary.unavailableListingDigests`
  { id displayUnit price bedroomCount fullBathroomCount halfBathroomCount livingAreaSize offMarketAt
  availableAt status leaseTermMonths monthsFree leadMedia.floorPlan }. Exactly the modal rows: one per
  unit, latest listing.
- `GetRentalsHistoryByBuildingId($buildingId)`: `rentalsHistoryByBuildingId(id)`, where buildingId is the
  numeric id in the plain building page's flight data (liberty-toye = 4088). Returns every past rental
  listing for the building (the "Export all rental history" source), as RentalListingDigest, so it also
  takes status, availableAt, createdAt (list date), noFee, monthsFree, leaseTermMonths,
  interestingPriceDelta. No pagination.
- `GetUnavailableSalesListingDigests` (sales).

The plain building page SSR carries `unavailableRentals: {"0":[],...}`, i.e. no rows.

## Replay

- Direct from thelio (no proxy): blocked by PerimeterX (captcha on click, then "Access denied"; direct
  POST to api-v6 returns a PX 403).
- Oxylabs universal, POST (http_method=post + base64 content): faulted with 613 twice.
- Oxylabs universal, GET, no render: works.
  `url = https://api-v6.streeteasy.com/?query=<urlencoded>&variables=<json>` with
  `context: force_headers` and header `apollo-require-preflight: true` (required, otherwise Apollo
  returns 400 CSRF). 1.0 to 2.3 s single query, 1.3 s for a 6-query batch, 4.1 s for a 218 KB response.
- Batching: GraphQL aliases put several buildings in one GET (3 buildings x 2 queries in one
  1,591-char URL worked). Limits untested.

## Completeness vs rendered captures

Digest ids vs modal /rental/ ids: liberty-toye 197/197, 16-st-marks-place 45/45, 240-east-9-street
20/20, 331-east-9-street 20/20, bowery-place-i 186/186. Zero missing, zero extra.

History rows vs modal rows: liberty-toye 625 vs 197 (2013 to 2026; RENTED 457, NO_LONGER_AVAILABLE 147,
DELISTED 21), 16-st-marks 109 vs 45, 240 E 9th 56 vs 20, 331 E 9th 77 vs 20. All fields non-null on
the 625 rows except size (6 null), monthsFree (32), leaseTermMonths (32). For comparison the East
Village crawl fetched 405 of liberty-toye's 428 non-modal listings as /rental/ pages, and 110 unit
pages' propertyHistory covered 535/625.

## Dead ends

Sitemap index (nyc_sitemap_index.xml) no longer lists buildings, units or listings.

## Cost of the probe

Oxylabs: 1 render, 10 plain (+2 POSTs that faulted). Direct from thelio: ~7 page/XHR requests.
The running Brooklyn crawl was not touched.

## Caveats

Unofficial API; could change or tighten PX, so keep the render path as a fallback. Batch-size
limits and behaviour at crawl concurrency untested. History rows don't replace /rental/ detail
fields (description, amenities).

Evidence on thelio:
/home/ben/code/apartments/.claude/worktrees/bridge-cse_01Dipb7xBSGy2bpJffQMQC3K/data/probes/no-render-20261013/
(README.md, oxylabs/calls.jsonl, replay/queries.py, mkget.py, mkbatch.py, js/8079-*.js).

## Pilot, 30 buildings (2026-10-13)

Evidence: /home/ben/code/apartments/data/probes/no-render-20261013/pilot/ (analysis.txt, requests.jsonl).
Stuy Town/PCV, Flatiron/Gramercy, Greenwich Village, East Village, NoMad; includes Zeckendorf Towers
(645 units), Hilary Gardens, The Caroline, The Vanguard, and two 1-row buildings.

- Digests vs rendered modal: 19/30 exact. The other 11 differ only by capture-date drift: 8 extra
  digests all went off market 2026-10-07..12 (after the capture), and rendered rows now missing from
  the digests are older listings of a unit that has since had a newer listing; all of them are in the
  history query.
- History is 3 to 4x the modal: Zeckendorf 1668 vs 527, Caroline 1703 vs 421, One Union Sq 1272 vs 418,
  Vanguard 1025 vs 241. Every digest id appears in its building's history; no duplicate ids.
  240 1st Ave returned exactly 200 rows (possible cap; being checked).
- Batching: the limit is Oxylabs' 8,192-char `url` parameter, not Apollo. With GraphQL fragments a
  building costs ~230 chars: 20 buildings = 4,756 chars, 3.2 s, 1.15 MB; 30 = 6,865 chars, 6.3 s,
  3.6 MB. Run 20 to 25 per GET.
- Latency at concurrency 4: 1 building median 2.6 s / p90 5.0 s; 5 buildings median 2.8 / p90 4.8.
  0 failures in 22 data requests (no PX blocks, no 613s).
- Unit linkage: RentalListingDigest has `unit`, `slug`, `urlPath`, `buildingId`. `slug` is constant
  across a unit's listings, so (buildingId, slug) ties each listing to one unit page
  /building/{building-slug}/{slug} without fetching it. A few very old listings have null unit/slug.
- Oxylabs used: 26 plain, 0 render.

### Is 200 a page cap? No.

`rentalsHistoryByBuildingId` takes only `id` (limit/first/offset/page/perPage/after/startDate all return
"Unknown argument"), and the JS uses no paging. 240 1st Ave's 200 rows span 2006-12-14 to 2025-12-08,
include all 77 rendered modal rows, and cover every one of the 65 unit pages archived for the building
(normalise zero padding: API "03a" = URL "3a"). Other Stuy Town buildings return 230, 297, 212, 96, 83.
Total Oxylabs use for probe + pilot: 27 plain, 1 render.
