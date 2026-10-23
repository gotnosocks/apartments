# As-of floor model with a wider amplitude prior: predictions, 2026-10-23

This is conference follow-up 3. It refits the as-of floor model, `building-zones-floor-asof`, with the zone-map amplitude prior widened from HalfNormal(0.3) to HalfNormal(1.0), using `rentfrontier.building_zones_floor_asof_amp1` (#1234). Check (e) of `conference-followups-2026-10-22.md` found the Manhattan amplitude at 0.916, 3.07 prior SDs out, where the prior gives it a 0.22% tail. I wrote these predictions before the launch.

## The fit

- Model `building-zones-floor-asof-amp1`, split latest, dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, at the master commit that merges #1234.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only, with `--input /data1/apartments/pipeline/datasets/rows-edc83b49f9bacd8c.parquet`.
- Comparison: the as-of base fit, `building-zones-floor-asof-b0-latest-9070e131-dense-w1000`, scored on the same held-out ads with `docs/notes/conference-followups-2026-10-22/score.py`, 400 draws.

## Predictions

- The fit passes the gate and takes 18 to 30 minutes on Modal, at $0.75 to $1.20.
- The Manhattan amplitude rises, by 0.02 to 0.15 at the median. With some 100,000 Manhattan ads the likelihood dominates even a prior at 3 SD, so the old prior shrank it only a little.
- The not-Manhattan amplitude, at 0.36 under the old prior, moves by under 0.03.
- Held-out elpd changes by less than 2 SE by building in either direction, and RMSE and 90% coverage move by under 0.0005 and 0.1 pp.
- Coefficients, floor curves, `bld_sd`, `sigma` and `nu` move by under 0.1 points or 1%.
- If the Manhattan amplitude rises by more than 0.15, I'll read that as the old prior binding, and check whether the zone-map lengthscale shrank to compensate.
