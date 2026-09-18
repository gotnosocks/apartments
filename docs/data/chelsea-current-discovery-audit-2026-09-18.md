# Chelsea current rental discovery audit — 2026-09-18

The 13 refreshed ACTIVE candidates are a selective search result, not current Chelsea market coverage. Saved search pagination also repeats ordinary listings: counting cards until their sum equals the header total is insufficient. This audit made **zero requests**. The root task separately acquired four saved Oxylabs search probes; all inspection and parser validation here used local bytes.

## Reviewable evidence

- `data/model/chelsea-current-discovery-audit-20260918`: immutable archive/candidate audit, 33 source-linked archived rental-search observations, two initial root probes, and replay script. `audit.json` SHA256 `f3dfb1621212fef7d27e329f4f2db3e67ed91e0b35eb41cd9c3edf31e57a8c1f`.
- `data/model/chelsea-current-search-four-page-audit-20260918-v2`: current immutable `pages.jsonl`, `coverage.json`, replay script, source/implementation hashes. Coverage SHA256 `10627d8ca08feab78391e8cb777e8afe5163979a66f35459daa46738f43f395c`. The earlier `chelsea-current-search-four-page-audit-20260918` remains unchanged; v2 binds its manifest and verifies identical saved bodies and ordered card IDs/URLs/placements.
- Raw current bodies and provider metadata: `data/probes/chelsea-current-search-preflight-20260918/{chelsea,chelsea-page2,west-chelsea,west-chelsea-page2}`. Each is one successful provider submission, HTTP 200. Request clocks are 21:47:13–21:49:31 UTC; these are capture clocks, not advertisement update dates.
- Parser: `src/apartments/rental_search.py`; focused tests: `tests/test_rental_search.py`. All 47 tests passed; parser additionally accepted all 33 archived pages and all four fresh probes. No crawler integration or analytical changes.

## Current candidate and archive state

The verified 16:00 UTC candidate snapshot has 297 latest ACTIVE advertisements. The seven-day selector retained 23, excluded three recent furnished/concession cases, and rejected 271 stale captures (September 7–11). Refreshing the 23 retained advertisements yielded 13 ACTIVE, five RENTED, four NO_LONGER_AVAILABLE, and one IN_CONTRACT, with no failed target. The 271 older ACTIVE records have not been refreshed; collection should also reconsider the three previously excluded product-scope cases before applying analytical filters. Thus 274 previously ACTIVE advertisements remain outside that refresh, before overlap with fresh discovery.

A 30-day candidate selection retains 254 advertisements and excludes 43 furnished/concession cases. The existing candidate-refresh CLI has a hard maximum of 100 targets and no batch/subset option. Widening its age window and supplying `--max-targets 100` does not truncate safely: it fails on the 254 selected targets. It also cannot discover newly listed advertisements.

The scoped archive generation's queue is drained, despite its `active` label; unrelated global pending work is not missing Chelsea work. Its 1,311 building roots and source observations are historical. Database modification time is not collection freshness. The audit read SQLite with `mode=ro` and `query_only`; constructing `ArchiveStore` merely to inspect status could migrate the database.

## What the primary search source says

The configured rental seeds, copied from `src/streeteasy_archive/scope.py`, are:

- `https://streeteasy.com/for-rent/chelsea`
- `https://streeteasy.com/for-rent/west-chelsea`

Both historical and fresh templates have one `main`, a primary `ListingCardsList_listContainer`, and ordered `listing-card` elements. Each observed full page contains two featured cards, one in-feed card, and 11 regular cards. Original address-link queries identify `featured=1` and `infeed=1`; the existing URL canonicalizer removes these, so placement must be captured first. Navigation/recommendation links outside the primary list are excluded.

Parser v2 requires supported rental detail routes (`/rental/id`, `/building/slug/rental/id`, or `/building/slug/unit`) and rejects collection, media, action, sales, and bare building routes. Embedded rental-path IDs must match the source advertisement ID. URL equality alone is not sufficient. Coverage separately reports `listing_identity_conflicts`, including source-linked occurrences within/across pages and seeds, and excludes those IDs from ordinary duplicate lists. A matching advertisement rental route plus a single unit route is recorded as `compatible_advertisement_url_aliases`; this does not infer a physical-unit merge or replace either URL. Multiple unit URLs or differing building paths remain conflicts. Ordered page signatures now include canonical URLs. No conflicts or aliases occurred in the four fresh pages or 31 explicit archived numbered pages; all previously reported card counts and overlaps remain unchanged.

The saved Flight container independently supplies ordered `listings` edges with explicit `FeaturedRentalEdge`, `SponsoredRentalEdge`, and `OrganicRentalEdge` types. The parser requires exact ordered DOM/edge URL and placement agreement, and binds each ID/address/price/area to its edge/node JSON path and hashes. It preserves reported gross/net-effective/concession and amenity scalars without promoting them to corrected analytical values. West Chelsea in-feed cards can be in Hudson Yards; placement in the list does not prove neighborhood membership.

