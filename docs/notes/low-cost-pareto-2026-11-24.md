# Low-Cost Pareto Frontier Sprint — Pre-Fit Predictions & Results (2026-11-24)

## 1. Objective & Authorized Budget

- **Direction (Ben, 2026-11-24 07:38 ET):** Expand the **low-cost side of the cost-performance Pareto frontier** over the next 4 hours so we can avoid `$12–$20` fits altogether — optimizing jointly across **Modal cost ($)**, **predictive accuracy (open-market ELPD, MAE, 80% coverage)**, **causal interpretability of feature effects**, and **usefulness for finding deals (backtest DOM/Cut monotonicity & top-100 overlap)**.
- **Authorized Modal spend ceiling:** **`$20.00`** (overriding previous caps).

---

## 2. Four Orthogonal Levers Tested

1. **Exact Algorithmic Speedups (`fast_scales` + Fisher-preconditioned HMC + `slow_trim` + `CELL_PADS`) — ZERO approximation to target posterior:**
   - Pulls the 36 `phase_scale` factors out of `update_scales` (cutting `update_scales` from `K=40` collapsed 68k-building Cholesky slice loops to `K=4`: `unit_sd`, `drift_sd`, `drift_tau`, `sigma`, and cutting warmup Hessian `scales_curvature` from `1,641 → 21` evals) and updates `(sigma, phase_scale)` jointly inside `update_noise` via **exact 5-step Fisher-preconditioned HMC** (`5` row passes instead of `~290`, exact Fisher information `I = (2ν/(ν+3)) M^T diag(N) M + P_0`).
   - Trims `update_slow` via `slow_within=0.001` (`41 → 18` columns, dropping 23 constant-within-building columns).
   - Adds intermediate `CELL_PADS = (..., 44, 60, 80, 108, 144)` in `drift.py` to stop `bld_monthly` from padding 45-month buildings to ~156.
   - *Local RTX 2060 SUPER zero-dollar benchmark (`n=42,565` train rows):* **`0.834 → 0.326 s/sweep` (`2.56×` faster)** with `sigma[0]` R-hat `1.0075`, `phase_factor[0]` R-hat `1.0038`, `phase_factor[12]` R-hat `1.0097`.
2. **Cheaper GPUs wired into `LEAN_FITS` (`A100-40GB --lean` at `$2.86/h` and `A100-80GB --lean` at `$3.26/h` vs `H200 --lean` at `$5.30/h`).**
3. **Temporal Windowing (`ops/modal-screen window`, keeping 100% of held-out open ads identical!):**
   - Training on `yr >= 2019` (`64%` rows), `yr >= 2020` (`55%`), `yr >= 2021` (`43%`), `yr >= 2022` (`32%`), `yr >= 2023` (`24%`), and `yr >= 2022 + tail_anchor` (`60%` rows, retaining 100% of unit baselines).
   - On a 5-year window (`2022–2026`), `bld_monthly` (`12/yr`) has only ~60 steps/building (same as quarterly on 13 years!) and drops the 2014–2019 segment-GP mixing bottleneck and 2020–2021 Covid shock.
4. **Low-Cost Model Structure (`ultralite`):** Zero GPs (`seg_add_lr12`), `spatial_k40`, no `sv_gp_mo` on post-2022 flat-volatility window, paired with `bld_monthly` + `attr_changes`.

---

## 3. Phase 1 & Phase 2 Pre-Fit Quantitative Predictions (Committed BEFORE Launch)

### Phase 1 — Full-NYC (1.76M-row `asof-20251110`) 40-Sweep Hardware + Algorithm Probes (`~$2.00`)
All 4 probes run `2 chains × (20 warmup + 20 draws, keep=1)`, `--large --lean`, `--split market`, on `b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext`:

