# Local Bayesian asking-rent experiments

`models/bayesian_rent_model.py` consumes the frozen `model_data.parquet` produced
by `models/minimal_rent_model.py`. It does not re-clean source data or use review
annotations. Each observation is a canonical unit/month's initial asking rent,
with attributes from its own advertisements. Keep the input file and its hash
with every experiment.

## Model

The outcome is log asking rent. Predictors are cumulative bedroom thresholds
`bedrooms > 0`, `> 1`, `> 2`, `> 3`, `> 4`, bathrooms, optional log square footage
and a missing-size indicator, a smooth monthly trend, month-of-year seasonality,
and hierarchical building and optional unit intercepts. Unit intercepts estimate
persistent differences between homes; they do not identify renovation dates.
Student-t residuals with five degrees of freedom accommodate unusually large
price deviations. A normal-residual alternative provides a robustness ablation.

Square footage is relative to the training set's bedroom-group median. Missing
size is imputed at that median and gets its own indicator. Bedroom coefficients
are incremental contrasts at each group's reference size; they are not causal
values of adding a bedroom while holding a particular home's area fixed.

The trend uses a cubic spline with knots every three months. A proper Gaussian
curvature prior regularizes its second differences; a small ridge makes the prior
proper. Pure annual patterns that the spline could exactly duplicate are removed
from its coefficient space, leaving those patterns to explicit seasonality.
The trend is anchored at January 2022 (index 100). Seasonal contrasts sum
to zero. Future periods are unobserved spline coefficients under the same prior,
so forecasting uses prior-driven extrapolation rather than future rent data.
Forecast uncertainty and bias must be checked on held-out dates.

Priors are documented directly in `build_model`. Centered time and season
coefficients are the default; `--noncentered-time` expresses the same prior with
standard-normal latent coefficients for sampler comparisons. Time directions are rotated and scaled using training observation counts while
preserving their prior covariance. The intercept is centered on the training
period. Building intercepts use a centered zero-sum normal prior; unit intercepts
use noncentered normal priors. The zero-sum building constraint removes a redundant
overall location without giving any particular building privileged status. Missing units/buildings at prediction time get
new draws from the fitted group distribution, preserving group-level uncertainty.

## Run

Use the existing environment with the project's `model` extra. Fits run locally;
the script makes no Modal or StreetEasy requests. One full fit at a time uses at
most four sampler cores and one BLAS thread per process.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --locked --extra model python models/bayesian_rent_model.py \
  --input /path/to/minimal-fit/model_data.parquet \
  --output /path/to/new-bayesian-fit \
  --train-end 2024-12-01 --predict-end 2025-12-01 \
  --chains 4 --tune 2000 --draws 3000 --linear-drift
```

A new output directory is required. The settings record input/source hashes,
training sizes, and sampler settings. Outputs include prior and posterior draws,
per-parameter diagnostics, held-out predictions, predictive intervals, index and
coefficient credible intervals, package versions, and an artifact hash manifest.
A `complete.json` means the computation completed, **not** that it converged;
inspect `diagnostics_acceptable` and `diagnostics.json`.

Use `--no-units`, `--no-size`, or `--likelihood normal` for matched ablations.
Use `--holdout-units` to reserve the same deterministic 20% of entire units used
by the minimal model; with train/predict ends both set to the last observed month,
this tests estimation for unseen homes in observed market periods. It is separate
from a future-date test. `--max-units` is only a deterministic runtime pilot and
must not be represented as a full-data fit.

```sh
uv run --locked --extra model python models/bayesian_model_analysis.py \
  --model /path/to/bayesian-fit --output /path/to/new-diagnostics
