# Validation — 2026-09-07

- Python 3.14.0; Scrapy 2.18.0; dependencies pinned in `uv.lock`.
- `uv run pytest -q`: **27 passed**. Tests use synthetic responses; no test sends
  requests to StreetEasy. Integration tests run the actual Scrapy engine through
  a fixture download handler.
- Coverage includes crash recovery, transactional discovery rollback, body dedup,
  conditional requests and 304 rediscovery, lastmod/deferred revisit behavior,
  403/429/503 cooldowns, redirects, CLI locks, stale HAR captures, archive
  relocation, and extraction of HTML, JSON, gzip sitemaps, and React Flight.
- Supplied HAR: four entries, two relevant StreetEasy HTML responses imported.
  Second import: **zero new observations**. The two decoded response bodies pass
  SHA-256 and length verification. The JSONL export contains both observations.
- Frontier after HAR import: 393 URLs total; two done, 391 pending. Includes 14
  listing URLs, 17 building URLs, eight directory URLs, 352 search URLs, the
  sitemap index, and the imported homepage. These are discovered URLs, not
  collected listings or evidence of complete historical coverage.
- One direct building-page probe returned **HTTP 403**. The probe used no cookies,
  account, terms acceptance, or challenge workaround. No subsequent live request
  or full crawl was run. The fixture tests establish behavior, not live access.
- Implementation and independent integration tests were delegated through Herdr
  to two `gpt-5.6-luna` agents, then reviewed and integrated by the parent agent.

Local data and the export are under `data/` and are ignored by Git/Jujutsu. The
original HAR was not copied into the repository. No crawler process is left
running. `status: active` means an unfinished generation, not a running process.

## Local browser follow-up

- Added a read-only Flask/Waitress app against the same live archive, with server-side
  pagination, URL/type/state filters, generation selection, source and extraction
  views, metadata, historical observations, and a 10-second overview refresh.
- API tests verify captured-detail counts, queued URLs, live updates, history,
  attachments, source-as-text, invalid-input handling, and read-only routes.
- JavaScript syntax checked with `node --check`; local route and API responses
  verified. Browser automation was unavailable, so no visual/browser interaction
  QA is claimed.
- Listing detail URLs now have indexed queue priority over search pages. A
  search-to-detail regression verifies full detail body, JSON, and history capture.

## Firefox building pilot — 2026-09-07

The prior HTTP 403 diagnosis is superseded for the tested Firefox transport.
Stock installed Firefox 156 + Selenium 4.48/geckodriver, fresh headless profiles,
no proxy/account, captured TEN23 at 500 West 23rd Street through the real Scrapy
crawler and SQLite archive:

- Initial budget of 3: building page, media gallery, apartment 4C; all HTTP 200.
- Resume budget of 4: apartments 4E, 8D, 9H, 6F; all HTTP 200. Previously completed
  pages were not fetched again. Each of these five unit pages contains two tables
  and 93–95 scripts, including price history and embedded data.
- One intervening local decoder error on 4E paused the queue. It was fixed and
  the local-error cooldown cleared; the subsequent resume succeeded. The failed
  observation remains visible as historical diagnostic evidence. It was not a
  StreetEasy 403 or rate-limit response.
- String-valued BiDi response data is browser-decoded text and is UTF-8 encoded;
  base64-valued data is decoded as bytes. Do not infer wire-byte fidelity from
  string data. Native BiDi payload retention was added for the resumed run.
  An attempted offline encoding conversion failed before any writes; the first
  three captures were not modified or re-downloaded (only representation metadata
  was clarified).
- Showcase/similarHDP2 tracking aliases are now normalized. Queued obsolete aliases
  are retired without downloading; owner-export and media-gallery endpoints are
  excluded from future listing discovery. The gallery already captured remains.
- Evidence: ignored data/diagnostics/building-smoke.log and
  data/diagnostics/building-resume-fixed.log; observations 4–6 and 8–11.
- Offline tests: 30 passed, 1 opt-in browser test skipped. Explicit browser test:
  2 passed, covering scope/resume plus real Firefox loopback HTML Unicode/NUL,
  exact UTF-8 fixture content, conditional 304, and prevention of redirect/image
  requests. No live site requests are made by the test suite.
- Local app API at http://127.0.0.1:8765/api/summary reads the live archive and
  reports no active writer. This pilot is not a complete building history or a
  neighborhood backfill; scoped work remains queued for explicit later runs.

## Chelsea scoped worker — 2026-09-07

Two Herdr gpt-5.6-luna agents reviewed geography and embedded data. Chelsea area
115 includes West Chelsea 163; Hudson Yards 146 is outside this hierarchy.
Persistent scope tables and profile prevent an unqualified resume from crawling
the pre-existing citywide queue. Tests cover unrelated neighborhoods, global area
dictionaries, historical-link provenance, offline completed-page reuse, scope
persistence, and inline Flight records. Existing tests: 33 passed / 1 skipped;
subsequent scope suite: 4 passed after adding the inline-record regression.

