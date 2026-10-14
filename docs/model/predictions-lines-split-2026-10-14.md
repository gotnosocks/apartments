# Predictions: lines on the split C (2026-10-14)

I wrote these before the fit, as the coordinator's brief of 15:27Z on 2026-10-14 asks. The fit
isn't served. I report its result to Ben before any switch.

## The fit

The fit is lines (`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` on
`nb8-nostuy-lines-v1`, row split) with C's sampler settings. It uses the split C's rules
unchanged: `latest-ask-v2`, `quarantine-v13` and `tune-westcoast-split-v1`. The label is the split
C's (`a100-4500k9cb1-nb8-ul15r1s4q13ad3la2-tune-westcoast-split-v1`), so both runs pair on the
same rows. I compare it with the split C fit (`...-rows-f469edaa-...`), which passed the gate.

`cap.py` estimates 2,835 s and $2.05 at lines' own rate of 0.424 s an iteration, under the
3,600 s per-fit cap. Its last Modal fit spent 2,035 s fitting and 415 s on LOO. The summary bundle
now runs on thelio (#761), so the container's 1,200 s summary step no longer counts.

## Predictions

The basis is lines against C on the first ask and `quarantine-v12`
([newbuilding-clustered-2026-10-13.md](newbuilding-clustered-2026-10-13.md)). There lines
gained +53.0 in PSIS-LOO, with an iid SE of 15.4 and a lot-clustered SE of 22.1. The new prices
and the split change neither model's terms, so I expect a similar gap.

| Quantity | Prediction | Basis |
|---|---|---|
| Gate | Passes, 75% likely; max group R-hat under 1.05 | lines passed on q12; split C's group max 1.026 |
| Fit time, cost | 2,400 to 2,900 s, $1.90 to $2.20 | 2,450 s fit and LOO on 2026-10-11 |
| Paired PSIS-LOO against the split C | +53 (+20 to +90) | +53.0 on q12 |
| iid SE / lot-clustered SE | 14 to 17 / 20 to 25 | 15.4 / 22.1 |
| Verdict | A win under the iid SE and a tie under the lot SE | the same on q12 |
| Held-out median miss against the latest ask | 3.68 to 3.78% | split C 3.73% |
| Held-out 80% / 95% coverage | 79.0 to 80.0 / 94.6 to 95.2 | split C 79.4 / 94.9 |
| New-building score: miss | 11.8 to 12.2% | lines 12.0%, split C 12.0% |
| New-building 80% / 95% coverage | 90.5 to 91.1 / 98.1 to 98.4 | lines 90.8 / 98.2, split C 90.4 / 98.1 |

If lines wins by more than 2 lot-clustered SEs, I report it to Ben with the numbers above and
ask before any rule or serving change. If it ties, it goes on the unadopted list with its result.

## Results

The fit ran as `...-nb8-nostuy-lines-v1-rows-11c81a08-...-tune-westcoast-split-v1` and finished at
12:24 ET on 2026-10-14. I scored it against the split C with `rentfrontier.clusterse` and
`rentfrontier.finalask`.

| Quantity | Prediction | Result | Hit |
|---|---|---|---|
| Gate | Passes, 75% likely | Passes: max R-hat 1.006, min ESS 580, max group R-hat 1.024 | yes |
| Fit time, cost | 2,400 to 2,900 s, $1.90 to $2.20 | 2,436 s, $1.79 settled | time yes, cost no |
| Paired PSIS-LOO against the split C | +53 (+20 to +90) | +22.5 | yes, at the low end |
| iid SE / lot-clustered SE | 14 to 17 / 20 to 25 | 9.3 / 10.3 | no |
| Verdict | A win under the iid SE, a tie under the lot SE | A tie under both | no |
| Held-out median miss against the latest ask | 3.68 to 3.78% | 3.72% (split C 3.73%) | yes |
| Held-out 80% / 95% coverage | 79.0 to 80.0 / 94.6 to 95.2 | 79.4 / 94.8 | yes |
| New-building score: miss | 11.8 to 12.2% | 12.0% | yes |
| New-building 80% / 95% coverage | 90.5 to 91.1 / 98.1 to 98.4 | 90.46 / 98.1 | 80% just under, 95% yes |

The building-weighted new-building log predictive density favors lines by +63.2 nats, with a lot
SE of 13.9, about the same as on the first ask (+83.9, lot SE 14.4). On PSIS-LOO, the gap shrank
from +53 to +22.5, and its SEs fell by more than half. I haven't checked which of the latest ask,
`quarantine-v13` and the split accounts for that.

Lines ties C on the board's PSIS-LOO rule, so it isn't served. I put it on the unadopted list and
report both scores to Ben.
