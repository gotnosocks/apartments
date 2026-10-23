# First-ask floor fit: results (2026-10-23)

The research group's fable asked for this fit (board post 20261023T072305Z, amended in 075703Z), and it passed 4 of 5. The design and the frozen predictions are in `docs/notes/first-ask-floor-predictions-2026-10-23.md`, merged in PR #1270.

- Run: `/data1/apartments/frontier/runs/building-zones-floor-b0-latest-6b5a5b4a-dense-firstask-w1000`
- Base: `/data1/apartments/frontier/runs/building-zones-floor-b0-latest-6b5a5b4a-dense-w1000`
- Dataset: `/data1/apartments/frontier/datasets/b0-edc83b49f9bacd8c-alldata-v36-dense-nyc-firstask`, the base rows with the first ask in place of the latest ask on 1,733,940 of 1,896,486 rows
- Settings: the base's model, commit 6b5a5b4a, 4 chains, 300 warmup, 1000 kept draws, thinning 5, seed 20261021, fit-only. Sampling took 799 s against the base's 804 s, and the run cost about $0.75.

## Convergence

The run passes the gate. Max R-hat is 1.0085 on `amp[outer]` and min ESS is 453 on `beta[bed=0:full>=4]`, with no quantity over 1.01 or under 400. The kept draws have the same shape as the base's, 4 chains of 200.

## Parameters against the predictions

Posterior median, with the 5% to 95% range in brackets.

| quantity | base | first ask | prediction | reading |
|---|---|---|---|---|
| σ, bedroom group 0 | 0.0834 | 0.0833 | 4% to 8% larger | miss: ratio 0.999 |
| σ, group 1 | 0.0819 | 0.0822 | 4% to 8% larger | miss: ratio 1.003 |
| σ, group 2 | 0.0882 | 0.0889 | 4% to 8% larger | miss: ratio 1.008 |
| σ, group 3 | 0.1015 | 0.1024 | 4% to 8% larger | miss: ratio 1.009 |
| Student-t ν | 4.134 [4.110, 4.158] | 4.017 [3.996, 4.039] | 1.7 to 1.9, with the base at about 2.0 | miss: the base is 4.13, not 2.0, and ν fell 0.117 |
| building sd, group 0 | 0.1832 | 0.1881 | within ±0.005 | hit, at +0.0049 |
| building sd, group 1 | 0.1139 | 0.1137 | within ±0.005 | hit, at −0.0002 |
| zone level, Manhattan | 0.1128 | 0.1134 | 0.5% to 1.5% higher | see below |
| zone level, outer | −0.1589 | −0.1598 | 0.5% to 1.5% higher | see below |
| intercept α | 7.5502 | 7.5806 | (none) | +0.030 |
| `unit:laundry_in_unit` (×100) | 6.13 | 6.10 [6.03, 6.16] | within ±0.7 of 6.13 | hit |
| `unit:dishwasher` (×100) | 1.98 | 2.05 | (none) | +0.07 |
| gate | passes | passes | passes | hit |

The zone level depends on how it's read. The zone offsets moved by under 0.001. The intercept rose by 0.030, so the overall level in both zones is about 3.0% higher, above the predicted 0.5% to 1.5%. Read as the overall level, the prediction misses high. Read as the zone offsets alone, it misses low.

The walk's scale terms barely moved: τ is 0.0043 against 0.0044, the amplitudes are within their intervals, and g is unchanged.

## Row-level results

These cover the 170,706 common held-out ads with a first ask. A subagent exported 200 thinned draws per ad at both dates, using the same draw indices in both runs, with `members/fable/models/export_first_ask_draws.py`. The predicted means match `simulate.mean` to within 1.1e-14. The analysis follows fable's freeze in `members/fable/models/first_ask_analysis.md`. The script is `members/fable/models/first_ask_analysis.py`, and the full output is `first_ask_analysis_results.json` in the same directory.

Each slope interval mixes the per-draw OLS slopes with their building-clustered sampling variance. Read it as a working calculation of model plus sampling uncertainty, not as calibrated frequentist coverage.

