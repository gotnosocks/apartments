# Flatiron + Gramercy Park collection

Neighborhood `flatiron-gramercy-park` (#281): StreetEasy areas `flatiron` and `gramercy-park`,
without the NoMad child area. Canonical rental crawl through the frozen runtime at master
`efc2de7`, launched on Oct 5 2026 at 12:25 EDT (Ben). It ran at 8/min, and from Oct 7 at
32/min (Ben). Controls are in `data/probes/flatiron-gramercy-park-20261005/` (local).

## Dataset (Oct 7 2026)

The crawl finished on Oct 7 at 21:01 EDT (`finish_reason: finished`). It made 39,191 requests
(about $45 on Oxylabs) with no HTTP 429s. The crawler's final status (unit journal) lists
8,659 frontier rows still pending; as in Greenwich Village, they are out of scope. Built the same evening with no requests, from
master `6ec13ad`, with the Greenwich Village build script as template
(`/data1/apartments/tmp/fgp-build-20261007/build.sh`):

- Snapshot: `/data1/apartments/archive/snapshots/flatiron-gramercy-park-20261005-final/archive.sqlite3`
  (read-only; SHA-256 in the adjacent `.sha256` file), copied under the crawler lock. Page
  bodies stay in the crawl's `bodies/`.
- Granular transform (`models/transform_local.py`, 2 workers, empty corrections ledger):
  `/data1/apartments/archive/datasets/flatiron-gramercy-park-granular-20261007-canonical-url-v1`.
  It has 38,819 snapshots, 36,983 listing observations, 147 listing exclusions, 706,902 event
  mentions, 808 building observations and 13,769 rental units (`canonical-url-v1`) with 35,351
  memberships.
- Collection audit: `/data1/apartments/tmp/fgp-build-20261007/audit.json`, run on `audit-input/`
  (the snapshot database plus the crawl's `bodies/`). Of the captured ads the policy did not
  accept, 1,455 are not verified rentals, 1,087 name a different canonical unit and 148 have no
  canonical unit; 372 captures were errors (404s).
- Unit spelling aliases, rule `unit-spelling-alias-v2` (#213):
  `/data1/apartments/archive/datasets/flatiron-gramercy-park-granular-20261007-unit-spelling-aliases-v2`.
  562 groups (1,151 units, 2,671 listings), 522 of them confirmed by a crawled unit page's
  history (1,066 units, 2,403 listings). Of the 1,087 canonical-unit-mismatch ads, v1 spelling
  matches 931, v2 1,059, and all 1,059 fall in history-confirmed groups; the other 28 are
  different units. Models opt in as for West Village and Greenwich Village: map `unit_id` to
  `representative_unit_id` for `history_confirmed` groups. The canonical-url-v1 dataset is
  unchanged.