| Probe | GPU (`--lean`, $/hr) | Variant | Pre-Fit Predicted `s/sweep` | Projected Full 4ch Fit Cost (`2×(300+2600)`) | Falsification / Decision Rule |
|---|---|---|---|---|---|
| `p1-h200-fast` | `H200` (`$5.30/h`) | `C1 + fast_scales,slow_trim` | **`0.45–0.75 s/sw`** (`2.2–3.5×` faster than `mem-probe` `1.61 s/sw`) | **`$5.50–$7.50`** (down from `$12.37`!) | Fail if `s/sw > 1.0` (means `update_scales` wasn't dominant at 1.76M rows) |
| `p1-a100-40-fast` | `A100-40GB` (`$2.86/h`) | `C1 + fast_scales,slow_trim` | **`0.70–1.20 s/sw`** (fits in 40 GB VRAM!) | **`$4.20–$6.00`** (beats H200 if `< 1.85×` H200) | Switch full fits to `A100-40GB --lean` if fits & `$/sweep < H200` |
| `p1-a100-80-fast` | `A100-80GB` (`$3.26/h`) | `C1 + fast_scales,slow_trim` | **`0.65–1.10 s/sw`** (guaranteed VRAM fit) | **`$4.50–$6.50`** | Use as backup if `A100-40GB` OOMs |
| `p1-a100-40-c2mo` | `A100-40GB` (`$2.86/h`) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | **`1.10–1.80 s/sw`** (with new `CELL_PADS`) | **`$6.50–$9.50`** (down from `$20–$23`!) | Switch `c2-monthly` to `A100-40GB` if fits & `< $10` projected |

### Phase 2 — Temporal Windowing & Ultralite Screen on `screen-mkt-k5` (`asof-20251110`, `n=1,891` open ads, `~$2.80`)
All 10 arms run on `A100-40GB`, `2 250 400 10`, `--seed 1`, evaluated on the **exact same `1,891` open ads** vs `b4-m-anchor` (`ELPD = 1,971.0`, `MAE = 0.07135`, `cov80 = 75.20%`, `$0.57`):

| Arm | Label | Window | Variant | Pre-Fit Predicted Raw ΔELPD (vs `b4-m-anchor`) | Pre-Fit Predicted Speedup & Wall Cost |
|---|---|---|---|---|---|
| 1 | `lc-fast-c1` | `2014+` (`100%`) | `C1 + fast_scales,slow_trim` | **`±3`** (exact same posterior!) | **`2.0–2.8×` faster**, `~$0.30` (vs `$0.57`) |
| 2 | `lc-yr2019` | `2019+` (`64%`) | `C1 + fast_scales,slow_trim` | **`-5` to `+10`** (tiny 6% unit loss, cleaner modern betas) | `~35%` faster than `lc-fast-c1`, `~$0.24` |
| 3 | `lc-yr2020` | `2020+` (`55%`) | `C1 + fast_scales,slow_trim` | **`-12` to `+8`** | `~$0.21` |
| 4 | `lc-yr2021` | `2021+` (`43%`) | `C1 + fast_scales,slow_trim` | **`-25` to `+5`** (`17%` open units lose prior) | `~$0.18` |
| 5 | `lc-yr2022` | `2022+` (`32%`) | `C1 + fast_scales,slow_trim` | **`-45` to `-10`** (`27%` open units lose prior) | `~$0.15` |
| 6 | `lc-yr2023` | `2023+` (`24%`) | `C1 + fast_scales,slow_trim` | **`-80` to `-30`** (`37%` open units lose prior) | `~$0.13` |
| 7 | `lc-yr2022-tail` | `2022+` + tail anchor (`60%`) | `C1 + fast_scales,slow_trim` | **`-15` to `+10`** (recovers 100% of unit priors!) | `~$0.22` |
| 8 | `lc-yr2021-c2mo` | `2021+` (`43%`) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | **`-10` to `+25`** (`cov80` jumps `+2–3 pp` to `~78%`!) | `~$0.22` |
| 9 | `lc-yr2022-c2mo` | `2022+` (`32%`) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | **`-25` to `+15`** (`cov80 ~78%`, 60-step monthly!) | `~$0.18` |
| 10 | `lc-yr2022-lite` | `2022+` (`32%`) | `layrng,size,marks,seg_add_lr12,floor_poly,ad_core,scalar_sigma,biweekly_walk,spatial_k40,attr_changes,bld_monthly,fast_scales,slow_trim` | **`-35` to `+5`** (zero GP, no `sv_gp_mo`, fastest!) | `~$0.14` (ultra-low frontier anchor!) |

---

## 4. Phase 1 & Phase 2 Results

*(To be populated after Phase 1 & Phase 2 complete.)*

---

## 5. Phase 3 Full-NYC Low-Cost Pareto Frontier Fits (Pre-Fit Predictions & Results)

*(To be written and committed BEFORE launching Phase 3.)*
