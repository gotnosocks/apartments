# Reviewed historical price/lease-scope exclusions

The new analytical candidate excludes two specifically reviewed historical
advertisements from the accepted corrected source. It contains **52,861 rows,
22,189 units, 1,131 buildings and 172 current listings**. The selected model and
its source are unchanged; reader integration and a source-sensitivity refit
remain pending.

| Advertisement | Finding | Decision |
| --- | --- | --- |
| 2675026, 101 W23 #5F | Initial target $2,878 equals explicitly advertised net rent; description also quotes $3,100 gross. Structured concession fields are null. | Exclude the unresolved gross-price target. Do not transplant the later $3,100 price to the initial event. |
| 970866, 101 W23 #6Q | Description affirmatively offers a short-term rental, without establishing a long-term option at this quote. | Exclude this advertisement from the ordinary long-term cohort. Other advertisements for the unit remain. |

Decisions are supported by every attached capture, exact source identity,
description/body/raw hashes and literal character spans. The first listing also
has independent event-shard verification: its own ACTIVE rental event is
date-labelled **2019-03-12 at $2,878**. Its first price-change timestamp is
**2019-03-12T20:56:30-04:00**, which becomes March 13 in UTC. The historical target
contract uses the rental event date, not the price-change timestamp. The initial
preparation failed because it conflated those fields; the revised check reads
the actual event and preserves both source representations.

The projection retains every included row unchanged and saves excluded rows,
their original positions and decisions in `quarantined.jsonl`. Validation
reconstructs the full ordered parent dataset and checks its original hash.
The decision file is independently bound to the parent and sidecar. Current
source evidence is copied unchanged. No numeric replacement, cross-advertisement
propagation or claimed physical-change date is introduced.

Thirty tests pass, covering exact reconstruction, retention of other ads and
current rows, tampering with rows/order/evidence/decision bindings, typed capture
IDs, clocks, literal spans, idempotent publication and the UTC date-boundary case.
Actual decision preparation, projection and identical full-cohort replay all
completed successfully.

Artifacts:

- `data/model/chelsea-reviewed-listing-scope-decisions-20260919`
- `data/model/chelsea-reviewed-listing-scope-analysis-20260919`

Implementation: `docs/analysis/scripts/prepare_reviewed_listing_quarantines.py`,
`models/reviewed_cohort_projection.py`, `src/apartments/reviewed_cohort_quarantine.py`.

Next: add sidecar-aware inverse verification to the fit, report and description
readers, then verify full source/design compatibility and fit the revised source.
Keep this change separate from the controlled laundry experiment. The broader
net-rent phrase audit and bedroom-count conflicts remain unresolved.
