# Midtown West collection

Neighborhood `midtown-west` (#717): StreetEasy area 124 ("Midtown West") with its children Hudson
Yards and Hell's Kitchen. Ben started the canonical rental crawl on Oct 13 2026 at 12:29 EDT,
after adding Oxylabs credits. It used the East Village policy: rentals only, a listing-ID cutoff
of 1210000, building-first claims (#620), and in addition `--graphql-inventory
--graphql-unit-paths` (#705, #708). Ben raised the rate to 128 submissions a minute at 17:00Z and
the workers to 32 at 17:22Z. From 19:18Z the crawl ran on the frozen runtime at `80f2e733`, which
reads each claim from an index (#721) and runs a thread per worker (#720). It fetched 105 to 117
pages a minute overnight, limited by the parse work on the crawler's main thread. Controls are in
`data/probes/midtown-west-20261013/` (local).

## Dataset (Oct 14 2026)

The crawl finished on Oct 14 at 11:09Z (`finish_reason: finished`) after 109,765 requests, about
$125 at East Village's cost per request. Oxylabs returned no 401, 402, 403 or 429 responses. 161
pages came back as 404 coverage gaps. In scope, the crawler fetched 109,765 pages, reused the
unit-page capture for 40,922 ads, and excluded 29,033 pages, 20,918 of them for falling before the
listing-ID cutoff. 7,698 frontier rows outside the scope stay pending, as in the earlier crawls.

I built the dataset the same morning with no requests, from master `ba9cb6d4`, using the East
Village build script as a template (`/data1/apartments/tmp/mw-build-20261014/build.sh`):

1. Snapshot: `/data1/apartments/archive/snapshots/midtown-west-20261013-final/archive.sqlite3`
   (read-only; SHA-256 in the adjacent `.sha256` file), written by `streeteasy_archive.compact`
   straight from the crawl database. The crawl already stored compact captures, so compaction
   stripped no rows and the snapshot stays at 79 GB. The build checked all 109,595 rows against
   the crawl database, and the collection audit came out identical on both. Page bodies stay in
   the crawl's `bodies/`; never prune them.
2. Granular transform (`models/transform_local.py`, 2 workers, empty corrections ledger):
   `/data1/apartments/archive/datasets/midtown-west-granular-20261014-canonical-url-v1`. It holds
   109,595 snapshots, 106,239 listing observations, 2,523,500 event mentions, 1,350 building
   observations and 42,399 rental units (`canonical-url-v1`) with 104,204 memberships, about 40%
   more units than East Village.
3. Collection audit: `/data1/apartments/tmp/mw-build-20261014/audit.json`. Among the captured
   pages the policy did not accept, 1,324 name a different canonical unit, 363 have no canonical
   unit and 1,563 are not verified rentals. 170 captures carry errors.
4. Unit spelling aliases, rule `unit-spelling-alias-v2` (#213):
   `/data1/apartments/archive/datasets/midtown-west-granular-20261014-unit-spelling-aliases-v2`.
   It finds 928 groups (1,897 units, 4,024 listings), and a crawled unit page's history confirms
   833 of them. Models opt in as for the other neighbourhoods: map `unit_id` to
   `representative_unit_id` for `history_confirmed` groups. The canonical-url-v1 dataset is
   unchanged.

Data improvements decides how Midtown West joins the analysis dataset. Modeling fits on it after
that.
