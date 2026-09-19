# Bounded Chelsea rental discovery: September 18, 2026

A fixed-ceiling pagination pass made **28 new Oxylabs requests**, all accepted,
and reused four verified preflight captures. All 32 reserved request slots are
accounted for. There were no retries. This discovers candidates for detail review;
it does not establish a current market census or change analytical eligibility.

| Search seed | Pages visited | Regular occurrences | Unique regular advertisements | Pagination |
| --- | --- | ---: | ---: | --- |
| Chelsea | 1–25 | 265 | 178 | Observed next-link chain closed |
| West Chelsea | 1–7 | 77 | 61 | Page 8 pending at request ceiling |

The seeds share 40 regular advertisements, giving a union of **199 regular ads**.
Including in-scope featured/in-feed placements produces **213 distinct ads and
213 distinct canonicalized detail URLs**. Of those URLs, 204 name units and nine
are advertisement routes whose physical-unit identities require detail-page
verification. The original review field was misleadingly named
`canonical_unit_url`; it does not establish 213 distinct physical units.
No advertisement identity conflicts were detected.
Seven Hudson Yards in-feed occurrences were retained separately and excluded.

Repeated regular listings prevent equating displayed totals or page counts with
coverage. Chelsea repeats 70 distinct regular IDs; West Chelsea repeats 16.
Displayed totals changed from 264 to 265 and 81 to 83, respectively. Every page
has a different experiment randomization identifier, but its causal role in the
ordering has not been tested. All pages report the default recommended descending
sort. The next discovery investigation should examine supported ordering/session
behavior or source-provided partitions before assuming pagination yields unique
inventory. No unobserved sort URL was constructed.

Of the 213 advertisements, 82 occur somewhere in the selected fitted cohort and
131 do not. Nine of its 13 currently eligible ads were rediscovered. The four not
seen are 5153890, 5154892, 5156327 and 5157447. Absence from this incomplete pass
is **not evidence of inactivity**; all 13 retain their existing eligibility.

Evidence clocks span 21:47:13–23:06:36 UTC, including earlier reused preflight
captures; the 28 new submissions ran approximately 23:04:32–23:06:36 UTC.

## Reproducible artifacts

- Run: `data/probes/chelsea-rental-discovery-live-20260918`.
- Frozen protocol SHA-256: `cf5fae4d9a78615f16ab37867b36aedb0cbcf40dce76e236c3e3b08c44c4d721`.
- Final report: `reports/6db4e5a16e7236d42c46f11c4dc3c783de469e00243c30ca5baa9a8319b7efe0`.
- Review: `data/model/chelsea-current-discovery-pass-review-20260918`.

`--resume --replay-only` reproduced the final report without requests. The review
publisher was also replayed identically. Its `detail-review-queue.jsonl` has one
record per advertisement, retaining every source card, placement, seed/page,
source clock, capture reference, body hash, observed detail URL and selected-fit
membership flag. `out-of-scope.jsonl` retains all seven excluded occurrences.
The review manifest binds the verified discovery report and selected dataset;
the exact publisher is saved in the bundle.

The queue requires bounded detail refresh and identity/source review before
transformation or fitting. Search cards alone do not establish complete apartment
attributes, price basis, current status or historical identity. The existing run
cannot increase its ceiling on resume. Collection commands and replay safeguards
are in the [orchestrator documentation](../data/rental-discovery-orchestrator.md).

The [bounded detail collector](../data/discovery-detail-refresh.md) now verifies
this queue against the original page report, handles the nine unresolved unit
identities, and completed all 213 targets with 213 Oxylabs submissions and no
retries. It produced 204 canonical candidates, including 201 ACTIVE listings;
168 pass the existing eligibility policy. Nine unit identities remain unresolved.
The [identity review](chelsea-discovery-detail-identities-2026-09-18.md) preserves
their history evidence. A new analytical cohort and fit remain pending.
