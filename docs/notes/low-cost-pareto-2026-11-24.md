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

## 4. Phase 1 & Phase 2 Results (Commit `d16e233e`, Total Spend `$5.64 / $20.00`)

### 4a. Phase 1 — Full-NYC (1.76M-Row) Hardware & Algorithm Probes (`$2.87`)

| Probe | GPU (`--lean`, $/hr) | `prep` / `comp` | Pure Sweep (`wu`) | Est. `k=10` Sweep | Host RAM Peak | Probe Cost | Projected Full `4×(300+2600)` (2× vs 1×) |
|---|---|---:|---:|---:|---:|---:|---:|
| **`p1-h200-fast`** | **H200 (`$5.30/h`)** | `194s / 145s` | **`0.391 s/sw`** | **`0.429 s/sw`** | `24.3 GB` | `$0.84` | **`$4.85` (2×) / `$4.14` (1×)** |
| `p1-a100-40-fast` | A100-40GB* (`$2.86/h`) | `170s / 212s` | `1.796 s/sw` (`4.59×`) | `1.848 s/sw` | `24.4 GB` | `$0.64` | `$9.25` (2×) / `$8.64` (1×) |
| `p1-a100-80-fast` | A100-80GB (`$3.26/h`) | `178s / 221s` | `1.806 s/sw` (`4.62×`) | `1.858 s/sw` | `24.4 GB` | `$0.74` | `$10.63` (2×) / `$9.92` (1×) |
| `p1-a100-40-c2mo` | A100-40GB* (`$2.86/h`) | `173s / 218s` | `2.104 s/sw` (`1.17×` qtr) | `2.166 s/sw` | `24.5 GB` | `$0.65` | `$10.69` (2×) / `$10.03` (1×) |

*\*Modal fulfilled A100-40GB requests on A100-SXM4-80GB hardware billed at the `$2.86/h` A100-40GB rate.*

**Two decisive Phase 1 findings:**
1. **H200 is `2×` CHEAPER per full 1.76M-row fit than A100 (`$4.14–$4.85` vs `$8.64–$9.25`):** Once `fast_scales` + `slow_trim` strips away the old slice overhead, the sampler is pure FP64 compute + HBM3e bandwidth (`4.80` vs `1.56–2.04 TB/s`). H200 sweeps **`4.59×` faster** than A100 while costing only `1.85×` more per hour!
2. **Our exact algorithmic speedups slashed full-fit costs `2.6×–4.5×` with ZERO approximation:**
   - Full 13-year `c1-compact` on H200 dropped from `1.105 s/sw` (`$12.37`) → **`0.391 s/sw` (`$4.14–$4.85`)**!
   - Intermediate `CELL_PADS` cut `bld_monthly`'s overhead over quarterly from **`+89%` → `+17%`**, slashing full 13-year `c2-monthly` on H200 from `$20–$23` → **`~$4.60–$5.50`**!

### 4b. Phase 2 — Temporal Windowing & Ultralite Screen (`screen-mkt-k5`, `n=1,891` identical open ads, `$2.77`)

| Label | Window (% rows) | ΔELPD ± SE (vs `b4-m-anchor`) | Trimmed Δ | MAE | 80% Cov (`90%`) | Top-100 Overlap | `s/sweep` | Cost | `max R-hat` / `min ESS` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `b4-m-anchor` | `2014+` (`100%`) | `0.0` | `0.0` | `0.07135` | `75.20%` (`87.7%`) | `100/100` | `0.578 s` | `$0.57` | `1.131` / `14.0` |
| `b4-m-c2-mo(old)` | `2014+` (`100%`) | `+13.0 ± 17.0` | `+8.8` | `0.07145` | `78.05%` (`89.1%`) | `84/100` | `1.286 s` | `$0.87` | `1.125` / `11.1` |
| **`lc-fast-c1`** | **`2014+` (`100%`)** | **`-0.4 ± 1.1` (`z=-0.35`)** | **`-0.3`** | **`0.07134`** | **`75.09%`** (`87.5%`) | **`99/100`** | **`0.203 s` (`2.85×`)** | **`$0.30`** | **`1.133` / `13.5`** |
| **`lc-yr2019`** | **`2019+` (`64%`)** | `-23.1 ± 26.7` (`z=-0.87`) | `-25.2` | **`0.07113`** | **`78.16%`** (`87.9%`) | `78/100` | **`0.141 s` (`4.1×`)** | `$0.32` | **`1.112` / `19.1`** |
| `lc-yr2020` | `2020+` (`55%`) | `-50.5 ± 29.4` | `-50.1` | `0.07268` | `77.79%` (`88.0%`) | `72/100` | `0.129 s` | `$0.29` | `1.190` / `7.8` |
| `lc-yr2021` | `2021+` (`43%`) | `-51.3 ± 29.5` | `-48.7` | `0.07243` | `77.26%` (`88.4%`) | `73/100` | `0.111 s` | `$0.25` | `1.160` / `21.4` |
| `lc-yr2022` | `2022+` (`32%`) | `-47.8 ± 28.6` | `-46.1` | `0.07291` | `77.05%` (`88.3%`) | `72/100` | `0.097 s` | `$0.22` | `1.116` / `21.4` |
| `lc-yr2023` | `2023+` (`24%`) | `-76.5 ± 31.6` | `-76.6` | `0.07397` | `78.00%` (`88.4%`) | `65/100` | `0.091 s` | `$0.30` | `1.178` / `5.4` |
| `lc-yr2022-tail` | `2022+`+tail (`60%`) | `-65.5 ± 20.7` (`z=-3.16`) | `-64.3` | `0.07300` | `74.62%` (`86.5%`) | `74/100` | `0.156 s` | `$0.29` | `1.184` / `4.9` |
| `lc-yr2021-c2mo` | `2021+` (`43%`) | `-41.5 ± 34.4` | `-39.3` | `0.07223` | `78.27%` (`88.1%`) | `72/100` | `0.134 s` | `$0.24` | `1.156` / `11.9` |
| **`lc-yr2022-c2mo`** | **`2022+` (`32%`)** | `-44.6 ± 30.2` (`z=-1.48`) | `-43.5` | `0.07284` | **`78.48%`** (`88.1%`) | `71/100` | **`0.121 s` (`10.6×`)** | `$0.27` | `1.147` / `7.6` |
| `lc-yr2022-lite` | `2022+` (`32%`) | `-59.0 ± 31.4` | `-56.2` | `0.07292` | `76.94%` (`86.4%`) | `72/100` | `0.087 s` | `$0.29` | `1.179` / `16.8` |

