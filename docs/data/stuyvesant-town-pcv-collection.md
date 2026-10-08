# Stuyvesant Town/PCV collection

Neighborhood `stuyvesant-town-pcv` (#482): StreetEasy area `stuyvesant-town`
("Stuyvesant Town/PCV"), without child areas. Canonical rental crawl through the frozen runtime at
master `df7a0aa`, launched on Oct 8 2026 at 02:23 EDT (Ben) with the FGP policy (rentals only,
listing-ID cutoff 1210000). It ran at 8/min throughout (24/min combined with the NoMad and East
Village crawls, then 32/min combined from 11:55 EDT). Controls are in
`data/probes/stuyvesant-town-pcv-20261008/` (local).

## Dataset (Oct 8 2026)

The crawl finished on Oct 8 at 15:21 EDT (`finish_reason: finished`). It made 6,139 requests
(about $7 on Oxylabs) with no HTTP 429s. All 1,875 capture errors are HTTP 404 coverage gaps on
`/building/<address>/<unit>` pages that StreetEasy does not serve. The crawler's final status
lists 1,943 frontier rows still pending that the run does not dispatch, as in Greenwich Village
and FGP. Built the same afternoon with no requests, from master `9631c96`, with the FGP build script as
template (`/data1/apartments/tmp/stuytown-build-20261008/build.sh`):

- Snapshot: `/data1/apartments/archive/snapshots/stuyvesant-town-pcv-20261008-final/archive.sqlite3`
  (read-only; SHA-256 in the adjacent `.sha256` file), written compacted by
  `streeteasy_archive.compact` straight from the crawl database: 5.9 → 3.3 GB, all 4,264
  snapshot rows stripped with verified bodies. Before keeping it, the build checked every row
  against the crawl database (as for the earlier snapshots, see `archive-storage.md`), and the
  collection audit was identical on both. Page bodies stay in the crawl's `bodies/`; never prune
  them.
- Granular transform (`models/transform_local.py`, 2 workers, empty corrections ledger):
  `/data1/apartments/archive/datasets/stuyvesant-town-pcv-granular-20261008-canonical-url-v1`.
  It has 4,264 snapshots, 4,140 listing observations, 134,696 event mentions, 57 building
  observations and 1,478 rental units (`canonical-url-v1`) with 4,133 memberships.
- Collection audit: `/data1/apartments/tmp/stuytown-build-20261008/audit.json`. Of the captured
  ads the policy did not accept, 963 name a different canonical unit and 1,882 have no canonical
  unit association; 289 (plus 107 probe sources) are before the listing-ID cutoff.
- Unit spelling aliases, rule `unit-spelling-alias-v2` (#213):
  `/data1/apartments/archive/datasets/stuyvesant-town-pcv-granular-20261008-unit-spelling-aliases-v2`.
  266 groups (535 units, 1,250 listings), 265 of them confirmed by a crawled unit page's history.
  258 differ only by a leading zero (`1-stuyvesant-oval/03d` and `/3d`), the rest by a hyphen
  (`10-h` and `10h`). Models
  opt in as for the other neighbourhoods: map `unit_id` to `representative_unit_id` for
  `history_confirmed` groups. The canonical-url-v1 dataset is unchanged.
