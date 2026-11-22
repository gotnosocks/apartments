# Variance GP Screen Pre-Fit Predictions: `sv_gp` vs `vel_gp` vs `y1 + covid_vol` (2026-11-22)

Committed before launching Modal GPU screening runs (`ops/modal-screen`) in accordance with `CLAUDE.md`.

## Controlled Experiment Design
Every arm shares the exact same proven base model (dropping only `bedunit` & `sbf`, keeping **all 6 `marks`**):
- **`screen-k5` (`latest`, `n = 37,929`, scale `×5.00`):** `layrng,size,marks,seg` + time-volatility arm.
- **`screen-mkt-k5` (`asof-20251110`, `n = 1,891`, scale `×5.01`):** `layrng,size,marks` + time-volatility arm (scored both raw and `open_scale = 1.12`).

| Arm | Token(s) | Time Params | Hypothesis |
|---|---|---:|---|
| 0. Floor (no time vol) | `layrng,size,marks[,seg]` | `0` | Baseline measuring total lift of time-varying volatility |
| 1. Incumbent (`y1 + covid_vol`) | `...,y1,covid_vol` | `14` | Best discrete time-volatility benchmark |
| 2. Smooth Log-Scale GP (`sv_gp`) | `...,sv_gp` | `18` (anchored Matérn-3/2, `α=0.25, ℓ=1.0 yr`, zero external CSVs) | Removes Jan 1 cliffs & Covid CSV; smooth quarterly trajectory |
| 3. Causal Market-Speed (`vel_gp`) | `...,vel_gp` | `2` (`vel:down`, `vel:up`, 100% leak-free trailing speed) | Tests if 2 physical parameters (`r=0.947`) match 14 discrete ones |
| 4. Hybrid (`vel_gp + sv_gp`) | `...,vel_gp,sv_gp` | `20` | Physical velocity + smooth residual GP |

## Pre-Fit Quantitative Predictions

| Arm | `screen-k5` (`latest`) Predicted ΔELPD vs Arm 0 (Floor) | `screen-k5` vs Arm 1 (`y1+covid_vol`) | `screen-mkt-k5` (`asof-20251110`) vs Arm 1 | Falsification Threshold |
|---|---|---|---|---|
| **Arm 1 (`y1+covid_vol`)** | **`+1,450 to +1,700`** | `0` (ref; `+250 to +380` over `u4s`) | `0` (ref) | `< +1,200` vs Arm 0 |
| **Arm 2 (`sv_gp`)** | **`+1,550 to +1,900`** | **`+80 to +250`** (beats `y1+covid_vol` by removing Jan 1 cliffs!) | **`-20 to +60`** (smoother boundary into late 2025) | `< -50` vs Arm 1 falsifies `sv_gp` |
| **Arm 3 (`vel_gp`)** | **`+950 to +1,350`** (captures 65–85% of full time-vol lift with just 2 params!) | **`-450 to -100`** (underperforms 18-mode GP on non-velocity shocks, but huge parsimony!) | **`-30 to +50`** (less overfitting on current year!) | `< +600` vs Arm 0 falsifies velocity mechanism |
| **Arm 4 (`vel_gp+sv_gp`)** | **`+1,600 to +1,950`** | **`+100 to +300`** (best overall) | **`-10 to +80`** | `< Arm 2` by `> 40` means `vel_gp` is redundant on top of `sv_gp` |

## Budget
- 5 arms on `screen-k5` + 4 arms on `screen-mkt-k5` (Arm 0, Arm 1, Arm 2, Arm 3 — plus Arm 4 on `screen-k5`; actually let's include Arm 4 on `screen-mkt-k5` too? 9–10 runs total on `A100-40GB`, projected **`$4.00–$5.00`** total).