One live directory diagnostic returned 403, archived as a coverage gap with a
900-second cooldown (until 17:15:29 EDT). No live requests were issued while
preparing the worker after that challenge. The worker waits for this cooldown,
then uses stock Firefox, concurrency one, average 60-second delay, no proxy,
no account, and no automatic retry or identity switching on another challenge.
Complete neighborhood/off-market coverage is explicitly unverified.

Worker launch verified: PID 82451, detached process, log at
`data/chelsea-worker.log`; profile reports Chelsea / Firefox / delay 60, 64 scoped
pending URLs and 7 completed scoped URLs. Local `/api/summary` reports the writer
active and the cooldown until 17:15:29 EDT. Archive browser restarted with the
scope status UI. Final targeted scope + Scrapy integration checks: 7 passed.

## Pacing trial — 2026-09-07, 17:28–17:31 EDT

Gracefully stopped the 60-second worker and resumed four queued pages with a
45-second configured delay, retaining concurrency one and stop-on-challenge.
Observations 24–27 all returned HTTP 200 with archived bodies and no new error or
cooldown. Mean spacing between successful responses was 54.35 seconds, versus
74.48 seconds across 11 successful responses in the preceding baseline. This
small sample does not establish a safe detection threshold or long-run success.
The unlimited scoped worker resumed at 45 seconds (PID 85518); current PID and
command are recorded in data/chelsea-worker.json. Delay remains randomized,
22.5–67.5 seconds before browser overhead/AutoThrottle effects. No concurrency,
proxy, fingerprint, account or challenge-handling changes were made. A Luna
review attributed existing callback warnings to subresource interception races;
the archived main-document bodies were present. Detailed trial evidence is in
data/diagnostics/speed-trial.json and data/chelsea-speed-trial.log.

## Second pacing trial — 2026-09-07, 19:07–19:10 EDT

The preceding 45-second worker handled 101 observed responses before shutdown
was requested: 93 HTTP 200 and 8 HTTP 308 redirects, without a new challenge or
cooldown. Mean spacing among successful pages was 60.68 seconds (including time
spent on intervening redirects). Graceful shutdown drained its pending request.

Four queued pages at a 35-second configured delay (observations 130–133) all
returned HTTP 200 with no errors, averaging 42.11 seconds between saved responses.
The unlimited Chelsea worker resumed at 35 seconds, PID 93034. Concurrency remains
one, delay randomized 17.5–52.5 seconds before browser/AutoThrottle overhead, and
new challenges stop the worker. This sample is not proof of long-term reliability.
Evidence: data/diagnostics/speed-trial-35.json and data/chelsea-speed-trial-35.log.

## Error repair — 2026-09-07, 20:27 EDT

The new 404 (observation186, OHM `/d`) was an extraction artifact. In archived
observation148 (`/rental/902386`), `/documents` is split across two Flight script
chunks as `/d` and `ocuments`. Reassembling text chunks before URL discovery and
scope JSON parsing removes the false unit URL. Extraction version2 was applied
offline to160 saved snapshots;23 obsolete URLs (split fragments, previously
normalized tracking aliases and excluded endpoints) were retired. Raw responses
and observations remain unchanged. Repair details: data/diagnostics/chunk-reassembly-repair.json.
A Luna agent traced the 404 independently (Herdr was unavailable).

Firefox interception now uses Selenium's public BiDi event/command APIs directly,
so completion errors occur inside our handler rather than deferred reconciliation
outside its exception boundary. Already-cancelled subresources are counted as
warnings; unexpected errors/timeouts are retained in capture metadata and pause
further crawling after saving the main document. Shutdown stops processing new
asset callbacks. Local browser checks passed for Unicode HTML, conditional304,
redirect/image blocking; unit regressions cover stale requests, other intercepts,
real failures, headers and shutdown. An additional regression verifies the main
body is saved before pausing on an interception failure.

A two-request live check saved HTTP308 and HTTP200 responses, with no uncaught
callback exceptions. The successful page recorded one cancelled-subresource
warning and zero interception errors. This does not guarantee no future browser
failures. TLS verification remains enabled using Scrapy's current
DOWNLOAD_VERIFY_CERTIFICATES setting. Dashboard unresolved issues now excludes
errors superseded by a successful response and retired URL artifacts; original
errors remain in page observation history. Test and smoke logs are retained.

Final verification:39 standard tests passed,1 opt-in browser test skipped; explicit
browser test suite passed3 tests. Continuous worker restarted at saved35-second
pace (PID9315); local dashboard restarted (PID9316). API confirms writer active,
no cooldown, and only the earlier directory403 remaining as an unresolved issue.
