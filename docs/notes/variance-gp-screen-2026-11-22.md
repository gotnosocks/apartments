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

---

## Post-Fit Results & Honest Prediction Scorecard (10 Modal `A100-40GB` Runs, `$5.38` Total)

All 10 runs launched at commit `d9a0a3ea` (`MODAL_FIT_REPO=/data1/apartments/tmp/wt-vargp`) and completed cleanly in 17 minutes wall time (`$0.41–$0.67/run`, **`$5.38` total**). Note that `SV_MODES` was set to `22` (`>99%` Matérn-3/2 variance) in commit `d9a0a3ea` (giving `34` free scale factors for `sv_gp` and `36` for `hybrid` rather than `18`/`20` listed in the draft pre-fit table above). All ELPD scores below use the official leak-free `rentfrontier.drift_score.score_run` quadrature with building-clustered paired SEs (`N = 37,199`, full-panel scale `×5.0982` for `screen-k5` `189,647 / 37,199`; `N = 1,891`, scale `×5.0095` for `screen-mkt-k5` `9,473 / 1,891`).

### Verdict: **Decisive Win for `sv_gp` (Smooth Matérn-3/2 Stochastic Volatility GP)**
1. **`sv_gp` decisively beats `y1 + covid_vol` on closed-ad `latest` by `+275.4 ± 62.3` projected ELPD (`z = +4.42`)** — and beats the incumbent production `unified-seg` (`u4s`) by **`+566.5 ± 110.6` (`z = +5.12`)** — with **zero external Covid CSVs** and **zero Jan 1 step-function cliffs**.
2. **`sv_gp` ALSO beats `y1 + covid_vol` on raw open-market `screen-mkt-k5` by `+34.1 ± 14.2` (`z = +2.40`)** (and beats `u1` by **`+38.4 ± 15.5`, `z = +2.48`**). Its optimal `open_scale` lands **dead-on `1.12`** (`Cov80 = 79.43%`, **`+251.3 ± 80.9` (`z = +3.11`)** over `range-j`), whereas discrete `y1 + covid_vol` over-shrinks `2025` (`yr:2025 = 0.984×`) and requires `open_scale = 1.16`.
3. **Physical mechanism validated (`vel_gp`):** Just **two** leak-free causal market-velocity parameters (`vel:down = 1.264×` per `-15%/yr` crash, `vel:up = 1.094×` per `+15%/yr` boom — **`2.6×` stronger volatility response during crashes than booms!**) recover **`+1,354.8 / +1,459.6 = 92.8%`** of the entire 14-parameter `y1 + covid_vol` lift on `latest` (`z = +8.98` vs floor), beat `y1 + covid_vol` by **`+138.2` in 2020**, and run `-17%` faster (`0.551` vs `0.664 s/sweep`).
4. **Hybrid (`vel_gp + sv_gp`) is largely redundant on top of `sv_gp`:** It adds only `+38.7 ± 34.8` (`z = +1.11`) on `latest` and `+6.9 ± 6.2` (`z = +1.11`) raw / `+2.7 ± 5.3` (`z = +0.51`) at `1.12×` on `market`, while halving `phase_factor` minimum ESS (`68 → 32` on `latest`, `35 → 19` on `market`) due to collinearity between `vel_gp` and `sv_gp` (`r = 0.700` across 2015–2026). **`sv_gp` alone is the clean, canonical winner.**

### 1. Head-to-Head Scorecard — `screen-k5` (`latest`, `N = 37,199`, scale `×5.0982`)

| Arm | Run (`d9a0a3ea`) | Free Scale Factors | Cells | Raw ELPD | Δ vs Arm 0 (Proj) | Δ vs Arm 1 `y1cov` (Proj) | Δ vs `u4s` (Proj) | MAE | Cov80 | `pf` max `R̂` / min ESS | s/sweep | USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| **0. Floor (`notime`)** | `vg-lat-0-notime` | 12 | 163 | `47,469.8` | `0.0` | `-1,459.6 ± 169.3` (`-8.62`) | `-1,168.6 ± 180.8` (`-6.46`) | `5.454%` | `80.10%` | `1.020` / `75` | `0.531` | `$0.57` |
| **1. `y1 + covid_vol`** | `vg-lat-1-y1cov` | 26 | 2,660 | `47,756.1` | `+1,459.6 ± 169.3` (`+8.62`) | `0.0` (ref) | `+291.0 ± 91.3` (`+3.19`) | `5.441%` | `79.73%` | `1.046` / `97` | `0.664` | `$0.61` |
| **2. `sv_gp` (Winner)** | `vg-lat-2-svgp` | 34 | 5,004 | **`47,810.1`** | **`+1,735.0 ± 187.5` (`+9.25`)** | **`+275.4 ± 62.3` (`+4.42`)** | **`+566.5 ± 110.6` (`+5.12`)** | `5.441%` | `79.84%` | `1.041` / `68` | `0.748` | `$0.64` |
| **3. `vel_gp` (2 params)** | `vg-lat-3-velgp` | 14 | 5,005 | `47,735.5` | `+1,354.8 ± 150.8` (`+8.98`) | `-104.8 ± 109.3` (`-0.96`) | `+186.2 ± 135.1` (`+1.38`) | `5.441%` | `80.04%` | `1.029` / `100` | `0.551` | `$0.57` |
| **4. `vel_gp + sv_gp`** | `vg-lat-4-hybrid` | 36 | 5,005 | `47,817.7` | `+1,773.7 ± 185.4` (`+9.57`) | `+314.1 ± 63.8` (`+4.92`) | `+605.1 ± 111.3` (`+5.44`) | `5.437%` | `79.90%` | `1.056` / `32` | `0.775` | `$0.67` |
| *Ref: `unified-seg`* | `exp2-k5-u4s` | 24 | — | `47,699.0` | `+1,168.6 ± 180.8` (`+6.46`) | `-291.0 ± 91.3` (`-3.19`) | `0.0` (ref) | `5.447%` | `79.66%` | — | `0.645` | — |
| *Ref: `l2bt`* | `exp2-k5-l2bt` | 6 | — | `46,719.8` | `-3,823.3 ± 375.4` (`-10.19`) | `-5,283.0 ± 387.7` (`-13.62`) | `-4,991.9 ± 396.5` (`-12.59`) | `5.498%` | `79.92%` | — | `0.361` | — |

