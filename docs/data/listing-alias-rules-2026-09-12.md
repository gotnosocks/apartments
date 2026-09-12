# Listing alias reuse and gallery filtering

Implemented after the unit URL audit showed that zero-padded unit labels can identify different historical episodes.

## Rules

- Only exact `/rental/<id>`, `/sale/<id>`, and corresponding `/building/<slug>/rental|sale/<id>` routes share a typed detail identity. Rental and sale IDs are distinct. Unknown query intent, descriptive suffixes, ordinary unit-label URLs and different IDs remain independent.
- Requests for the same identity are serialized within a crawl generation. Other listing IDs retain full concurrency. On success, an alternate route can be superseded only after validating its source capture; failure or missing evidence leaves the alternate route available.
- Reuse requires a successful latest same-generation observation, saved body and matching snapshot, matching embedded listing ID, address, and resolved nonempty category-specific property history with episode IDs and dated price events. Rel=canonical and HTTP 200 alone are insufficient. Missing or unusual history structures fail closed and may result in an additional request. These checks establish reusable payload evidence, not completeness of StreetEasy's entire historical record.
- Alias provenance records the source URL, observation, snapshot, body hash, typed identity and history counts. Observations, collection timestamps and raw bodies are not rewritten or fabricated. No unit labels are normalized.
- Later refreshes fetch again according to their generation and interval. A superseded alias can inherit the freshness of its exact validated source observation, but never its HTTP validators. Changed lastmod evidence can still trigger a refresh.
- Known dedicated `media_gallery` routes are filtered from discovery, direct queue insertion and refresh. Existing pending gallery requests become excluded on resume. Already saved gallery observations and images/scripts embedded in full detail captures remain intact. No image downloads or new cloud browser are introduced.

The queue identity migration changes only frontier metadata and commits its schema and backfill atomically. A `(generation, listing_key, state)` index keeps claims and alias lookup bounded. Saved extraction payloads are read only when there is an actual alternate same-ID capture to evaluate.

## Verification

The final archive/Modal suite passed 131 tests with one integration test skipped. Cases cover same-ID concurrency, successful reuse, incomplete or mismatched payloads, HTTP failures, missing bodies/snapshots, unresolved history, restart recovery, new-generation isolation, refresh intervals, gallery preservation, and schema upgrade.

Deployment uses a committed batch boundary and the existing 10 concurrent / 2 RPS configuration. The previous controller allocated 3,750 of 7,750 requests, leaving 4,000 for the replacement controller. The boundary had 2,003 scoped URLs pending.

The final reuse guard also checks that the archived body file is present; the identity regression suite covers missing-file fallback. Deployed to `chelsea-remote-scrape` and submitted controller `5dc4e967-36f4-4ebb-b1fd-fe4347272a46` with a 4,000-request cap. The existing two-hour monitoring remains in place.

Live saved-page validation found compact hydration copies of the same listing that omit history. The validator now ignores those copies while requiring the full history-bearing object and rejecting conflicting IDs. Caledonia listing 5153964 passes with four episodes and 12 events. SQLite initially chose the URL-order index and scanned the generation for alias lookups; the query now explicitly uses the typed identity index, with an actual query-plan regression test. A controlled child interruption committed the identity migration and scope replay before the corrective deployment; no provider requests had started in that interrupted run.

Final build passed 131 tests (one skipped) and was deployed after the controlled interruption's cloud commit released the writer lock. Replacement controller: `49b12867-4f7d-49b4-ae30-de77c1b8fd68`, capped conservatively at 3,250 requests after the previous controller's 750-request allocation. Concurrency remains 10 with a 2 RPS submission limit.

Live startup applied the final rules: 254 pending gallery URLs excluded globally, including one in the Chelsea scope; two scoped listing aliases superseded. The reused routes were rental 5153964 (Caledonia) and sale 1845810 (362 West 19th Street). Chelsea pending listing URLs fell from 2,003 to 2,000 before new downloads. All 1,809 completed scoped inventory URLs and existing observations remain intact. Scrapy opened at 03:15:15 UTC on September 12.

Post-start verification: the latest ten newly collected responses were all HTTP 200 with no errors (through epoch 1789183010.999).
