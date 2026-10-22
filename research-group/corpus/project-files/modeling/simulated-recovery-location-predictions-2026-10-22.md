# Simulated recovery of the location terms: predictions, 2026-10-22

This fit checks whether `building-zones-location` returns the six location coefficients when I
know them, and whether the map soaks up any of them. I wrote these predictions before launching
it.

## The data

I built the dataset with the `fitted` scenario of `rentfrontier.simulate`, which takes every
term's posterior median from the combined location fit
`building-zones-location-b0-latest-732b36ec-dense-w1000` as the truth and changes nothing:

    python -m rentfrontier.simulate make building-zones-location-b0-latest-732b36ec-dense-w1000 \
        fitted /data1/apartments/frontier/datasets/sim-location-fitted-20261022 \
        --seed 20261023 --root /data1/apartments/tmp/sim-location

The truth is in `/data1/apartments/tmp/sim-location/fitted/truth.npz`. The simulated log rents
have mean 8.137 and SD 0.434 over the 1,896,486 rows, against 8.140 and 0.438 in the real data,
with noise SD 0.122 on the 1,706,837 training rows. The planted location coefficients, in points
of log rent x100 per unit of each log column, are station -0.42, routes +0.97, park +0.21, big
park -2.08, water -1.65 and noise -0.60.

## The fit

I'll run `building-zones-location` on this dataset at the code of #1212 (35131df8), with the
night's settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021,
fit-only. I expect it to take about 16 minutes and cost about $0.70. I'll score it with
`python -m rentfrontier.simulate score`, and I'll check map leakage myself by comparing the
fitted map F with the true F at each building.

## Predictions

- It passes the gate (R-hat <= 1.01, ESS > 400).
- Each of the six location coefficients' 90% intervals covers its planted value. Water has the
  widest interval in the real fit (2.5 points), and I expect its median to land within 0.8
  points of -1.65. The other five land within 0.3 points of the truth.
- Across all coefficients, nu and the sigmas, 90% coverage is between 80% and 97%, as in the
  floor model's simulated recovery.
- The map doesn't absorb the big-park term. Over the buildings with training rows in the
  nearest fifth by big-park distance (mostly along Central and Prospect Park), the
  row-weighted mean of fitted F minus true F is under 0.5 points in size, and the same holds in
  the farthest fifth. If the map took part of the term, the near fifth's error would be
  positive and the big-park coefficient would come back smaller in size than -2.08.
- The same check on water's nearest and farthest fifths gives an error under 0.5 points in size.
- The source fit's map amplitudes, 0.868 (Manhattan) and 0.346 (outside), fall inside the new
  fit's 90% intervals for them.
