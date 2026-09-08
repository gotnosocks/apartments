# StreetEasy Archive

Python + Scrapy crawler for an evolving local archive of public NYC listing and
building pages. It stores original HTTP response bodies, not just a fixed table of
listing fields. Git and Jujutsu share this repository.

**Coverage is best effort, not a claim that every historical listing is public.**
On September 7, 2026, a direct public building-page probe returned HTTP 403. No
account was created, no terms were accepted, and no challenge was bypassed. The
supplied HAR contains the homepage and a Chelsea rental search page, not a full
listing or building-history browsing session. Offline tests and HAR import can
validate the archive without resolving that live-access limitation.

## Install

```sh
cd ~/code/streeteasy-archive
uv sync --extra dev
```

## Local archive browser

```sh
uv run streeteasy-archive serve --port 8765
```

Open <http://127.0.0.1:8765>. The Flask/Waitress app reads the live SQLite archive
in read-only mode and refreshes its overview every ten seconds. It can run beside
the crawler. It does not fetch pages from StreetEasy or upload the archive.

Browse captured pages or the pending queue, filter by page type and URL/address,
select a crawl generation, and inspect response headers, extracted JSON, raw
source, or historical observations. Source is displayed as text; downloading it
returns an attachment. Listing-detail counts include only successfully captured
**detail pages**, not search results or discovered URLs. `Open original` is an
explicit link to StreetEasy.

The default view shows captured pages. With the supplied HAR, this is the homepage
and Chelsea search page. Select **Listing details → Queued** to inspect the 14
known detail URLs. No detail response is claimed to be captured from that HAR.

The crawler prioritizes discovered listing detail URLs ahead of search pages,
including `/sale/<id>`, `/rental/<id>`, and modern `/building/<slug>/<unit>` pages.
A regression test follows a synthetic search link into a detail response and checks
that its full body, pricing JSON, and history table are archived separately.

## Crawl and resume

```sh
uv run streeteasy-archive backfill --max-requests 100
uv run streeteasy-archive status
uv run streeteasy-archive resume --max-requests 100
# After the preceding crawl generation finishes:
uv run streeteasy-archive update --max-requests 100
```

`--max-requests` bounds a single invocation; zero means no request-count limit.
Use Ctrl-C once for a graceful stop, then `resume`. Data defaults to `./data`;
select another archive with the global `--data /absolute/path` option before the
command. Keep using the same archive directory to resume or update it.

Discovery starts with the NYC sitemap index, building directory, and sale/rental
searches. It follows active and **off-market building sitemaps**, building pages,
public unavailable-unit/history links, listing links in HTML and embedded data,
and pagination links. It does not depend on a building having an active listing.
No IDs are brute-forced. It follows only recognized StreetEasy page paths and
approved public redirects; it does not navigate authentication or account pages.

The crawler uses one outstanding request, randomized delays with a five-second
minimum, and Scrapy AutoThrottle. Robots enforcement is disabled at the user's
explicit request. Cookies, automatic retries, and automatic redirects are disabled.
Access blocks, rate limits, challenges, and transient failures pause the crawl
and persist its cooldown. Repeatedly launching a command cannot bypass a pending
cooldown. The same archive permits only one mutating process at a time.

SQLite tracks pending, in-flight, and completed URLs. A resumed run skips completed
URLs and recovers requests that were in flight. Response recording and newly
discovered URLs commit together. A process killed after the server sent a response
but before local commit may need to repeat **that one uncommitted request**;
exactly-once network delivery is impossible to guarantee across that crash window.

## Incremental collection

`update` creates a new pass once the previous one has finished. It rediscovers the
site and revalidates known URLs using ETag / Last-Modified when available. A 304
observation refers back to the archived body. Identical bodies share the same
SHA-256-addressed file; changed bodies remain available as separate versions.

`--revisit-interval SECONDS` can reduce checks of recently fetched building/listing
pages. The default is zero, checking all known pages on every update. Discovery
pages are refreshed each pass. A longer interval saves requests but delays change
detection. Sitemap lastmod is captured as evidence, not treated as an exhaustive
listing change feed. If the server does not provide validators, detecting a change
requires downloading the page again; content deduplication saves storage, not that
network transfer. There is no verified public feed of every StreetEasy change.

