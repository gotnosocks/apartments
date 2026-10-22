# Floor model with park frontage: predictions, 2026-10-22

Two fits add `bld:park_front` to the floor model, `building-zones-floor`, and add nothing else. Ben approved both on 2026-10-22 as conference follow-ups 1 and 2. I wrote these predictions before launching either fit.

So far the park frontage flag has run only in the location model (`docs/notes/building-zones-parkfront-2026-10-22.md`):
- There it came out at +3.46 (90% interval +2.57 to +4.25).
- Held out, it beat the location fit by 2.3 SE.
- The explained-share test missed its null.

The location model also carries the smooth park and water distances. Those terms moved when the flag joined them. The floor model has no distance terms, so this pair of fits asks a simpler question: does the flag help the model the paper reports?

## The module

`rentfrontier.building_zones_floor_parkfront` builds the floor design and appends `building_zones_parkfront.columns`. The flag is 1 when the building's outline lies within 40 m of a NYC Parks property of 5 acres or more. It reads the same snapshot as the location run, `building-park-front/20261022-5ddc0e5d`. Everything else, priors and sampler included, comes from `building_zones_floor` unchanged.

## The fits

Both run on dataset `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc` at the commit that adds the module. They use the floor fit's settings:
- 4 chains, 300 warmup, 1,000 sweeps with every 5th kept;
- seed 20261021;
- fit-only.

| fit | split | comparison run |
|---|---|---|
| 1 | latest | `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000` |
| 2 | whole-building split from #1212 | `building-zones-floor-b0-buildings-35131df8-dense-w1000` |

I score each fit against its comparison with `docs/notes/conference-followups-2026-10-22/score.py` (400 draws). On the buildings split I also run the explained-share test against the permutation null, with the scripts from `docs/notes/building-zones-parkfront-2026-10-22/heldout/`.

## Predictions

- Both fits pass the gate (R-hat at most 1.01, bulk ESS over 400). Each takes 18 to 25 minutes on Modal, at an estimate of $0.75 to $1.10.
- `bld:park_front` has a median between +2.5 and +5 points on both splits, and its 90% interval excludes 0. With no distance terms to share the effect, I expect it at or above the location fit's +3.46.
- Every other coefficient moves by under 0.2 points, and the floor curves by under 0.2 points at every floor.
- On the latest split, the elpd gain over the floor fit is positive and under 2 SE by building. Only about 3% of the training ads sit in park-facing buildings.
- On the buildings split, the elpd gain is positive, and the gain on the held-out ads in park-facing buildings is larger per ad than on the rest.
- On the buildings split, the explained share of the park-facing buildings' residual gap again fails to clear the 95th percentile of the permutation null, as it failed for the location fit.
- RMSE and 90% coverage on all held-out ads move by under 0.0005 and 0.1 percentage points.
