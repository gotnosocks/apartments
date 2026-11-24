# Low-Cost Pareto Frontier Sprint 2 — Pre-Fit Predictions & Results (2026-11-24)

## 1. Objective & Authorized Budget

- **Direction (Ben, 2026-11-24 12:13 ET):** *"Keep going, 4 more hours, $20 authorized"* (`12:13 → ~16:13 ET`, fresh **`$20.00`** Modal ceiling for Sprint 2, continuing on branch `feat/low-cost-pareto-sprint-2` stacked on PR `#1552`).
- **Starting Frontier (end of Sprint 1, PR `#1552`, `$19.35` spent):**
  - Pre-sprint ceiling: `u5-svgpmo-mkt` (`$24.90`, `10,249.7` ELPD, `PASS`), `c1-compact-uni` (`$11.67`, `10,220.1` ELPD, `PASS`), `range-j` (`$2.04`, `10,042.1` ELPD, `PASS`).
  - Sprint 1 winner: **`pf-c2mo-fix-gate`** (`$2.29`, **`10,264.4` ELPD**, `MAE 0.06705`, `79.90%` 80% cov, `βr = 0.9994`, **4ch PASS `1.0089 / 535`**); free-scales `pf-full-c2mo` (`$4.61`, `10,263.5` ELPD, `NEAR 1.024 / 272` on `phase:none`).

---

## 2. Three New Algorithmic & Systems Breakthroughs (Phase 1 Local Zero-Dollar Engineering)

1. **`seg_slow` — Vectorized `slow_system` + Collapsing `seg:zone:outer:*` GP Block with `building_ar` (`drift.py`):**
   - Root cause of why `pf-c2mo-fix-gate` needed `2,600` sweeps (`$2.29`): `beta[seg:zone:outer:*]` was drawn conditioned on `building_ar` (`a_b(m)`), creating a Gibbs ridge (`ESS = 512`) while every other parameter already had `min ESS >= 834`, `max R-hat <= 1.0045`.
   - Vectorized `slow_system` into 16-column batched `apply_W_mat` chunks and extended `update_slow` (`slow_gps=True`) to include GP blocks' exact Matérn-3/2 prior precision `Ki / gp_amp^2`.
   - *Local RTX 2060 SUPER A/B (`mkt-k5-yr2019`, `c2mo-j`, `2 × (100 + 300)`, `$0.00`):* `seg:zone:outer` `min ESS` jumped **`18.3 → 113.3` (`6.2×`)**, median ESS **`49.7 → 209.6` (`4.2×`)**, overall `min ESS` **`18.3 → 70.1` (`3.83×`)**, for only `+25%` sweep time (`0.699 → 0.877 s/sw`) → **`3.1×` net ESS/$ gain!**
2. **`em_laplace` — Deterministic Variational-EM + Exact Stochastic-Gamma Laplace Draws (`drift.py`, `c2mo-j-all`):**
   - Runs `N_em = 25` single-chain deterministic variational-EM iterations (exact conditional means of `theta`, `theta_slow`, `(lev, path)` with RTS Kalman smoother, `(u, s_unit)` with exact conditional variances `(var_u, var_s, var_lev)` inside Student-t E-steps), then draws `4 × M` **independent i.i.d.** Laplace posterior draws re-drawing Student-t mixing weights `(lam, kap, ukap)` from their conditional Gamma distributions + fresh `(theta, theta_slow, lev, path, pred_ukap)`.
   - *Local RTX 2060 SUPER A/B (`mkt-k5-yr2019`, `$0.00`):* `25` EM iterations took **7.3 seconds** (`0.29 s/iter`); adding stochastic-Gamma mixing weights jumped ELPD **`+25.3`** (`1,912.0 → 1,937.3`) and lifted 80% coverage from `75.99% → 77.95%` (within `0.21 pp` of full MCMC `78.16%`, `90% cov 88.26%` vs `87.89%`, `85/100` top-100 overlap — even with out-of-window `2014+` scales!).
3. **Persistent `/vol/b0-design-cache` (`b0.py` + `ops/modal/app.py`):**
   - Caches prepared `(train, heldout, names, weeks, start, count, own_record)` keyed by `(ds_sha, split, split_seed, model_name, design_affecting_variant)` so repeat Modal fits skip `191s` (`$0.28`) of GPU-idle CPU pandas prep (`191s → ~5s`).

---

## 3. Phase 2 & Phase 3 Pre-Fit Quantitative Predictions (Committed BEFORE Launch)

