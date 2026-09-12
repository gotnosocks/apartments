# Chelsea discovered-scope backfill audit — September 12, 2026

The controller reported `queue_drained`; no scoped pending URLs remain. This is completion of the discovered StreetEasy scope, not proof that every physical building or unit in Chelsea appears on StreetEasy.

## Coverage

- 1,311 distinct building roots captured. The 1,832 completed building URL rows include 521 previously fetched variants and are not a building count.
- 1,809 expanded unavailable inventories: 1,217 rental and 592 sale inventories.
- 25,535 rental rows and 9,535 sale rows; these are source inventory records, not deduplicated physical units. Sale rows include 1,166 recorded-closing records, retained in the inventories; separate closing-page details are outside this listing crawl.
- All 33,904 distinct listing URLs linked directly from these inventories have successful captures (one through a captured redirect target).
- Every inventory matches its own displayed total and embedded summary; all inventory raw body files exist. No expected inventory or scoped building capture is missing.
- Across the broader discovered historical listing frontier, 121,109 URLs have direct successful captures and 35 resolve through captured aliases/redirects. These are URL counts, not unique listing IDs or units.
- 966 historical detail URLs have a latest HTTP 404 outcome. They remain explicit source coverage gaps; repeated blind retries were not justified. Embedded histories on other pages may retain events but do not establish that the missing episode attributes were recovered.

## Point-in-time count differences

Eleven inventories have one fewer row than an earlier, separately fetched building summary. In every case the inventory count equals both its displayed total and its own embedded summary, and all its linked details are captured. The building summaries precede inventories by roughly 14–27 hours. This supports treating the discrepancy as a cross-capture source-count difference, not evidence of truncated expansion. The precise cause (for example a changed listing state or source revision) is unverified. Both observations and their timestamps remain retained. The audit reports these differences explicitly instead of inventing a missing row or replacing the inventory's contemporaneous count with an older count.

## Full-history sample

The remote raw-body audit sampled 310 rental detail pages, combining dense-history buildings and a deterministic broader sample. All 310 contained embedded listings and history events, with no parser errors: 8,219 extracted event records, and 206 pages with more events than initially visible table rows. These are raw event counts, not deduplicated price changes.

TEN23 unit 4C contains 102 events across six listing episodes from 2015-01-31 through 2026-09-04, versus five initially visible rows. The audit therefore verifies that the archive retains history beyond the collapsed table in sampled pages. This is sample evidence, not exhaustive independent validation of every history or a sale-history audit.

## Preservation

The explicit cloud snapshot is named `chelsea-backfill-20260912`; Modal confirmed successful publication and volume commit; the writer lock is released. The saved publication result is `chelsea-snapshot-2026-09-12.json`. The original `chelsea-20260908` remains unchanged. The snapshot contains the archive database and provenance, references shared append-only raw bodies, and does not seed stale analytical outputs. No local archive download, cloud browser, or periodic browser checkpoint was added.

Compact machine-readable coverage and history audit reports accompany this document. Intensive reads and snapshot copying run on Modal CPU workers, with no GPU or additional Oxylabs calls for these audits.
