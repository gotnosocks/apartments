# Residential-scope revision: matched PyMC results

Removing the four reviewed commercial/location-conflict advertisements yields
a converged fit with largely stable contributions and fitted prices. It does
**not** improve median residuals on the common observations. The justification
is the evidence-based residential/source scope in the
[experiment](../model/residual-scope-experiment-2026-09-19.md), not improved
performance after discarding inconvenient residuals. The candidate has not yet
replaced the main analysis.

## Full posterior checks

Both fits use four chains, 4,000 warmup and 6,000 retained draws per chain,
PyMC/nutpie/Numba diagonal NUTS, the same 47-feature specification and spline
coordinate prior. The comparison verifies exact source inversion, unchanged
retained observations and sidecars, archived loader-only code changes, matching
sampler protocols, and reconstructed designs. The floor knots and induced
floor-contrast priors are identical. Data-dependent centering changes and the
tiny elevator normalization change remain recorded explicitly.

| Diagnostic group | Maximum R-hat | Minimum bulk ESS |
|---|---:|---:|
| Primary parameters | 1.004895 | 833.09 |
| Derived quantities | 1.001870 | 911.84 |
| Joint floor contrasts | 1.001742 | 2,152.89 |

All gates pass, with zero divergences, zero depth-limit hits and no nonfinite
diagnostics. Both fits use 63 leapfrog steps per retained draw, totaling
1,512,000 over 24,000 retained draws. These are work counts, not a controlled
wall-time benchmark. The candidate completed at `2026-09-20T02:28:54Z`.

## Common observations and fixed panels

| Cohort | Rows | Reference median absolute log residual | Candidate | Median absolute fitted-price movement |
|---|---:|---:|---:|---:|
| All retained observations | 52,649 | 0.03508681 | 0.03508985 | $0.97 |
| Same capture-time ACTIVE observations | 172 | 0.02438805 | 0.02448875 | $1.52 |
| Same floor development panel | 26 | 0.02190247 | 0.02184064 | $1.13 |

These are descriptive training residuals. ACTIVE is the recorded capture-time
status, not verified live availability. The 26-row panel is a fixed development
panel, not representative market sampling or a holdout. Its original membership
and floor/elevator cells were retained through verified comparison ancestry.
Maximum fitted-price movement is $144.33 overall, $14.53 among the 172
capture-time ACTIVE observations and $5.15 on the 26-row panel.

The separate fixed eight-case residual review passes all contribution
diagnostics and its bedroom scenario. These checks preserve the established
review cases; they do not replace review of the newly exposed residual tail.

Largest distinct-unit movements begin with ad 4892020 at 344 W22 (+$144.33),
followed by ads 4189081 (+$131.20), 3967693 (+$110.04) and 4811825 (+$90.56) at
133 W14, then 5083167 at 410 W24 (+$89.63). Detailed source/movement review is
still pending. Common-reference building-effect medians move by +0.02004 log
units at 133 W14, −0.01573 at 163 W23, −0.00346 at The Cass Gilbert and
−0.00292 at 267 W15. These are differences between posterior summaries, not
paired posterior draws or causal effects.

## Feature contrasts

All 54 matched floor contrasts, 32 bedroom scenarios and 16 amenity contrasts
pass their joint diagnostics. Maximum absolute median changes are 0.0513,
0.0458 and 0.1462 percentage points, respectively. Corresponding pointwise
intervals overlap descriptively; overlap is not an equivalence test.

| Advertised floor versus floor 2 | Candidate median effect | Pointwise 95% interval |
|---|---:|---:|
| 10 | +2.65% | +1.99% to +3.30% |
| 20 | +5.46% | +4.48% to +6.43% |
| 57 | +18.62% | +14.10% to +23.37% |

These are conditional modeled associations using advertised floor measurements,
not causal values of physical height. Full-bath contrasts move by at most
0.084 percentage points; half-bath contrasts by at most 0.592 points. All
corresponding intervals overlap. The three net-bathroom-balance differences
change by at most 0.00124 log units.

The largest half-bath movement is the one-bedroom/one-full-bath scenario from
one to two half baths: candidate +43.17%, interval +11.18% to +68.80%, versus
reference +43.77%. Its destination has only **one observation/unit/building**.
The large premium predates this scope revision and must not be advertised as a
well-supported general valuation. This is an existing identified weakness, not
a newly unreviewed source anomaly: the current source already accepts
corroborated multiple-half-bath counts for ads 1945700 and 2762077, the only two
unflagged supporting advertisements overall. The one-bedroom endpoint is
1945700. Thirty other records with multiple reported half baths remain flagged
and do not supply known composition to this term. The
[earlier prior-sensitivity work](chelsea-bayesian-prior-sensitivity-2026-09-18.md)
already showed strong dependence on the feature prior. A representation or
prior ablation remains more informative than repeating the same source review.
Convergence alone does not establish adequate feature support.

## Artifacts and remaining review

All paths below are under `data/model/`:

- Fit `chelsea-bayesian-residual-scope-spline-disk-20260919`, fit manifest
  `501a513bcaab810f5107f0ec292dacda32a614e4fb7d1fb2d9229f60e89ba96e`.
- Comparison `chelsea-residual-scope-spline-comparison-20260919`, manifest
  `4ce1fe6b793b6786a655db79cac12fc57656725e319dc38a5e69914fa533b6a7`.
- Fixed floor panel `chelsea-residual-scope-spline-floor-panel-comparison-20260919`,
  manifest `86d3d85e62a00e911f14258cc19f4358d478c97804e386e7d63a7c770ac91799`.
- Fixed eight-case review `chelsea-residual-scope-spline-fixed-residual-review-20260919`,
  manifest `64b6c5b49a7d4a757dc327583d254add46f05dee81596c1ba5f83ae672576421`.

All three comparison/review bundles passed file-hash verification. Candidate
selection preparation is separate from `config/main-analysis.json`. Remaining
work includes the largest-movement source review,
source-warning continuity in the actual UI and a recorded promotion decision.
The [new residual-tail review](chelsea-residual-scope-tail-review-2026-09-19.md)
is complete: eleven exact prior reviews reused and four new full-description
reviews, including a concrete retrospective attribute/price-timing concern.
The separately audited v7 floor extractor has not been projected into these
frozen observations or fitted values.
