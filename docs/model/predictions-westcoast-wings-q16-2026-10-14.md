# Predictions: C on the wing rule and quarantine-v16 (2026-10-14)

I wrote these before the fit. The first wing C (`...-nb8-nostuy-wings-v1-rows-676a0348-...-wings1`,
predictions in `predictions-westcoast-wings-2026-10-14.md`) failed the gate on one traced
building effect, 110 West 26th Street: split R-hat 1.015, bulk ESS 183. Ben ruled out a rerun on
a new seed and asked for the data to be checked first.

## What changed

Five asks at 110 W 26th are $2,395 to $2,595 one-bedroom ads with no square footage, among 1,600
sq ft loft asks of $5,000 to $8,400. Their phone contact matches an agent's East Village
one-bedrooms, so Data improvements reads them as ads filed under the wrong address.
`quarantine-v16` (#786) holds them out, along with 28 Brooklyn ads joined to Manhattan buildings
with the same number and street. It changes 28 NB8 rows (0.013%).

## The fit

C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` on
`nb8-nostuy-wings-v1`, row split) with C's sampler settings and the same seed, on master's rules
at launch: `baths-ad-v3`, `bedrooms-ad-v3`, `building-joins-v1`, `fields-review-v3`,
`latest-ask-v4`, `quarantine-v16`, `west-coast-wings-v1`, `unit-labels-v17`, `unit-reviews-v1`,
`unit-splits-v4`. The only difference from the first wing C is the 28 quarantined rows.

The random traced buildings stay the same if the building count stays at 5,414, so 110 W 26th is
still trace 0. Over all buildings, the first wing C had 6 with split R-hat over 1.01 on the kept
draws, the worst at 222 E 17th (1.037), 106 E 10th (1.030) and 110 W 26th (1.025). The passing
split C also had 6, the worst at 1.013. Quarantine-v16 changes nothing at 222 E 17th or 106 E 10th.

I report the gate as it stands and also the all-building split R-hat and ESS, so that the result
reads under either gate while Ben decides between them.

## Predictions

| Quantity | Prediction | Basis |
|---|---|---|
| Current gate (traced 32 + 32) | Passes, 65% likely | 110 W 26th loses its five outlying asks; the other traced effects passed |
| 110 W 26th split R-hat on the kept draws | Under 1.01, 70% likely | the outliers drove its building and walk apart |
| Buildings over 1.01 R-hat on the kept draws | 3 to 8 | 6 in both earlier fits |
| Max group R-hat | Under 1.05 | 1.031 on the first wing C |
| Fit time, cost | 1,550 to 1,800 s fitting, $1.80 to $2.30 settled | first wing C 1,648 s, settled $1.89 |
| Held-out median miss against the latest ask | 3.65 to 3.80% | split C 3.73% |
| Held-out 80% / 95% coverage | 79.0 to 80.0 / 94.6 to 95.2 | split C 79.4 / 94.9 |
| Serve test: no worse than the served C on miss and coverage against the latest ask | Passes, 85% likely | split C beat it by 0.29 pp and 2.6 / 1.3 points |

The fit is not served until Ben chooses the gate.
