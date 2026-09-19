# What the laundry categories can identify

The full-cohort overlap audit gives a reason to be cautious about adding a
four-level price factor. The candidate categories describe **reported facility
options**. “In building” does not say that laundry is on a different floor.

| Candidate contrast | Buildings containing both categories | Units seen in both categories | Buildings with different units consistently in each category |
| --- | ---: | ---: | ---: |
| None vs in building | 0 | 0 | 0 |
| None vs on floor | 0 | 0 | 0 |
| None vs in unit | 1 | 0 | 0 |
| In building vs on floor | 17 | 40 | 8 |
| In building vs in unit | 283 | 1,391 | 177 |
| On floor vs in unit | 17 | 16 | 9 |

“Consistently” requires that a unit has only that category across all its fitted
observations, including no unknown-category rows. These are descriptive support
counts, not matched causal comparisons. Units can change real equipment as well
as their advertisements' wording; the audit does not infer which occurred.

Of 149 units with an on-floor category, 99 retain it across all their observations
and 50 also have another category. I inspected archived measurement witnesses for
eight of the 40 units seen as both in-building and on-floor. All eight in-building
witnesses contain only a positive structured `LAUNDRY` claim; none asserts that
the facility is on a different floor. The paired on-floor witness adds a literal
location claim. Examples include The Thomas Eddy, The Grand Chelsea, Chelsea
Mercantile, 135 West 24th Street and 101 West 23rd Street.

These examples establish a reporting distinction, not an installation or removal
event. In one Thomas Eddy unit, an April 2025 advertisement reports laundry on
every floor and a June advertisement supplies only the generic code. Both source
captures were collected in September 2026. Neither price month nor capture time
establishes when the facility changed. Backfilling an on-floor value across its
history would invent a validity interval.

The explicit-none candidates have especially weak support: 12 observations,
eight units and six buildings, no overlap with shared-laundry categories inside
a building, and no stable-unit comparison even against in-unit laundry. A
coefficient could be numerically fitted through hierarchical assumptions, but
this cohort cannot separate it convincingly from building differences. Direct
review of absence scope remains necessary too. Do not publish it as a measured
no-laundry discount merely because Bayesian fitting returns an interval.

The floor split is a plausible **reported-detail sensitivity experiment**, with
its interpretation stated explicitly. It should first split verified shared
laundry observations while preserving the accepted encoder's other assignments.
Replacing the entire encoder simultaneously would mix several effects: current
v3 proposes 239 in-building→on-floor changes, but also 383 in-building→unknown,
294 in-unit→unknown, and other new classifications. Those changes require their
own source review. A reported-detail association must not be presented as the
value of moving a laundry room onto the apartment's floor.

For a physical-access contrast, seek explicit shared-facility locations relative
to the dwelling, preserve unknown floor location separately, and assess support
before fitting. Same-building contemporaneous evidence may help, but should not
silently fill historical dates or override conflicting unit-specific evidence.

Artifact `data/model/chelsea-laundry-category-overlap-20260919` contains pair
inventories, per-building support, the eight units' paired source witnesses,
category-transition counts and the frozen generating script
`docs/analysis/scripts/audit_laundry_category_overlap.py`. All 52,863 observation
identities and the measurement/source manifest binding were checked. No model
inputs or main selection changed.