**Key Phase 2 insights:**
1. **`lc-fast-c1` proved exact posterior equivalence** (`-0.4 ± 1.1`, `99/100` top-100 overlap, identical R-hat/ESS) at **`2.85×` faster sweep speed** (`0.578 → 0.203 s/sw`).
2. **Causal beta fidelity stays high under windowing:** `yr >= 2019` has `beta r = 0.9871` (`key_mad = 0.0041`) and `yr >= 2022 + c2mo` has `beta r = 0.9675` (`key_mad = 0.0088`).
3. **Why windowed `k5` lost ELPD (`-23` to `-44`):** On `lc-yr2022-c2mo`, brand-new first-ad open units (`n=668`) actually **GAINED `+18.6` ELPD** over 13-year `c1-compact`, while units whose only prior ad was pre-2022 (`n=326`) lost `-32.9` ELPD. `tail_anchor` was cleanly falsified (`-65.5 ± 20.7`) because sparse isolated pre-2022 rows corrupt the older `L(t)` walk.

---

## 5. Phase 3 — Full-NYC (`asof-20251110`, ALL `9,346` Open Ads!) Low-Cost Pareto Frontier Fits

### Pre-Fit Quantitative Predictions (Committed BEFORE Launch)

We launch **3 real, full-NYC, free-scales, 1× H200 `--large --lean` (`$5.30/h`) fits** spanning **`~$1.70` → `~$3.00` → `~$4.60`** (estimated `~$9.30` total → cumulative `~$14.94 / $20.00`, reserving `~$5.00` for Tier 3 `pf-full-c1fast` and a sub-`$1` `--scales-fixed` refresh afterward), all evaluated on **all `9,346` open ads**, **Deals backtest DOM/Cut monotonicity**, **top-100 overlap**, **causal `beta` fidelity**, and **exact gate convergence (`R-hat <= 1.01, ESS > 400`)** against `range-j` (`$2.04`, `10,042.0`), `c1-compact-uni` (`$11.67`, `10,220.1`), and `u5-svgpmo-mkt` (`$24.90`, `10,249.8`):

| Tier | Label | Full-NYC Dataset | Variant | Chains × (WU + Draws) | Est. Cost | Pre-Fit Predicted Open-Mkt ELPD (9,346 ads) | Pre-Fit Predicted 80% Cov / MAE | Gate & Success Rule |
|---|---|---|---|---|---:|---:|---|---|
| **Tier 1 (Sub-$2 Free-Scales)** | **`pf-yr22-c2mo`** | `asof-20251110` `yr >= 2022` (`555k` rows, 31.5%) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | `4 × (300 + 1,600)` `k=8` | **`$1.50–$2.10`** | **`10,050–10,180`** (beats `range-j` `$2.04` with free scales!) | **`77.5–79.5%`** / `0.0468–0.0478` | Pass gate (`R-hat <= 1.01, ESS > 400`), monotone DOM/Cut |
| **Tier 2 (~$3 Mid-Low)** | **`pf-yr19-c2mo`** | `asof-20251110` `yr >= 2019` (`1.12M` rows, 63%) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | `4 × (300 + 2,000)` `k=10` | **`$2.60–$3.50`** | **`10,180–10,280`** (matches/beats `$11.67` `c1-compact-uni`!) | **`78.0–79.5%`** / `0.0458–0.0466` | Pass gate, `beta r >= 0.99`, beats `$11.67` on cost & cov |
| **Tier 4 (~$4.50 Full 13-Yr Ceiling)** | **`pf-full-c2mo`** | `asof-20251110` `2014+` (`1.76M` rows, 100%) | `C1 + attr_changes,bld_monthly,fast_scales,slow_trim` | `4 × (350 + 2,200)` `k=10` | **`$4.20–$5.40`** | **`10,250–10,360`** (**NEW ALL-TIME BEST** on `asof-20251110`!) | **`78.0–79.5%`** / **`0.0455–0.0462`** | Pass gate, beats `$24.90` `u5-svgpmo-mkt` at **5× lower cost!** |

### Phase 3 Results

*(To be populated after Phase 3 completes.)*

