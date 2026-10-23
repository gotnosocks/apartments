# Kitchen sink with unit effects: predictions, 2026-10-23

Fit (a) beat fit 8 on the latest split by 7,871 elpd (about 24 SE) and lost to fit 4 by 21,032 (about 25 SE). Fit 4 differs from fit 8 mainly by a random effect for each unit. This third fit adds those unit effects to fit (a), to see how much of fit 4's lead the kitchen sink's columns keep once each unit's own level is in the model. I wrote these predictions before launching it.

The model is `rentfrontier.building_zones_kitchen_sink_unit`. It takes fit (a)'s design, past-only unit means included, numbers the units as fit 4 does, and samples with fit 4's sampler (`building_zones_floor_asof2_unit`) and the joint amplitude step. That sampler reads the floor curves' priors up to floor 47, so the module hands it fit 8's priors to floor 64 for the length of the call, without editing the hashed sampler module. It runs fit-only on a Modal A100-40GB, on the dataset, split and seed of fits 4, 8 and (a):

    ops/modal-fit --input /data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet \
      --dataset /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc \
      --split latest COMMIT ksu-jointamp-w1000 building-zones-kitchen-sink-unit b0 4 300 1000 5 \
      --seed 20261021 --joint-amp --no-loo --no-heldout

It queues behind fit (b) and launches when the limiter covers it.

## The unit means beside unit effects

Fit 4's unit means average a unit's training ads at any date. Here they come from the row's own ad and the unit's earlier training ads, as in fit (a). With a unit effect beside them, a column's coefficient still measures the change from the unit's earlier ads, and the unit effect takes the unit's level, which fit (a) left to the building level and the residual.

## Predictions

1. It misses the convergence gate on the columns that stay fixed within a unit, as fit 4 did: the bedroom and bath steps and the floor curves, with max R-hat over 1.01 and min ESS under 400. Fit 4's note traces this to the Gibbs blocks: the sweep draws the coefficients with the unit effects held at their last draw, so a unit-constant column and the effects of its units trade off slowly. This fit keeps that sampler, so I expect the same miss. The building columns, the unit means, `unit_sd`, the zone amplitudes and the noise scales pass.
2. The chains still agree on the failing terms to within 0.3 points, apart from a few thin bath steps, as in fit 4.
3. `unit_sd` comes in at 0.07 to 0.08, a little under fit 4's 0.0794, as the new columns explain part of each unit's level.
4. `sigma` falls by 36 to 41% from fit (a)'s in every group, close to fit 4's fall from fit 8.
5. On the latest split it beats fit 4 by 1,000 to 6,000 elpd, more than 2 two-way SE. Most of fit (a)'s 7,871 over fit 8 came from the ad's own terms, the months free and the lease length, which change between ads of a unit and which unit effects can't absorb. Part of the rest came from unit-level columns, which the unit effects will now take.
6. Its 90% intervals cover 0.89 to 0.91 of the 189,647 held-out ads, as fit 4's do.
7. `ad:months_free` stays within 1 point of fit (a)'s -5.68, since it changes from ad to ad.
8. The rebuilt doorman stays under 3 points, as in fit (a), because the building level still carries the building's lasting premium.
9. Sampling takes 28 to 36 minutes at about 1.42 s a sweep (fit (a)'s 1.34 s plus fit 4's 0.08 s for the unit effects), for $1.70 to $2.20.

If prediction 1 holds, the held-out scores still count as fit 4's did, since the chains agree on nearly every term. A fit that passes the gate needs the unit effects integrated out of the coefficient draw, as fit 4's note proposes, and that would come as its own module with its own predictions.
