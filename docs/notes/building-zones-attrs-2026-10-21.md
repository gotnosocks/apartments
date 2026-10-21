# Building zones with building attributes, 2026-10-21

Ben asked for roof height, elevator, condo and doorman columns in the Gibbs building-zones
model, a fit-only Modal run of it, and a second run with the surfaces at 500 m. The model is
building zones on Gibbs from #1180, with each building's level centred on its map value plus
its attributes:

    eta_s ~ Normal(F(s) + x_s' gamma, b_z)        gamma_j ~ Normal(0, 0.5)

`rentfrontier.building_zones_attrs` builds x_s from eight columns:

1. `bld:log_height`: log roof height from the NYC building footprints (snapshot
   `20261016-5f07157-all`, `height_roof`, joined on the registry's BIN), centred at 78 ft.
   `bld:height_unknown` flags a placeholder BIN (N000000), a missing BIN, or no footprint with a
   positive height. An unknown height gets no fallback to MapPLUTO's floors.
2. `bld:elevator` and `bld:elevator_unknown`, against no elevator, from the building-attributes
   snapshot `20261020-0a7254f`.
3. `bld:condo`, a MapPLUTO class starting with R, against everything else. There is no co-op
   column.
4. `bld:doorman_full`, `bld:doorman_part` and `bld:doorman_virtual`, against none.

Each column is constant within a building, so I append them to the rows' fixed design. That
leaves the model unchanged and puts gamma in the global block, which the sweep draws exactly
with the building levels integrated out. Its prior is the Normal(0, 0.5) that B0 gives a column
outside its named groups. The saved building effects `bld` are each building's departure from
its map value net of its attributes.

`rentfrontier.building_zones_attrs_500m` runs the same model with both zones' surfaces built at
500 m from the same buildings.

## Data

The fits use NYC only, in two zones: Manhattan, and Brooklyn + Queens, with the zone taken from
the BBL. They use registry snapshot `20261019-bcfbb52-extend`. The brief named
`b0-30b3edae310c2fae-alldata-v36-dense-nyc`, but that copy predates the bath-count fix (#1172).
The last building-zones run used the bath-fixed `b0-edc83b49f9bacd8c-alldata-v36-dense`. I
built `b0-edc83b49f9bacd8c-alldata-v36-dense-nyc` from it with `rentfrontier.b0nyc`, which set
aside the same 72,598 NJ rows and left 1,896,486. Against the last run, then, only the NJ rows
and the attributes change.

On the latest split's 1,706,837 training rows:

| column | rows set |
|---|---|
| height unknown | 58,996 (3.5%) |
| elevator | 1,011,027 (59.2%) |
| elevator unknown | 13,587 (0.8%) |
| condo | 295,717 (17.3%) |
| doorman full | 350,817 (20.6%) |
| doorman part | 249,604 (14.6%) |
| doorman virtual | 389,933 (22.8%) |

## Checks on thelio

- `test_columns_code_heights_and_attributes` checks each column against the footprint and
  attributes tables of a toy registry, including placeholder BINs.
- `test_recovers_simulated_building_coefficients` redraws a toy design's rents from the model
  with gamma at known values and recovers all eight within their 99.8% intervals.
- `test_run` runs the model end to end through `rentfrontier.run`.
- `test_500m_rebuilds_the_surfaces_with_the_same_buildings` checks that the 500 m design keeps
  the buildings and rows and only rebuilds the waves.

## Time

On thelio's GPU, with the full training rows:

| surfaces | waves (Manhattan + outer) | global block | 1 chain | 2 chains |
|---|---|---|---|---|
| 1 km | 85 + 110 | 908 | 0.63 s | 1.34 s |
| 500 m | 340 + 440 | 1,493 | 1.16 s | 2.44 s |

At 1 km the sweep costs what the last run's did on thelio (1.36 s for two chains). On the A100
that run swept four chains in 0.54 s, with a fit stage of 532 s and a cost of $0.38, so this
fit should take about the same. `ops/modal/cap.py` takes that run's measured rate for this
model, and it estimates 1,712 s and $1.14 because of its default-rate floor.

At 500 m thelio's sweep costs 1.82 times as much. The dense factor of the global block grows
with the cube of its size, 4.4 times, and the A100 might scale closer to that than thelio's
card. Even then the fit stage would take about 39 minutes. I keep 650 kept sweeps a chain.
cap.py takes a stated 0.7 s an iteration per pair of chains and estimates 2,160 s and $1.44.
The balance was $9.89 when I checked, enough for both.

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest COMMIT dense-w650 building-zones-attrs b0 4 150 650 5 \
  --seed 20261020 --no-loo --no-heldout
```

The 500 m run uses `building-zones-attrs-500m` with the same arguments, after the 1 km run
finishes.

## Predictions for the 1 km fit, written before it

The timing run printed each chain's state after 11 sweeps. At 1 km Manhattan's building spread
was 0.228 and 0.231 and the outer zone's 0.140 and 0.141. In the last run the same printout
(0.267, 0.150) came within 0.001 of the final medians. I saw these before writing the
predictions below.

The earlier building-attributes fit without location (`building-attrs-fit-2026-10-20.md`)
found elevator +12.2%, condo +5.9%, floors +13.4% per e-fold, full-time doorman +6.7%,
part-time +9.4% and virtual -1.8%. Here the map and the building levels take the share of
those premiums that comes from where the buildings stand, so I expect smaller coefficients.

| # | Prediction |
|---|---|
| A1 | Max R-hat 1.005 to 1.025 and min bulk ESS 300 to 700, so the repo's 1.01 gate likely fails on the sparse bath steps again. Every gamma has bulk ESS over 1,000. |
| A2 | The fit stage takes 7 to 12 minutes, under the hour's cap, and the run costs $0.30 to $0.50. |
| A3 | Roof height: +4% to +11% per e-fold of height. |
| A4 | Elevator: +4% to +10%. |
| A5 | Condo: +2% to +7%. |
| A6 | Doorman: full-time +3% to +9%, part-time +3% to +9%, virtual -3% to +2%. |
| A7 | Building spread: 0.220 to 0.240 in Manhattan (10% to 17% below the last run's 0.266) and 0.135 to 0.145 in Brooklyn + Queens (3% to 10% below 0.150). |
| A8 | Building share of location variance: 0.45 to 0.53 in Manhattan (last run 0.559) and 0.34 to 0.40 in Brooklyn + Queens (0.402). |
| A9 | The 2-bed second-bath step lands at +20.5% to +23.5% (last run +22.9%). |
| A10 | Manhattan's map averaged over its ads lands 29% to 35% above Brooklyn + Queens' (last run +37.3%), since taller doorman buildings cluster in Manhattan. |
| A11 | nu lands within 0.05 of the last run's 3.85, and each sigma within 0.003 of its value. |

## Predictions for the 500 m fit, written before it

After 11 sweeps at 500 m Manhattan's spread was 0.221 and 0.224 and the outer zone's 0.139 and
0.138. Earlier fits found 500 m added little over 1 km.

| # | Prediction |
|---|---|
| B1 | Max R-hat 1.005 to 1.03 and min bulk ESS 200 to 600, with the amplitudes among the slowest. |
| B2 | The fit stage takes 14 to 30 minutes, the whole run under 35, and it costs $0.60 to $1.30. |
| B3 | Building spread 0.005 to 0.015 below the 1 km fit's in Manhattan and 0 to 0.008 below it in Brooklyn + Queens. |
| B4 | Building share 0.02 to 0.08 below the 1 km fit's in each zone. |
| B5 | Each amplitude 0% to 40% above the 1 km fit's. |
| B6 | Each gamma within 2 points of the 1 km fit's, with height the likeliest to fall. |
| B7 | The zone gap within 2 points of the 1 km fit's. |
| B8 | nu and the sigmas within 0.01 and 0.002 of the 1 km fit's. |

## Results at 1 km

The fit `building-zones-attrs-b0-latest-9bd8c1a3-dense-w650` ran on a Modal A100 from 20:48 to
20:57 ET on 2026-10-20, fit-only, seed 20261020. The fit stage took 535 s and the whole
container 557 s, at an estimated $0.37.

It misses the repo's convergence gate on the same sparse bath step as the last run:

| quantity | R-hat | bulk ESS |
|---|---|---|
| beta[bed=2:full>=4] | 1.0212 | 325 |
| tau | 1.0150 | 654 |

Every building coefficient has R-hat at or below 1.0023 and bulk ESS of 1,486 or more, and the
four chains' medians agree to within about 0.2 points.

| column | premium, median (90% interval) |
|---|---|
| roof height, per e-fold | -0.73% (-1.10 to -0.38) |
| height unknown | +0.23% (-0.52 to +0.99) |
| elevator | +9.05% (8.65 to 9.43) |
| elevator unknown | +1.73% |
| condo | +14.76% (14.25 to 15.32) |
| doorman, full-time | +19.57% (18.66 to 20.61) |
| doorman, part-time | +11.96% (11.13 to 12.86) |
| doorman, virtual | +4.39% (4.10 to 4.73) |

| # | Prediction | Posterior median | Result |
|---|---|---|---|
| A1 | max R-hat 1.005 to 1.025, min ESS 300 to 700, gamma ESS over 1,000 | 1.021, 325, gamma 1,486 or more | hit, though the repo gate fails |
| A2 | fit stage 7 to 12 min, $0.30 to $0.50 | 8.9 min, $0.37 | hit |
| A3 | roof height +4% to +11% | -0.7% | miss |
| A4 | elevator +4% to +10% | +9.1% | hit |
| A5 | condo +2% to +7% | +14.8% | miss |
| A6 | doorman full +3% to +9%, part +3% to +9%, virtual -3% to +2% | +19.6%, +12.0%, +4.4% | miss |
| A7 | spread 0.220 to 0.240 Manhattan, 0.135 to 0.145 BK+Q | 0.228, 0.141 | hit |
| A8 | share 0.45 to 0.53 Manhattan, 0.34 to 0.40 BK+Q | 0.494, 0.363 | hit |
| A9 | 2-bed second bath +20.5% to +23.5% | +23.49% (23.40 to 23.59) | hit, at the edge |
| A10 | zone gap 29% to 35% | +30.1% (29.6 to 30.6) | hit |
| A11 | nu within 0.05 of 3.85, sigmas within 0.003 | 3.83; 0.086, 0.086, 0.092, 0.103 | hit |

The map amplitudes fell from 1.10 to 1.03 in Manhattan and from 0.48 to 0.38 in Brooklyn +
Queens, and tau stayed at 0.0043.

The misses all come from the building columns. I expected the map to take part of the premiums
the no-location fit found, so I put every coefficient below that fit's. Instead condo and every
doorman level came out larger, and roof height fell to slightly below zero once elevator and
doorman enter. That earlier fit had much heavier noise (nu 6.85, sigmas 0.165 to 0.26), so its
coefficients are not directly comparable, and I have not checked which difference moved them.

The explainer data (map grid, buildings net of attributes, gamma with chain medians, R-hat,
ESS and traces, and a comparison with the last run) is at
https://claude.ai/artifact/DLdQHZgDQy6nWqkw7wyEdL.

## Results at 500 m

The fit `building-zones-attrs-500m-b0-latest-9bd8c1a3-dense-w650` ran on a Modal A100 from
20:58 to 21:08 ET on 2026-10-20, fit-only, seed 20261020. The fit stage took 576 s and the
whole container 594 s, and the Modal ledger settled it at $0.39. The A100 swept the larger
global block almost as fast as the 1 km one, so my estimate from thelio's card was about
three times too long.

It misses the gate on four quantities:

| quantity | R-hat | bulk ESS |
|---|---|---|
| amp[outer] | 1.0243 | 303 |
| amp[manhattan] | 1.0225 | 256 |
| beta[bed=2:full>=4] | 1.0211 | 324 |
| tau | 1.0141 | 679 |

| # | Prediction | Posterior median | Result |
|---|---|---|---|
| B1 | max R-hat 1.005 to 1.03, min ESS 200 to 600, amplitudes among the slowest | 1.024, 256, both amplitudes slowest | hit |
| B2 | fit stage 14 to 30 min, run under 35, $0.60 to $1.30 | 9.6 min, 9.9 min, $0.39 | miss |
| B3 | spread 0.005 to 0.015 lower in Manhattan, 0 to 0.008 lower in BK+Q | 0.2204 (0.008 lower), 0.1391 (0.0016 lower) | hit |
| B4 | share 0.02 to 0.08 lower in each zone | 0.468 (0.026 lower), 0.361 (0.002 lower) | half: hit in Manhattan, miss in BK+Q |
| B5 | each amplitude 0% to 40% higher | 0.336 (67% lower), 0.176 (54% lower) | miss |
| B6 | each gamma within 2 points | largest moves +0.41 points (height unknown, part-time doorman) | hit |
| B7 | zone gap within 2 points | +29.9% (29.3 to 30.4), 0.2 lower | hit |
| B8 | nu within 0.01, sigmas within 0.002 | nu 3.83, sigmas unchanged to 0.0001 | hit |

The building coefficients barely move: elevator +8.9%, condo +14.7%, full-time doorman +20.0%,
part-time +12.4%, virtual +4.5%, roof height -0.8% per e-fold.

I got B5 wrong about what the amplitude measures. It scales the waves' spectral weights, and
those weights change with the lengthscale. The map itself barely changed: its row-weighted
spread over Manhattan's buildings went from 0.183 to 0.188, and over Brooklyn + Queens' it
stayed at 0.167. At 500 m the map takes a little more of Manhattan's building-to-building
variation and almost none of the outer zone's, as earlier fits found.

The explainer data is at https://claude.ai/artifact/Gay8BUWr5iqNC1JdEAj2Mh.
