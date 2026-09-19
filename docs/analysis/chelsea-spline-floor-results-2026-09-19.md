# Expanded floor data with a regularized spline

The replacement PyMC model retains the reviewed floor extraction and replaces
51 independent floor increments with five natural-cubic-spline coefficients.
The full fit and all parameter, derived-contribution and joint-floor diagnostic
gates pass. Typical fitted rents barely move relative to the expanded increment
model; the benefit is a more coherent floor curve and much less sampling work,
not a demonstrated gain in prediction accuracy.

The spline is now selected in `config/main-analysis.json` for the main
contribution, residual and counterfactual workflow, with the expanded source,
matching description archive and eight fixed source-review notes. Final
selection verification confirms it exactly matches the candidate exercised by
the real-posterior UI check. `fit-pricing` also defaults to this floor design.

## Source and specification

The frozen Chelsea cohort contains 52,653 observations, 22,155 units and 1,129
buildings. Floor is known for 29,907 rows (56.8%): 349 explicit-floor records and
29,558 reviewed label-derived proxies. Unknown floors remain unknown. Of the
172 capture-time ACTIVE observations, 95 have known floors. ACTIVE describes
the archived capture, not present availability. This is not a representative
NYC sample or a held-out evaluation.

The source is `data/model/chelsea-label-floor-analysis-20260919`; the fitted
experiment is `data/model/chelsea-bayesian-spline-floor-disk-20260919`.
Prices, source membership, nonfloor columns and their priors are unchanged in
the matched comparison. Time, building and unit effects retain the same
specifications and priors; their fitted posterior values can change.

The spline has knots at listed floors 1, 5, 10, 20, 35 and 52. Its six zero-sum
knot heights use five orthonormal coordinates with independent Normal(0, 0.10)
priors. The displayed curve is relative to floor 2. There is no monotonicity
constraint. Missing floors retain a separate indicator, not a floor-2 imputation.
The full feature design drops from 93 to 47 columns. See the
[specification](../model/floor-spline-experiment-2026-09-19.md) for equations,
centering, priors, support rules and the reproducible command.

This addresses the old design's strongly correlated adjacent increments and
accumulating prior variance. It does not resolve the broader problem that floor
is almost constant within a unit: attribution between floor and unit effects
still depends on the hierarchical assumptions.

## Full fit and computational work

PyMC/nutpie with the Numba backend used four chains, 4,000 warmup and 6,000
retained draws per chain, target acceptance 0.93, diagonal adaptation and seed
20260924. The depth ceiling returned to 10. Draw collection ran from 21:18:52 to
21:42:08 UTC on September 19; export and diagnostics completed at 22:01:33 UTC.
These are full-length fits, not startup-dominated short benchmarks.

| Diagnostic | Result |
|---|---:|
| Retained draws | 24,000 |
| Divergences / depth-limit hits | 0 / 0 |
| Maximum parameter R-hat | 1.00542 |
| Minimum parameter bulk / tail ESS | 723 / 1,443 |
| Minimum BFMI | 0.441 |
| Maximum derived-contribution R-hat | 1.00449 |
| Minimum derived-contribution bulk ESS | 1,086 |
| Maximum adjacent/range floor-contrast R-hat | 1.00404 |
| Minimum adjacent/range floor-contrast bulk ESS | 1,777 |

Every retained transition used 63 leapfrog steps (depth 6). The expanded
increment fit averaged 289.97 steps, with 6.2% of transitions consuming 60.6%
of all retained leapfrog work. Totals fell from 6,959,168 to 1,512,000 steps,
**4.60 times fewer**. This compares different specifications and execution
graphs; it is not a controlled wall-time speed ratio for the same posterior.
The spline still uses exact PyMC/NUTS, without a surrogate model.

Lower step counts do not mean uniformly higher effective sample sizes. Minimum
parameter bulk ESS fell from 2,075 to 723, while minimum floor-coefficient bulk
ESS was 1,760 in the spline. Both fits pass the same convergence gates; the
computational claim above is specifically about retained leapfrog work.

Direct versus compressed density/gradient checks passed on the complete cohort
at three parameter points (maximum absolute discrepancies 1.46e-11 and 2.39e-9).

## Floor contribution

| Listed floor | Median difference from floor 2 | 95% credible interval |
|---|---:|---:|
| 3 | +0.07% | −0.14% to +0.29% |
| 5 | +0.49% | +0.00% to +0.98% |
| 10 | +3.08% | +2.32% to +3.83% |
| 20 | +5.42% | +4.31% to +6.50% |
| 30 | +9.32% | +7.91% to +10.70% |
| 40 | +13.29% | +11.07% to +15.45% |
| 52 | +15.73% | +11.99% to +19.63% |