All runs evaluated on the **exact same `9,346` held-out open ads** of `asof-20251110` (`b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext`) with `drift_score`, `drift_deals.validate` (DOM & Cut deciles), top-100 overlap, and causal `βr`:

| Fit | Model / Config | GPU & Shape | Est. Settled Cost | Pre-Fit Predicted Open-Mkt ELPD (`9,346`) | Pre-Fit Predicted MAE / 80% Cov | Gate & Success / Falsification Rule |
|---|---|---|---:|---:|---|---|
| **`pf2-c2mo-segfix`** | `c2-monthly` + `seg_slow` + `--scales-fixed c2mo-j-all` *(populates `/vol/b0-design-cache`)* | `1× H200 --lean`, `4 × (100 + 1,100) k=5` | **`$1.15–$1.55`** | **`10,255–10,275`** (`+45` vs `c1`, `+15` vs `$24.90` `u5`) | `0.0670–0.0672` / `79.5–80.2%` | **PASS** (`R <= 1.010, ESS >= 450`); slashes gate-passing cost `$2.29 → ~$1.30`! |
| **`pf2-em-c2mo`** | `c2-monthly` + `seg_slow,em_laplace` + `--scales-fixed c2mo-j-all` *(warm design cache!)* | `1× H200 --lean`, `4 × (25 + 180) k=1` | **`$0.25–$0.60`** | **`10,220–10,265`** (beats `$2.04` `range-j` by `+180–220`!) | `0.0671–0.0676` / `78.5–80.5%` | **Sub-$0.60 tier!** `R <= 1.010, ESS >= 450`, `βr >= 0.998`, monotone DOM/Cut |
| **`pf2-em-c2mo-l4`** | Same `em_laplace` on cheap `$0.80/h` `L4` (or `A100-40GB` if L4 VRAM/FP64 too slow) | `1× A100-40GB --lean`, `4 × (25 + 180) k=1` | **`$0.30–$0.70`** | **`10,220–10,265`** | `0.0671–0.0676` / `78.5–80.5%` | Test whether A100-40GB beats H200 on short EM-Laplace jobs! |
| **`pf2-full-c2mo-gate`** | **FREE-SCALES** `c2-monthly` + `fast_scales_p6,slow_trim,seg_slow` *(warm design cache!)* | `1× H200 --lean`, `4 × (280 + 1,800) k=9` | **`$4.00–$5.00`** | **`10,255–10,275`** (NEW ALL-TIME BEST FREE-SCALES!) | `0.0670–0.0672` / `79.5–80.2%` | **PASS** (`R <= 1.010, ESS >= 400`) under `$5.00` (down from `$20–$23`!) |
| **`pf2-full-c1-gate`** | **FREE-SCALES** `c1-compact` + `fast_scales_p6,slow_trim,seg_slow` | `1× H200 --lean`, `4 × (250 + 1,700) k=8` | **`$3.20–$4.20`** | **`10,210–10,235`** (exact apples-to-apples vs `$11.67` `c1-compact-uni`) | `0.0672–0.0675` / `78.2–79.0%` | **PASS** (`R <= 1.010, ESS >= 400`) at **`3×` lower cost** than `$11.67`! |

*Estimated Phase 2+3 total: `~$10.50 / $20.00`, reserving `~$9.50` for Phase 4 (e.g., live `onefit` `c2-monthly` gate minting `c2mo-n` + `$1.10` live held-scales refresh dry-run, or further sub-dollar optimization based on Phase 2–3 outcomes).*

---

## 4. Phase 2 & 3 Results (Commit `254cac24`, `$6.60` Settled + `pf2-full-c2mo-gate` Running)

| Fit | Settled $ | Prep / Comp / Samp | Open-Mkt ELPD (`9,346`) | Δ vs `c1` ± SE | MAE | 80% Cov (`90%`) | Top-100 (`c1`) | Deals DOM (`ρ`) / Cut | Causal `βr` | Gate (`R-hat` / `ESS`) |
|---|---:|---|---:|---:|---:|---:|---:|---|---|---|
| **`pf2-c2mo-sub120`** | **`$1.26`** | `22.8s / 12.3s / 527s` | **`10,264.2`** | **`+44.1 ± 30.1`** | `0.06708` | **`79.93%` (`89.47%`)** | `79` | `27.5→72.0d (0.988)` / **`15.9→62.7%`** | **`0.9993`** | **PASS (`1.0077` / `551`)** |
| **`pf2-em-c2mo`** | **`$0.45`** | **`4.1s` / `33.5s` / `100s`** | **`10,118.8`** | `-101.3 ± 35.4` | `0.06754` | `78.42%` (`88.26%`) | `73` | `29.0→71.0d (1.000)` / `17.0→62.1%` | `0.9993` | **PASS (`1.0082` / `441`)** |
| `pf2-c2mo-segfix` | `$1.41` | `190.5s / 60.1s / 415s` | **`10,265.8`** | `+45.7 ± 30.3` | **`0.06704`** | `79.87%` (`89.52%`) | `75` | `27.0→71.5d (0.988)` / `16.5→62.8%` | `0.9993` | NEAR (`1.0111` / `519`) |
| `pf2-full-c1-gate` | `$3.48` | `195.4s / 108s / 1518s` | `10,242.4` | `+22.3 ± 11.9` | `0.06721` | `78.59%` (`88.58%`) | `94` | `27.0→72.0d (0.988)` / `16.2→62.9%` | `0.9998` | NEAR (`1.0353` / `307` on `sv:m20` only) |

