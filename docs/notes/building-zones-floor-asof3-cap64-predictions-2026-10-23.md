# As-of floor model with the elevator floor curve to 64, on the build after #1242: predictions, 2026-10-23

This is follow-up fit 8, moved to the build made after the #1242 ledger rows. That build sets two studios to 1 bath and drops one row. Otherwise the model and fit settings are those in `docs/notes/building-zones-floor-asof2-cap64-predictions-2026-10-23.md`, which gives the reasons for the cap of 64. `rentfrontier.building_zones_floor_asof3_cap64` reads the ads from `rows-b3ddebf19af1dc1e.parquet`. I wrote these predictions before the launch.

## The fit

- Model `building-zones-floor-asof3-cap64`, split latest, dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, input `rows-b3ddebf19af1dc1e.parquet`.
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only.
- It runs after fits 6 and 7. I score it with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws) and compare it with the asof2 fit of #1241 using `compare.py`, on the held-out ads both runs list. The two builds differ by three rows, so nearly every held-out ad is shared.

## Predictions

These are the asof2-cap64 predictions, unchanged, since three rows can't move any of them by a visible amount.

- The fit passes the gate (R-hat at most 1.01, bulk ESS over 400) and takes 18 to 35 minutes on Modal, at $0.75 to $1.40.
- The elevator curve keeps rising from 47 to 64, by between 1 and 6 points, and its 90% band at 64 is under 4 points wide.
- The curve below 47 moves by under 0.3 points at every floor, and `gp_ls[elev]` changes by under 15%.
- Held-out elpd on the elevator ads at floor 48 and up rises by between 5 and 60 against the asof2 fit. On all shared held-out ads the change stays within 2 SE by building.
- Other coefficients move by under 0.3 points, and `bld_sd`, `sigma` and `nu` by under 1%.

The asof2 fit missed the gate on `amp[outer]` (#1245). If this fit misses it on the same term, I'll record that as a miss on the first prediction and trace it to the data or the model structure. I won't rerun it on a new seed.
