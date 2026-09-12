# Building queue duplicate audit

Read-only audit of the live cloud archive at epoch 1789173649 (September 12 UTC; September 11 local). No provider calls or queue changes were made.

## Results

| Building URL form | Completed | Pending | Total |
|---|---:|---:|---:|
| Main URL, no query | 1,311 | 0 | 1,311 |
| similar=1 | 101 | 8 | 109 |
| unit_type=rentals | 266 | 1,041 | 1,307 |
| unit_type=sales | 154 | 439 | 593 |
| Total | 1,832 | 1,488 | 3,320 |

All 3,320 URLs map to 1,311 roots. All 2,009 variants already have a main-page capture. The 521 completed variant URLs each have one observation in this generation and a latest HTTP 200 response. Thus 28.4% of completed building-page requests were alternate views of buildings already represented by main URLs. This percentage concerns building requests, not total scraper spend. The already-used requests cannot be recovered; 1,488 currently pending requests are avoidable under the recommended normalization.

This explains why the completed queue count exceeded the approximately 1,500 buildings-on-residential-lots public-data proxy. The 1,832 count was URL requests, while the distinct StreetEasy IDs total 1,311. Differences between city tax lots, physical buildings and StreetEasy IDs still remain; normalization does not itself prove geographic completeness.

## Saved-page comparisons

Compared 12 main/variant pairs: four similar=1, four unit_type=rentals, four unit_type=sales. Every pair matched on canonical URL, primary building attributes (ID, slug, name, type, residential units, floors, year built, address, amenities, policies), rental and sale unavailable-summary counts, and selected tabs. This is a targeted sample, not byte-for-byte equality across every capture. The raw pages may contain dynamic differences.

Examples include 100 West 15th Street, 100 Eleventh Avenue, 110 Ninth Avenue, and 111 West 17th Street. Similar=1 appears in recommendation links. Both main and variant pages identify the no-query main URL as canonical.

## Root cause

`src/streeteasy_archive/extract.py:canonical_url` drops parameters in `_TRACKING`, but that allowlist omits `similar` and `unit_type`. `kind_for` classifies each main-path query variant as a building. `scope.py:expand` accepts a discovered URL when its building_root is known; the frontier then deduplicates only exact URL strings. A valid in-scope page can therefore have multiple scheduled identities.

## Recommended remediation

1. Normalize the known presentation/referral parameters for main building URLs before discovery, scope enrollment, and frontier insertion: similar=1 and unit_type=rentals|sales. Keep a record of the original URL and discovery source. Unknown parameters and other resource paths require explicit treatment rather than blanket query stripping.
2. Give each capture a stable key including canonical resource and capture intent. Preserve distinct expanded unavailable-rental and unavailable-sale inventories (`archive_view`) and real pagination. A main-page capture does not satisfy an expanded inventory capture.
3. At a committed batch boundary with no writer, run an auditable migration. Recheck each pending variant's main URL has a successful capture in this generation, then mark the variant superseded with alias_of/reason evidence. Preserve old observations and bodies; do not pretend unsent requests succeeded. Expected dry-run impact: 1,488 pending URLs superseded, zero main roots lost.
4. Learn aliases from observed redirects and rel=canonical, constrained to the same property and equivalent capture intent. Apply alias checks before provider submission, not just during extraction.
5. Add meaningful regression checks: all three variants collapse; rediscovery does not re-enqueue aliases; capture intent and pagination survive; a main-page error does not suppress the only valid work item; resume and later refresh generations still work.
6. Report unique building identities, main captures, inventory captures, and URL attempts separately. A later incremental run may intentionally refresh a canonical building once; this is separate from duplicate URLs within a backfill generation.

The 1,809 completed expanded inventory captures are separate from this duplicate building queue and should be preserved. This audit does not authorize deduplication of distinct historical listing episodes, which may carry different attributes.

## Evidence

Small local exports are in `data/exports/building-queue-audit-2026-09-12/`: summary.json, comparisons.json, and sample-provenance.json (URLs, archive body hashes and observation counts). All large reads and HTML comparisons ran on Modal. No mutation to the running scrape was performed.

## Implemented correction and unit audit

