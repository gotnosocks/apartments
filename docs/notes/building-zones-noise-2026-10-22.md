# Outdoor noise in the floor model: results, 2026-10-22

I fit `building-zones-noise` on the floor fit's dataset and split
(`b0-edc83b49f9bacd8c-alldata-v36-dense-nyc`, latest split) with the floor fit's settings: 4
chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The run is
`building-zones-noise-b0-latest-9a8a81aa-dense-w1000`. It took 19 minutes on a Modal A100 for
an estimated $0.76. I compare it with the base fit,
`building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`, on posterior medians. The predictions
are in docs/notes/building-zones-noise-predictions-2026-10-22.md. The numbers below come from
`building-zones-noise-2026-10-22/summary.json`, which `build_summary.py` in the same folder
writes:

    python build_summary.py building-zones-noise-b0-latest-9a8a81aa-dense-w1000 summary.json

Like the transit and parks fits, this one adds its column to the floor model alone.

## Against the predictions

The coefficient is in points of log rent x100 per unit of log(1 + complaints a year).

| prediction | result | hit |
|---|---|---|
| passes the gate | max R-hat 1.004 (`unit:elev_f16`), min ESS 586 (`amp[outer]`) | yes |
| `bld:log1p_noise` between -2 and +0.5, interval reaching 0 or just below it | -0.58 (-0.75 to -0.39) | yes on the point, no on the interval, which lies clearly below 0 |
| map amplitudes move by under 1% | Manhattan 0.916 to 0.902 (-2%), outside 0.360 to 0.380 (+6%) | no |
| `bld_sd` moves by under 1% | 0.183 and 0.114, unchanged | yes |
| unit premiums move by under 0.1 | all unit columns move by under 0.01 | yes |
| held-out log score within 1 SE of the base | not scored, the fit ran fit-only | not run |

The amplitude miss is a miss against what I wrote, but like the falls in the transit and parks
fits, both moves sit well inside each fit's own uncertainty on the amplitude, whose 90% interval
spans 35% (Manhattan) to 40% (outside) of its median.

The predictions note said a zero-reaching interval would mean recording noise as not
explaining building levels. The interval excludes 0, so I record noise as explaining a small
part of them.

## The size of it

Over the fit's 67,977 buildings, the median building has 88 outdoor noise complaints a year
within 150 m, the 10th percentile 29 and the 90th 243. The term is 1.2 points lower at the 90th
percentile building than at the 10th (0.58 x (5.50 - 3.41)). The intercept rises by 2.7 points,
which takes back the term's average. No other term moves by more than 0.09 points.

## Reading it

Outdoor noise complaints go with slightly lower rent once the map and the building attributes
are in: about 1.2 points across the middle 80% of buildings, smaller than transit's 2 and much
smaller than parks' 5.7. The free check's coefficient on
the building residual, -0.9 points, is close to the fit's -0.58. The check's 0.2% share of
variance made it look like nothing, but a small slope over a column with this much spread still
adds up to about a point across buildings.

A complaint count mixes two things: how loud a block is, and how ready its residents are to call
311, which rises with rent. The second makes the coefficient less negative, so the association with noise
itself may be stronger than 0.58. A measure that doesn't depend on who calls, like traffic volume on the
building's own street, would separate the two.

Neither model is served, so the site doesn't change.
