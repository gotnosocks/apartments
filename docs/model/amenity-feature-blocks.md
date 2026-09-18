# Which reported values add predictive information?

`models/amenity_feature_blocks.py` adds one family of known amenity values at a
time to layout, area, time, building/unit effects and **all** amenity missingness
indicators. The six families are laundry, doorman, HVAC, pets, vertical attributes
and exposures. This is an additive comparison against missingness controls, not
leave-one-feature-out importance or a causal decomposition. Correlated families
can provide overlapping information; their gains need not add up to the full
model's gain.

The frozen reference is `chelsea-recovered-amenity-validation-20260918`, using the
v4 historical analytical dataset. Baseline, missingness-only and full-model
predictions are verified and reused without fitting those models again. Each
block fits the same rows on all five building holdouts and the 2024 annual
holdout: 36 new fits. The protocol records source, code, package, split-membership
and reference-artifact hashes before fitting; completion bundles bind each fit
to its own split and block. Implementation sources are archived. Changed data or
implementation requires a new output directory.

Pooled building metrics use exactly one held-out prediction for every development
unit-month. Annual and building tests are reported separately. Paired error
comparisons resample held-out buildings while conditioning on the fitted models;
these are not coefficient uncertainty estimates. Tests check matched source rows,
resumability, wrong-checkpoint rejection and the distinction between positive-only
exposure evidence and a genuinely observed positive/negative contrast.

For an exposure with only known positive values and unknowns, the centered known-value
column is zero. Any learned signal belongs to its reporting indicator. The runner
checks the actual train/test matrices and compares predictions with the verified
missingness model. Finding no additional value signal does not imply that renters
place no value on the physical exposure.

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  uv run --locked --extra model python -m models.amenity_feature_blocks \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --reference data/model/chelsea-recovered-amenity-validation-20260918 \
  --output data/model/chelsea-feature-blocks-20260918
```

Only the verified `summary/complete.json` marks a completed comparison. The
research remains retrospective, uses reused development folds, and predicts
advertised asking rents rather than signed leases or current availability.
