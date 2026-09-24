# Combined v2: the last code-hash protocol fit (September 24)

**This is the last code-hash protocol version.** Per Ben's decision
(September 24), new modeling work uses self-contained experiment scripts kept
at HEAD, with commit IDs and run records for reproducibility. A shared
summary-output reader for both model lines follows (merge plan F6). Combined
v2 exists so that the screened candidate can be selected in the app now.
Do not add further protocol versions.

## Model

`observable-bayesian-combined-experiment-v2` (`models/bayesian_combined_experiment.py`,
graph `models/bayesian_structure_graph_v5.py`) is the combined v1 candidate
(as-of attribute flags, per-unit linear drift, bedroom-group time curves,
per-building half-year random walk) plus every term accepted in screening
([screen log](screen-log-2026-09-23.md)):

| term | form | screened ΔELPD (rows / units) |
|---|---|---|
| per-building bedroom slope | τ·z_b·(min(beds, 4) − 1), τ ~ HalfNormal(0.1) | together with ν: +249.9 ± 35.6 / +505.5 ± 40.5 |
| estimated Student-t ν | ν ~ Gamma(2, 0.1); posterior ≈ 2 | (in the row above) |
| per-building size and bath slopes | τ_j·z_bj·x_j on `log_size_within_bedrooms`, `full_bathrooms_gt_1`, `full_bathrooms_gt_2`; τ_j ~ HalfNormal(0.1) | with the two above: +388 / +756 (unpaired) |
| quarterly citywide random walk, building walks centered across buildings | scale ~ HalfNormal(0.05); walk levels minus their row-weighted mean at each knot | +2.5 / +3.1 (unpaired); 24% faster sampling |

It also keeps the exact reparameterizations: the intercept as the
building-level mean, within-building feature centering and the QR feature
basis. Centering the building walks is safe only together with the
citywide walk. Without it, centering over-predicted 2021–22 by about 1.7%
(E3, research backlog).

Sampling: 8 chains × (1,000 tune + 3,000 draws). In screens, the
per-building bedroom slopes of a few buildings mix slowly (ESS about 150
per 4,000 draws), because they correlate with those buildings' levels.

## Reader

`models/bayesian_location_terms_v2.py` reconstructs each row's μ for the
main page:
- It adds the bedroom slope, the feature slopes (raw design columns) and
  the citywide walk (saved per period).
- It centers the building walk. The graph saves the cross-building common
  mode `building_walk_common` per knot, so a building's walk needs only its
  own slice.
- The feature slopes are stored as one flat building-major vector
  (`building_slope`), which also allows bounded reads.

Counterfactuals move every term jointly, including the size and bath slopes.

## Leave-own-row-out fitted rent (in-sample caveat)

Ben's use is to compare a listing with the model's estimate of its underlying
price. `fitted_rent` is in-sample: it is fitted with the listing's own row
and pulled toward its ask, most strongly for units listed once. Posterior
predictive intervals from the same fit do not remove that pull. Refitting
without the row does.

`residuals.jsonl` therefore also carries:
- `loo_fitted_rent`, `loo_latent_rent_lower_95` / `_upper_95` and
  `loo_residual_log`: the posterior of μ with the row's own likelihood
  removed, estimated by Pareto-smoothed importance sampling (weights
  1/p(y_i | θ_s));
- `loo_pareto_k` per row. Values above 0.7 mean the importance estimate is
  unreliable for that row. `summary.json` reports the count.
- `loo_method`, which says how each row was left out:
  - `psis` for units with other listings;
  - `unit_prior` for units listed once (47% of units). The listing's own
    row is the only information about that unit's effect, so importance
    sampling cannot remove it: in the smoke fit, 8,388 rows had k > 0.7.
    Instead, the unit effect is replaced by an exact draw from its prior,
    σ_unit·ε with ε ~ N(0, 1), fixed seed. The other parameters are shared
    by about 52k rows and barely move. The unit's drift term is zero by
    construction.
  - For such a listing, the left-out estimate is what the model expects for
    a new unit with these attributes in this building and month.

A unit test checks the estimator against the exact leave-one-out posterior of
a normal mean.

**Not yet done in the bridge:** the main page and the review queue still
show the in-sample `fitted_rent`. Switching the residual view to
`loo_fitted_rent` is a small follow-up to the page. It changes what users
see, so it lands separately after this fit is reviewed.

In the smoke fit (2 × 40/40 draws, unconverged), 10,431 rows used
`unit_prior`. Among PSIS rows, the median k was 0.48 for units with two
listings and 0.38 for units with six or more; 8–20% were above 0.7. k is
biased upward at 80 draws, so recheck these counts on the full fit.

## Why walk centering is safe here (review note on PR #4)

Centering the building walks was withdrawn on September 23. The E3 fit
over-predicted 2021–22 by about 1.7%: the smooth citywide trend basis could
not absorb the 2021 rebound once the walks' common mode was removed. In v2,
the quarterly citywide random walk (with its own scale) carries that shared
movement. Centering only moves the movement between two terms; it no longer
deletes it.

Direct check: held-out mean log error (%) by half-year, for the reference
(`nuts-hwalk`, no centering, no citywide walk) and the full v2 candidate
spec (`nuts-cand2`):

| half-year | rows: reference | rows: v2 spec | units: reference | units: v2 spec | rows held out |
|---|---|---|---|---|---|
| 2020a | −0.84 | −0.40 | −1.71 | −1.44 | 207 |
| 2020b | +0.46 | +0.05 | −0.85 | −1.17 | 261 |
| 2021a | −0.46 | −0.56 | +0.57 | −0.26 | 183 |
| 2021b | +0.68 | +0.76 | −2.05 | −2.34 | 156 |
| 2022a | −0.45 | −0.37 | +0.10 | +0.29 | 219 |
| 2022b | +0.13 | −0.03 | +0.45 | +0.03 | 178 |

The differences are within noise (roughly ±0.4 SE per half-year). There
is no systematic 2021–22 shift like E3's (median residual −1.6 to −2.0% in
every 2021–22 half-year). The fitted 2021–22 levels will also be compared
with the selected fit once the protocol fit lands.
