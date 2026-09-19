# Laundry residual review: what the extreme cases actually say

Follow-up: [extractor v4 and complete-cohort replay](chelsea-laundry-v4-replay-2026-09-19.md)
now recover both missed every-floor phrases. Exactly two capture measurements
change; ad 970866 is already excluded from the pending source revision, leaving
one additional surviving same-floor observation. The frozen laundry fit is
unchanged.

Before reading the candidate fit, I selected eight distinct units using the
accepted model's signed residual extremes within each laundry category in The
Thomas Eddy and 101 West 23rd Street. These two buildings supply 82.4% of the
newly classified same-floor observations. I reviewed complete descriptions and
all ten attached original structured captures, checking archive-shard and raw
payload hashes. This is residual-selected development review, not an independent
estimate of source-error prevalence.

| Advertisement | Accepted ask / fitted median | Finding and resulting action |
| --- | ---: | --- |
| 3338940, Thomas Eddy #2V | $3,200 / $2,545 | Studio agrees; structured balcony is absent from prose and model. Ask falls to $3,000 the same day, then $2,700. Preserve initial ask; review outdoor-space and price-path hypotheses. |
| 3223153, Thomas Eddy #2C | $2,700 / $3,524 | Structured one bedroom conflicts with explicit studio prose; room count is one. Preserve both assertions and flag unresolved bedroom measurement. |
| 4764409, Thomas Eddy #5K | $7,000 / $5,749 | Raw address is Chelsea, but prose includes Hell’s Kitchen/Central Park boilerplate and similar-unit photos. Large home office is described. Keep verified address/price history; flag unreliable descriptive context. |
| 3895033, Thomas Eddy #5S | $3,995 / $5,357 | Sleeping alcove behind French doors, balcony and renovation. Explicit washer/dryer access on every floor is missed by extractor v3. Add the phrase to future measurement validation; “alcove” alone does not establish a bedroom correction. |
| 1894894, 101 W23 #4E | $4,800 / $3,704 | Explicit true one-bedroom convertible to two. Ask falls to $4,200 twelve days later. Preserve one bedroom and initial ask; investigate flexible layout/area. |
| 2675026, 101 W23 #5F | $2,878 / $3,628 | Prose names $3,100 gross and $2,878 net with one free month over 14 months; junior one-bedroom with divider. Queue gross-basis quarantine, without replacing the earlier event with a later quote. |
| 2034677, 101 W23 #5O | $3,400 / $2,715 | Structured studio / three rooms; prose mentions a queen/full-size bedroom without establishing separation. Layout/count remains unresolved. |
| 970866, 101 W23 #6Q | $3,100 / $3,966 | Explicit short-term offer; two bedrooms / 800 square feet agree. “Laundry with new machines on every floor” is missed by v3. Review lease-product scope and add this measurement example. |

Fitted values are conditional medians from the accepted corrected model before
the laundry split, not independent appraisals. Later asking-price reductions do
not by themselves prove the initial target was erroneous.

## Price basis and source clocks

Both original captures of ad 2675026 preserve **$2,878 on March 12, 2019 →
$3,100 on March 25, 2019**. The description explicitly distinguishes these net
and gross amounts, while structured `netEffectiveRent`, `monthsFree` and
`leaseTermMonths` are null. The modeled initial target equals the explicitly
named net amount. The captures are retrospective: do not manufacture gross
terms at the initial event from the later $3,100 event. A gross-price-basis
quarantine is supported under the existing review policy; a replacement initial
gross price is not established.

This wording says “net rent,” without “effective.” The earlier broad
net-effective screen misses that form. The existing
[net-rent follow-up](chelsea-net-rent-wording-followup-2026-09-18.md) found other
reversed-order forms outside the first frozen screen. Source price-basis review
remains a priority before promoting more amenity coefficients.

## Conditional source scenarios

All eight selected cases pass joint contribution diagnostics under the accepted
posterior. Changing only ad 3223153's encoded bedroom count from one to studio,
while retaining its fitted building/unit effects and other attributes, changes
the fitted rent from **$3,524 [$3,215, $3,819]** to
**$2,774 [$2,530, $3,005]**. The joint percentage contrast is
**−21.28% [−21.60%, −20.97%]**. These are 95% posterior intervals. Closer agreement
with the $2,700 ask does not resolve the source conflict or substitute for a
refit with corrected data.

Same-unit context adds evidence without establishing a renovation timeline.
Thomas Eddy #2C's 2018, 2022 and 2025 ads are recorded as studios and explicitly
describe a studio; its 2020 ad alone has structured count one despite studio
prose. For 101 W23 #5F, the 2016 ad calls it a studio with an installed divider;
the 2019 ad calls it a junior one-bedroom with a divider. These records support
reviewing bedroom/layout measurement and reporting changes, not automatically
inferring a physical bedroom was added between advertisements.

The separately quoted $3,100 gross amount is 7.71% above the modeled $2,878
initial ask. At a fixed fitted value that changes the signed log residual by
0.07431. This arithmetic comparison is not a replacement target or a refit; the
junior/divided layout and historical lease terms remain separate questions.

## Measurement and next decisions

Two direct same-floor phrases remain in the generic-building group. This further
rules out treating that group as a different-floor control. Add source-bound
regression examples and remeasure the full cohort under a new extractor version.
The reviewed eight-unit set is now development evidence and cannot serve as
independent validation for that revision.

Keep the running controlled fit reproducible and use it to measure sensitivity
to the current reported-detail split. Do not promote the factor solely because
residuals shrink or an interval excludes zero. Address explicit price basis and
lease-product scope in a separate source revision. No raw records or running-fit
inputs were changed by this review.

Artifacts under `data/model/`:

- `chelsea-laundry-dominant-building-review-candidates-20260919`: selected cases,
  accepted residuals and literal descriptions.
- `chelsea-laundry-dominant-building-raw-review-20260919`: original pricing,
  counts, addresses and source hashes for all ten captures.
- `chelsea-laundry-dominant-building-source-review-20260919`: eight manual
  findings with literal offsets and capture identities.
- `chelsea-laundry-reviewed-source-scenarios-baseline-20260919`: joint posterior
  case details, studio scenario, and separate price-basis arithmetic.
- `chelsea-laundry-reviewed-unit-context-20260919`: eleven observations for the
  three source-problem units, with their verified attached descriptions and
  separate reported counts/dates. No values are propagated between ads.

Each bundle archives its generating script, also maintained in
`docs/analysis/scripts/`. None changes the selected main model.