## Import the supplied HAR without network access

```sh
uv run streeteasy-archive import-har \
  '/Users/ben/Desktop/streeteasy.com_Archive [26-09-07 13-53-49].har'
uv run streeteasy-archive export data/observations.jsonl --offline-reextract
```

Only StreetEasy response content is imported. Request cookies, authorization
headers, POST bodies, and browser sessions are never replayed. Sensitive response
headers are omitted. The original HAR remains where you put it and is ignored by
Git. Response bodies can themselves contain embedded identifiers or personal
information: treat the local archive as private data. HAR text bodies are saved
as their available decoded content, not represented as original wire bytes.

## Archive and schema evolution

- `data/archive.sqlite3`: crawl generations, durable frontier, observations,
  snapshot extractions, and body metadata.
- `data/bodies/<prefix>/<sha256>.gz`: original response entity bytes, compressed
  locally. Scrapy decodes HTTP content encoding before archival; binary gzip
  sitemap files remain recoverable as received by the parser.
- JSONL export: per-observation metadata, body reference, and derived extraction.

Extraction preserves all script text, JSON-LD/JSON, decoded React Flight chunks,
metadata, data attributes, text, links, image URLs, and table HTML. JavaScript is
never executed. Images and floorplan **URLs** are preserved; external image binaries
are not fetched. The complete source body is authoritative. Extend `extract.py`
and rerun `export --offline-reextract` to evolve your downstream schema without
fetching the site again. No columnar schema is imposed on the archive.

Back up the entire data directory together. Stop the crawler before a simple
filesystem copy so the SQLite WAL and body files stay consistent.

## Coverage limits

A drained frontier means all *discovered* URLs were handled, not that StreetEasy's
entire historical database was downloaded. Removed/unlinked pages, undisclosed
API data, account-only history, and histories behind interactive controls without
public links may be missing. HTTP errors, blocked requests, and unsupported
redirects must be investigated through status and observation metadata. Search
result caps can also limit discovery; building sitemaps provide an independent
route but cannot prove completeness. The archive retains raw pages so deeper
history extraction can be added when representative public responses are available.

The source sitemap index was inspected at
<https://streeteasy.com/sitemaps/secure/nyc_sitemap_index.xml>; it includes
`nyc_buildings_*` and `nyc_off_market_buildings_*`. A public building page at
<https://streeteasy.com/building/147-west-22-street-new_york> exposes unavailable
sales/rentals in the web index, but direct crawler access was blocked during this
implementation. Scrapy documentation: <https://docs.scrapy.org/en/latest/>.

## Development

```sh
uv run pytest -q
jj status
jj log
git log --oneline
```

The tests use synthetic responses and local fixtures; they do not contact StreetEasy.

Validation from this implementation is recorded in [VALIDATION.md](VALIDATION.md).
The supplied HAR has already been imported into the local `data/` archive; start
with `resume --max-requests 100` to use that frontier. No crawler is left running.
`status: active` denotes an unfinished generation. Exit status 3 means a persisted
cooldown/access pause; 2 means an error; 0 includes an intentional request-budget
stop. `status` reports pending work separately, and works while the crawler runs.

### Firefox and a single-building pilot

Install the optional browser transport with `uv sync --extra dev --extra browser`.
It uses installed Firefox (automatically detected on macOS) and Selenium Manager
for geckodriver. No StreetEasy account or proxy is needed for the successful pilot.

```sh
uv run --extra browser streeteasy-archive resume --transport firefox \
  --building https://streeteasy.com/building/ten23-500-west-23rd-street-new_york \
  --max-requests 4
```

For a new archive use `backfill` instead of `resume`. Repeat `--building` and
`--transport firefox` on each scoped run. The scope includes that building's URL,
query variants and child detail paths; it does not include standalone `/rental/`
URLs or imply complete historical coverage. Other discovered URLs stay queued but
are not downloaded during the scoped run. `--max-requests` counts page navigations,
not browser subresources. Saved pages are skipped on resume. Completed archives
can use `update` for revisits; an unfinished generation must first be completed.