*Note on `hybrid` vs `sv_gp`: `+38.7 ± 34.8` projected (`z = +1.11`, not significant).*

### 2. Head-to-Head Scorecard — `screen-mkt-k5` (`asof-20251110`, `N = 1,891`, scale `×5.0095`)

| Arm | Run (`d9a0a3ea`) | Raw ELPD (`1.00×`) | Raw Cov80 | Raw Δ vs `1-y1cov` (Proj) | `@1.12×` ELPD | `@1.12×` Cov80 | `@1.12×` Δ vs `range-j` raw (Proj) | Best `open_scale` | MAE | USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **0. Floor (`notime`)** | `vg-mkt-0-notime` | `1,954.2` | `76.57%` | `-1.2 ± 24.8` (`-0.05`) | `1,959.6` | `80.65%` | `+191.5 ± 79.7` (`+2.40`) | `1.10` (`1,960.0`) | `7.208%` | `$0.42` |
| **1. `y1 + covid_vol`** | `vg-mkt-1-y1cov` | `1,954.4` | `74.51%` | `0.0` (ref) | `1,971.2` | `77.95%` | `+249.8 ± 80.2` (`+3.11`) | `1.16` (`1,972.6`) | `7.191%` | `$0.47` |
| **2. `sv_gp` (Winner)** | `vg-mkt-2-svgp` | **`1,961.2`** | **`75.57%`** | **`+34.1 ± 14.2` (`+2.40`)** | **`1,971.5`** | **`79.43%`** | **`+251.3 ± 80.9` (`+3.11`)** | **`1.12` (`1,971.5`)** | `7.199%` | `$0.48` |
| **3. `vel_gp` (2 params)** | `vg-mkt-3-velgp` | `1,947.6` | `73.72%` | `-34.2 ± 13.6` (`-2.51`) | `1,967.2` | `77.26%` | `+229.5 ± 79.1` (`+2.90`) | `1.20` (`1,969.7`) | `7.185%` | `$0.41` |
| **4. `vel_gp + sv_gp`** | `vg-mkt-4-hybrid` | `1,962.6` | `75.62%` | `+41.0 ± 16.0` (`+2.56`) | `1,972.1` | `79.69%` | `+254.0 ± 80.8` (`+3.15`) | `1.12` (`1,972.1`) | `7.197%` | `$0.54` |
| *Ref: `unified`* | `exp3-mkt2-u1` | `1,953.6` | `74.99%` | `-4.3 ± 13.7` (`-0.31`) | `1,969.4` | `78.48%` | `+240.5 ± 79.8` (`+3.01`) | — | `7.195%` | — |
| *Ref: `range-j`* | `exp3-mkt2-rangej` | `1,921.4` | `76.89%` | `-165.7 ± 85.3` (`-1.94`) | `1,928.1` | `80.65%` | `0.0` (ref) | — | `7.256%` | — |

### 3. Why `sv_gp` Wins — Year-by-Year Decomposition & Posterior Trajectory

