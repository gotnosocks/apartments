# Numerical verification of saved amenity fits

`models/amenity_solver_diagnostic.py` verifies a completed full-amenity fit, replays its held-out predictions, reconstructs the exact training rows and saved encoder, and evaluates the penalized Huber objective with the saved outcome center and penalty settings. It reports the negative stationarity gradient

`X.T @ clip(y - X @ beta, -.2, .2) - P.T @ (P @ beta)`

along with its infinity/L2 norms and a norm scaled by design-plus-penalty column lengths. It then performs twelve additional IRLS weighted least-squares steps with LSMR `atol=btol=1e-10`, `maxiter=20000`, starting at the saved coefficients. The refinement has no early exit based on objective change. All inputs, masks, category centers, vocabularies and penalty settings stay fixed.

The output is an immutable numerical diagnostic bundle, including refinement coefficients solely for audit. It does not replace a fitted model, select a hyperparameter setting, estimate a statistical interval, or establish causal amenity values. Tests compare the analytic gradient to finite differences, compare refined coefficients to an independent BFGS optimization, and demonstrate how small aggregate loss changes can conceal an incorrect rare contrast.

Example:

```sh
uv run --locked --extra model python -m models.amenity_solver_diagnostic \
  --dataset data/exports/chelsea-historical-20260918-v4 \
  --experiment data/model/chelsea-recovered-amenity-validation-20260918 \
  --output data/model/chelsea-solver-diagnostics-20260918/original \
  --split year-2024 --specification full --steps 12
```

The sensitivity fits use experiment `data/model/chelsea-amenity-sensitivity-20260918` and specifications `building-1-units` or `building-100-units`. Their own saved specification controls penalties; the global default is never substituted.

## Results from the Chelsea pilot

The verified aggregate report is `data/model/chelsea-solver-diagnostics-20260918/summary/report.json`. All fits use the v4 analytical data, training before 2024 and the same 3,591 held-out 2024 unit-months.

| Saved fit | Gradient infinity norm before → after | Largest change across five contrasts, percentage points | Mean absolute held-out prediction change |
| --- | --- | --- | --- |
| Original building penalty 10 | 0.0401 → 0.00000162 | 0.0000839 | $0.0293 |
| Building penalty 1 | 0.0122 → 0.0000158 | 0.000254 | $0.107 |
| Building penalty 100 | 0.1436 → 0.00000290 | 0.000292 | $0.0782 |

Relative objective reductions were between `1.06e-8` and `9.18e-8`. The original aggregate objective-change check was therefore not a strict stationarity check. Nonetheless, the five requested laundry/doorman/pet/HVAC contrasts barely moved under tighter fixed-objective refinement. The observed numerical stopping error does not explain their much larger differences across building-penalty settings. This distinguishes numerical stability from statistical identification: it does not resolve building/unit confounding or supply uncertainty intervals. The fixed twelve-step check also does not assert an exact optimizer solution, particularly for the weak-building fit's remaining gradient.

## Bootstrap numerical check

A separate verified check reconstructs bootstrap replicate zero, reproduces its
saved amenity coefficients exactly, and applies the same twelve tighter refinement
steps. Its largest contrast change is 0.000357 percentage points; mean sample
prediction change is $0.0318. The artifact is
`data/model/chelsea-bootstrap-replicate0-solver-diagnostic-20260918`, including the
reproducible driver and original checkpoint. This checks one declared draw, not
every bootstrap fit, and leaves the bootstrap estimator and acceptance rule unchanged.

## Producer-version compatibility

Diagnostic version `amenity-solver-diagnostic-v2` accepts sensitivity protocols v1 and v2. It still requires the currently executed encoder, objective, feature normalization, and contrast helper to match their fitted protocol hashes. The sensitivity producer wrapper is not executed by numerical replay; its source is instead verified against the protocol-bound archived `implementation/amenity_sensitivity.py`. Legacy v1 runs use a flat source snapshot, while v2 runs require the archived checksummed implementation bundle to bind the same protocol and file hashes. Missing or altered producer snapshots fail verification.

This is a deliberate diagnostic implementation/version change. Existing numerical diagnostic bundles remain unchanged and valid records of their original code. Use a fresh output directory for new diagnostics with the updated implementation; the three previously completed refinements need not be repeated merely because the producer wrapper changed.