Firefox uses a fresh profile per page, normal browser identity, verified TLS,
one navigation at a time, and the existing Scrapy delays and durable cooldowns.
Images, media, fonts, non-GET requests and navigation to another document are
blocked. Scripts and other page resources may still load. Redirect status/headers
are archived and approved destinations enter the queue; Firefox redirect bodies
are unavailable. A challenge pauses the run rather than triggering driver or
proxy rotation. Pass `--firefox-binary /path/to/firefox` to select an installation.

The browser archive retains the BiDi response payload, serialized response body,
response headers, and rendered DOM separately in extraction metadata. Base64 data
preserves entity bytes; string data preserves browser-decoded text encoded as
UTF-8, which is **not a guarantee of original wire bytes**. The first three pilot
captures predate retention of the native BiDi payload but retain their serialized
bodies and DOM. No encoding repair or re-download of those three was required.
Selenium is pinned because its responseCompleted binding needs a small compatibility
shim to retain the request ID. Check this shim when upgrading Selenium.

Run browser integration checks against a loopback fixture only:
`ARCHIVE_TEST_FIREFOX=1 uv run --extra browser --extra dev pytest tests/test_browser.py -q`.

Proxy fallback: retain direct Firefox as the baseline. If sustained access fails,
trial Oxylabs residential proxies against the same small sample; compare Oxylabs
Web Scraper API and Zyte API if managed fetching is needed. No paid service has
been tested or configured. Compare complete archived pages and actual cost, not
provider headline success rates. Provider pricing must be checked at trial time.

### Running Chelsea, excluding Hudson Yards

```sh
uv run --extra browser streeteasy-archive resume --neighborhood chelsea \
  --transport firefox --delay 60 --wait-for-cooldown
```

This starts an unlimited-budget crawl of the scoped queue. `--wait-for-cooldown`
waits for an existing cooldown once; a newly encountered challenge still pauses
and exits, with no automatic retry loop. One navigation runs at a time, with
30–90 second randomized start spacing at the 60-second setting. Browser assets
can generate additional requests. Scope, transport and delay persist for later
`resume` commands. The neighborhood scope includes StreetEasy Chelsea (115) and
West Chelsea (163), excluding Hudson Yards (146) and Staten Island Chelsea.

Scope evidence comes from explicit result-card neighborhoods, primary building
associations, filtered building-directory ItemLists, and property-history links.
Unrelated navigation/recommendation URLs remain outside the runnable scope.
Archived pages are processed offline to populate the scope without redownloading.
The archive browser shows scoped pending counts and the cooldown alongside global
archive totals. Worker metadata and output live at `data/chelsea-worker.json` and
`data/chelsea-worker.log` when launched by the assistant.

**Coverage limitation:** on September 7 the Chelsea building directory returned a
403 challenge. No complete off-market building inventory or complete unavailable
unit roster has been verified. TEN23's saved building data lists current units,
but does not expose paths for all unavailable units. The crawl follows explicit
historical links and preserves complete embedded response data; it does not guess
unit numbers or claim all Chelsea history is complete. The citywide off-market
sitemaps are known but cannot yet identify Chelsea membership without additional
building metadata. These gaps need follow-up after the directory can be accessed.

### Oxylabs Web Scraper API

Store `OXYLABS_USERNAME` and `OXYLABS_PASSWORD` in the repository-root `.env`
(or export them in the environment). `.env` is ignored by git; keep it owner-only
with `chmod 600 .env`. These are API credentials, not your dashboard login.

Resume with a bounded trial:

```sh
streeteasy-archive --data data resume --transport oxylabs --max-requests 200
```

The Chelsea profile remembers the transport. The handler uses the Realtime API
with `source=universal` and `render=html`; it archives returned HTML plus sanitized
provider result metadata. No image-download product or structured/AI parser is
requested. Rendering may still load assets inside the provider's browser.
Returned UTF-8 HTML is provider-rendered content, not original wire bytes.
Provider API failures leave URLs pending and pause the crawl; authentication errors
never become successful page captures. Existing cooldown and single-writer rules
still apply. This does not implement an automatic worker supervisor.

September 7 trial: Chelsea building directory and TEN23 #4C both returned real
HTTP 200 pages. #4C retained 102 embedded price-history events through January 2015.
Directory discovery supports legacy result cards with explicit Chelsea/West Chelsea
labels, excluding navigation recommendations and Hudson Yards. These checks do not
establish complete historical-unit discovery or citywide coverage.
