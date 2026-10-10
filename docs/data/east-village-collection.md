# East Village collection

Neighborhood `east-village` (#482): StreetEasy area `east-village` ("East Village"). Canonical
rental crawl launched on Oct 8 2026 at 02:23 EDT (Ben) with the FGP policy (rentals only,
listing-ID cutoff 1210000), beside the NoMad and Stuyvesant Town/PCV crawls. It ran at 8/min, then
took the rest of the combined 32/min budget as the other crawls finished (16/min from 11:55 EDT Oct
8, 24/min from 15:35, 32/min from 08:50 Oct 9). Oxylabs returned HTTP 429 for every request from
about 18:14 EDT Oct 8; the crawls were paused 18:40–20:00 EDT and resumed with no further 429s
(Ben). From 16:10 EDT Oct 9 it claimed building-directory and building pages before units and ads
(#620, Ben: "fetch all directory and building pages first, then units and listings"), on the
frozen runtime at master `91f9ed4`; earlier it ran on `df7a0aa`. From 18:57 EDT Oct 9 it ran at
64/min (Ben: "Double the rate to 64/min"). Controls are in `data/probes/east-village-20261008/`
(local).

## Dataset (Oct 10 2026)

The crawl finished on Oct 10 at 05:55 EDT (`finish_reason: finished`). It made 82,979 requests
(about $95 on Oxylabs at FGP's cost per request): 82,214 captures, 585 HTTP 404 coverage gaps and
180 Oxylabs job failures after retries. 28,039 ads were not fetched because a capture of the same
advertisement under another unit URL was reused (`canonical-unit-same-advertisement-v1`). The
crawler's final status lists 6,661 frontier rows still pending that the run does not dispatch, as
in the earlier crawls. Built the same morning with no requests, from master `3ebfea04`, with the
NoMad build script as template (`/data1/apartments/tmp/ev-build-20261010/build.sh`):

- Snapshot: `/data1/apartments/archive/snapshots/east-village-20261008-final/archive.sqlite3`
  (read-only; SHA-256 in the adjacent `.sha256` file), written compacted by
  `streeteasy_archive.compact` straight from the crawl database: 99.7 → 55.7 GB, all 82,214
  snapshot rows stripped with verified bodies. Before keeping it, the build checked every row
  against the crawl database, and the collection audit was identical on both. Page bodies stay in
  the crawl's `bodies/`; never prune them.
- Granular transform (`models/transform_local.py`, 2 workers, empty corrections ledger):
  `/data1/apartments/archive/datasets/east-village-granular-20261010-canonical-url-v1`. It has
  82,214 snapshots, 78,339 listing observations, 1,519,922 event mentions, 1,706 building
  observations and 29,090 rental units (`canonical-url-v1`) with 77,387 memberships.
- Collection audit: `/data1/apartments/tmp/ev-build-20261010/audit.json`. Of the captured ads
  the policy did not accept, 585 name a different canonical unit, 313 have no canonical unit
  and 659 are not verified rentals; 10,424 (plus 2,309 probe sources) are before the listing-ID
  cutoff, 1,486 had no canonical unit association when claimed, and 459 are sale routes.
- Unit spelling aliases, rule `unit-spelling-alias-v2` (#213):
  `/data1/apartments/archive/datasets/east-village-granular-20261010-unit-spelling-aliases-v2`.
  558 groups (1,162 units, 3,253 listings), 405 of them confirmed by a crawled unit page's
  history (for example `101-east-10th-street-new_york/02a` and `/2a`). Models opt in as for the
  other neighbourhoods: map `unit_id` to `representative_unit_id` for `history_confirmed` groups.
  The canonical-url-v1 dataset is unchanged.
