# Greenwich Village collection

The crawl uses the same policy as West Village (`docs/data/west-village-collection.md` on the
`west-village-unit-probes` line): canonical rentals only, inventory-label unit probes first, then
advertisements round-robin by unit, and advertisements below ID 1,210,000 (listed before 2014)
skipped without a request. Scope is StreetEasy area `greenwich-village` (116) without its child
area NoHo (118). Unit `apartments-greenwich-village-20261001`; archive
`/data1/apartments/archive/crawls/greenwich-village-20261001`; controls and rate in
`data/probes/greenwich-village-20261001/README.md` (local, not in git).

## Progress (Oct 3 2026, 14:30 EDT)

- 10,196 observations since Oct 1. Since 2 workers began (Oct 2 18:09): 8 requests/minute, no
  HTTP 429. The only 429s (91) came from the Oct 1 quota episode.
- 116 buildings done and 94 queued, plus 348 directory pages and 127 searches that can reveal more
  buildings; 3,336 listing pages pending. 3,502 units with a canonical rental membership.
- Exclusions: 3,029 `before_min_listing_id`, 980 `captured_listing_not_eligible`, 685
  `missing_canonical_unit_association`, 86 `sale_route`.

## Unit probes

Of 4,497 inventory-label probes captured, 3,457 (77%) were rental unit pages, 708 (16%) were
sale-only unit pages and 332 (7%) returned 404. A sample of 80 sale-only pages had no rental
events at all, so these are not rentals hidden by the page's current listing type. Rates vary a
lot by building, from 0% sale-only (the-hilary-gardens, 1-university-place, 60-east-12-street)
to over 50% (the-john-adams, the-randall-house, 250-mercer-street).

Bedrooms and price barely separate the outcomes. The date of the inventory row, which is the
unit's latest past rental advertisement, does (read a little later, 4,531 probes):

| Latest rental ad | Probes | Rental | Sale-only | 404 |
|---|---:|---:|---:|---:|
| 2006–2009 | 110 | 0.48 | 0.45 | 0.07 |
| 2010–2013 | 641 | 0.36 | 0.21 | 0.44 |
| 2014–2019 | 1,140 | 0.77 | 0.21 | 0.02 |
| 2020–2023 | 1,240 | 0.80 | 0.19 | 0.01 |
| 2024–2026 | 1,400 | 0.96 | 0.04 | 0.00 |

**Probes whose source advertisement is below the ID cutoff never pay off.** 766 such probes were
captured; about 60% were sale-only or 404, and none of the rest unlocked an advertisement at or above
1,210,000. Since the inventory row is the latest advertisement, every ad such a unit could unlock is
also below the cutoff and would be skipped. Rule `probe_source_before_min_listing_id` (in
`collection_policy.exclusion_reason`) skips them before any request when a cutoff is set. It would
have saved about 765 of the first 10,196 requests (7.5%). Most of Greenwich Village's are already spent,
so it pays off in the remaining buildings and in later neighborhoods.

The inventory lists only past advertisements, so a unit re-let after its last inventory row
would be skipped too if its route were reached another way. None of the 5,157 captures of
post-cutoff advertisements, or any other capture, links to one of these units.

The remaining sale-only probes (2014 onward) have no cheap predictor yet: rental and sale-only units
interleave within buildings, so a per-building early stop would lose rentals.
