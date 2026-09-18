# First converged Bayesian bathroom model

The first full reviewed-cohort Bayesian fit passed both parameter and derived
quantity diagnostics on September 18 at 20:50 UTC. It includes 52,711 observations,
22,165 units, 1,134 buildings and all 13 refreshed current listings. The reviewed
serving model remains unchanged.

Four chains each retained 4,000 draws after 1,000 warmup iterations. Maximum
parameter R-hat is 1.00767; minimum bulk/tail ESS are 559/966. For joint bathroom
contrasts and scaled unit effects, maximum R-hat is 1.00333 and minimum bulk/tail
ESS are 666/1,285. There are no divergences or maximum-depth events; minimum
E-BFMI is 0.412. These establish numerical reliability for this specification,
not robustness to source errors or different model assumptions.

## Initial conditional associations

| Comparison | Median asking-rent change | 95% credible interval | Endpoint units before / after |
|---|---:|---:|---:|
| 2 bedrooms, 1→2 full baths, no half bath | +23.7% | +22.9% to +24.5% | 2,426 / 2,340 |
| 2 bedrooms, 2→3 full baths, no half bath | +39.7% | +37.2% to +42.4% | 2,340 / 49 |
| 3 bedrooms, 2→3 full baths, no half bath | +38.8% | +36.7% to +40.8% | 612 / 241 |
| 3 bedrooms, 3→4 full baths, no half bath | +24.8% | +19.6% to +30.1% | 241 / 10 |
| First half bath, shown at 2 bedrooms / 2 full baths | +13.6% | +12.7% to +14.5% | 2,340 / 341 |

These hold the encoded building, unit, date, area and other features fixed. They
are conditional model associations, not renovation returns or personal willingness
to pay. Endpoint counts describe observed configurations, not matched experiments.
Half-bath effects are pooled across bedroom/full-bath configurations. The current
tabulated bathroom scenarios cover one through four bedrooms; the fit itself
includes studios and five-bedroom observations as well.

![Initial Bayesian bathroom associations](../../data/model/chelsea-bayesian-bathroom-figure-20260918/contrasts.png)

There is no single result that eliminating a full-bath shortage is always more
valuable than adding a surplus bathroom. At two bedrooms, the first increment is
smaller; at three bedrooms, it is larger. Much of this pattern comes from the
separate absolute full-bath increments. The additional shortfall coefficient is
0.00683 log points, with a 95% interval of −0.00505 to +0.01882. Thus this
specification does not establish an additional shortage penalty beyond the
absolute count effects. This is not evidence that shortages have no real value.

The second half-bath coefficient has only two supporting advertisements. Its
conditional median implies +43.3%, with a wide +10.4% to +68.8% interval. It is
retained for sensitivity research, not offered as a reliable general premium.
The [identification audit](chelsea-bayesian-identification-2026-09-18.md) explains
the dependence on group pooling and the limited within-unit variation.

## Source review changes the next action

The ten largest distinct-unit residual cases contain three explicit commercial
offers: gallery ad1572189, former restaurant ad1150734 and storefront ad859915.
These are proposed residential-scope quarantines, not price corrections. Two
low-residual Port10 ads4761346 and4758015 explicitly impose household-income
ceilings. Those are eligibility/product distinctions rather than automatic errors.
One case needs unit/building identity review, and four remain unresolved.

The evidence bundle `data/model/chelsea-bayesian-residual-source-review-20260918`
retains every reviewed description, capture identity, hash, clock and literal
span alongside the accepted fitted estimate. No new patch was applied in that
review. The [extreme-group review](chelsea-bayesian-extreme-groups-2026-09-18.md)
adds a retail advertisement, furnished/flexible-stay products, net-effective
wording, within-source geography conflicts and possible unit aliases.

The [eight-unit bathroom-change review](chelsea-bathroom-within-unit-review-2026-09-18.md)
found three explicit count/text conflicts and no verified physical change date.
Those selected cases do not estimate an error rate, but they show why reported
within-unit variation cannot automatically be treated as renovation evidence.

The [subsequent source overlay](chelsea-bayesian-source-revision-2026-09-18.md)
now applies seven named quarantines and five composition masks. It retains
52,704 observations and all 13 current captures. Its effects on the coefficients
remain a separate refit question; the table above still describes the original
52,711-row accepted Bayesian fit.

## Residual-fit check and next experiments

Corrected conditional posterior predictive checks find almost zero overall signed
bias but more extreme residuals for larger apartments than the shared residual
scale reproduces. For three bedrooms, the observed median share above a 1.25 rent
ratio is 3.91%, versus 0.95% in replications; below a 0.8 ratio it is 3.09%, versus
0.95%. Studio/one-bedroom mean absolute log residuals are roughly 0.059, versus
0.086 for three bedrooms. The shared-noise replications remain around 0.063.

These are conditional in-sample checks over 200 balanced joint draws, not
out-of-sample coverage tests. They motivate a partially pooled residual scale by
bedroom count while retaining the existing mean structure and Student-t degrees
of freedom. The [stronger-feature-prior retry](chelsea-bayesian-prior-sensitivity-2026-09-18.md)
on the identical cohort passed both diagnostic gates at21:33 UTC. Common bathroom
increments barely move; the second-half-bath estimate falls to+16.9%, with an
interval including zero. The preceding attempt failed maximum R-hat1.01288 and
remains diagnostic-only. The bedroom-dependent-scale experiment is now running
separately on this same cohort.

The first checker exposed a saved-design reload bug: alphabetized JSON metadata
changed numeric/category column order. It did not affect fitting or original
fit summaries, which used the in-memory training design. The corrected ordered
loader reproduces every entry of the 52,711×43 training matrix exactly and checks
column names before positional multiplication. Current-unit joint predictions
also match the original design exactly. The original PPC artifact is **invalid**;
use only `data/model/chelsea-bayesian-posterior-checks-20260918-v2`. The legacy
checker entrypoint now delegates to v2. Frozen fit dependencies remain unchanged
while the same-code prior comparison runs.
The immutable invalidation/replacement decision is retained in
`data/model/chelsea-bayesian-checks-status-20260918` with both manifest hashes.

## Artifacts and checks

- Fit: `data/model/chelsea-bayesian-bathrooms-long-20260918`.
- Verified HTML/JSON report: `data/model/chelsea-bayesian-long-report-20260918`.
- Standalone PNG/SVG figure: `data/model/chelsea-bayesian-bathroom-figure-20260918`;
  plotting source is included, using Matplotlib3.11.2 and the verified report.
- Corrected predictive checks: `data/model/chelsea-bayesian-posterior-checks-20260918-v2`.
- Exact reload proof: `data/model/chelsea-bayesian-design-reload-parity-20260918`.
- Prior-half run: `data/model/chelsea-bayesian-bathrooms-prior-half-20260918`.

Fifty focused checker, reload, sensitivity and report tests pass. The earlier
full suite passed917 tests with two skips; it predates these additions. Plotting
dependencies are recorded in the project model extra and lockfile. The figure
was visually inspected after rendering.

The later v3/overlay/reporting regression run passed1,170 tests with two skips
and nine warnings in182seconds. It does not change the frozen accepted fit.
