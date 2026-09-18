# Bedroom-dependent residual scale research

The centered bedroom-scale experiment completed on September 18 at 22:35:41 UTC and passed both convergence gates. It substantially reduces the larger-bedroom dispersion mismatch seen under a shared Student-t scale, while aggregate extreme tails remain heavier than replicated data. This is an accepted research result; the main selected model was not changed by this analysis.

The [verified report](../../data/model/chelsea-bayesian-bedroom-noise-centered-report-20260918/report.html) uses the same 52,711 observations, source targets, encoded mean design and mean priors as the accepted shared-scale baseline. Four chains each retained 4,000 draws after 2,000 warmup iterations, with seed 20260920. Parameter maximum R-hat is **1.005401**, minimum bulk ESS **613**, and minimum tail ESS **1,134**. Derived maximum R-hat is **1.003725**, minimum bulk ESS **1,045**, and minimum tail ESS **1,773**. Both have zero divergences or maximum-depth hits; minimum BFMI is 0.461.

## Residual scales and conditional checks

The likelihood retains Student-t ν=5. Bedroom log-scale offsets have a partially pooled, equal-level zero-sum prior. These are residual **scales in log rent**, not standard deviations, feature premiums or fitted-rent uncertainty; Student-t standard deviation is scale × √(5/3). Global sigma is the geometric mean across the six bedroom-level scales, not a frequency-weighted market average.

| Bedrooms | Observations | Scale median [95% credible interval] |
| --- | ---: | ---: |
| Studio | 14,010 | 0.0577 [0.0566, 0.0588] |
| 1 | 22,303 | 0.0595 [0.0586, 0.0605] |
| 2 | 11,489 | 0.0794 [0.0776, 0.0811] |
| 3 | 3,785 | 0.1078 [0.1037, 0.1120] |
| 4 | 973 | 0.1010 [0.0938, 0.1087] |
| 5 | 151 | 0.1244 [0.1036, 0.1504] |

The [bounded posterior checks](../../data/model/chelsea-bayesian-bedroom-noise-centered-checks-20260918/checks.md) select 50 retained draws per chain before materializing posterior values, for 200 joint draws total. They verify the centered offset identity and bedroom-coordinate mapping and replicate each row with its own fitted bedroom scale. No global-sigma substitution is allowed. Exact source, posterior and implementation bindings remain enforced. Bundle verification transiently reads the posterior file for its hash; numeric posterior loading is restricted to the selected draws.

The [source-matched check comparison](../../data/model/chelsea-bayesian-noise-check-comparison-20260918/comparison.md) verifies identical cohorts, thresholds, slice support and 15 accepted slices against the corrected shared-scale checker. Values below are medians across the selected draws of the mean absolute log residual:

| Slice | Shared: observed / replicated | Bedroom scale: observed / replicated |
| --- | ---: | ---: |
| Overall | 0.06425 / 0.06255 | 0.06569 / 0.06427 |
| 2 bedrooms | 0.07059 / 0.06258 | 0.07650 / 0.07532 |
| 3 bedrooms | 0.08578 / 0.06264 | 0.10380 / 0.10234 |
| 4 bedrooms | 0.08068 / 0.06247 | 0.09695 / 0.09569 |
| 5 bedrooms | 0.09743 / 0.06209 | 0.12360 / 0.11599 |

The observed residual distribution changes when the mean parameters and group offsets are refit under different noise weights. These checks assess observed-versus-replicated discrepancy within each fitted model; a larger observed residual is not itself a worse fit or out-of-sample error.

Extreme-tail mismatch remains. For the bedroom-scale model, overall positive residuals above log(1.25) occupy **1.735%** of observations versus **1.273%** in replications; the negative tail below −log(1.25) is **1.552%** versus **1.269%**. None of the 200 replications reaches either observed overall tail statistic. This is finite Monte Carlo evidence, not a literal zero probability. Signed median residuals remain near zero. The 13 current listings have mean absolute log residual about 0.044 versus 0.064 replicated, but form a small in-sample subset; they do not establish calibration. Missing bedroom/current slices are explicitly omitted for insufficient support.

## Effects and current residual sensitivity

