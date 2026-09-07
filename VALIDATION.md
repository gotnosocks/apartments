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