```

This adds chain energy diagnostics, group scales, market-change intervals and
validation slices by date, bedroom count, known unit/building, and missing size.

## Acceptance and comparison

Inspect four-chain rank-normalized R-hat, effective sample sizes, divergences,
energy mixing, and posterior predictive performance. The runner's conservative
acceptance gate requires R-hat below 1.01, bulk and tail ESS at least 400, no
post-warmup divergences, finite diagnostics, and minimum chain E-BFMI at least
0.3. These checks follow [Stan's diagnostic guidance](https://mc-stan.org/learn-stan/diagnostics-warnings.html).
Inspect trace plots and Monte Carlo error for the substantive conclusions too.

Compare candidates using 2025 before selecting a model for the final 2026
retrospective test. Retain the robust point model as a reference. Predictive
intervals include residual noise, parameter uncertainty, and unseen-group
uncertainty. Trend/coefficient intervals describe the model's latent quantities.
Log predictive density is measured on the **log-rent scale**, not dollars.
A good fit need not outperform the point model; report that distinction openly.

These are nominal asking prices, not signed leases. The archive has later
capture-time covariates, so date-based validation is retrospective rather than a
strict as-of-date forecasting test. Source-declared canonical identities and
unobserved condition changes remain modeling assumptions.

## Bounded ablation batch

`models/bayesian_experiments.py` runs the four validation variants sequentially,
freezes its runner, writes per-fit logs and a durable `progress.json`, and stops
at the first failed diagnostic gate. Supply a deadline with an explicit offset:

```sh
uv run --locked --extra model python models/bayesian_experiments.py \
  --input /path/to/minimal-fit/model_data.parquet \
  --output /path/to/new-experiment-batch \
  --deadline 2026-09-18T09:00:00+00:00
```

The default batch uses ordinary diagonal mass adaptation. The training-based
rotation and centered building effects resolve the severe posterior correlations
encountered in initial pilots. Experimental low-rank adaptation remains available
for comparisons; every fit needs the same acceptance checks. Run the selected model separately on the final
held-out year, then refit all dates for the descriptive index; don't repeatedly
tune against the final test.

`models/bayesian_model_report.py` combines experiment comparisons, an accepted
full-data fit, a separate final-year test, and the robust baseline into standalone
HTML. It refuses unaccepted posterior fits or a subset masquerading as the
full-data fit. Plotly is included in the model extra; the report embeds its
JavaScript and needs no external CDN.


Reload the exact design with `Design.load(run / "design.json")`; `design.npz`
retains its fitted basis matrices. Open `posterior.nc` with `xarray.open_datatree`
and pass the resulting tree, saved design and a new data frame to `predict_table`.
Prediction periods must lie within the run's saved horizon; extending that horizon
requires an explicit new fit. Never recompute medians, feature centering, or basis
rotations from the prediction data.


The optional `--linear-drift` model separates a long-run annual slope from the
nonlinear spline. The slope has a Normal(0.03, 0.05) prior on log rent per year;
the corresponding exact linear direction is removed from the spline to prevent
duplication, and the nonlinear component is orthogonal to linear time under
training-observation weights. This defines the drift as the linear component of
the training trend, rather than relying on competing correlated time priors. This tests whether explicitly continuing long-run growth improves
held-out extrapolation relative to the proper, mean-reverting spline alone.
Drift variants are explicit options in the batch controller. Select the time
prior using the validation year, before the final-year test.

Parameter diagnostics are computed in blocks of at most 512 group coefficients,
retaining every chain and draw. This limits temporary rank-statistic allocations
for models with tens of thousands of unit effects. Regression tests verify that
the resulting diagnostic table matches an unchunked calculation exactly.


## September 18 selected specification

The overnight study selected the drift model, with unit effects, available size,
and Student-t residuals, using 2025 log predictive density. Its selection record
was written before the 2026 test began. The annual drift parameter is an
observation-weighted long-run component, not the latest year-over-year market
growth; calculate recent growth from posterior trend differences instead.

Pass `--holdout-fit` to the report to include an accepted whole-unit holdout.
If model selection used observations belonging to those units, label this an
exploratory check, not another independent test. The report includes paired
building-bootstrap comparisons saved as `comparison-*.json` under experiment
directories.
