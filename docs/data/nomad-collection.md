# NoMad collection

Neighborhood `nomad` (#482): StreetEasy area `nomad` ("NoMad"), without child areas, as Flatiron +
Gramercy Park excluded NoMad. Canonical rental crawl through the frozen runtime at master
`df7a0aa`, launched on Oct 8 2026 at 02:23 EDT (Ben) with the FGP policy (rentals only,
listing-ID cutoff 1210000). It ran at 8/min throughout, beside the East Village and Stuyvesant
Town/PCV crawls (24/min combined, then 32/min combined from 11:55 EDT). Oxylabs returned HTTP 429
for every request from about 18:14 EDT; the crawls were paused 18:40–20:00 EDT and resumed with no
further 429s (Ben). Controls are in `data/probes/nomad-20261008/` (local).

## Dataset (Oct 9 2026)

The crawl finished on Oct 9 at 08:39 EDT (`finish_reason: finished`). It made 13,504 requests
(about $15 on Oxylabs at FGP's cost per request). Of its 110 capture errors, 73 are HTTP 404
coverage gaps and 37 are Oxylabs job failures after retries. The crawler's final status lists
4,222 frontier rows still pending that the run does not dispatch, as in the earlier crawls. Built
the same morning with no requests, from master `ea932fe3`, with the Stuyvesant Town build script
as template (`/data1/apartments/tmp/nomad-build-20261009/build.sh`):

- Snapshot: `/data1/apartments/archive/snapshots/nomad-20261008-final/archive.sqlite3`
  (read-only; SHA-256 in the adjacent `.sha256` file), written compacted by
  `streeteasy_archive.compact` straight from the crawl database: 20.4 → 11.5 GB, all 13,394
  snapshot rows stripped with verified bodies. Before keeping it, the build checked every row
  against the crawl database, and the collection audit was identical on both. Page bodies stay in
  the crawl's `bodies/`; never prune them.
- Granular transform (`models/transform_local.py`, 2 workers, empty corrections ledger):
  `/data1/apartments/archive/datasets/nomad-granular-20261009-canonical-url-v1`. It has 13,394
  snapshots, 11,434 listing observations, 607,881 event mentions, 213 building observations and
  3,388 rental units (`canonical-url-v1`) with 10,962 memberships.
- Collection audit: `/data1/apartments/tmp/nomad-build-20261009/audit.json`. Of the captured ads
  the policy did not accept, 229 name a different canonical unit, 1,519 have no canonical unit
  association and 423 are not verified rentals; 3,675 (plus 446 probe sources) are before the
  listing-ID cutoff, and 95 are sale routes.
- Unit spelling aliases, rule `unit-spelling-alias-v2` (#213):
  `/data1/apartments/archive/datasets/nomad-granular-20261009-unit-spelling-aliases-v2`.
  113 groups (233 units, 509 listings), 107 of them confirmed by a crawled unit page's history
  (for example `102-east-31-street/02d` and `/2d`). Models opt in as for the other
  neighbourhoods: map `unit_id` to `representative_unit_id` for `history_confirmed` groups. The
  canonical-url-v1 dataset is unchanged.
