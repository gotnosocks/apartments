# Comparing feature-prior sensitivity

`models/bayesian_feature_sensitivity.py` compares saved summaries from at least two completed v2 Bayesian experiments. It performs no fitting and does not load posterior draws into a statistical model. The existing report verifier checks every bundle hash, including the posterior file, and requires both parameter and derived diagnostics to pass.

```bash
.venv/bin/python -m models.bayesian_feature_sensitivity \
  --experiment PATH_TO_MULTIPLIER_05_RUN \
  --experiment PATH_TO_MULTIPLIER_1_RUN \
  --experiment PATH_TO_MULTIPLIER_2_RUN \
  --dataset PATH_TO_THEIR_EXACT_SOURCE_DATASET \
  --output NEW_IMMUTABLE_COMPARISON_DIRECTORY
```

Every fit must use exactly the same observation/source hashes, target policy, implementation hashes, feature specification, software versions, sampler adaptation and target acceptance. Feature-design JSON, time-design JSON and time-design arrays must have identical hashes. Only draws, tuning iterations, chain count, seed and a distinct positive feature-prior multiplier may differ. These allowed changes are reported explicitly. The reference is multiplier 1 when supplied, otherwise the smallest supplied multiplier.

The immutable output includes:

- `comparison.json` with supported full-bath, half-bath and bedroom/bath balance contrasts; separate per-fit median and 95% interval; descriptive median/endpoint changes and interval overlap; unchanged endpoint support.
- Coefficient comparisons retaining the existing encoded-unit and reporting-association labels. Category contrast-basis coefficients remain omitted, rather than labeled as amenity premiums.
- Signed and absolute log-residual Spearman correlation over every observation, using average ranks for exact ties. Each current captured listing has both fitted summaries, residual movement, all-row ranks, complete source record and advertisement ID. The count comes from the verified cohort rather than a hardcoded expectation of 13.
- `comparison.md`, archived comparison/report source code, and source/protocol/fit manifest hashes and full manifests in `complete.json`.

Different fits' draws are never paired. Differences of medians and interval overlap are descriptive; there is no between-fit posterior interval or probability. Rank stability measures in-sample review stability, not predictive accuracy or a causal amenity value. Endpoint support is unadjusted observational support, not matched identification. The comparison refuses unfinished fits, failing diagnostics, source changes, design changes or reuse of an output directory for different results.

Synthetic verification covers three-fit reference selection, independently rehashed incompatible protocols/designs/implementations, target and source mismatches, both diagnostic gates, rank ties and constant ranks, source-linked current residual movement, preserved coefficient semantics, and deterministic immutable replay. No numerical prior-sensitivity conclusion is available until the real fits finish and pass both diagnostic families.