The [noise-only comparison](../../data/model/chelsea-bayesian-noise-sensitivity-20260918/comparison.md) verifies exact saved mean-design hashes and fixed source/mean-prior protocols. It compares separate posterior summaries; it does not pair draws across independently fitted models or infer a posterior probability of the between-fit change.

For two-bedroom apartments, the one-to-two-full-bath association shifts from **23.72% [22.91%, 24.54%]** to **24.14% [23.29%, 24.97%]**, with 5,247 and 5,038 rows at the two endpoints. The first-half-bath association shifts from **13.64% [12.74%, 14.54%]** to **13.54% [12.63%, 14.44%]**. These remain conditional associations at fixed building, unit, date, area and other encoded features.

Sparse extremes are more sensitive. The four-to-five-full-bath contrast for four-bedroom apartments shifts from **10.83% [0.50%, 21.77%]** to **6.59% [−4.68%, 19.11%]**; the endpoint has only **two rows, two units and two buildings**. The four-bedroom net-balance difference (the net −1→0 increment minus net 0→+1, where net means full baths minus bedrooms) moves from 0.1125 [−0.0033, 0.2291] to 0.1666 [0.0335, 0.3005] **log units**, again relying on that sparse five-bath endpoint. A changed interval sign classification is not reliable identification of a new effect. The second-half-bath coefficient still relies on only two advertisements overall, with one row at each displayed endpoint; its bedroom-scale interval remains very broad, about 8.37%–69.68%.

Across all observations, signed residual rank correlation is **0.99293** and absolute residual rank correlation **0.97575**. The median absolute residual calculated from saved fitted medians changes from 0.03520 to 0.03596; this is a different statistic from the posterior-check table above. The largest movement among the 13 current fitted medians is **$246.65** for four-bedroom advertisement **5155651**: $12,232.03 becomes $11,985.38 against an ask of $12,200. Its latent-rent interval changes from [$11,265.15, $13,188.66] to [$10,782.88, $13,199.61]. Current residual movements and every supported bathroom comparison are preserved in the artifact.

Remaining tail mismatch motivates focused source/feature review and further likelihood-shape sensitivity. It does not authorize automatic corrections, establish that an apartment is a bargain, or demonstrate out-of-sample predictive calibration. No new fit was started for this report and no source or analytical patches were applied.

## Computational history and reproducibility

The first noncentered experiment, `chelsea-bayesian-bedroom-noise-20260918`, completed at 21:58:53 UTC but remains **diagnostic-only**: maximum parameter R-hat 1.01464, five parameters above 1.01, and minimum bulk ESS 268. Its derived gate passed, which does not override the parameter failure; its intervals remain withheld.

The centered version samples the zero-sum offset directly with standard deviation τ, preserving the original scale × standardized-offset prior and likelihood. The [equivalence proof](../../data/model/chelsea-bayesian-centered-residual-proof-20260918/proof.json) checks the `(K−1) log(τ)` Jacobian, matching row likelihoods and gradients at nine points. Maximum adjusted log-density error is 3.02e−14 and gradient chain-rule error 5.33e−15. The [full-cohort shared-mode parity artifact](../../data/model/chelsea-bayesian-v3-centered-shared-parity-20260918/parity.json) found exactly zero log-density and gradient differences at three points. The corrected shared v3 checker reproduces the earlier safe v2 checks, as recorded in `chelsea-bayesian-shared-checker-parity-20260918`; the unsafe original saved-design reload remains excluded.

All accepted report/check/comparison artifacts were generated with the frozen environment, for example:

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --frozen --no-sync python -m models.bayesian_feature_checks_v3 \
  --experiment data/model/chelsea-bayesian-bedroom-noise-centered-20260918 \
  --dataset data/model/chelsea-reviewed-bathroom-projection-20260918 \
  --output data/model/chelsea-bayesian-bedroom-noise-centered-checks-20260918 \
  --draws-per-chain 50 --seed 20260919
```

The independently fitted models happen to use the same selected draw positions and replication seed in these checks. That supports reproducibility, not a pairing of posterior samples across models. Raw artifacts preserve exact selected chain/draw coordinates, thresholds, source and fit hashes, code snapshots and all discrepancy intervals.
