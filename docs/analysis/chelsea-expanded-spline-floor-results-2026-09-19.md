# Expanded label floors in the Chelsea Bayesian model

The expanded floor source has a completed, converged PyMC fit on the same
52,653-observation Chelsea cohort. Known floors rise from 56.80% to 68.36%,
while typical fitted rents move little. This improves the recorded evidence
available for attribution; it does not establish uniformly better residuals
or identify a causal floor premium. Promotion remains pending the final source
movement review and actual analysis-page verification.

## What changed

The source contains the same 22,155 units, 1,129 buildings, prices and observation
dates. It adds 6,085 inferred-floor rows: 4,748 numeric-hundreds labels, 502
north/south wing prefixes, 834 front/rear suffixes and one explicit ordinal
label. Five separately reviewed photograph-reference errors at 160 W22 are
masked by exact-source correction records, then replaced by independently
recorded label proxies. The raw descriptions and both projection layers remain
available. Full inverse reconstruction and unchanged nonfloor design/evidence
checks passed, including 71,813 linked captures.

There are now **35,992 known-floor observations**, including **134 of 172
capture-time ACTIVE observations (77.91%)**. ACTIVE means the state in the
archived capture, not present availability. These are neither a representative
NYC sample nor a holdout. The remaining 16,661 unknown floors include unsupported
labels and missing or contradictory building evidence; they are not asserted
to be unrecoverable.

The model remains the five-coordinate natural cubic spline with zero-sum knot
heights, Normal(0, 0.10) coordinate priors and floor 2 as the displayed reference.
The feature design still has 47 columns. The observed upper floor changes the
boundary knot from 52 to 57; the other knots remain 1, 5, 10, 20 and 35.
This changes the induced function prior despite matching coefficient scales:
prior standard deviation at floor 45 increases 13.00%, and at floor 52 decreases
7.32%. This is therefore not a pure data-only experiment. Ten observations
above floor 52 represent nine units, all in 3Eleven. Listed floors are proxies,
not a map of physical height or skipped building labels.

The [source experiment](../model/expanded-floor-source-experiment-2026-09-19.md)
records the exact rules, corrections, support and unchanged model components.
The direct/compressed PyMC density and gradient proof passed at three complete
parameter points (maximum absolute differences 2.91e-11 and 4.07e-10).

## Sampling and uncertainty

The exact PyMC model uses nutpie/Numba, diagonal NUTS, four chains, 4,000 warmup
and 6,000 retained draws per chain, target acceptance 0.93, maximum depth 10 and
seed 20260924. Sampling began around 00:05 UTC September 20, entered export at
00:30:16, and completed export, diagnostics and reporting at 00:48:42.

| Diagnostic | Expanded source fit |
|---|---:|
| Retained draws | 24,000 |
| Divergences / depth-limit hits | 0 / 0 |
| Maximum parameter R-hat | 1.00398 |
| Minimum parameter bulk / tail ESS | 821 / 1,513 |
| Minimum BFMI | 0.436 |
| Maximum derived-effect R-hat | 1.00215 |
| Minimum derived-effect bulk ESS | 1,129 |
| Maximum floor-contrast R-hat | 1.00286 |
| Minimum floor-contrast bulk ESS | 1,895 |

All three diagnostic gates pass. Both the old and expanded source fits use
63 leapfrog steps on every retained transition, or 1,512,000 steps each. The
comparison does not establish a wall-clock speed advantage. The fit is saved
with its full joint posterior; no surrogate or reduced-draw approximation was
substituted for fitting.

| Listed floor | Median difference from floor 2 | 95% credible interval |
|---|---:|---:|
| 3 | +0.06% | −0.13% to +0.26% |
| 5 | +0.41% | −0.05% to +0.87% |
| 10 | +2.65% | +1.99% to +3.30% |
| 20 | +5.45% | +4.46% to +6.44% |
| 30 | +8.85% | +7.63% to +10.11% |
| 40 | +12.77% | +10.87% to +14.70% |
| 52 | +16.96% | +13.59% to +20.31% |
| 57 | +18.68% | +14.03% to +23.33% |

These pointwise intervals preserve within-fit coefficient covariance. They are
conditional associations holding the other terms, including building and unit
effects, fixed. They do not capture uncertainty about source mistakes, omitted
attributes, or causal interpretation. Most units do not change floors, so
attribution relies on comparisons across units and the hierarchical assumptions.

![Prior and posterior floor curves](../../data/model/chelsea-expanded-spline-floor-comparison-20260919/floor-curves.png)

Whole-draw importance sensitivity at coordinate scales 0.05 and 0.20 passes
all weight, chain and Pareto-k gates, with no withheld points. The largest
median changes occur at floor 57: −1.48 and +0.40 percentage points. Raw weight
ESS is 16,592 and 23,263; multiplying by the coefficient relative efficiency
gives heuristic safeguards of 1,305 and 1,829, not formally adjusted ESS values.
These are importance approximations, not full refits or new main posteriors.
They do not test alternative knots or the proposed GP/random-walk designs.

## Residuals and attribution shifts

