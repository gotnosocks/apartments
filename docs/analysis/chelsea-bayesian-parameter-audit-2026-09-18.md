# Skeptical parameter and representation audit

The next specification uses listed-floor threshold increments and challenges
every other term on its source meaning, support, identification, prior sensitivity
and practical contribution to interpreting apartments. This is not a search for
the greatest number of nonzero coefficients. The accepted main posterior remains
unchanged while these alternatives are evaluated.

The source-bound, reproducible audit is
`data/model/chelsea-bayesian-parameter-audit-20260918`: 52,704 observations,
22,158 units and 1,131 buildings after the reviewed scope/composition overlay.
`models.bayesian_parameter_audit` publishes raw measurement support, known-only
group variation, encoded-column variation, category overlap and the time/group
inventory. It estimates no new coefficients. Its source and implementation hashes
are in `complete.json`.

## Immediate findings

Listed floor is observed in **364 rows, 285 units and 142 buildings**—under 0.7%
of rows. Values enter through the existing `advertised_floor` alias; the literal
`listed_floor` source field is empty. There are 19 observed levels. Only 41
buildings contain more than one known level; known floor varies in three unit
identities. Those changes need source/identity review, not interpretation as
apartments moving floors. Only 7.4% of known-floor sum of squares lies within
buildings. Encoded-column variation is much higher because known-to-unknown
changes also change the encoded value; it must not be mistaken for floor support.

An offline capture review now covers all three differing-floor unit identities:
180 Seventh Avenue #3C (2 versus 3), 452 West 22nd Street #3A (2 versus 3), and
115 West 23rd Street #63 (4 versus 6, also differing bedroom counts). All eight
retained observations have literal supporting floor wording in ten archived
captures. Thus these are source-label/identity conflicts, not demonstrated
extraction mistakes or physical floor changes. The hash-bound packet is
`data/model/chelsea-floor-label-change-review-20260918`, including exact text
spans and capture clocks. No replacement value or source patch was inferred.

The new research design uses
`sum_k beta_k * 1(known listed_floor > k)`, with thresholds at observed levels
below the maximum and a separate reporting indicator. Levels 12 and 13, among
others, are absent: the 11→14 contrast is one supported endpoint contrast, not
three independently learned floor increments. Of the 18 adjacent observed-level
pairs, only seven share a building. Most upper-floor endpoints contain one or two
units. A prior and pooled group model can produce estimates despite this limited
overlap; that does not make the evidence stronger. Negative/ground floors are
preserved when observed, and unseen known levels require new evidence/refitting.
The increments are unconstrained in sign; this construction does not assume
that higher floors always command higher rent.

Physical floor, listed-versus-physical gap and physical-floor×elevator have
**zero observed support** and are absent from the active matrix. No unit-label
inference supplies physical height. If physical measurements become available,
including listed height, physical height and their difference indiscriminately
would create algebraic redundancy. The next measurement design must choose an
independent parameterization before fitting these terms.

All 11 active window/view exposure columns are **reporting indicators**. Each
source exposure has positive claims and unknowns, with no explicit negatives.
They cannot establish presence-versus-absence premiums. Keep physical
counterfactual estimates withheld for reporting-only changes, and compare a
model without these indicators as nuisance terms. A reporting term may help
control selection while still being unsuitable as an amenity contribution.

There are **10,441 single-observation units** and **134 single-unit buildings**.
The 43-column feature matrix is full rank, but feature/group allocation still
depends on hierarchical priors. In particular, a small residual can result from
a unit offset absorbing an omitted attribute. Group offsets are necessary to
scrutinize alongside the feature coefficients, not exempt controls.

## What each part must demonstrate