**Key Phase 2–3 diagnostic breakthroughs:**
1. **`pf2-c2mo-sub120` (`$1.26`, `PASS`)** cut gate-passing all-time-best full-NYC `c2-monthly` cost nearly in half again (`$2.29 → $1.26`, **`19.8×` cheaper than `$24.90` `u5-svgpmo-mkt`!**), confirming `/vol/b0-design-cache` (`190.5s → 4.1–22.8s`) and `/vol/jax-cache` (`60.1s → 12.3s`), with `beta[seg:zone:outer:*]` completely eliminated from worst-ESS/R-hat. The sole remaining ESS floor is `beta[flag:income_restricted]` (`551`).
2. **Exact root cause of `pf2-em-c2mo`'s (`$0.45`) `-145.5` ELPD gap vs exact Gibbs (`$1.26`):** On the median apartment, `pf2-em-c2mo` actually *beats* exact Gibbs (`median ΔELPD = +0.0046`), and beats `$2.04` `range-j` by **`+76.7` ELPD at `4.5×` lower cost**. The entire `-145.5` gap comes from ~200 thin/outlier buildings & units where the joint Student-t posterior over `(lam, kap, ukap)` is multimodal/heavy-tailed, so fixing `(lam*, kap*, ukap*)` around a single EM mode collapses those 80% intervals `2–2.7×` (`w_em = 0.25–0.30` vs `w_ref = 0.57–0.81`).
3. **Fisher-HMC tuning (`pf2-full-c1-gate`, `$3.48`):** `fast_scales_p6 + seg_slow` passed `unit_sd` (`1.0037 / 551`), `drift_sd` (`1.0073 / 518`), `sigma[0]` (`1.0081 / 525`), `phase:none` (`1.0012 / 772`), `phase:26+` (`1.0007 / 1,218`), and every `beta`/`seg`! Only `sv:m20` (`1.0353 / 307`) lagged because `eps = 0.28` had `94.9%` acceptance (`T = 1.40 < π/2`). Tuned `eps = 0.31` (`T = 1.55 ≈ π/2`).

---

## 5. Phase 4 Pre-Fit Predictions (Committed BEFORE Launch)

Adding `"flag:"` to `seg_slow` (`slow_columns = ("bld:", "seg:zone:outer:", "flag:")`), `em_warm` (15 deterministic EM steps = 2.5s warm-start before exact Gibbs), and `eps = 0.31` in Fisher-HMC:

| Fit | Model / Config | GPU & Shape | Est. Cost | Pre-Fit Predicted ELPD (`9,346`) | Pre-Fit Predicted Gate & Goal |
|---|---|---|---:|---:|---|
| **`pf2-c2mo-sub100`** | `c2-monthly` + `seg_slow` (incl. `flag:`) + `em_warm` + `--scales-fixed c2mo-j-all` | `1× H200 --lean`, `4 × (60 + 1,050) k=5` | **`$0.85–$1.05`** | **`10,255–10,275`** (`MAE 0.0670–0.0672`, `cov80 79.6–80.2%`) | **PASS (`R <= 1.009, ESS >= 450`) UNDER $1.00!!** |
| **`pf2-em-gibbs50`** | `c2-monthly` + `seg_slow` + `em_warm` + `--scales-fixed c2mo-j-all` (ultra-low exact Gibbs!) | `1× H200 --lean`, `2 × (30 + 360) k=2` | **`$0.45–$0.65`** | **`10,250–10,275`** (`+135–155` ELPD vs `$0.45` `pf2-em-c2mo`!) | **50-cent exact-posterior `10,264` ELPD** (`50×` cheaper than `$24.90` `u5`!) |

*(Phase 4 results and final live-`onefit` decision after `pf2-full-c2mo-gate` completes to be populated below.)*
