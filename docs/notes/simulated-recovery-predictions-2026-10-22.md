# Simulated recovery of the floor model: predictions, 2026-10-22

Ben approved three Modal fits of `building-zones-floor` on simulated rents (2026-10-22 00:15Z).
These fits test whether the model returns effects I planted myself. I wrote these
predictions before launching any of them. The results go in
`simulated-recovery-results-2026-10-22.md`, and I'll record each miss there as a miss.

## The data

I built the three datasets with `python -m rentfrontier.simulate make`, starting from the floor
fit `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`. For each one I:

1. rebuilt the fit's design and checked it against the fit: the same 114 columns, the same latest
   split and the same snapshot paths (registry `20261019-bcfbb52-extend`);
2. took each term's posterior median from the 800 kept draws as the truth, covering the
   coefficients, the 673-week walk, the map's 195 wave coefficients, the 67,977 residual
   building levels, nu (4.13) and the four sigmas;
3. changed the scenario's terms;
4. drew every row's log rent around the truth with Student-t noise at the fit's scale;
5. wrote the copy with only `latest_ask` replaced.

The datasets are under `/data1/apartments/frontier/datasets/`, and the truths are in
`/data1/apartments/tmp/sim-recovery/<scenario>/truth.npz`.

| set | dataset | seed | what changes from the fit's medians |
|---|---|---|---|
| realistic | `sim-floor-realistic-20261022` | 20261022 | walk-up curve +0.4 pts a flight (floor k gets 0.004(k-1)); `unit:elev_top` log 1.04; `unit:lower` 0; elevator curve as fitted |
| null | `sim-floor-null-20261022` | 20261023 | both floor curves, all 7 floor flags and all 22 building feature terms set to 0: every `bld:` column plus in-unit laundry, in-building laundry and dishwasher; building levels are the fit's residual levels |
| height | `sim-floor-height-20261022` | 20261024 | curves and flags 0; every building's level gains 0.002 per MapPLUTO floor, centred on the training rows' mean, so +2% for every 10 floors with nothing for floor |

The simulated log rents have SD 0.437, 0.389 and 0.434 on all rows, against 0.440 in the real
data. Each correlates 0.92, 0.86 and 0.92 with the real log rent. The noise SD on training rows
is 0.122 in all three. MapPLUTO has a floor count for 99.1% of training rows' buildings. The
planted height term has SD 0.99 points across buildings.

## The fits

I'll run each fit exactly as the floor fit ran: the same code at 6b5a5b4a, 4 chains, 300
warmup and 1,000 sampling sweeps, every 5th kept, seed 20261021, fit-only. I'll launch them
one at a time, each when `ops/modal/cap.py` covers it. I expect each to take about 18 minutes
and cost about $0.75. I expect all three to pass the gate, because the model on these data is
the true model.

## Predictions

### All runs

- Every run passes the gate (R-hat <= 1.01, ESS > 400).
- nu and the four sigmas are covered by their 90% intervals in each run.
- Across the 114 coefficients, nu and the sigmas, 90% coverage in each run is between 80% and
  97%. The truth comes from posterior medians, not a draw from the prior, so the shrunk
  building levels and the map are smoother than the prior expects. I expect that to push
  coverage of the hierarchical parts up, and I don't expect it to move the fixed coefficients.
- The coefficients with the most rows miss most often, among them dishwasher, size and the bed
  steps, whose intervals are under 0.25 points wide. A miss there is a bias of a tenth of a point
  or so, not a wrong sign.
- Map F, scored at every building: 90% coverage between 75% and 97% for buildings with rows.
  Buildings with no training rows have F from the waves alone, and I expect coverage there to
  be close to the rest.
- Building residual levels: coverage between 85% and 97% for buildings with rows, with the
  shrinkage slope of median on truth between 0.75 and 0.95 overall. The slope falls with fewer
  rows: below 0.6 for buildings with 1 to 4 rows and above 0.9 for 100+.
- No misses clustered by floor: elevator-curve coverage at floors 30 and up is within 20 points
  of coverage below 30. Rare flags (`unit:lower`, 564 rows; `bld:built_unknown`, 7,368 rows)
  cover.

### Run 1, realistic

- The elevator curve is recovered: the truth falls inside the 90% band at every floor from 2
  to 30, and the error is under 0.5 points at every floor up to 40.
- The walk-up curve comes back rising: the median is positive at floors 3 to 6 and increases
  from floor 2 to floor 5. The band covers the truth (0.4 to 2.0 points) at no fewer than 4 of
  the 5 floors.
- `unit:lower` covers 0 and its interval is wide: at least 1.5 points, as in the floor fit (1.8).
- `unit:elev_top` covers 3.92%, with a median between 3.6% and 4.2%.

### Run 2, null

- Both floor curves come back flat. Every curve value's 90% interval covers 0 at no fewer than
  90% of floors, and no elevator floor up to 40 has a median above 0.5 points in size.
- The 7 floor flags cover 0, with no more than one miss.
- The 22 building feature terms cover 0, with no more than three misses, and no median exceeds
  0.7 points in size.
- The building levels absorb nothing from the zeroed features. Their shrinkage slope on truth
  is within 0.05 of run 1's.

### Run 3, height

- The elevator curve stays flat: the median at floors 10, 20, 30 and 40 is under 0.5 points in
  size, and the intervals at 10 and 20 cover 0. The floor's effect is identified within
  buildings, and the planted term varies between buildings only.
- The planted term goes into the building level, as the sum of `bld:log_height`, the other
  `bld:` columns, the residual levels and the map. I take each building's recovered level less
  its truth before planting and regress it on the planted term, weighting by training rows. The
  slope comes out between 0.85 and 1.15.
- Most of it goes to `bld:log_height`: a building's floor count and log height in feet go
  together, so I expect the coefficient to move from its truth of -0.92 to a positive value,
  with the residual levels taking the part log height can't express.
- The walk-up curve also covers 0 at every floor. Walk-ups run 2 to 6 floors, so the planted
  term varies by at most 1 point among them.
