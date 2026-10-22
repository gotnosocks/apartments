# Simulated recovery of park frontage: predictions, 2026-10-22

The park frontage fit (`building-zones-parkfront-b0-buildings-188d83cf-dense-w1000`, notes in
docs/notes/building-zones-parkfront-2026-10-22.md) puts a building within 40 m of a park of 5
acres or more 3.46 points above other buildings with the same measured traits. This fit checks
whether the model can return that value from rents with a known answer, and whether the map or
the building levels take part of it. I wrote these predictions before building the data or
launching the fit.

## The data

`python -m rentfrontier.simulate make building-zones-parkfront-b0-buildings-188d83cf-dense-w1000
fitted sim-parkfront-fitted-20261022` takes the park fit's posterior medians as the truth:
every coefficient (`bld:park_front` at 3.46), the walk, the map, every building's residual
level, nu and the sigmas. It draws a rent for each row of the fit's own design and writes a copy
of the dataset with `latest_ask` replaced. This PR adds `building-zones-parkfront` to the source
fits `simulate` accepts.

## The fit

I'll fit `building-zones-parkfront` on the simulated copy, on the same whole-building split, at
the commit of this PR, with the night's settings: 4 chains, 300 warmup, 1,000 sweeps with every
5th kept, seed 20261021, fit-only. Then I'll score it with `python -m rentfrontier.simulate
score` and check leakage with a version of the location recovery's `leak.py` from #1215.

## Predictions

All numbers are in points of log rent x100.

- It passes the gate (R-hat <= 1.01, ESS > 400), in 16 to 24 minutes.
- The 90% interval of `bld:park_front` covers 3.46, and its median lands within 0.6 of it.
- The six smooth location terms' intervals cover their planted values, and 90% coverage across
  all coefficients, nu and the sigmas falls between 80% and 97%.
- The map doesn't take up the step. Over park-facing buildings with training rows, the
  row-weighted mean error of the fitted map, less the same error over other buildings in their
  zone, is under 0.5 points in size.
- The building levels don't take it up either. The row-weighted mean error of the fitted
  building levels over park-facing buildings is under 0.5 points in size.
