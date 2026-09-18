# Chelsea model-to-search verification

The robust model now connects to canonical, capture-dated apartment selection and
the preference frontier through `build-candidates` and `score-apartments`.
This is an end-to-end research example, not a personalized recommendation or a
claim of live availability. The [usage guide](../model/robust-candidate-scoring.md)
documents the commands, data contracts and interpretation limits.

## Current-month model

The source projection was rebuilt at the already-passed September 18, 16:00 UTC
knowledge cutoff. It contains exactly the same 54,105 analytical observations
as v4, with the same observation hash:
`e03d83dc4a55d6e80228f56184aad192af5c2da2b8b55fa33fc444a5511c5420`.
The new manifest avoids relying on v4's later end-of-day cutoff for current scoring.

The fixed monthly specification was refitted for September on **53,218 selected
unit-months, 22,253 units and 1,140 buildings**, through August 2026. The artifact
records its publication at `2026-09-18T17:01:26.978923+00:00`. Every training
identity/attribute combination was checked at the September prediction month
against the scientific implementation. Maximum prediction discrepancy was
**$0.000000000081**, attributable to floating-point summation.

The active bundle is `data/model/chelsea-serving-20260918-v3/model`;
its parent protocol hash is
`0cd17ac781a57fceb8b097446c1e7e184abcf9ddcd52d0502fb6e1e1e923971f`.
The bundle retains unit/building mappings and training advertisement IDs to flag
identity errors and self-overlap in current candidate comparisons. An unchanged rerun verified and
reused the completed fit without refitting.

This is a point-model refit, not a new performance estimate. It uses previously
analyzed 2025–2026 prices and does not establish prospective accuracy. The target
remains initial gross advertised asking rent; current candidate prices may have
changed since the initial ask.

## Capture-time search data

`data/exports/chelsea-candidates-20260918-asof1600` projects all **88,689 rental
captures** through the knowledge cutoff, preserving canonical source-unit IDs,
description evidence, current capture prices, status, clocks and corrections.
No capture was quarantined for identity or clock inconsistency in this source.
An unchanged snapshot rebuild verified and reproduced the completed artifact.
There are 505 ACTIVE capture records; these are neither 505 unique homes nor
505 freshly verified available homes.

The search selector resolves each advertisement's latest known capture before
combining advertisements for the same unit. This prevents a later crawl of an old
inactive advertisement from hiding a separate active advertisement. A latest
inactive capture within one advertisement still overrides its older active
captures. Contradictory active advertisements are excluded before budget filtering.

At `2026-09-18T17:02:16.194421+00:00`, the seven-day, $6,000 example selection is:

| Outcome | Count |
| --- | ---: |
| Input capture records | 88,689 |
| Earlier captures superseded within their advertisement | 23,339 |
| Latest advertisement capture not confirmed ACTIVE | 65,053 |
| Stale latest ACTIVE captures | 271 |
| Over-budget candidates | 12 |
| Selected canonical units | **14** |

The selected captures date from September 12, about six and a half days earlier.
The freshness limit admits them as saved evidence, but does not establish that
they remain available. A bounded Oxylabs refresh is the next collection step.

## Illustrative preferences and model comparisons

The example assigns $600 per bedroom, $100 for elevator access, and $150 for
in-unit laundry. These are arbitrary demonstration inputs, not the user's stated
preferences or inferred market premiums. Under the default unknown-attribute
exclusion policy, **10 units are preference-eligible and three are Pareto-efficient**.
All 14 selected units receive separate model point comparisons.

Twelve units were seen in training; two are new units in known buildings. One
candidate's same advertisement contributed an initial ask to training. Its result
explicitly flags that overlap: its residual cannot establish an independent
bargain. Changes to model coefficients cannot alter the preference frontier.

No uncertainty band is served. Familiar-property research bands have not been
promoted as a serving calibration artifact, and unfamiliar-building pooled bands
failed validation. Unsupported or stale model comparisons retain the preference
ranking with an explicit market-score status rather than fabricating a quote.

The verified output is `data/model/chelsea-search-example-20260918`. It contains
the exact candidate input, example preferences, ranked results, exclusions,
selection counts and model/code provenance. An identical rerun reproduced the
completion manifest.

## Checks and remaining work

The regression suite passed **525 tests with two skips**. Tests cover portable
prediction parity, additive log decomposition, floor/elevator recomputation,
unknown/unseen attributes, unit/building mismatches, model clocks and horizon,
advertisement supersession, correction effective dates, source tampering,
same-time conflicts, frontier independence and idempotent publication.

Next steps remain a fresh Oxylabs capture pass, a renter-facing preference
interface, validation of unfamiliar-building uncertainty, and evaluation of
market comparisons that exclude the candidate's own advertisement. NYC-wide
coverage and dated public-record integration remain broader project work.
