# Bayesian listed-floor increments: first completed fit

The first floor-increment fit is complete on the same **52,704-row** cleaned
cohort as the accepted source-refit reference. It uses four chains, 4,000 warmup
and 6,000 retained draws per chain, with an independent 0.15-log-point prior for
each of 18 observed-level increments. All parameter, derived-effect and joint
floor-contrast diagnostic gates pass. The main model selection is unchanged.

| Diagnostic group | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
| --- | ---: | ---: | ---: |
| Parameters | 1.00424 | 1,071 | 1,764 |
| Derived effects | 1.00435 | 1,162 | 1,972 |
| Joint floor contrasts | 1.00286 | 1,781 | 3,200 |

There are no divergences or maximum-depth events; minimum BFMI is 0.452. These
are numerical checks, not evidence that all floor coefficients are useful.

Most increments remain uncertain:

| Recorded floor-label change | Median association | 95% credible interval |
| --- | ---: | ---: |
| 2→3 | −1.99% | −5.12% to +1.36% |
| 3→4 | +1.34% | −1.91% to +4.65% |
| 4→5 | −0.03% | −3.30% to +3.40% |
| 5→6 | +1.48% | −3.68% to +6.96% |
| 11→14 | −12.68% | −22.39% to −1.17% |
| 14→15 | +15.97% | +1.79% to +31.69% |
| 1→41, joint observed range | +5.09% | −10.31% to +23.23% |

The two intervals excluding zero are not persuasive evidence for a real dip at
floor 14. Only **two units in two buildings** supply its four observations.
Neither 11→14 nor 14→15 has a building represented at both endpoints. Three
floor-14 rows are repeated advertisements for 181 Seventh Avenue #14B; the other
is 21 Chelsea #1404. Captured descriptions explicitly call these fourteenth-floor
apartments, so this review did not establish a simple numeric extraction error.
Group effects, unit quality and prior allocation remain plausible explanations.
No source floor was changed based on a fitted coefficient.

The [design note](../model/listed-floor-increment-design.md) records the sparse
support and prior difference from the earlier linear slope. These results do not
separate representation flexibility from the changed induced prior. The matched
comparison must assess residual movement, nonfloor contrasts and prior support
before any promotion. Elevator interaction support is separately audited in
[the overlap review](chelsea-floor-elevator-support-2026-09-18.md).

## Reporting recovery

The disk run finished sampling, export, both large diagnostic passes and the
ordinary coefficient/group/residual reports. It then exited with status 1 because
the floor report used `floor_contrast` for both a variable and its dimension.
Xarray treated it as a coordinate, leaving the diagnostic routine no data variable.
This was a reporting failure, not failed sampling or a memory kill. The original
run took 39:37 and peaked at 9,966,868 KiB RSS.

The fix renames only the dimension to `contrast`. A new regression test runs
the real diagnostics and asserts that all three synthetic contrasts are checked;
the earlier covariance test had mocked the diagnostic function. Seventy-five
focused runner, report, recovery, storage and comparison tests pass.

`models.recover_floor_report` permits only those three coordinate-name edits
relative to the archived runner, verifies unchanged scientific dependencies and
the source/design, and preserves the original posterior and completed products.
It computes the missing floor checks and residual-scale summary, records an
explicit recovery manifest and passes the verified report reader. Recovery
completed at **02:24:00 UTC September 19** (September 18 locally), in **51 seconds**,
with peak RSS **5,213,024 KiB**. No resampling or diagnostic relaxation occurred.

Experiment: `data/model/chelsea-bayesian-floor-increments-disk-20260918`.
The immutable `floor-report-recovery/` stage binds the original/fixed code,
preserved-product hashes and original summary; the final fit contains the same
bindings. Its status is `exploratory_converged`.

## Matched comparison

`data/model/chelsea-bayesian-floor-sensitivity-20260918` verifies identical source
rows, time design and all 42 nonfloor/reporting columns and priors. The full-cohort
median absolute log residual changes only **0.035189→0.035149**; median absolute
fitted-rent movement is **$1.02**. Among the 364 rows with explicit floor labels,
the median absolute log residual is **0.032011→0.030265** and median absolute
fitted movement is **$13.91**. These in-sample changes alone do not establish that
18 floor increments earn their complexity.

All 13 current fitted rents move by less than **$8.33**. Common bathroom contrasts
remain stable: the two-bedroom, one-to-two-full-bath association changes from
**23.737% [22.952%, 24.549%]** to **23.722% [22.921%, 24.515%]**.

The largest unit movement is again the weakly supported single-observation
townhouse at 344 West 22nd Street: **$29,239→$29,950**. It has no known floor, so
this is not a direct estimated floor premium. The next two movements are
21 Chelsea #1404 (**$4,810→$4,384**, ask $4,075) and a Chelsea Centro observation
(advertisement 3091654, **$4,618→$4,241**, ask $4,040). The first is one of the two
units supporting floor 14. Source and group-effect review remains necessary;
selection of the largest movements is a diagnostic exercise, not a population
sensitivity estimate.

Disposition: keep this as a completed research comparison. Do not promote the
standout upper-floor coefficients as physical premiums or automatically select
this model because residuals are slightly smaller. Better floor measurement,
prior sensitivity and a simpler floor-reporting-only comparison remain useful
next tests. The refreshed 172-current-listing cohort still requires its own fit.
