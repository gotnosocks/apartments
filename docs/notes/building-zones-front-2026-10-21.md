# Building zones with street frontage, 2026-10-21

Ben asked for frontage columns in the 1 km building-zones model with attributes, and for a
fit-only Modal run of it. I start from `rentfrontier.building_zones_attrs` with the 2-bed bath
ladder capped at 3 full baths (#1185), and I append six building columns:

    eta_s ~ Normal(F(s) + x_s' gamma, b_z)        gamma_j ~ Normal(0, 0.5)

## How I measure frontage

`rentfrontier.frontage` writes one row per registry building from the footprint outlines, the
LION street centerlines in the basemap and MapPLUTO (snapshot `20261020-fbf9a82`):

1. I put points every 3 m around the building's outline and every 5 m along each street,
   highway or service road. A building faces a street when one of the street's points lies
   within the roadway's half width plus 20 m of the outline. The 20 m is how far I look past
   the curb for the building's wall, since many Brooklyn and Queens houses stand behind a front
   yard. I never add it to any width.
2. A street's width is LION's `streetwidth`, curb to curb for one roadway. Where a road is
   divided, I add up the parallel roadways of the same name within 60 m of each other, taking
   one median width for each roadway. Park Avenue comes out at 84 ft, Broadway on the Upper West
   Side at 80 ft and Eastern Parkway at 110 ft.
3. `front_width_ft` is the widest street the building faces.
4. A corner comes from MapPLUTO's lot type (3 is a corner lot, any other nonzero type is not).
   Where the lot type is 0 or the BBL has no lot, I call the building a corner when it faces two
   differently named streets crossing at more than 45 degrees.

`tests/test_frontage.py` checks these steps on a toy boulevard with two 36 ft roadways, a 30 ft
side street, and buildings at the corner, 15 m back and 26 m back.

## Encoding

`rentfrontier.building_zones_front` codes the width in bands against 40 ft or less: 41 to 60 ft,
61 to 80 ft, and over 80 ft, plus a flag for unknown width. Row by row, the widths cluster at
side streets of 30 to 34 ft and avenues of 56 to 84 ft, and the 1 km model's building effects
move in opposite directions with width in the two zones, so I did not want a single log-width
slope. Corner is a 0/1 column against every other lot, with its own unknown flag.

On the latest split's 1,706,837 training rows:

| column | rows set | Manhattan | Brooklyn + Queens |
|---|---|---|---|
| widest street 41 to 60 ft | 350,553 (20.5%) | 23.8% | 15.9% |
| widest street 61 to 80 ft | 217,556 (12.7%) | 19.7% | 3.0% |
| widest street over 80 ft | 35,360 (2.1%) | 2.4% | 1.6% |
| width unknown | 67,176 (3.9%) | 3.1% | 5.2% |
| corner | 461,769 (27.1%) | 31.3% | 21.1% |
| corner unknown | 10,281 (0.6%) | 0.4% | 0.9% |

MapPLUTO decides the corner for 1,549,041 rows and the geometry for 147,515.

## Checks on thelio

- `test_columns_code_bands_and_corners` checks each column against a toy frontage table and
  checks that the attributes design is unchanged underneath.
- `test_recovers_simulated_frontage_coefficients` redraws a toy design's rents with all 14
  building coefficients at known values and recovers each within its 99.8% interval.
- `test_run` runs the model end to end through `rentfrontier.run`.

## What the 1 km fit's residuals suggest

Before writing predictions I averaged the 1 km attributes run's building effects (each
building's departure from its map value net of attributes) by band, weighted by training rows,
against buildings on streets of 40 ft or less, and corners against other lots:

| column | Manhattan | Brooklyn + Queens |
|---|---|---|
| 41 to 60 ft | +0.032 | -0.016 |
| 61 to 80 ft | +0.070 | -0.020 |
| over 80 ft | +0.059 | -0.012 |
| width unknown | +0.085 | +0.027 |
| corner | +0.066 | -0.001 |

The model gives each column one coefficient across both zones, so the fit lands between the
zones' values, closer to Manhattan's because Manhattan has more rows on wide streets.

## The run

The same dataset, split and sampler settings as the 1 km attributes run:

```sh
ops/modal-fit --dataset /data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc \
  --split latest COMMIT dense-w650 building-zones-front b0 4 150 650 5 \
  --seed 20261020 --no-loo --no-heldout
```

## Predictions, written before the fit

| # | Prediction |
|---|---|
| C1 | With the 2-bed 4-bath step gone, max R-hat 1.004 to 1.016 and min bulk ESS 450 to 900, with tau the slowest. Every gamma has bulk ESS over 1,000. |
| C2 | The fit stage takes 8 to 11 minutes and the run costs $0.33 to $0.45. |
| C3 | Widest street 41 to 60 ft: 0% to +4%. 61 to 80 ft: +2% to +7%. Over 80 ft: -2% to +6%. |
| C4 | Corner: +2% to +6%. |
| C5 | Width unknown: 0% to +6%. Corner unknown within 4 points of zero. |
| C6 | Every attribute coefficient stays within 1.5 points of the 1 km run's. Doorman full-time is the likeliest to fall, since doorman buildings line the avenues. |
| C7 | Building spread falls 0.002 to 0.008 in Manhattan (from 0.228) and 0 to 0.003 in Brooklyn + Queens (from 0.141). |
| C8 | Pairs of buildings 100 to 200 m apart in the same neighborhood, on opposite sides of a 41 to 70 ft street, differ by rms 0.222 to 0.229 in their building effects, against 0.230 in the 1 km run. Pairs with no street between them move by less than 0.003 from 0.202. The shrink stays small because both buildings of a pair often face the same avenue. |
| C9 | The zone gap stays within 1 point of +30.1%, nu within 0.03 of 3.83, and each sigma within 0.002. |
