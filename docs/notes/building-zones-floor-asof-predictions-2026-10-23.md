# Floor model on as-of features: predictions, 2026-10-23

This fit reruns the floor model, `building-zones-floor`, with the features rebuilt from the latest split's training rows by `rentfrontier.building_zones_floor_asof` (#1231). Ben approved it on 2026-10-22 as the base for the remaining conference follow-ups. I wrote these predictions before the launch.

The snapshot features read every pipeline ad, held-out ones included. Check (f) of `conference-followups-2026-10-22.md` counted what the rebuild changes:
- sqft or relative size changes on 30.6% of training rows and 33.3% of held-out rows;
- elevator, doorman or gym change on 0.06% to 1.48% of rows;
- 7.4% of training rows take a size fill with no earlier training ad.

## The fit

- Model `building-zones-floor-asof`, split latest, dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at master 9070e131.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
- The module reads the pipeline rows file, so the launch adds `--input /data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet`.
- Comparison: `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`, scored on the same held-out ads with `docs/notes/conference-followups-2026-10-22/score.py`, 400 draws. The as-of run scores with its own design, since its held-out features differ.

## Predictions

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400) and takes 18 to 30 minutes on Modal, at $0.75 to $1.20.
- Held-out elpd falls against the floor fit, by between 100 and 2,000, and by more than 2 SE by building. Held-out ads lose the sizes and building flags their own and later ads supplied.
- RMSE rises by less than 0.003, and 90% coverage stays within 1 percentage point of 0.904.
- The log size coefficients move by under 0.03. Elevator, doorman and gym move by under 1 point each.
- The floor curves move by under 0.5 points at every floor below 47.
- `bld_sd`, `sigma` and `nu` change by under 2% each.