The approved correction now normalizes only the known main-building view parameters before enqueueing. SQLite records alias provenance in `url_aliases`, and queued aliases with a successful same-generation main capture become `superseded`. Existing observations, snapshots, and completed URL rows remain intact. Scope membership transfers to the canonical queue item. Incremental refresh groups prior URL variants into one canonical request and retains only that exact URL's validators and freshness. Expanded inventories, unknown query parameters, pagination, and unit-label spellings remain separate.

The migration runs under the existing writer lock at CLI startup, before any provider request. Its reviewed cloud dry run found 2,028 building aliases globally: 1,488 eligible pending requests, 521 already completed variants, and 19 aliases without a successful current-generation main capture. The latter are not retired by this migration. The 1,488 eligible retirements are all in the Chelsea scope. Claim-time normalization still queues an unfetched canonical target, transfers scope, and records supersession; it never pretends the target was fetched.

Archive status and the local browser now separately report distinct captured main URLs, expanded inventory captures, completed building URL rows, and superseded requests. These remain source-resource counts, not a claim of physical-building or unit completeness. No cloud browser or database mirror was added.

### Unit audit results

The frozen queue contains 121,989 scoped listing-detail URLs: 116,314 done, 5,665 pending and 10 left in flight by graceful shutdown (recovered on resume). These are URL records, not physical units. None contains query parameters. No two latest successful saved listing bodies had identical content hashes; this is a byte-level check, not proof that page content is semantically distinct.

- 51 groups / 108 URLs share a numeric rental or sale ID, with 57 extra URL forms. Some are nested building routes and some are media-gallery routes. Only three URLs in these groups remain pending, across two IDs: sale 1845810 (both forms unfetched), and rental 5153964 (a nested form already captured). These are a small candidate for future identity-based consolidation, not a broad source of remaining cost.
- 533 groups / 1,073 URLs have potentially equivalent labels after case/zero normalization, containing 453 pending URLs. This is deliberately a candidate count: **do not strip the zeroes in the scraper**.
- Compared eight already-saved label pairs from eight buildings. All eight pairs identify different listing IDs, all eight have different property-details hashes, and two have different property histories. Each page retains its own canonical URL. At 520 West 28th, `/0007` identifies listing 3059501 and `/7` identifies 1772069, with two versus three history episodes. At Lantern House, `/0610` and `/610` identify 4683031 and 1618713, with three versus two episodes. At 3 Eleven, `/0304` and `/304` share the displayed unit and history but retain different listing IDs and attributes.
- Also inspected eight numeric-ID groups, including both groups with pending work. Five complete direct/nested pairs match listing ID, canonical URL, property details and history; a sixth direct form is an observed redirect to its already captured nested counterpart. Gallery forms can omit history entirely. The remaining two groups do not yet have both sides captured. No zero-padded unit aliases or different historical IDs are automatically merged.

This supports the intended point-in-time model: physical-unit reconciliation belongs in derived analysis, while each listing's original attributes and history remain available in the archive. The raw comparisons used no Oxylabs requests.

### Verification and operation

The full archive/Modal regression suite passed with 110 tests and one skipped integration test. Coverage includes migration dry run, idempotence, restart and rediscovery, missing/failed canonical captures, same-generation evidence, scope transfer, exact-URL validators, incremental refresh, retained inventory intents, and reporting counts.

The running scraper was interrupted with SIGINT to its child process; it completed its responses, exited successfully, checkpointed, committed the cloud volume, and released its writer lock. The controller stopped at the requested batch boundary. Its request allocation was 2,250 of 10,000, leaving a conservative 7,750-request cap for the replacement controller. The corrected deployment retains 10 concurrent requests and 2 requests/second.

Verified live at epoch 1789175516: replacement controller `dc1437f3-a979-4ce3-b742-08c605422286` applied all 1,488 retirements and recorded 2,028 alias mappings. The Chelsea scope has zero pending building requests and retains all 1,809 completed inventory URLs. The first 88 new responses were HTTP 200 with zero errors. At that instant, 5,580 listing URLs were pending and nine in flight. The batch will checkpoint and commit through the existing controller procedure. Small reports: `queue-preview.json`, `unit-pairs.json`, and `resume-verification.json` alongside the earlier audit exports.
