# Predictions: C refit on latest-ask-v2 (2026-10-14)

I wrote these before the fit. Ben asked at 09:21Z on 2026-10-14 for the latest-ask change to be
followed through. The coordinator's brief at 09:23Z set the plan.

## The fit

The fit is C (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` on
`nb8-nostuy-v1`, row split) with C's sampler settings. Only the data rules change:

- `latest-ask-v2` (#730) prices each row at its listing's last on-market ask. It changes 73,424 of
  215,156 rows, by 4.7% at the median.
- `quarantine-v13` replaces `quarantine-v12` and adds 2 rows from a price screen.

Its label is `a100-4500k9cb1-nb8-ul15r1s4q13ad3la2`.

## Predictions

The basis is the tune fit on `tune-latestask-v1` (#714), which repriced 79,719 rows on an earlier
outcomes file.

| Quantity | Prediction | Tune fit on v1 |
|---|---|---|
| Gate | Passes (R-hat < 1.01 on scales, ESS > 400) | R-hat 1.005, ESS 663 |
| Fit time, cost | 2,100 to 2,600 s, about $2.05 | 2,307 s, $2.05 |
| New fit against the new prices, held-out rows: median miss | 3.65 to 3.85% | 3.73% |
| Same, 80% / 95% coverage | 78.5 to 80.0 / 94.5 to 95.3 | 79.3 / 94.9 |
| Served C against the new prices, same rows: median miss | 3.9 to 4.1% | 4.01% |
| Same, 80% / 95% coverage | 76 to 78 / 93 to 94 | 76.8 / 93.5 |
| New-building score: miss | 11.8 to 12.3% | 12.0% |
| Same, 80% / 95% coverage | 90.0 to 90.8 / 97.8 to 98.3 | 90.4 / 98.0 |
| Descriptive share | 25.3 to 26.5% | 25.9% |
| Concession coefficient | -2.5 to -4.0% | -3.6% |

PSIS-LOO isn't comparable with C's, since the target changes. A pair against C would measure the
repricing rather than the model.

## Decision rule

If the fit passes the gate and its held-out miss and coverage against the new prices are no worse
than the served C's on the same rows, with its new-building score no worse, it becomes the new C and
is served. Website hears about the switch.
