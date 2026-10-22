# Normal walk results (2026-10-19)

**Run:** `normal-walk-b0-latest-98a9fe44-dense-w1500`. This was a fit-only run with the same data, settings and seed as the centered walk.

- Merged as [PR #1156](https://github.com/gotnosocks/apartments/pull/1156), with the predictions written into it before launch.
- Hardware: A100 40 GB.
- Wall time: 20.8 min. Cost: about $0.83.
- Report: https://claude.ai/artifact/QhYuiY36ZWpHuA55nomrKE
- Explainer: https://claude.ai/artifact/DL5iHPX21owniKQjiyVjXE

**What changed relative to the centered walk:**
- Sampler coordinates only, with the same posterior:
  - The intercept is dropped, and week 0's level takes the intercept's prior.
  - The sampler stores each week's total level (trend plus season), and the trend is computed as total minus season.
- Changes to the model itself:
  - Each bed/bath step is independent, with a Normal(0, 0.5) prior. The pool means and s_bath are gone.
  - The walk shocks are Normal(g, τ) in place of Student-t, so ν_T is dropped.
- Because the two model changes went into one fit, their effects can't be separated.

**Verdict:** The fit converged. Every quantity has R-hat ≤ 1.003 except τ, which is at 1.009.

## Convergence compared with the centered walk

| | Centered walk | Normal walk |
|---|---|---|
| Max R-hat | 4.63 (cos1) | 1.009 (τ) |
| Min ESS | 8.8 | 1,678 (τ) |
| Divergences, sampling / warmup | 0 / 291 | 0 / 221 |
| Step size | 0.0078 | 0.25 |
| Mean leapfrog steps | 32.5 | 19.8 |
| Tracked weekly levels with R-hat > 1.01 | 337 of 337 (worst 3.99) | 9 of 337 (worst 1.021) |

The ESS of everything except τ runs about 5,200–7,000.

## τ and the shocks

- τ is 0.0118 [0.0106, 0.0130], up from 0.0091.
- The realized shock sd is 0.0119, so sd/τ is 1.01 [0.955, 1.058]. In the centered walk it was 1.34.
- The largest shock is 3.47τ [2.93, 4.17], down from 6.8τ. No week exceeds 4τ, down from 9.
- Three of the five largest weekly shocks fall in the first week of January.

## Scorecard: 9 of 10 hit

- **Miss:** I predicted the largest shock would be 3.5–5.5τ. It came in at 3.47τ, just below the range.
- **Hits:**
  - 1 bed over a studio: +21.4%.
  - 2 beds over 1 bed: +1.1%.
  - 2-bed second bath: +71.2%.
  - 4-bed with one bath fewer: −28.6%.
  - Covid drop: −24.9%, with the trough in the week of 2020-12-28.
  - Drift g: +2.89%/yr.
  - Season peak: day 167, in June.
  - τ and sd/τ: both inside their ranges.

## Other results

- The season's peak-to-trough swing is 5.9%, down from 8.4%.
- The contrasts match the centered walk to within 0.1 point.
- Only thin bath cells moved by more than 0.01 log:
  - studio 3rd bath (75 ads);
  - studio 4th bath (15 ads), now at 0.59;
  - 2-bed 4th bath (78 ads).

## Possible follow-ups (none started)

- A New Year week term, since three of the five largest shocks fall in the first week of January.
- Pooling the thin bath cells.
- Serving this model.