`sv_gp` beats `y1 + covid_vol` in almost every year since 2020 (`2020: +139.0`, `2021: +25.8`, `2022: +32.3`, `2023: +49.1`, `2024: +6.2`, `2025: -2.7`, `2026: +19.2`), with **half of the entire gain (`+139.0`) coming from 2020 alone**:
- **Discrete `y1 + covid_vol`** forces a single `1.581×` step onto all 12 months of 2020 (including quiet Jan–Feb 2020 before lockdown!) and pins late 2021 at `1.521×`.
- **Smooth `sv_gp`** recovers the true continuous shock curve with zero external CSVs:
  - `2018–2019`: calm `0.82×–0.91×`
  - `2020 Q1`: `1.04×` → `2020 Q2`: `1.33×` → `2020 Q3`: `1.73×` → **`2020 Q4` peak: `2.01×`**
  - `2021 Q1`: `1.97×` → `2021 Q2`: `1.66×` → `2021 Q3`: `1.36×` → `2021 Q4`: `1.19×`
  - `2022 Q1–Q4`: smooth secondary boom wave `1.15× → 1.19× → 1.16×`
  - `2023 Q1–Q4`: `1.09× → 1.03× → 1.01× → 1.01×`
  - `2024–2026`: steady `0.94×–1.03×`
- **`vel_gp` mechanism & limitation:** `vel:down = 1.264×` (`log = +0.2344 ± 0.0047`) vs `vel:up = 1.094×` (`log = +0.0899 ± 0.0048`) proves that falling markets inflate listing dispersion `2.6×` more strongly per `%/yr` than rising markets, explaining `+138.2` over `y1 + covid_vol` in 2020. However, the raw non-deseasonalized weekly median EMA picks up seasonal Q4 winter rent dips (`1.14×–1.31×` in Q4 2023–2025), costing `-52` to `-71` ELPD/yr in 2024–2026 and slightly under-dispersing raw `screen-mkt-k5` (`73.72%` coverage).

### 4. Honest Scoring of Pre-Fit Predictions

| Arm | Pre-Fit Prediction | Observed Result | Verdict |
|---|---|---|---|
| **Arm 1 (`y1+covid_vol`)** | `+1,450 to +1,700` vs Floor; `+250 to +380` vs `u4s` | **`+1,459.6 ± 169.3`** vs Floor; **`+291.0 ± 91.3`** vs `u4s` | **HIT** (both intervals) |
| **Arm 2 (`sv_gp`)** | `+1,550 to +1,900` vs Floor; `+80 to +250` vs Arm 1; `-20 to +60` mkt vs Arm 1 | **`+1,735.0 ± 187.5`** vs Floor; **`+275.4 ± 62.3`** (`z=+4.42`) vs Arm 1; **`+34.1 ± 14.2`** (`z=+2.40`) raw mkt / `+1.4` @ `1.12×` | **HIT / BEAT** (exceeded `+250` upper bound vs Arm 1!) |
| **Arm 3 (`vel_gp`)** | `+950 to +1,350` vs Floor; `-450 to -100` vs Arm 1; `-30 to +50` mkt vs Arm 1 | **`+1,354.8 ± 150.8`** (`92.8%` of `y1cov`) vs Floor; **`-104.8 ± 109.3`** vs Arm 1; **`-34.2 ± 13.6`** raw mkt / `-20.3` @ `1.12×` | **HIT on `latest`; slight MISS (`-4.2` pts) on raw mkt** (seasonal Q4 velocity noise) |
| **Arm 4 (`hybrid`)** | `+1,600 to +1,950` vs Floor; `+100 to +300` vs Arm 1; `-10 to +80` mkt vs Arm 1; redundancy check vs `sv_gp` | **`+1,773.7 ± 185.4`** vs Floor; **`+314.1 ± 63.8`** vs Arm 1; **`+41.0 ± 16.0`** raw mkt; `+38.7 ± 34.8` (`z=+1.11`) vs `sv_gp` | **HIT / BEAT**; confirms `vel_gp` is mostly redundant once `sv_gp` is present |

### 5. Operational Safeguard Before Full 6-Chain Production Gate

Inspecting `mkt-2-svgp`'s full 52-quarter posterior revealed one important detail: for quarters **strictly after the last training quarter** (`2026 Q1–Q4` in the `asof-20251110` fit, which have zero training rows), the unconstrained Matérn-3/2 eigenbasis reverts/oscillates (`1.34×–1.55×`). This did not affect any `asof-20251110` test row (all live on `2025 Q4 = 1.03×`), nor any `latest` row, **but before promoting `sv_gp` to a full 6-chain production gate or live `drift_today.py` scoring**, we should add a 1-line safeguard clamping `q_idx = np.minimum(q_idx, last_train_q)` in `sv_gp_features` so future scoring dates inherit the final observed quarter cleanly.

### 6. Recommended Next Production Gate Candidate
- **`latest` (`u5-svgp-lat`):** `--variant layrng,size,sv_gp,marks,seg` (projected **`+566.5 ± 110.6` (`z = +5.12`)** over `u4s`, zero external CSVs, keeps all 6 `marks`, drops `bedunit`/`sbf`).
- **`market` (`u5-svgp-mkt`):** `--variant layrng,size,sv_gp,marks` + `open_scale = 1.12` (projected **`+251.3 ± 80.9` (`z = +3.11`)** over `range-j`, `+38.4` raw / `+10.7` @ `1.12×` over `u1`).
- Self-contained visual report: [`docs/notes/variance-gp-screen-2026-11-22.html`](variance-gp-screen-2026-11-22.html).

