# All-data fit with NJ: results (converged)

*Visual tour: https://claude.ai/artifact/V9Pr5fhmGpBGxm5xFpj72f*

*Fit 2026-10-19. This is the #1156 design (normal walk, b0), unchanged, run on a new "all data" dataset that adds Hoboken and Jersey City (Historic Downtown, Waterfront, Paulus Hook, Newport) to the NYC rows. Ben approved this one fit and lifted the Modal budget for it. It was a fit-only run, with no LOO or held-out scoring. Predictions were written before launch in PR #1170. Nothing on the served model changed.*

## Inputs

- **Fit dataset:** `frontier/datasets/b0-30b3edae310c2fae-alldata-v36-dense`, 1,969,084 rows.
  - 1,896,504 are NYC and 72,598 are NJ. 18 pre-2013 rows are set aside, the same 18 as #1156.
  - It's built from pipeline build `rows-30b3edae310c2fae`. The NYC rows in that build match `rows-1ed2cd98fe208d45` in every column.
- **NJ cleanup:** 197 NJ listings that aren't whole apartments are set aside at the dataset level. They are 171 room shares, 25 shops or offices and 1 short stay, read in full by Sonnet readers. They come from `quarantine-v36` (PR #1168, not merged). The model's `data_rules` are empty, so the fit doesn't depend on #1168.
- **Registries:** NYC `20261019-bcfbb52-extend` (unchanged) and NJ `registry-nj 20261019-2d485c6`. The #1156 design reads neither.
- **Split:** latest. 1,772,176 rows train and 196,908 are held out.

## Run

- `normal-walk-b0-latest-ea4bcbd6-dense-w1500`. 16 chains, 1,500 warmup, 500 draws (every 12th kept), with up to 64 leapfrog steps.
- 23.3 minutes of wall time (22.4 of fitting) and $0.83, matching the cap.py estimate.
- 0 divergences while drawing, 195 in warmup. Step size 0.189, about 33 leapfrog steps per draw, acceptance 0.83.
- Draws: `/data1/apartments/frontier/runs/normal-walk-b0-latest-ea4bcbd6-dense-w1500/posterior.npz` on thelio.

## Convergence

| | This fit | #1156 |
|---|---|---|
| Max R-hat | 1.004 (τ) | 1.009 (τ) |
| Min bulk ESS | 2,296 (τ) | 1,678 (τ) |
| Divergences while drawing | 0 | 0 |

No chain disagreement shows on any traced quantity.

## Estimates, median [95%]

**Noise**

| | This fit | #1156 |
|---|---|---|
| ν | 21.5 [21.0, 22.0] | 21.3 |
| σ[0..3] | 0.235, 0.280, 0.284, 0.340 (each ±0.001) | 0.236, 0.282, 0.284, 0.341 |

**Bedroom ladder, % premium per step**

| Step | This fit | #1156 |
|---|---|---|
| Studio → 1 bed | +20.7 [20.6, 20.9] | +21.4 |
| 1 → 2 | +1.5 [1.4, 1.6] | +1.1 |
| 2 → 3 | +8.2 [7.9, 8.4] | +8.0 |
| 3 → 4 | +46.5 [45.9, 47.1] | +46.4 |
| 4 → 5 | +10.3 [9.2, 11.4] | +10.1 |
| Week-0 base | $2,491 [$2,424, $2,557] | $2,477 |

**Trend and season**

| | This fit | #1156 |
|---|---|---|
| Drift g | +2.8%/yr [−0.6, +6.7] | +2.9 |
| τ | 0.0116 [0.0104, 0.0127] | 0.0118 |
| 2020 trough | −24.2% [−25.2, −23.4], week of 2020-12-28 | −24.9 |
| Season peak | day 172 (June) | day 167 |

The largest weekly shocks are about 2.6 τ each, in 2022-01, 2014-06 and 2019-01.

## Where NJ sits

The #1156 design has no borough, zone or NJ term, so the fit itself gives NJ no level. Instead, this is each group's median training residual against the fitted mean, over 200 draws. The intervals cover only uncertainty in the mean, so they are tight and understate the real uncertainty about a group level.

| Group | Median residual, log [95%] | Rows |
|---|---|---|
| Hoboken + Jersey City | −0.147 [−0.147, −0.146] | 64,151 |
| Manhattan | +0.103 [+0.103, +0.104] | |
| Brooklyn | −0.136 [−0.137, −0.136] | |
| Queens (Ridgewood) | −0.142 [−0.150, −0.134] | 134 |
| All NYC | −0.002 | |

By NJ neighbourhood (median residual, log; every interval is within ±0.001):

| Neighbourhood | Offset | ≈ % | Rows |
|---|---|---|---|
| Waterfront | −0.058 | −5.6% | 11,217 |
| Newport | −0.098 | −9.3% | 10,438 |
| Paulus Hook | −0.108 | −10.2% | 6,752 |
| Hoboken | −0.206 | −18.6% | 23,510 |
| Historic Downtown | −0.250 | −22.1% | 12,234 |

Historic Downtown and Hoboken coming in lowest is a surprise, since both are sought-after. The model has no building age, size or amenity terms, so an older walk-up stock with smaller rooms would show up here as a lower residual. This is unchecked.

Net of beds, baths, season and trend, Hoboken and Jersey City ask about what Brooklyn does, and about 22% less than Manhattan. This is descriptive. A model with a location term (the Baseline thread's NJ zone) is what would put this on a footing that holds outside the model.

## Predictions (PR #1170): 10 of 12 hit

- **Convergence:** 4 of 4 hit.
- **τ, trough, g, season month:** hit.
- **NJ offset in [−0.15, +0.05]:** hit, at −0.147, near the low edge.
- **NYC residual moves < 0.01:** hit (0.006).
- **Miss, estimate 1:** the 2-bed second-full-bath premium fell 4.1 points, from +71.2% to +67.1%. The other three contrasts moved by less than 1 point.
- **Miss, estimate 6:** I predicted the noise scales would rise with NJ added. They moved −0.5% to +0.2%. ν moved by less than 10%, as predicted.

Standing scorecard (`normal_walk.scorecard`): 9 of 10. Item 7 missed: the largest shock is 3.4 τ against a 3.5 to 5.5 range. #1156 also missed it, at 3.5.

## Reading

- **Adding NJ didn't disturb the fit.** It converged as cleanly as #1156, and every shared estimate moved less than its run-to-run noise, except the 2-bed bath premium. NJ's ~4% more rows mostly fold into the noise and the mean.
- **The bath premium's move is unexplained so far.** My guess, not checked: NJ's newer, two-bath-heavy 2-bed stock sits below the NYC mean, and with no location term part of that gap loads on the bath contrast. That's the same kind of confound the same-building check flagged in NYC.
- **NJ sits about where Brooklyn does.** This is a residual reading, not a model term.

## Not done

- No LOO or held-out scoring (fit-only default).
- #1168 (`quarantine-v36` and the ad-screen fixes) is unmerged. Merging it would make the served fit unservable until a refit on v36. Its full test suite also hits a `test_b0_4` failure that fails on master too.
- Floor plans and photos for NJ ads: not collected, per Ben.
