# Whole-building holdout of the location columns: predictions, 2026-10-22

The latest split holds out each sampled unit's last ad, and every held-out building also has
training ads in it. The building effect then carries each building's level, and the transit,
parks and noise columns have little left to add: on that split their paired held-out elpd
against the floor fit was +0.2 (SE 0.7), +2.9 (SE 1.6) and -0.3 (SE 0.8). The evaluation
framework scores building-level features on grouped building holdouts instead, so I added one
and wrote these predictions before fitting on it.

## The split

`splits.building_split` (`--split buildings`) draws 10% of buildings with equal chance (seed
20260922) and holds out every ad in them. On `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc` it
holds out 6,798 of 67,977 buildings and 184,437 of 1,896,486 ads (9.7%). The median held-out
building has 7 ads, the 90th percentile 63 and the largest 2,255. A held-out building enters
each fit only through its columns and the map, with its building effect drawn from the zone's
spread.

## The fits

Two fits on the same split, with the settings of the latest-split fits: 4 chains, 300 warmup,
1,000 sweeps with every 5th kept, seed 20261021, fit-only.

1. `building-zones-floor`, the base.
2. `building-zones-location`, the floor model with the six transit, parks and noise columns.

I score both on the held-out ads with 400 draws each and pair them ad by ad. The SE comes from
per-building sums, since a held-out building's ads share its unknown level.

## Predictions

- Both fits pass the gate (R-hat <= 1.01, ESS > 400).
- Each location coefficient's median lands inside the 90% interval of the latest-split
  combined fit's coefficient. 10% fewer buildings should widen the intervals a little and
  move the medians little.
- On held-out ads, the location fit's elpd beats the floor fit's by more than 2 SE. My guess
  for the size is +300 to +2,000 over the 184,437 ads: the columns' combined spread across
  buildings is a few points, against a building spread of 11 to 18 points they help predict.
- RMSE on held-out ads falls by 0.1 to 0.6 points of log rent x100, and 90% coverage moves by
  under 1 percentage point.
- The gain is larger for held-out buildings far from the map's average in the location
  columns, such as those next to Central Park, Prospect Park or the water, than for buildings
  near the median of every column.
- As an explained-share check: over the held-out buildings, the location fit's location
  contribution explains a share of the floor fit's mean building residual that exceeds the 95th
  percentile of a permutation null (the contribution shuffled across held-out buildings within
  each zone, 1,000 times).
