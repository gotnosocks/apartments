# Building-cluster sampling stability for amenity contrasts

`models/amenity_contrast_bootstrap.py` estimates how the five reported categorical
amenity contrasts vary when the observed training buildings are resampled. It
uses the verified v4 historical dataset and the pre-2024 training membership of
`chelsea-recovered-amenity-validation-20260918/year-2024/full`.

The declared run has 200 replicates, seed `2026091801`, two spawned workers, one
BLAS/OpenMP thread per worker, at most 20 robust-fitting iterations, and the
existing objective-relative-change acceptance threshold of `1e-5`. Each worker
refits both the centered amenity encoder and robust penalized model. Regularization
settings remain exactly those of the reference experiment.

For each replicate, sample B buildings with replacement, where B is the number
of observed training buildings. Retain every unit-month from each draw. Repeated
copies of a building receive independent collision-free building and unit IDs
based on canonical arrays containing the replicate and draw position. This matters:
retaining the same nuisance-effect IDs would repeat its likelihood contribution
while penalizing that building/unit effect only once. No unit-month deduplication
is applied after resampling. Original source building/unit IDs and audit IDs are
preserved, and the selected source-building list is saved with a hash.

Seeds use `numpy.default_rng(SeedSequence([seed, replicate]))`, so worker scheduling
and resumption do not affect draws. The protocol verifies the original fit bundle,
parent protocol, analytical source manifest, train/test membership hashes, package
versions and code hashes. It also snapshots all participating Python sources.
Per-replicate immutable bundles bind the protocol, replicate index, seed, cluster
draw hash and expected row/unit-copy counts. A valid bundle copied into the wrong
replicate directory is rejected. Each checkpoint records convergence, category
support, masks, category centers, amenity coefficients and contrast estimates.

Every absent-category, nonconverged or failed replicate remains explicit. A missing
category produces no contrast estimate; it is never filled with zero. Summary
status counts retain the planned and completed replicate denominators. Percentiles
and sign fractions use the available, converged estimates and explicitly state
that conditioning. The first two replicates additionally record the penalized
Huber objective's stationarity gradient as a numerical diagnostic.

The output is **exploratory conditional sampling stability**, not a causal or
calibrated confidence interval. The empirical building-resampling distribution
assumes buildings are exchangeable clusters; cross-building spatial or common
market dependence is not resampled. Model selection, penalty uncertainty,
source/identity errors, extraction mistakes, and nonrandom Chelsea coverage are
also outside these intervals. Different-sized buildings cause sampled row counts
to vary. Fixed sum-loss penalties therefore have different effective strength
relative to sample size; this is recorded, not silently normalized away. With
200 successful draws only about five replicates lie in each 2.5% tail, so reported
tail quantiles have limited Monte Carlo precision. Sparse categories and failed
fits can make conditional intervals selectively narrow.

Whole-cluster pairs resampling follows the general approach discussed by
[Cameron and Miller](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf).
The variable row count with unequal clusters is also discussed by
[MacKinnon, Nielsen and Webb](https://arxiv.org/html/2205.03285v1).
Those references do not validate nominal coverage for this selected, penalized,
historical-source estimator.

To prepare without fitting:

```sh
uv run --locked --extra model python -m models.amenity_contrast_bootstrap \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --experiment data/model/chelsea-recovered-amenity-validation-20260918 \
  --output data/model/chelsea-amenity-building-bootstrap-20260918 \
  --draws 200 --seed 2026091801 --workers 2 --prepare-only
```

Omit `--prepare-only` to run or resume. `--max-new-replicates 2` performs a bounded
preflight without changing the 200-draw protocol. Published replicates are verified
and reused; failed ones are not silently retried with new draws. A changed source,
implementation, seed, draw count, or estimator requires a new output directory.
Mutable progress and partial summaries are not completion artifacts. The verified
`summary/complete.json` is written only after all planned replicate bundles exist,
including explicit failures.

## Completed Chelsea run

The September 18 run completed all 200 replicates with convergence and category
support for every reported contrast. The summary bundle and unchanged replay
were verified. See the [results table](../analysis/chelsea-amenity-stability-2026-09-18.md)
for empirical percentiles, sign counts, and comparison with model-setting sensitivity.
Laundry remained positive in 200/200 draws; doorman crossed zero. These completed
results retain all of the conditional-interpretation limits above.