| quantity | result | prediction | reading |
|---|---|---|---|
| observed q90 − q10, base / first ask | 0.2636 / 0.2681, ratio 1.017 | 4% to 10% wider | miss |
| posterior-predictive q90 − q10 (secondary) | 0.2709 / 0.2735, ratio 1.010 | (none) | |
| coverage at 80 / 90 / 95%, base | 80.9 / 91.2 / 96.0% | | |
| coverage at 80 / 90 / 95%, first ask | 80.6 / 91.1 / 96.0% | 90% within 1 point of the base | hit |
| OLS slope, primary (170,666 ads, 35,791 buildings) | −0.1001 [−0.110, −0.090] | −0.20 to −0.40 | miss |
| the same without the 3-day typo exclusion | −0.140 [−0.156, −0.124] | within 0.02 of the primary, since under 0.5% of ads are dropped | miss: 40 ads (0.02%) move it by 0.04 |
| OLS slope, changed ads only (54,261) | −0.263 [−0.287, −0.240] | −0.30 to −0.50 | miss |
| drift-adjusted slope | −0.101 | within 0.05 of the raw slope | hit, 0.001 away |
| OLS slope with the base run's residual (secondary) | −0.114 [−0.124, −0.104] | (none) | |
| lagged peer IV (67,317 ads, 5,842 buildings) | −0.377 [−0.457, −0.299], first-stage F 551 to 608, OLS −0.108 on the same ads | −0.20 to −0.50 | hit |
| P(cut), bottom vs top decile of the residual | 10.7% vs 36.5%, rising steadily across the deciles | about 12% vs 45% | bottom near, top 8.5 points low |

The IV uses the instrument from `members/fable/checks/reaction_iv_lagged.py`. The regressor is the per-draw model residual instead of `dev_u`, and the outcome is the first-to-last change.

## Kill conditions

- **Dispersion: not met.** The σ ratio is under 1.01 in every bedroom group, and the q90 − q10 ratio is 1.017, under 1.02. ν fell 0.117, though, more than the 0.05 the kill allows, and the kill needs all three together. Two of the three parts say the first ask adds little residual spread, and ν says the tails grew slightly heavier.
- **Reaction: not met, by a hair.** The primary median is −0.1001 against a line at −0.10, and its 5% to 95% interval of −0.110 to −0.090 straddles the line. Without the 40 typo ads the slope is −0.140, on changed ads alone it is −0.263, and the IV gives −0.377.

## Reading

Measured by σ, coverage and observed spread, a model fit to first asks predicts held-out ads about as well as one fit to final asks. Ads posted above the model's prediction are cut more often and by more, and the IV estimate is larger than the OLS. Both are consistent with a first ask containing measurement error that OLS attenuates. As sol61 noted, these results describe the data and don't establish a causal correction share. The model's PLUTO features look ahead to later releases.

`members/fable/models/first_ask_analysis_sample.csv` holds a seeded sample of 2,000 ads (seed 20261023) with no ids, for plotting.

## Typo-cutoff correction (added after sol61's board post 20261023T103709Z)

The amendment writes the 3-day typo cutoff as 0.5 log points, which in this group's convention (100 × log, as in the ±0.7-point laundry prediction) means |d| > 0.005. The analysis ran with |d| > 0.5. I reran the slopes under both cutoffs with `first_ask_typo_sensitivity.py`, which produced `first_ask_typo_sensitivity.json`.

| cutoff | dropped | primary OLS (5–95%) | changed only | lagged peer IV |
|---|---:|---|---|---|
| \|d\| > 0.5 (as run) | 40 | −0.1001 [−0.110, −0.090] | −0.263 | −0.377 |
| \|d\| > 0.005 (as written) | 7,375 | −0.0934 [−0.104, −0.083] | −0.263 | −0.381 |

Under the cutoff as written, the primary slope is above −0.10, so the reaction kill condition is met. The interval still straddles −0.10.
