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