| Same-observation slice | Rows | Old median absolute log residual | New | Median absolute fitted-rent change |
|---|---:|---:|---:|---:|
| All | 52,653 | 0.035138 | 0.035091 | $1.62 |
| Newly inferred floors | 6,085 | 0.032034 | 0.031649 | $8.27 |
| Corrected photo floors | 5 | 0.014047 | 0.003658 | $59.41 |
| Capture-time ACTIVE | 172 | 0.024897 | 0.024388 | $2.61 |
| Remaining unknown floors | 16,661 | 0.034890 | 0.034941 | $1.48 |

The fixed 26-observation development panel retains exactly its prior membership
and cells. Median absolute fitted-rent movement is $1.70, maximum $29.90;
median absolute log residual **worsens from 0.020814 to 0.021902**. All eight
fixed source-review contribution checks pass. These development checks are
repeated on fitted observations; none is an out-of-sample accuracy estimate.

The largest distinct-unit fitted-price movements are:

| Building / advertisement | Asking rent | Old fitted median | New fitted median | Change |
|---|---:|---:|---:|---:|
| Lantern House / 5035970 | $49,000 | $36,625 | $38,050 | +$1,425 |
| 3Eleven / 4861368 | $30,000 | $17,294 | $16,472 | −$822 |
| Ruby Chelsea / 4805575 | $20,252 | $14,101 | $14,613 | +$512 |

All three joint-posterior contribution checks pass. At Lantern House, the
posterior mean log-rent change is +0.03587: the centered floor spline contributes
+0.04537, reporting indicators −0.02613, building +0.01206 and unit +0.00617,
with smaller changes in other terms. At Ruby Chelsea the total is +0.03399,
including floor +0.05710, reporting −0.02339, building −0.00439 and unit +0.00608.
Changing from unknown to inferred floor removes an unknown-floor indicator;
the spline change alone is not the net change attributed to floor measurement.

The reviewed 3Eleven unit still has an unknown floor. Its total mean log-rent
change is −0.04890, chiefly building −0.04306 and unit −0.00568. The common-reference
building effect, calculated against the same unweighted set of 1,129 buildings,
falls from 0.18157 to 0.13849 log units. New floor information on other units
can reallocate attribution and move an unchanged unit's estimate. That is not
evidence that the property's physical quality changed. These additive log-mean
decompositions are not causal dollar allocations; independent posterior draws
are never paired to invent between-fit uncertainty.

## Review and selection status

The deterministic source-movement panel contains 32 cases: the 25 largest
distinct-unit fitted-rent changes plus examples of the five largest unit-offset
and five largest common-reference building-effect movements, deduplicated.
The [complete movement review](chelsea-expanded-spline-floor-movement-review-2026-09-19.md)
read all 59 own captures and found no contrary numbered-floor claim; 26 cases
gain a floor proxy and six remain unknown. It establishes no further floor
correction. It flags pre-existing bathroom composition, price basis and
furnishing/lease-scope issues for targeted follow-up. A single selected example
does not adjudicate an entire building. The separate 20-advertisement expanded-rule/high-floor source audit
found no contrary numbered-unit floor claim, but silence was not counted as
confirmation. See the [source panel](chelsea-expanded-floor-source-panel-2026-09-19.md).

The candidate selection retains the eight fixed notes and four unresolved issues
on three historical advertisements: furnished-only scope, an unextracted washer/
dryer, a furnished offer, and a bathroom-count conflict. These annotations do not
alter the fitted data. The actual Streamlit analysis-page check is pending;
`config/main-analysis.json` still selects the prior accepted source and fit.

## Artifacts

All artifact directories below are under `data/model/`:

- `chelsea-expanded-label-floor-analysis-20260919`: immutable source and both
  projection layers; manifest SHA-256
  `d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`.
- `chelsea-bayesian-expanded-spline-floor-disk-20260919`: fit, protocol and
  posterior; fit manifest SHA-256
  `26b5dd019416cbd39839c1a4c2c9278979dd6d68e09b449f28f4d7cf4f1f6c37`.
- `chelsea-expanded-spline-floor-comparison-20260919`: matched observations,
  curves, sampler work and unit/building movements; manifest SHA-256
  `3c763470eac7188988d077d947175af340a718be216881877668cfe12821396f`.
- `chelsea-expanded-spline-floor-fixed-coverage-comparison-20260919` and
  `chelsea-expanded-spline-floor-fixed-residual-review-20260919`: fixed panels.
- `chelsea-expanded-spline-floor-prior-sensitivity-20260919`: importance gates
  and curve sensitivity.
- `chelsea-expanded-spline-floor-movement-review-inputs-20260919` and
  `chelsea-expanded-spline-floor-movement-decomposition-20260919`: exact source
  evidence and full-posterior contribution decompositions.

The floor/elevator interaction, GP and random-walk curve specifications remain
separate matched experiments. Expanded support now includes 1,502 walk-up rows,
but observed walk-up floors remain 1–6; a high-rise walk-up contrast would be
unsupported extrapolation. Bathroom, furnishing, laundry and exposure evidence
also remain important targets for residual-driven improvement.
