# As-of floor model with the elevator floor curve to 64: predictions, 2026-10-23

This is follow-up fit 8. The floor model pools every elevator floor from 47 up into one column, `unit:elev_f47`. `rentfrontier.building_zones_floor_asof2_cap64` splits that column at each floor from 47 to 64 and extends the elevator floor GP to match. Everything else is as in `building-zones-floor-asof2`, with as-of features read from the corrected build. I wrote these predictions before the launch.

I picked 64 from the floors of training ads on the latest split of the corrected build, after rebuilding them:
- the 99th, 99.5th and 99.9th percentiles of elevator floors are 47, 53 and 64;
- every floor up to 64 has at least 12 buildings;
- 862 training ads sit on floor 64 or higher;
- 956 held-out elevator ads sit on floor 48 or higher.

## The fit

- Model `building-zones-floor-asof2-cap64`, split latest, dataset `b0-b495f6dd53222649-alldata-v36-dense-nyc`, input `rows-b495f6dd53222649.parquet`.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
- It runs after the `building-zones-floor-asof2` fit, which serves as the comparison. I score both on the same held-out ads with `docs/notes/conference-followups-2026-10-22/score.py`, 400 draws.

## Predictions

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400) and takes 18 to 35 minutes on Modal, at $0.75 to $1.40.
- The elevator curve keeps rising from 47 to 64, by between 1 and 6 points, and its 90% band at 64 is under 4 points wide.
- The curve below 47 moves by under 0.3 points at every floor, and `gp_ls[elev]` changes by under 15%.
- Held-out elpd on the 956 elevator ads at floor 48 and up rises by between 5 and 60 against the asof2 fit. On all held-out ads the change stays within 2 SE by building.
- Other coefficients move by under 0.3 points, and `bld_sd`, `sigma` and `nu` by under 1%.
