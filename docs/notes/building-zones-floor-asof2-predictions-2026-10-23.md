# As-of floor model on the corrected build: predictions, 2026-10-23

This fit reruns the as-of floor model on the pipeline build made after the studio 3+ bath corrections (#1235). I wrote these predictions before the launch.

The as-of base fit on the old build (`building-zones-floor-asof-b0-latest-9070e131-dense-w1000`) and fit 3 with the wider amplitude prior both missed the gate on one quantity, the studio coefficient for 3+ full baths (`bed=0:full>=3`): R-hat 1.0103 and 1.0102, bulk ESS 373 in both. I read the 70 training rows in that cell, and none of them was a studio with 3+ full baths. About 14 were commercial spaces, about 25 had the bedroom count missing or swapped, 7 came from 45 Wall St, and the rest were whole houses, shared rooms or empty ads. The Data improvements thread corrected them in the ledger (#1235): it excluded 14 nonresidential ads and fixed the bedrooms or baths of 15 units.

## The fit

- Model `building-zones-floor-asof2`, split latest, at the master commit that adds it.
- The model is the as-of floor model, and only the ads' source changes. Its ads come from `rows-b495f6dd53222649.parquet` rather than `rows-edc83b49f9bacd8c.parquet`.
- Dataset `b0-b495f6dd53222649-alldata-v36-dense-nyc`, built from the same pipeline rows: 1,896,472 rows, 14 fewer than before, with 17 rows changed in bedrooms, baths or unit. The studio 3+ full bath cell now has 40 training rows and 1 held-out row.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. This is the old fit's seed, on new data.
- Comparison: the as-of base on the old build, and the floor fit (`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`), each scored on the held-out ads the two splits share with `docs/notes/conference-followups-2026-10-22/score.py`, 400 draws.

## Predictions

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400) and takes 18 to 30 minutes on Modal, at $0.75 to $1.20.
- `bed=0:full>=3` falls from 41.0 points to under 25. The 30 rows the corrections moved out of the cell priced like larger units.
- Every other coefficient moves by under 0.3 points against the as-of base on the old build. `bld_sd`, `sigma`, `nu` and the zone amplitudes change by under 1%.
- On shared held-out ads, elpd changes by under 30 against the as-of base, and the difference to the floor fit stays within 1 SE by building of the old -175.
- RMSE and 90% coverage move by under 0.0005 and 0.1 percentage points.
