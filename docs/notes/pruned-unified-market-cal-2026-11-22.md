# Option 1 Pre-Fit Predictions: Pruned Unified Model, Individual Marks, 24-Factor Speedup & Two-Date Market Calibration (2026-11-22)

Committed before launching Modal GPU screening runs (`ops/modal-screen`) in accordance with `CLAUDE.md`.

## Research Questions
1. **24-factor trace speedup (`drift.py`):** Does tracing only the `F <= 24` free `phase_factor` scalars (expanding `phase_scale` only on kept draws) cut `unified-seg` / mapped `ablate` wall time on `A100-40GB` by at least **25–40%** with zero change in posterior accuracy?
2. **Individual `marks` ablation on `screen-mkt-k5` (`asof-20251110`):** Which of the 5 mark groups (`mark_changed`, `mark_baths`, `mark_floor1`, `mark_large01br`, `mark_thin`) drive the `+55` projected market ELPD and `+0.37 pp` coverage boost observed when adding `marks` on top of `layrng,size,y1,covid_vol`?
3. **Freezing `2024+` year scale (`y1_pre2024`) + `seg` GPs on `latest` & TWO independent `market` dates (`screen-mkt-k5` `2025-11-10` and `screen-mkt2-k5` `2026-11-20`):**
   - Does `y1_pre2024` preserve `latest` ELPD while lifting `market` 80% coverage (by removing the `yr:2025 = 0.960` closed-ad dip)?
   - Does pruned `clean-u-seg` (`layrng,size,y1_pre2024,covid_vol,marks,seg`) beat `unified-seg` (`exp2-k5-u4s`) on `screen-k5` (`latest`) by dropping negative passengers (`bedunit`, `sbf`) and adding `covid_vol`?
   - Does `seg` (Matérn-3/2 segment GPs) help or hurt on **both** `market` dates (`2025-11-10` and `2026-11-20`)?
4. **Out-of-sample open-market scale calibration (`drift_score --open-scale 1.12`):** Calibrated on full `u3-mkt` (`2025-11-10`, where `1.12x` achieved exact `80.00%` coverage and `+33.50` ELPD), does `open_scale = 1.12` improve 80% coverage toward `80%` and gain ELPD **completely out-of-sample** on `screen-mkt2-k5` (`2026-11-20`)?

## Pre-Fit Quantitative Predictions (Committed Before Launch)

| Run | Split | Variant | Predicted Projected ΔELPD (vs `l2bt`) | Predicted 80% Cov (raw) | Falsification Threshold |
|---|---|---|---|---|---|
| `o1-mkt-mk-thin` | `screen-mkt-k5` | `mark_thin` | `+40 to +120` (largest single mark on market) | `+0.2 to +0.5 pp` vs `l2bt` | `< +15` falsifies `mark_thin` as main market driver |
| `o1-mkt-mk-baths` | `screen-mkt-k5` | `mark_baths` | `+10 to +60` | `+0.0 to +0.3 pp` | `< -20` falsifies `mark_baths` |
| `o1-mkt-mk-changed` | `screen-mkt-k5` | `mark_changed` | `+5 to +50` | `~0 pp` | `< -20` falsifies `mark_changed` |
| `o1-mkt-mk-floor1` | `screen-mkt-k5` | `mark_floor1` | `-10 to +30` (near noise) | `~0 pp` | `> +40` surprises upside |
| `o1-mkt-mk-large01br` | `screen-mkt-k5` | `mark_large01br` | `-10 to +30` (near noise) | `~0 pp` | `> +40` surprises upside |
| `o1-lat-clean-pre24` | `screen-k5` | `layrng,size,y1_pre2024,covid_vol,marks` | `+3,100 to +3,400` (beats `u1` `+2,844` by `+300+`) | `79.5% to 80.5%` | `< +2,900` means `y1_pre2024` or `marks` hurt `latest` |
| `o1-lat-clean-seg` | `screen-k5` | `layrng,size,y1_pre2024,covid_vol,marks,seg` | `+5,100 to +5,600` (beats `u4s` `+5,097`) | `79.5% to 80.8%` | `< +5,000` means pruning didn't beat `u4s` |
| `o1-mkt-clean-pre24` | `screen-mkt-k5` | `layrng,size,y1_pre2024,covid_vol,marks` | `+150 to +300` vs `l2bt` | `76.5% to 78.2%` (`+0.5 pp` over `y1`) | `< 76.0%` means `yr:2025` wasn't a real contributor |
| `o1-mkt-clean-seg` | `screen-mkt-k5` | `layrng,size,y1_pre2024,covid_vol,marks,seg` | `+100 to +350` vs `l2bt` (`seg` neutral-to-positive on market) | `76.5% to 78.5%` | `> 60` ELPD below `clean-pre24` means `seg` hurts market |
| `o1-mkt2-clean-pre24` | `screen-mkt2-k5` | `layrng,size,y1_pre2024,covid_vol,marks` | `+150 to +350` vs `o1-mkt2-l2bt` | `75.0% to 78.5%` raw; `79.0% to 81.5%` with `open_scale=1.12` | `open_scale=1.12` hurting ELPD or overshooting `>83%` falsifies fixed `1.12x` |
| `o1-mkt2-clean-seg` | `screen-mkt2-k5` | `layrng,size,y1_pre2024,covid_vol,marks,seg` | `+150 to +400` vs `o1-mkt2-l2bt` | `75.0% to 78.5%` raw; `79.0% to 81.5%` with `open_scale=1.12` | `seg` inconsistent sign between `2025-11-10` and `2026-11-20` flags non-stationarity |

### Speedup Prediction
- Mapped `clean-seg` (`o1-lat-clean-seg`) on `A100-40GB` warm will complete in **8–13 minutes** (down from `~19–21 min` before tracing 24 factors instead of 1,905 cells).

## Budget
- 12 screening runs on `A100-40GB` (2 chains, 400 warmup + 400 post-warmup, warm XLA cache): projected **`$3.50–$5.50`** total.
