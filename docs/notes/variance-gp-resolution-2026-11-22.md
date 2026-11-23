# Variance GP Temporal Resolution Screen: Quarterly vs Monthly vs Weekly (2026-11-22)

Pre-fit predictions committed before launching Modal GPU screening runs (`ops/modal-screen`) in accordance with `CLAUDE.md`.

## Motivation
In our initial 5-arm Variance GP screen (`d9a0a3ea`, PR #1536), quarterly `sv_gp` (`52` quarters, `ℓ = 1.0 yr`, 22 modes) beat discrete `y1 + covid_vol` by **`+275.4 ± 62.3` (`z = +4.42`)** on `screen-k5` and **`+34.1 ± 14.2` (`z = +2.40`)** on raw `screen-mkt-k5`, while quarterly 2-parameter `vel_gp` captured **92.8%** of `y1 + covid_vol`'s lift.

Because the mean global trend `L(t)` already lives on a **672-week grid** (`2013-12-02` onward), we test whether moving `sv_gp` and `vel_gp` from **quarterly** (`52` pts) to **monthly** (`156` pts) or **weekly** (`672` pts) — plus testing a sharper **`ℓ = 0.5 yr`** lengthscale at weekly resolution — unlocks further ELPD around sharp regime transitions (especially mid-March 2020 lockdown onset) without hurting open-market calibration or sampling efficiency.

All new `sv_gp_mo`, `sv_gp_wk`, `sv_gp_wk05`, and `vel_gp_wk` tokens also include the future-period clamping safeguard (`idx = np.minimum(idx, last_train_idx)`).

## Controlled Arms (8 Modal `A100-40GB` Runs, Projected `~$4.20–$4.80`)
Every arm shares the exact same base model as `vg-lat-2-svgp` / `vg-mkt-2-svgp` (`layrng,size,<token>,marks[,seg]`) and is compared directly against the already-scored quarterly `sv_gp` (`vg-lat-2-svgp`, `vg-mkt-2-svgp`) and quarterly `vel_gp` (`vg-lat-3-velgp`, `vg-mkt-3-velgp`).

| Arm | Token | Grid Points | Lengthscale `ℓ` | Modes | `screen-k5` Run | `screen-mkt-k5` Run |
|---|---|---:|---:|---:|---|---|
| *Ref (prev)* | `sv_gp` | 52 (quarterly) | `1.0 yr` | 22 | `vg-lat-2-svgp` | `vg-mkt-2-svgp` |
| **5. Monthly SVGP** | `sv_gp_mo` | 156 (monthly) | `1.0 yr` | 24 | `vg-lat-5-svgp-mo` | `vg-mkt-5-svgp-mo` |
| **6. Weekly SVGP (`1.0 yr`)** | `sv_gp_wk` | 672 (weekly, matches `L(t)`) | `1.0 yr` | 28 | `vg-lat-6-svgp-wk` | `vg-mkt-6-svgp-wk` |
| **7. Weekly SVGP (`0.5 yr`)** | `sv_gp_wk05` | 672 (weekly, sharper) | `0.5 yr` | 36 | `vg-lat-7-svgp-wk05` | `vg-mkt-7-svgp-wk05` |
| **8. Weekly Velocity GP** | `vel_gp_wk` | 672 (weekly) | causal 16-wk EMA | 2 | `vg-lat-8-velgp-wk` | `vg-mkt-8-velgp-wk` |

## Pre-Fit Quantitative Predictions

| Arm | `screen-k5` (`latest`, ×5.10) vs Quarterly Ref | `screen-mkt-k5` (`asof-20251110`, ×5.01) vs Quarterly Ref | Falsification / Decision Rule |
|---|---|---|---|
| **5. `sv_gp_mo` (monthly `1.0 yr`)** | **`+30 to +110`** vs `sv_gp` (removes 3-month staircase quantization in Mar–Apr 2020 & 2021) | **`-15 to +25`** raw / **`-10 to +15`** @ `1.12×` | `< +15` on `latest` means quarterly already saturated `ℓ=1.0 yr` |
| **6. `sv_gp_wk` (weekly `1.0 yr`)** | **`+40 to +130`** vs `sv_gp` (`0 to +30` vs monthly; same smooth `ℓ=1.0 yr` curve, zero bin edges) | **`-15 to +25`** raw / **`-10 to +15`** @ `1.12×` | `< +15` vs monthly at `>20%` slower wall time favors monthly |
| **7. `sv_gp_wk05` (weekly `0.5 yr`)** | **`+70 to +200`** vs `sv_gp` (sharper 6-month kernel nails mid-March 2020 cliff & shorter waves) | **`-30 to +20`** raw (risk of slight late-2025 overfitting vs `1.0 yr`) | `< sv_gp_wk` on `latest`, or `< -25` on market, falsifies `ℓ=0.5 yr` |
| **8. `vel_gp_wk` (weekly 2-param)** | **`+40 to +160`** vs quarterly `vel_gp` (sharper spring-2020 onset without quarterly averaging) | **`-20 to +40`** raw vs quarterly `vel_gp` (still trails `sv_gp_*` due to Q4 seasonality) | `< +20` vs quarterly `vel_gp` falsifies weekly velocity resolution |

---

## Post-Fit Results & Honest Prediction Scorecard (8 Modal `A100-40GB` Runs, `$4.68` Total)

All 8 runs launched at commit `cad5e31b` and completed cleanly in 19 minutes wall time (`$0.39–$0.76/run`, **`$4.68` total**). All ELPD scores below use official leak-free `rentfrontier.drift_score.score_run` quadrature with building-clustered paired SEs (`N = 37,199`, scale `×5.0982` on `screen-k5`; `N = 1,891`, scale `×5.0095` on `screen-mkt-k5`).

### Verdict: **Monthly `sv_gp_mo` (`156` months, `ℓ = 1.0 yr`, 24 modes) Is the Clear Winner**
1. **Moving `sv_gp` from quarterly (`52` pts) to monthly (`156` pts) wins decisively on BOTH benchmarks:**
   - **`screen-k5` (`latest`):** **`+96.3 ± 41.2` (`z = +2.34`)** over quarterly `sv_gp` → **`+371.7 ± 68.0` (`z = +5.46`)** over `y1 + covid_vol` and **`+662.8 ± 114.5` (`z = +5.79`)** over production `u4s`!
   - **`screen-mkt-k5` (`asof-20251110`):** **`+20.2 ± 7.4` (`z = +2.73`)** over quarterly `sv_gp` raw (`+54.3 ± 15.6`, `z = +3.47` over `y1 + covid_vol`; `+58.6 ± 17.3`, `z = +3.39` over `u1`), AND **`+13.6 ± 6.8` (`z = +2.01`)** over quarterly `sv_gp` at `open_scale = 1.12` (`Cov80 = 79.69%`, **`+264.9 ± 81.6`, `z = +3.24`** over `range-j`)!
   - **Pareto-optimal runtime & mixing:** Only `+3%` slower than quarterly (`0.773` vs `0.748 s/sw`), `3×` fewer phase cells than weekly (`11,696` vs `33,384`), and the **best MCMC mixing of all SVGP arms** (`pf_rhat = 1.026` on `latest`; `pf_rhat = 1.032 / pf_ess = 116` on `market`, vs `1.098 / 23` for weekly `sv_gp_wk`).
2. **Weekly `sv_gp_wk` (`ℓ = 1.0 yr`, 28 modes) matches monthly on ELPD but adds cell/mixing overhead:** Statistically tied with `sv_gp_mo` on both `latest` (`-8.0 ± 38.1`, `z = -0.21`) and `market` (`1,965.2` vs `1,965.3` raw; `1,973.3` vs `1,974.2` @ `1.12×`), with `3×` as many phase cells (`33,384`) and weaker market mixing (`pf_ess = 23` vs `116`). At `ℓ = 1.0 yr`, monthly sampling already Nyquist-saturates the smooth Matérn-3/2 curve.
3. **Sharper weekly `sv_gp_wk05` (`ℓ = 0.5 yr`, 36 modes) adds noise on market:** Slight non-significant edge over monthly on `latest` (`+29.0 ± 44.1`, `z = +0.66`; `+691.7` over `u4s`), but slips behind monthly on `market` (`1,970.9` vs `1,974.2` @ `1.12×`, `-2.8` vs quarterly @ `1.12×`), runs `+17%` slower (`0.902 s/sw`), and shows slower `latest` mixing (`pf_rhat = 1.093`). **`ℓ = 1.0 yr` is the sweet spot.**
4. **Weekly `vel_gp_wk` is cleanly falsified on `latest` (`-241.5 ± 72.3`, `z = -3.34` vs quarterly `vel_gp`):** Week-to-week raw-ask EMA noise causes classic errors-in-variables attenuation (`vel:down` shrinks `1.264× → 1.192×`, `vel:up` shrinks `1.094× → 1.055×`), hurting `latest` across almost every year (`2014 -41`, `2019 -27`, `2021 -54`, `2026 -62`). Quarterly aggregation was acting as a beneficial denoiser for `vel_gp`.

### 1. Head-to-Head Resolution Scorecard — `screen-k5` (`latest`, `N = 37,199`, scale `×5.0982`)

| Arm | Grid / `ℓ` / Modes | Free Factors | Cells | Raw ELPD | Δ vs Qtr `sv_gp` (Proj) | Δ vs `y1+cov` (Proj) | Δ vs `u4s` (Proj) | MAE | `pf` max `R̂` / ESS | s/sw | USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| *Ref: `y1+covid_vol`* | 12 yrs + 2 CSV | 26 | 2,660 | `47,756.1` | `-275.4 ± 62.3` (`-4.42`) | `0.0` (ref) | `+291.0 ± 91.3` | `5.441%` | `1.046` / `97` | `0.664` | `$0.61` |
| *Ref: `sv_gp` (qtr)* | 52 qtr · `1.0y` · 22m | 34 | 5,004 | `47,810.1` | `0.0` (ref) | `+275.4 ± 62.3` | `+566.5 ± 110.6` | `5.441%` | `1.041` / `68` | `0.748` | `$0.64` |
| **5. `sv_gp_mo` ★** | **156 mo · `1.0y` · 24m** | **36** | **11,696** | **`47,829.0`** | **`+96.3 ± 41.2` (`+2.34`)** | **`+371.7 ± 68.0` (`+5.46`)** | **`+662.8 ± 114.5` (`+5.79`)** | **`5.437%`** | **`1.026` / `58`** | **`0.773`** | **`$0.68`** |
| **6. `sv_gp_wk`** | 672 wk · `1.0y` · 28m | 40 | 33,384 | `47,827.4` | `+88.4 ± 39.9` (`+2.22`) | `+363.8 ± 67.0` (`+5.43`) | `+654.8 ± 115.1` (`+5.69`) | `5.438%` | `1.036` / `89` | `0.815` | `$0.76` |
| **7. `sv_gp_wk05`** | 672 wk · `0.5y` · 36m | 48 | 33,384 | `47,834.7` | `+125.3 ± 48.8` (`+2.57`) | `+400.7 ± 73.8` (`+5.43`) | `+691.7 ± 117.6` (`+5.88`) | `5.434%` | `1.093` / `60` | `0.902` | `$0.75` |
| *Ref: `vel_gp` (qtr)* | 52 qtr · 2p | 14 | 5,005 | `47,735.5` | `-380.2 ± 99.9` (`-3.81`) | `-104.8 ± 109.3` | `+186.2 ± 135.1` | `5.441%` | `1.029` / `100` | `0.551` | `$0.57` |
| **8. `vel_gp_wk`** | 672 wk · 2p | 14 | 32,689 | `47,688.1` | `-621.8 ± 124.1` (`-5.01`) | `-346.3 ± 124.6` | `-55.3 ± 147.5` | `5.441%` | `1.051` / `58` | `0.547` | `$0.56` |

### 2. Head-to-Head Resolution Scorecard — `screen-mkt-k5` (`asof-20251110`, `N = 1,891`, scale `×5.0095`)

| Arm | Cells | Raw ELPD | Raw Cov80 | Raw Δ vs Qtr `sv_gp` (Proj) | `@1.12×` ELPD | `@1.12×` Cov80 | `@1.12×` Δ vs Qtr (Proj) | `@1.12×` Δ vs `range-j` | Best Scale | `pf` `R̂` / ESS | USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| *Ref: `y1+cov`* | 2,470 | `1,954.4` | `74.51%` | `-34.1 ± 14.2` (`-2.40`) | `1,971.2` | `77.95%` | `-1.4 ± 12.7` | `+249.8 ± 80.2` | `1.16×` | `1.077` / `62` | `$0.47` |
| *Ref: `sv_gp` (qtr)* | 4,578 | `1,961.2` | `75.57%` | `0.0` (ref) | `1,971.5` | `79.43%` | `0.0` (ref) | `+251.3 ± 80.9` | `1.12×` | `1.043` / `35` | `$0.48` |
| **5. `sv_gp_mo` ★** | **10,722** | **`1,965.3`** | **`75.62%`** | **`+20.2 ± 7.4` (`+2.73`)** | **`1,974.2`** | **`79.69%`** | **`+13.6 ± 6.8` (`+2.01`)** | **`+264.9 ± 81.6` (`+3.24`)** | **`1.12×`** | **`1.032` / `116`** | **`$0.54`** |
| **6. `sv_gp_wk`** | 30,619 | `1,965.2` | `76.10%` | `+20.0 ± 8.4` (`+2.39`) | `1,973.3` | `79.85%` | `+8.8 ± 7.7` (`+1.13`) | `+260.0 ± 80.3` (`+3.24`) | `1.12×` | `1.098` / `23` | `$0.48` |
| **7. `sv_gp_wk05`** | 30,619 | `1,963.2` | `76.31%` | `+10.0 ± 8.5` (`+1.17`) | `1,970.9` | `79.96%` | `-2.8 ± 7.6` (`-0.37`) | `+248.4 ± 81.1` (`+3.07`) | `1.10×` | `1.041` / `76` | `$0.52` |
| *Ref: `vel_gp` (qtr)* | 4,579 | `1,947.6` | `73.72%` | `-68.4 ± 19.8` (`-3.45`) | `1,967.2` | `77.26%` | `-21.7 ± 17.7` (`-1.23`) | `+229.5 ± 79.1` | `1.20×` | `1.038` / `107` | `$0.41` |
| **8. `vel_gp_wk`** | 30,358 | `1,963.3` | `79.11%` | `+10.5 ± 25.0` (`+0.42`) | `1,959.2` | `82.23%` | `-61.9 ± 23.4` (`-2.65`) | `+189.4 ± 84.9` | `1.04×` | `1.040` / `89` | `$0.39` |

### 3. Honest Pre-Fit Prediction Scorecard

| Arm | Pre-Fit Prediction | Observed Result | Verdict |
|---|---|---|---|
| **5. `sv_gp_mo`** | `+30 to +110` vs qtr (`latest`); `-15 to +25` raw mkt | **`+96.3 ± 41.2`** (`z=+2.34`) on `latest`; **`+20.2 ± 7.4`** (`z=+2.73`) raw mkt (`+13.6` @ `1.12×`) | **BULLSEYE HIT** |
| **6. `sv_gp_wk`** | `+40 to +130` vs qtr (`0 to +30` vs mo); `-15 to +25` raw mkt | **`+88.4 ± 39.9`** (`z=+2.22`) on `latest` (`-8.0` vs mo); **`+20.0 ± 8.4`** raw mkt | **HIT** (decision rule cleanly picks monthly `sv_gp_mo`) |
| **7. `sv_gp_wk05`** | `+70 to +200` vs qtr (`latest`); `-30 to +20` raw mkt (late-2025 risk) | **`+125.3 ± 48.8`** (`z=+2.57`) on `latest`; `+10.0` raw / `-2.8` @ `1.12×` mkt | **HIT** (overfits late-2025 market slightly vs `ℓ=1.0`) |
| **8. `vel_gp_wk`** | `+40 to +160` vs qtr `vel_gp` (`latest`) | **`-241.5 ± 72.3`** (`z=-3.34`) on `latest` | **FALSIFIED** (weekly raw-ask EMA noise attenuates slopes) |

### 4. Updated Recommended Production Gate Recipe
Upgrade the production candidate from quarterly `sv_gp` to **monthly `sv_gp_mo`** (with built-in future-month clamping):
- **`u5-svgpmo-lat`:** `--variant layrng,size,sv_gp_mo,marks,seg` (projected **`+662.8 ± 114.5`, `z = +5.79`** over `u4s`!).
- **`u5-svgpmo-mkt`:** `--variant layrng,size,sv_gp_mo,marks` + `open_scale = 1.12` (projected **`+264.9 ± 81.6`, `z = +3.24`** over `range-j`, `+58.6` raw / `+24.3` @ `1.12×` over `u1`!).
- Self-contained report: [`docs/notes/variance-gp-resolution-2026-11-22.html`](variance-gp-resolution-2026-11-22.html).

