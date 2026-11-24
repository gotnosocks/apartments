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

## 4. Results

*(To be populated as Phase 2–4 complete.)*