| Component | Question and next comparison | Current disposition |
|---|---|---|
| Bedroom increments | Stable joint fixed-area contrasts, credible endpoint counts, and evidence that each added step is distinct; source checks for flexible bedrooms | Retain as a candidate; review sparse upper counts and recompute area normalization in contrasts |
| Full-bath increments | Separate known counts, joint bedroom-relative contrasts, sensitivity at the fourth/fifth-bath tail | Common increments have evidence; highest increment has only nine units in the prior cohort and no within-unit encoded variation in the cleaned cohort |
| Half-bath increments | Does a separate second-half step survive reasonable priors and source verification? | Only two advertisements support two half baths; earlier prior sensitivity moved its median from 43% to 17%. Do not present as a stable premium |
| Bathroom shortfall | Does adding `max(bedrooms-full_baths,0)` explain residual structure or change well-supported contrasts beyond separate bedroom/bath steps? | Baseline interval spans zero; compare full/half-only against balance on the identical cohort before retaining complexity |
| En-suite access | Can the evidence distinguish bedroom-exclusive, shared-vestibule and hall access reliably? | Not fitted. Four newly reviewed plans yielded only one clear two-bedroom-exclusive-bath case; collect/validate evidence first |
| Area and within-bedroom normalization | Is one log-area slope adequate, and are bedroom comparisons understandable at fixed area? | Compare to globally centered log area and inspect area-sliced residuals; changing centering also changes the induced prior and needs explicit accounting |
| Listed floor | Are increments supported beyond building effects, and how sensitive are sparse upper floors to increment shrinkage? | Versioned threshold design prepared; no new floor posterior yet. Compare threshold, linear-reference and floor-reporting-only variants |
| Elevator / physical-height interaction | Is known elevator variation credible within buildings, and is physical height observed? | Audit elevator contradictions. Physical-height interaction cannot enter with current evidence; don't substitute advertised floor silently |
| Laundry | Does in-building→in-unit survive grouping/prior changes with credible shared-building support? | Stronger evidence than sparse categories; existing joint contrast stable under the feature-prior comparison |
| Doorman | Do mutually exclusive categories represent services that actually coexist? | Rewrite measurement policy before assigning physical meaning. Two contrast columns correlate 0.907; raw basis coefficients are not service increments |
| HVAC | Do rare mini-split/PTAC values support separate effects beyond buildings and reporting? | Eight rows/seven units each in the prior audit, with no shared buildings between mini-split and PTAC; each overlaps central AC in a few buildings. Test removing this block or pooling justified measurement categories |
| Pet rules | Do permission, approval and unspecified restrictions describe comparable policies? | Keep source meaning explicit; test block removal and group-prior sensitivity before treating contrasts as useful renter-facing factors |
| Window/view reporting | Does nuisance adjustment materially change supported contrasts or only absorb broker description practices? | Test removal as a block; never recast positive-versus-unknown as physical absence-versus-presence |
| Other missingness indicators | Is a reporting adjustment needed, stable, and tied to a plausible selection process? | Audit each alongside known-value effects; unknown is not a physical zero |
| Building/unit offsets and scales | How much do different reasonable pooling priors move named feature contrasts and large group effects? | Compare scale priors, not only feature priors; single-unit buildings cannot independently resolve two offset layers from data alone |
| Trend and seasonality | Are 65 trend coefficients, 11 seasonal contrasts and annual drift warranted over 201 months? | Compare coarser trend and harmonic seasonality; inspect month/year residual structure and prior smoothness, preserving separation of drift/seasonality |
| Student-t likelihood and residual scale | Does fixed ν=5 with common dispersion fit tails across layouts? | Centered bedroom-scale retry passes diagnostics and improves larger-bedroom dispersion checks, while aggregate tail mismatch remains. Test tail sensitivity separately from mean features |
| Intercept, centering and coefficient priors | Are reference values, induced joint contrasts and prior predictive rents sensible? | Intercept is required for location; centering is a convention. Check prior predictive contrasts and alternative scales, not significance tests on the intercept |

## Matched decision protocol

First freeze the source-corrected shared-scale refit so source changes are not
confounded with representation changes. Every subsequent comparison must use
the same retained observations. Freeze each fit's exact versioned encoder,
posterior, priors and sampler settings; hold all nonexperimental choices fixed
while varying the declared representation or prior. Use PyMC and compiled NUTS
throughout.

For each proposed addition, removal or representation change, record: its
measurement and intended interpretation; independent unit/building endpoint
support and overlap; induced prior for the actual contrast; parameter and derived
convergence gates; posterior checks for the residual pattern it is supposed to
explain; changes to supported joint contrasts, current residuals and large group
offsets; and source review of the largest changed cases, including cases outside
the motivating examples. Test defensible prior alternatives. Lower in-sample
error, a narrow interval, or a coefficient excluding zero is insufficient alone.

Prefer the simpler model when added detail is unstable, measurement-dependent,
or does not improve the intended interpretation. Retain useful nuisance controls
with that label rather than advertising them as physical premiums. Unsupported
features remain evidence/research items. Record retain/revise/remove/defer
decisions explicitly after comparisons; this initial audit does not pretend those
fits have already been performed.

Reproduce the support audit with:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --locked --extra model python \
  -m models.bayesian_parameter_audit \
  --dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --output data/model/chelsea-bayesian-parameter-audit-20260918
```