These are conditional associations with all other model terms held fixed,
including building and unit effects. They are not causal renovation returns,
physical-height effects or personal willingness to pay. Floor 40 has only 13
units in two buildings and floor 52 only nine units in one building. The model
shares information across those sparse labels through the smooth curve.

The [curve comparison](../../data/model/chelsea-spline-floor-comparison-20260919/floor-curves.png)
shows both the changed prior and posterior shape. The old floor-52 median was
20.69%, versus 15.73% now: smoothness assumptions matter even when total fitted
prices are stable.

A separate whole-draw importance-reweighting sensitivity check changed the five
spline prior scales from 0.10 to 0.05 and 0.20. Both passed the prespecified
weight, chain-balance and Pareto-k gates. Maximum median-curve changes were
0.91 and 0.24 percentage points respectively. Raw weight ESS was 19,371 and
23,602 out of 24,000. This is a diagnostic reweighting, not a refit or replacement
posterior; it does not test alternative knot locations or omitted features.

## Residuals and fixed development panels

| Matched slice | Rows | Old median absolute log residual | Spline | Median absolute fitted-rent change |
|---|---:|---:|---:|---:|
| All | 52,653 | 0.035141 | 0.035138 | $1.62 |
| Capture-time ACTIVE | 172 | 0.024666 | 0.024897 | $2.44 |
| New label-derived floors | 29,558 | 0.036000 | 0.036060 | $2.22 |
| Explicit floors | 349 | 0.034100 | 0.032811 | $2.26 |
| Unknown floors | 22,746 | 0.034093 | 0.034098 | $1.14 |

The largest individual fitted-rent change is $376.03. The typical residual is
essentially unchanged; the spline's cleaner decomposition is the reason to
prefer it. Independent fits are compared through summaries, not arbitrarily
paired draws.

All eight predefined source-residual cases retain accepted contribution
diagnostics and their source warnings. The fixed 26-observation floor/elevator
coverage panel also retains exactly its original membership: median absolute
fitted-rent change $3.50, maximum $105.47, and median absolute log residual
0.021513 to 0.020814. These panels are repeated development checks, not
representative samples, holdouts or accuracy estimates.

The largest fitted, unit-offset and common-reference building-effect movements
are reviewed separately in the [34-case source review](chelsea-spline-floor-movement-review-2026-09-19.md).
The source remains frozen: no correction is justified by a model movement alone.

## Reproducible artifacts

The actual Streamlit contribution/residual page passed validation against the
saved candidate posterior, without mocked prices or evidence. It displayed the
52,653-row fitted cohort count, all 172 capture-time ACTIVE rows and eight review notes. A
floor-only scenario for ad 5155021 initialized from its label-derived floor 2,
changed to floor 3, and matched the backend's joint-posterior prices ($2,885 to
$2,887 at display precision). The source record and bedroom-conflict warnings
remained intact. The validation bundle is
`data/model/chelsea-spline-main-page-validation-20260919`.

Focused design/experiment, reconstruction/readers, legacy compatibility,
comparison, sensitivity and CLI tests passed. An integrated model/reader run
passed 117 tests; the later CLI/spline run passed 102 tests (overlapping suites,
not additive counts). The full fit, numerical parity check, immutable matched
comparison and real-posterior UI check provide the substantive end-to-end
validation.

All paths below are relative to the repository:

- `data/model/chelsea-spline-floor-comparison-20260919`: exact matched comparison,
  all row/group movements, retained work, prior/posterior curves.
- `data/model/chelsea-spline-floor-prior-sensitivity-20260919`: reweighting gates
  and full curve sensitivity.
- `data/model/chelsea-spline-floor-fixed-residual-review-20260919`: eight fixed
  residual cases and source-conflict notes.
- `data/model/chelsea-spline-floor-fixed-coverage-comparison-20260919`: unchanged
  26-row development panel.
- `data/model/chelsea-spline-floor-movement-review-inputs-20260919`: 34 source
  cases selected by a recorded rule, with exact source/evidence bindings.

Source manifest SHA-256:
`5c307d4c39abef27926a3af146145d040c7d979fddfb111255f03326deacd605`.
Observation SHA-256:
`f32280906454687da145f3904aeb7ea70cdbd7b8c44ad32328c1ace404ddb974`.
Fit manifest SHA-256:
`ef5d1a119bf6d2fb5731ec89e8bc557e0a1dec0ad8af17b4ab3503dd150a5df5`.

The earlier expanded-increment/elevator interaction is retained as a completed
research artifact. It is not transferred into the spline. A spline/elevator
interaction needs its own supported comparison; unrelated bathroom and exposure
specification concerns also remain separate research questions.
