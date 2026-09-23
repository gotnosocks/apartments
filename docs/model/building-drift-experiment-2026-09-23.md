# Building-level price drift

Research, September 22–23. The full protocol fit is
`data/model/chelsea-bayesian-product-scope-structure-20260923`, from
`models/bayesian_structure_experiment.py`. Promotion is decided in the last
section.

## Motivation from individual observations

In the promoted bedroom-time fit, deviations (unit effect + residual) of the
same building differ by era by more than sampling noise allows. Across 157
well-observed buildings, the between-era variance of building means is 0.00169
against 0.00051 expected from noise: an excess SD of 3.4%. Raw per-building
slopes range from −4%/yr (336 W 19th St) to +5%/yr (64 7th Ave). The model gave
every building one constant effect for 2010–2026. For the same unit, the spread
of its residual change also grows with the gap between listings: SD 0.11 within
a year, 0.145 after more than ten years.

## Specification

Each building b gets a piecewise-linear random walk on knots every *k* years:

    mu_i += w_b(t_i) − Σ_t ω_{b,t} w_b(t),   w_b(knot_j) = s·sqrt(k)·Σ_{m≤j} z_{b,m},  z ~ N(0, 1)

Here ω_b are the building's own training-month weights, so building effects
keep their meaning as period-averaged offsets. s is the walk scale, per year;
the protocol fit gives it a HalfNormal(0.1) prior. The feature design,
bedroom-group time curve, priors and likelihood are those of the promoted
bedroom-time model. The building-walk draws are stored as one flat
`building_knot` vector, so diagnostics and reports read bounded slices.

## Screening (same declared held-out rows)

Conditional MAP (variance components fixed at the promoted model's NUTS
screen), held-out ΔELPD against the promoted model (4,916.4):

| representation | best scale | ΔELPD |
|---|---|---|
| linear slope per building | 0.01 | +307 |
| walk, 4-year knots | 0.045 | +525 |
| walk, 2-year knots | 0.045 | +646 |
| walk, 1-year knots | 0.06 | +729 |
| **walk, half-year knots** | **0.06** | **+778** |
| walk, quarter-year knots | 0.045 | +793 |
| 2-year walk + 3-month iid building shocks | 0.03 / 0.05 | +756 |
| 6-month iid building shocks only | 0.05 | +566 |
| separate 4+ bedroom time group (no walk) | — | −2 |

NUTS with a free scale (4-year knots, 1,000/1,000 × 4) gives **+525.6 ± 35.7**
against conditional MAP's +524.9 (per-row correlation 0.93). NUTS puts the
scale at 0.0451, the MAP optimum. Residual σ falls from 0.066 to 0.057.

NUTS on the chosen specification (half-year knots, scale free with a
HalfNormal(0.1) prior, 1,000/1,000 × 4, same rows): **+825.5 ± 45.0** against
the promoted model's NUTS screen; conditional MAP predicted +778. Posterior
means: walk scale 0.054 per √year, residual σ 0.050 (0.066 before),
σ_unit 0.082, σ_building 0.273. 0 divergences.

Checks against an artifact:

- The gain appears in every era and building-size band; 58.5% of held-out rows
  improve, and the top 1% of rows carry 21% of the gain.
- Rows sharing building, month, layout and rent with a different unit (possible
  identity duplicates, or genuinely identical line units) contribute 58 of 728
  nats. Excluding them leaves about +670.

On a declared whole-unit split (every listing of ~10% of units held out,
each held-out unit's effect integrated over its prior), the half-year walk
gains **+379.5 ± 39.3** over the promoted model. Building drift also improves
prices for units with no history.

Half-year knots were chosen: quarter-year adds +15 for twice the parameters,
and a two-component drift-plus-shock model did not beat the single walk.

## Full protocol fit

Pending.

## Decision

Pending.