The fresh header counts are 264 Chelsea and 81 West Chelsea. Chelsea includes West Chelsea advertisements, so these totals are not additive. All four probes show default sorting. Exact source evidence at Flight `/a/3/children/3/paramsState/sorting` reports `RECOMMENDED`, `DESCENDING`; the contextual block agrees. The header flag `isPerEnhancedListingInsightsEnabled` is true. The parser preserves these values, sort-button attributes, and experiment metadata. Different probe randomization GUIDs and default ranking could motivate an ordering investigation, but these facts do not establish the cause of repeats. `searchMetadata.url` is literally `https://streeteasy.comundefined`; it cannot authenticate scope. The actual request URL, H1, and pagination route do that.

| Source set | Regular occurrences | Unique regular ad IDs | Repeated regular IDs |
| --- | ---: | ---: | ---: |
| Archived Chelsea explicit pages 1–24 | 261 | 178 | 63 |
| Archived West Chelsea explicit pages 1–7 | 77 | 53 | 19 |
| Fresh Chelsea pages 1–2 | 22 | 16 | 6 |
| Fresh West Chelsea pages 1–2 | 22 | 19 | 3 |

The historical regular occurrence totals exactly match the displayed totals, while unique IDs do not. The explicit page-1 URL and base URL are alternate captures, not separate pages. Historical regular union is 191 IDs; 40 are in both seed sets. Fresh regular union is 33 IDs, with two cross-seed overlaps. Fresh same-seed repeats within approximately two minutes demonstrate that this issue cannot be dismissed solely as days of capture drift.

Fresh Chelsea repeated organic IDs: `5064558` (Ruby Chelsea N17D), `5135371` (21 Chelsea 613), `5141414` (21 Chelsea 402), `5148675` (Chelsea Tower 30A), `5160152` (Chelsea Tower 20F), `5162288` (Ruby Chelsea S20L). Fresh West Chelsea repeats: `5120305`, `5161356`, `5161879` (3 Eleven). Exact positions, URLs, source roles, field references, clocks, and hashes are in the four-page artifact. Featured and regular placement can also repeat the same advertisement within one page; both observations are retained.

## Pagination and a bounded collection plan

Observed first-page next links are `?page=2`. Fresh page 2 next links are `?page=3`. The furthest displayed page links are 24 for Chelsea and eight for West Chelsea, versus seven for the archived West Chelsea set. These are **displayed terminal hints**, not a guarantee that all pages or unique inventory have been obtained. Historical terminal pages have valid matching H1/current-page markers and a previous link but no next link.

The existing capture-only command performs one Oxylabs submission, retains request/body/response/extraction/metadata, and does not enqueue buildings or write the archive database:

```sh
.venv/bin/python -m streeteasy_archive.probe \
  https://streeteasy.com/for-rent/chelsea --mode html \
  --output data/probes/NEW-UNUSED-PREFLIGHT/chelsea

.venv/bin/python -m streeteasy_archive.probe \
  https://streeteasy.com/for-rent/west-chelsea --mode html \
  --output data/probes/NEW-UNUSED-PREFLIGHT/west-chelsea
```

These are reviewed command templates, not additional requests made by the audit. Use a new output directory per capture. The completed four-page probes already satisfy this preflight. HTTP 200 alone is insufficient: the offline parser rejects challenge bodies, ambiguous/missing primary containers, unknown role/placement contracts, mismatched source identities/counts, unsupported URL filters, and inconsistent H1/page/next links.

A bounded next collection could follow only each accepted page's **observed next URL**, stopping at a validated terminal page or explicit request ceiling. Current displayed hints imply 32 total page requests, of which four are already captured: approximately 28 additional requests if pagination does not change. Set a hard ceiling and retain the reason when it stops. Do not construct speculative URLs or revisit base and `?page=1` as independent inventory pages. Record each ordered page signature, all repeated IDs, changing header totals, failures, and cross-seed overlap. A closed next-link chain is a separate observation from completeness of unique inventory; the parser always leaves market-census establishment false.

Only after reviewing the page coverage evidence should a detail-refresh stage deduplicate in-scope IDs across regular and promoted observations, join already known ACTIVE advertisements, and refresh their exact source-bound detail URLs. At the observed 14 cards per page, 32 pages provide at most 448 card occurrences before deduplication/scope filtering; adding the 274 previously unrefreshed ACTIVE ads gives a conservative 722-detail ceiling before overlap, not a forecast of 722 distinct available apartments. Actual requests should be based on the deduplicated published manifest. Capture currently inactive outcomes too; absence from a search page is not evidence that an old advertisement is rented. Product-scope exclusions belong after collection.

The broad `streeteasy-archive update --neighborhood chelsea --transport oxylabs --no-include-unavailable` workflow is unsuitable for this bounded rental pass: its six configured seeds include sales and building directories, it restores known building/search scope, and the crawler prioritizes buildings ahead of remaining search pages. A small generic request budget therefore does not bound the intended rental pagination alone. Reconstructing scope also reads large historical extraction payloads from the roughly 149 GiB database.

Remaining implementation needs are an explicit rental-search capture orchestrator with manifest/request ceiling, reviewed handling of unstable recommended ordering, and a bounded detail-target batching interface. The offline parser supplies observations and coverage diagnostics; it intentionally makes no requests, changes no status, and does not infer completeness or analytical eligibility.
