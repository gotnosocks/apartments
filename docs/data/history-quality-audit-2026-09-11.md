# Chelsea saved-history audit — September 11, 2026

The audit supports continuing collection. It made no StreetEasy or Oxylabs requests: a separate read-only Modal worker inspected committed archive metadata and saved bodies. It took about 211 seconds after worker startup. The live scraper was not interrupted.

## Evidence

- 1,217 captured unavailable-rental inventories passed the displayed-row and embedded-summary count checks.
- Their 25,535 distinct-within-inventory detail links have 25,534 direct saved captures. The remaining rental/5138062 returns HTTP 308 to building/225-west-28th-maverick-chelsea/3h; that destination is saved as snapshot 70. This accounts for all links in the captured inventories, not all possible Chelsea buildings.
- Dense examples, each with all inventory detail links directly captured: Caledonia 645, Abington House 576, Tate 459, Westminster 419, Ruby Chelsea 405, Sierra 393, 3 Eleven 381, 507 West Chelsea 326, TEN23 119.
- All 306 sampled detail bodies decoded successfully and contained embedded rental history; 199 contained more history events than their rendered table.
- 22 sampled pages contained at least 100 events; 58 spanned at least ten years. These are page statistics, not unique physical-unit statistics.
- TEN23 3B: 400 events, 2012–2026; 7H: 297 events, 2014–2025; 4C: 102 events, January 31, 2015–September 4, 2026.
- TEN23 4C matched all six user-supplied date/price pairs: 2015-01-31 $3,120; 2015-02-01 $3,315; 2015-02-02 $3,315; 2018-01-24 $3,375; 2018-01-25 $3,370; 2018-01-26 $3,365.
- Sierra is the building at 130 West 15th Street. Its 393 unavailable-rental rows and linked detail pages are captured. Sampled Sierra 10A contains 15 events spanning 2011–2025.

## Sampling and limitations

The sample contains 206 selected pages emphasizing dense inventories and TEN23 4C, plus 100 hash-selected rental URLs from the captured generation. It is not a representative sample of all physical Chelsea apartments. It verifies source data retention, not an independent census or agreement with every live expanded history.

Inventory rows and listing URLs are not unique physical units. Historical source labels can be numeric and require later reconciliation. Bedroom counts appeared in all 306 embedded details; square footage appeared in 78. Current attributes must not be retroactively treated as known historical attributes. Collection timestamps remain in snapshots.observed and observations.fetched.

Pending building pages can discover additional inventories. The archive still has unresolved HTTP outcomes and the entire scoped queue has not drained. Do not interpret complete captured inventories as complete Chelsea coverage.

## Reproduction

Run `modal run models/modal_history_audit.py --output /tmp/chelsea-history-audit.json` using the project environment. This launches only a read-only cloud audit. The script includes redirect-destination checking added after the initial run; that one redirect was verified separately against the live archive.

Detailed sample evidence (URLs, snapshot IDs, body hashes, raw events) and the chart are saved locally in `data/exports/history-audit-2026-09-11/`. These are small audit exports, not an archive/database download. The chart is a presentation of saved source data and does not interpolate between listing episodes.

During chart setup, `uv run` replaced the local environment while attempting project resolution. The environment was rebuilt on its original Python 3.14 with the project's declared extras; Modal remains pinned to 1.5.5. Worker-control and archive-import tests passed (24 tests). The running cloud deployment and archive were unaffected. Use `uv run --no-project` outside the project for isolated presentation tools.
