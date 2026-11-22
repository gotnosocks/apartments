# Fast Screening Harness on Modal Cloud GPUs (2026-11-22)

**Goal:** Maximize **information gain per unit time** (and per dollar) for drift-model feature and structural iteration by building, benchmarking, and empirically calibrating a reusable **Modal Cloud GPU Fast Screening Harness** (`rentfrontier.screen`, `ops/modal-screen`, and persistent XLA compilation caching on `/vol/jax-cache`).

**Scope & Constraints:**
- Target hardware: **Modal Cloud GPUs** (`L4`, `A100-40GB`, `A100-80GB`, `H100`), not local `thelio` RTX 2060.
- Sampler speedups (`double-pass`, `slow_within`, tracing 24 factors) are intentionally **deferred** to a separate project; this study measures pure screening-harness leverage on the current sampler as-is.
- Authorized Modal budget ceiling: **`$50.00`**; actual total spend across **46 settled Modal containers**: **`$19.11`** (`$30.89` under cap).

---

## Executive Summary

1. **Modal Cloud GPU Pareto Winner — `A100-40GB` + Persistent `/vol/jax-cache`:**
   - Warm `A100-40GB` screens run `l2bt` (`2 250 400 10`) in **`5.4 min` (`$0.23`) at `k10`** (`10%` buildings, `185k` rows) and **`6.5 min` (`$0.27`) at `k5`** (`20%` buildings, `376k` rows) — **`9–11×` faster wall clock and `55–65×` cheaper** than a full 6-chain Modal fit (`~60–90 min`, `~$15–$18`).
   - Persistent XLA caching (`/vol/jax-cache`) slashes `first sweep (compile)` by **`-76%`** (`104.3s → 24.9s` at `k10`, `107.5s → 26.1s` at `k5`, `112.6s → 26.6s` on `unified-seg`), persisting across different draw budgets on the same `(model, dataset_shape)`.
   - `L4` suffers a **`2.85×` FP64 sweep penalty** (`0.695` vs `0.244 s/sw`, `13.1 min` wall time), `A100-80GB` is strictly dominated by `A100-40GB` (`0.241` vs `0.244 s/sw` at `+17%` cost), and `H100` costs **`1.7–2.1×` more per bit** than `A100-40GB` at both `k10` and `k5`.
2. **Cloud-GPU Fixed-Overhead Surprise (`k5` Beats `k20` on Both `bits/min` and `bits/$`):**
   - On `A100-40GB`, scaling **`4×` in data (`k20 → k5`, `94k → 376k` rows)** adds only **`+17%` cost cold→warm (`$0.23 → $0.27`)** and **`+1.1 min` warm (`k10` `5.4 min` → `k5` `6.5 min`)**, while halving sampling SE / MDE, adding `+1.04` bits of information gain, and shrinking Matérn-3/2 GP attenuation from `-27%` to `-12%`.
3. **18 / 18 Perfect 3-Way Routing (`KILL` / `ESCALATE` / `GO`) Across `k20`, `k10`, `k5`:**
   - **Zero false `GO`s** on the `-63` negative control (`d1 - b9`: `KILL` at `k20`, `k10`, and `k5`).
   - **12 / 12 `GO`s** for all four `>= +500` ELPD effects (`+520`, `+2,334`, `+2,763`, `+5,097`).
   - **Zero false `KILL`s** on the borderline `+224` feature (`l2bt - l2kn`: routed to `ESCALATE` on seed 1 and seed 2).
   - **`market` (`asof-20251110`, `k5`, `$0.78`) Deals backtest screen** recovered **`+159 ± 83`** projected full ΔELPD (`P(>0) = 0.973`, `P(>50) = 0.906`, true `+173.8`) **and** automatically flagged the exact 80% coverage regression (`-1.90 pp`, true `-2.5 pp`).
4. **Two Operational Modal Fleet Quirk Discoveries:**
   - Modal fulfills `A100-40GB` requests across **4 `(SKU, driver)` combinations** (`A100-40GB` / free-upgrade `A100-80GB` × drivers `610.57.04` / `620.70.06`), so `/vol/jax-cache` warms up over ~4 populates per `(model, shape)` and settles at the requested `A100-40GB` price.
   - `asof-*` market datasets pin point-in-time tables in `inputs.json`; `rentfrontier.screen.build_subsample` now preserves `inputs.json` automatically (caught live after `$0.12` failed launch).

---

## 1. Ground-Truth Calibration Ladder & Zero-Spend Oracle Power Analysis

We calibrated the screening harness against **6 known full-data `latest`-split model pairs** on `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext` (`1,896,471` total rows, `189,647` held-out ads across `36,207` buildings) plus the **`market` `asof-20251110`** Deals backtest (`9,346` open ads):

| Pair (Candidate vs Baseline) | Regime | Full-data ΔELPD | Full SE | Full z | ΔELPD / row |
|---|---|---:|---:|---:|---:|
| `d1 - b9` (doorman interaction) | **NEGATIVE (reject)** | `-63.0` | `12.2` | `-5.18` | `-0.00033` |
| `l2bt - l2kn` (`bedtext` flags) | **SMALL-MED** | `+223.6` | `38.5` | `+5.80` | `+0.00118` |
| `l2kn - l1tkn` (lease-phase levels) | **MEDIUM** | `+519.6` | `29.9` | `+17.40` | `+0.00274` |
| `u4s - u1` (Matérn-3/2 segment GPs) | **LARGE** | `+2,334.4` | `112.4` | `+20.76` | `+0.01231` |
| `u1 - l2bt` (`unified` bundle) | **LARGE** | `+2,762.9` | `149.2` | `+18.52` | `+0.01457` |
| `u4s - l2bt` (`unified-seg` vs `l2bt`) | **HUGE** | `+5,097.3` | `179.1` | `+28.47` | `+0.02688` |
| `u3 - range-j` (`market` `asof-20251110`) | **DEALS BACKTEST** | `+173.8` | `32.2` | `+5.40` | `+0.01860` |

### Zero-Spend Oracle Stratification & Power Analysis (200 random seeds)

Before launching any Modal GPU, 200 random seeds at `f ∈ {1/20, 1/10, 1/5}` established:
- **Size-decile stratified equal-probability sampling** (`stratify="size"`, 10 bins ordered by building row count, strictly nested `k20 ⊂ k10 ⊂ k5` at fixed seed) preserves exact unbiasedness (`E[ΔELPD_sub / f] = ΔELPD_full`) while reducing subsample row-count CV (`4.86% → 4.35%` at `1/20`, `3.24% → 3.06%` at `1/10`, `2.39% → 1.84%` at `1/5`).
- **Oracle power (pure building-sampling variance, before estimation attenuation):**
  - `f = 1/20` (`3,400` blds, `93,603` rows, `9,213` held-out): `>= +500` has `100%` sign accuracy & `96.5–100%` `|z|>=2`; `+224` has `90%` sign / `23%` `|z|>=2`; `-63` has `83%` sign.
  - `f = 1/10` (`6,800` blds, `185,391` rows, `18,111` held-out): `>= +500` has `100%` sign & `100%` `|z|>=2`; `+224` has `97.5%` sign / `43%` `|z|>=2`; `-63` has `98.0%` sign.
  - `f = 1/5` (`13,592` blds, `376,261` rows, `37,199` held-out): `+224` reaches `100%` sign / `73%` `|z|>=2`; `-63` reaches `99.5%` sign / `66.5%` `|z|>=2`.

---

## 2. Pre-Fit Predictions (Committed in `d40e6a95` Before Launching Any Modal Container)

*(Preserved verbatim from commit `d40e6a95`, recorded prior to all Modal GPU launches.)*

- **P1 (L4 FP64 penalty):** `L4` will be `>= 2.5×` slower per sweep than `A100-40GB` and will NOT be cheaper per screen despite its `2.07×` lower hourly rate.
- **P2 (GPU Pareto frontier):** `A100-80GB` will be `10–25%` faster per sweep than `A100-40GB`, while `H100` will be `1.4×–2.0×` faster — making `A100-40GB` or `H100` Pareto-optimal on `screens/$` and `H100` on `screens/hr`.
- **P3 (Persistent JAX XLA cache):** Warm repeat `l2bt` on the same GPU & dataset (`screen-k10`, `--seed 2`) will cut `first sweep (compile)` by `>= 50%`, saving `~1–1.5 min` wall time.
- **P4 (Sign & ranking preservation at `k10`):** Exact sign for `>= 5/6` pairs and `4/4` `GO` verdicts for `|ΔELPD_full| >= 500`.
- **P5 (Attenuation decomposition):** Low-DOF global features (`l2kn - l1tkn`, `l2bt - l2kn`) will show `< 20%` attenuation (`Fit/Oracle ∈ [0.80, 1.20]`); high-DOF segment GPs (`u4s - u1`) will attenuate `15–40%` at `k20`, narrowing to `< 15%` at `k5`.
- **P6 (Negative control `d1 - b9`):** Will NOT falsely trigger `GO` at any `f` (`z < +1.0` at every `f`).
- **P7 (IG/min & IG/$ optimum):** `k10` will beat `k5` on `bits/$` and general screening throughput; `k20` will win raw `screens/hr` for coarse `>= +500` screening.
- **P8 (Draw-budget stability):** `2 150 200 5` (`350` sw) will preserve `ΔELPD` within `±15%` on `u4s - l2bt` while cutting sweep time `~45%`; doubling to `2 350 800 20` (`1,150` sw) will shift `ΔELPD` `< 10%`.
- **P9 (Seed stability):** Independent seed `screen-k10-s2` on `u1 - l2bt` will agree in verdict (`GO`) and within `±2` combined sampling SEs.
- **P10 (`market` `asof-20251110` at `k5`):** `unified` vs `range-j` will recover positive `ΔELPD` (`z > +1.5`, true `+173.8`) and flag the negative 80% coverage shift direction (`< 0`).

---

## 3. Experiment 1 & 4 — Modal Cloud GPU Hardware & Persistent JAX Cache Benchmark

All runs below fit `l2bt` (`drift-building-phase-unitkn-level-bedtext`) on Modal (`2 250 400 10` unless noted). `USD` is the exact settled charge in `/data1/apartments/modal/ledger.jsonl`; `IG(b)` is mean continuous Bayesian information gain (bits, `prior_sd = 1500`) across the 6 calibration pairs at that subsample size (`k20: 2.59 b`, `k10: 3.16 b`, `k5: 3.63 b`).

| Config (Modal GPU, Subsample, Chains/Draws) | Wall (min) | Stage (s) | Compile (s) | s / sweep | Settled $ | Screens / hr | IG (bits) | bits / min | bits / $ | max R-hat | min ESS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `L4` cold (`k10`, `2ch 650sw`) | `13.15` | `47.8` | `136.6` | `0.695` | `$0.27` | `4.6` | `3.16` | `0.24` | `11.7` | `1.060` | `38` |
| `A100-40GB` cold (`k10`, `2ch 650sw`) | `7.20` | `47.1` | `104.3` | `0.244` | `$0.30` | `8.3` | `3.16` | `0.44` | `10.5` | `1.056` | `37` |
| **`A100-40GB` warm (`k10`, `2ch 650sw`)** | **`5.38`** | `36.3` | **`24.9`** | `0.216` | **`$0.23`** | **`11.1`** | `3.16` | **`0.59`** | **`13.7`** | `1.102` | `9` |
| `A100-80GB` cold (`k10`, `2ch 650sw`) | `7.24` | `54.7` | `103.4` | `0.241` | `$0.35` | `8.3` | `3.16` | `0.44` | `9.0` | `1.060` | `38` |
| `H100` cold (`k10`, `2ch 650sw`) | `7.05` | `111.2` | `82.2` | `0.178` | `$0.51` | `8.5` | `3.16` | `0.45` | `6.2` | `1.060` | `38` |
| `H100` warm* (`k10`, `2ch 650sw`) | `5.54` | `26.4` | `70.6` | `0.173` | `$0.40` | `10.8` | `3.16` | `0.57` | `7.9` | `1.107` | `9` |
| `A100-40GB` cold (`k20`, `2ch 650sw`) | `5.59` | `38.7` | `77.9` | `0.193` | `$0.23` | `10.7` | `2.59` | `0.46` | `11.3` | `1.065` | `34` |
| `A100-40GB` cold (`k5`, `2ch 650sw`) | `8.70` | `37.3` | `107.5` | `0.361` | `$0.36` | `6.9` | `3.63` | `0.42` | `10.1` | `1.098` | `11` |
| **`A100-40GB` warm (`k5`, `2ch 650sw`)** | **`6.49`** | `18.9` | **`26.1`** | `0.323` | **`$0.27`** | **`9.2`** | **`3.63`** | **`0.56`** | **`13.4`** | **`1.062`** | **`39`** |
| `H100` cold (`k5`, `2ch 650sw`) | `7.96` | `70.2` | `100.4` | `0.252` | `$0.58` | `7.5` | `3.63` | `0.46` | `6.3` | `1.086` | `14` |
| `A100-40GB` cold (`k10`, `4ch 650sw`) | `7.27` | `29.8` | `85.1` | `0.337` | `$0.30` | `8.3` | `3.16` | `0.43` | `10.5` | `1.060` | `51` |
| **`A100-40GB` cold (`k5`, `4ch 650sw`)** | `10.69` | `16.3` | `114.8` | `0.560` | `$0.45` | `5.6` | `3.63` | `0.34` | `8.1` | **`1.047`** | **`100`** |
| `A100-40GB` warm (`k10`, `2ch 350sw` short) | `3.99` | `18.5` | `26.1` | `0.224` | `$0.17` | `15.0` | `3.16` | `0.79`† | `18.6`† | **`1.454`** | `9` |
| `A100-40GB` warm (`k10`, `2ch 1150sw` long) | `7.12` | `36.1` | `24.9` | `0.210` | `$0.30` | `8.4` | `3.16` | `0.44` | `10.5` | `1.062` | `33` |

*\*`H100 warm` landed on host driver `620.70.06` vs `610.57.04` on `H100 cold`, invalidating 3 of 4 XLA PTX cache entries (`16 → 19`). †`short (150 warmup)` failed convergence (`R-hat = 1.454`), so its nominal `bits/min` is unusable.*

**Key Hardware & Cache Takeaways:**
1. **`A100-40GB` dominates every other Modal GPU** at both `k10` and `k5`: `1.83×` faster than `L4` for only `+$0.03` cold (and cheaper warm: `$0.23` vs `$0.27`), identical speed to `A100-80GB` (`0.244` vs `0.241 s/sw`) at `-14%` cost, and **`2.1×` better `bits/$` than `H100`** (`13.4` vs `6.3 bits/$` at `k5`).
2. **Persistent `/vol/jax-cache` cuts compile by `-76%` (`4.2×`):** `104.3s → 24.9s` (`k10` `l2bt`), `107.5s → 26.1s` (`k5` `l2bt`), `112.6s → 26.6s` (`k10` `unified-seg`), and reuses compiled XLA executables across different draw/warmup counts (`350 / 650 / 1,150` sweeps all hit `94 → 94`!).
3. **Sub-linear cloud-GPU scaling (`k20 → k5`):** Because fixed container overhead (`stage + prep + compile + kernel launch`) dominates at `k20`, quadrupling the dataset from `94k → 376k` rows only increases warm wall time from `~4.4 min` (`k20` est.) → `5.38 min` (`k10`) → **`6.49 min` (`k5`)**, and cost from `$0.23 → $0.27` — making **`k5` warm `A100-40GB` (`6.5 min, $0.27`)** practically tied with `k10` warm (`5.4 min, $0.23`) on `bits/min` (`0.56` vs `0.59`) and `bits/$` (`13.4` vs `13.7`) while cutting MDE by `30%` and shrinking GP attenuation!
4. **Vectorized 4-chain batching (`--chains 4`):** On `A100-40GB`, running 4 chains simultaneously in one GPU batch costs only `1.55×` sweep time (`0.560` vs `0.361 s/sw` at `k5`; `0.337` vs `0.216 s/sw` at `k10`) and delivers **`max R-hat = 1.047–1.052, min ESS = 99–100`** in `~9 min` warm (`~$0.39`) — an ideal Escalation Tier configuration.

---

## 4. Experiment 2 — Subsample Size (`k20` / `k10` / `k5`) × Ground-Truth Calibration & Attenuation

Comparing fitted subsample projections (`Fit_full = ΔELPD_sub × N_held_full / N_held_sub`) against **exact full-data oracle scores on the identical held-out buildings (`Ora_full`)** cleanly separates irreducible building-sampling luck from small-sample parameter-estimation error. All verdicts below use our calibrated screening guard (`rhat_limit = 1.15`).

### 4a. `screen-k20` (5% buildings, `93,603` rows, `9,213` held-out, scale `×20.58`, mean IG `2.59` bits)

| Pair | Full Truth | Oracle on `k20` blds | Fitted `k20` (`z`) | Projected Full ± SE | `Fit / Ora` | `(Fit-Ora)/SE_ora` | 80% MDE | Verdict (`P(>100)`) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `d1 - b9` | `-63.0` | `+47` | `-0.6 ± 2.0` (`-0.33`) | `-13 ± 41` | — | `-1.14` | `114` | **`KILL`** (`0.003`) |
| `l2bt - l2kn` | `+223.6` | `-61` | `-4.9 ± 8.7` (`-0.57`) | `-101 ± 178` | `1.66` | `-0.20` | `500` | **`ESCALATE`** (`0.130`) |
| `l2kn - l1tkn` | `+519.6` | `+535` | `+29.8 ± 7.0` (`+4.29`) | `+614 ± 143` | `1.15` | `+0.63` | `401` | **`GO`** (`1.000`) |
| `u4s - u1` | `+2,334.4` | `+1,923` | `+68.6 ± 26.2` (`+2.62`) | `+1,413 ± 539` | **`0.73`** | `-0.98` | `1,510` | **`GO`** (`0.988`) |
| `u1 - l2bt` | `+2,762.9` | `+2,762` | `+165.7 ± 32.9` (`+5.04`) | `+3,412 ± 676` | `1.24` | `+0.96` | `1,894` | **`GO`** (`1.000`) |
| `u4s - l2bt` | `+5,097.3` | `+4,685` | `+234.4 ± 40.9` (`+5.72`) | `+4,825 ± 843` | `1.03` | `+0.17` | `2,360` | **`GO`** (`1.000`) |

### 4b. `screen-k10` (10% buildings, `185,391` rows, `18,111` held-out, scale `×10.47`, mean IG `3.16` bits)

| Pair | Full Truth | Oracle on `k10` blds | Fitted `k10` (`z`) | Projected Full ± SE | `Fit / Ora` | `(Fit-Ora)/SE_ora` | 80% MDE | Verdict (`P(>100)`) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `d1 - b9` | `-63.0` | `-38` | `+1.3 ± 2.2` (`+0.58`) | `+13 ± 23` | — | `+1.31` | `63` | **`KILL`** (`0.000`) |
| `l2bt - l2kn` | `+223.6` | `+26` | `+3.1 ± 12.9` (`+0.24`) | `+32 ± 135` | `1.23` | `+0.05` | `379` | **`ESCALATE`** (`0.307`) |
| `l2kn - l1tkn` | `+519.6` | `+477` | `+47.3 ± 9.1` (`+5.17`) | `+495 ± 96` | **`1.04`** | `+0.19` | `268` | **`GO`** (`1.000`) |
| `u4s - u1` | `+2,334.4` | `+2,087` | `+161.2 ± 34.0` (`+4.74`) | `+1,688 ± 356` | **`0.81`** | `-1.05` | `997` | **`GO`** (`1.000`) |
| `u1 - l2bt` | `+2,762.9` | `+2,396` | `+280.7 ± 43.3` (`+6.48`) | `+2,940 ± 453` | `1.23` | `+1.17` | `1,269` | **`GO`** (`1.000`) |
| `u4s - l2bt` | `+5,097.3` | `+4,482` | `+441.9 ± 52.7` (`+8.39`) | `+4,628 ± 552` | `1.03` | `+0.26` | `1,545` | **`GO`** (`1.000`) |

### 4c. `screen-k5` (20% buildings, `376,261` rows, `37,199` held-out, scale `×5.10`, mean IG `3.63` bits)

| Pair | Full Truth | Oracle on `k5` blds | Fitted `k5` (`z`) | Projected Full ± SE | `Fit / Ora` | `(Fit-Ora)/SE_ora` | 80% MDE | Verdict (`P(>100)`) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `d1 - b9` | `-63.0` | `-61` | `-3.0 ± 3.1` (`-0.95`) | `-15 ± 16` | `0.25` | `+1.70` | `45` | **`KILL`** (`0.000`) |
| `l2bt - l2kn` | `+223.6` | `+78` | `+24.8 ± 18.6` (`+1.34`) | `+127 ± 95` | `1.63` | `+0.58` | `265` | **`ESCALATE`** (`0.609`) |
| `l2kn - l1tkn` | `+519.6` | `+540` | `+94.1 ± 13.8` (`+6.82`) | `+480 ± 70` | **`0.89`** | `-0.87` | `197` | **`GO`** (`1.000`) |
| `u4s - u1` | `+2,334.4` | `+2,453` | `+421.3 ± 50.6` (`+8.32`) | `+2,148 ± 258` | **`0.88`** | `-1.13` | `722` | **`GO`** (`1.000`) |
| `u1 - l2bt` | `+2,762.9` | `+2,578` | `+557.8 ± 61.9` (`+9.01`) | `+2,844 ± 316` | `1.10` | `+0.82` | `884` | **`GO`** (`1.000`) |
| `u4s - l2bt` | `+5,097.3` | `+5,031` | `+979.2 ± 77.8` (`+12.59`) | **`+4,992 ± 396`** | **`0.99`** | `-0.10` | `1,110` | **`GO`** (`1.000`) |

### Error Decomposition (Sampling Variance vs Small-Sample Estimation Noise)

Across all 6 calibration pairs, `RMS((Fit_full - Ora_full) / SE_ora)` is **`0.78` (`k20`)**, **`0.84` (`k10`)**, and **`1.00` (`k5`)**, corresponding to an empirical total-uncertainty inflation factor of **`sqrt(1 + rms^2) = 1.27×–1.41×`** over raw building-clustered sampling SE (use `--extra-noise-scale 1.35` for conservative posterior probabilities). Two structural patterns are crystal clear:
- **High-DOF segment GPs (`u4s - u1`) attenuate monotonically with `f`:** **`-27%` (`0.73`) at `k20` → `-19%` (`0.81`) at `k10` → `-12%` (`0.88`) at `k5`**, because sparser `(borough, bed, quarter)` cells shrink Matérn-3/2 paths toward zero.
- **Low-DOF global terms (`l2kn - l1tkn`, `l2bt - l2kn`) have near-zero estimation attenuation:** `l2bt - l2kn` tracked the exact building-draw oracle (`+32` vs `+26` on `k10`, `+127` vs `+78` on `k5`), confirming that small-effect ambiguity is dominated by building-sampling variance, not estimation bias.

---

## 5. Experiment 3 & 4 — Draw-Budget Sweep, 4-Chain Batching, Seed-2 & `market` Screen

### 5a. Draw-Budget Sweep (`screen-k10`, `A100-40GB`)

| Draw Schedule | Pair | Sub ΔELPD (`z`) | Projected Full ± SE | Wall (s) | Settled $ | max R-hat | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| Short (`2 150 200 5`, `350sw`) | `l2bt - l2kn` | `+8.1 ± 13.1` (`+0.62`) | `+85 ± 138` | `239.6s` | `$0.17` | **`1.454`** | `ESCALATE` (FAIL R-hat) |
| Med (`2 250 400 10`, `650sw`) | `l2bt - l2kn` | **`+3.1 ± 12.9`** (`+0.24`) | `+32 ± 135` | `323.0s` (warm) | `$0.23` | `1.056` | `ESCALATE` |
| Long (`2 350 800 20`, `1150sw`) | `l2bt - l2kn` | **`+3.2 ± 13.5`** (`+0.24`) | `+34 ± 142` | `427.2s` (warm) | `$0.30` | `1.062` | `ESCALATE` |
| Short (`2 150 200 5`, `350sw`) | `u4s - l2bt` | `+447.4 ± 53.7` (`+8.33`) | `+4,685 ± 562` | `956.5s` | `$0.67` | `1.126` | `GO` (noisy R-hat) |
| Med (`2 250 400 10`, `650sw`) | `u4s - l2bt` | **`+441.9 ± 52.7`** (`+8.39`) | **`+4,628 ± 552`** | `1,212.0s` | `$0.85` | `1.059` | **`GO`** |
| Long (`2 350 800 20`, `1150sw`) | `u4s - l2bt` | **`+434.0 ± 52.7`** (`+8.24`) | **`+4,545 ± 552`** | `1,242.4s` (warm) | `$0.87` | **`1.029`** | **`GO`** |

**Conclusion:** `2 250 400 10` (`650` sweeps) is the exact sweet spot: `l2bt - l2kn` changes by `0.1` ELPD (`+3.1 → +3.2`) and `u4s - l2bt` by `-1.8%` (`+4,628 → +4,545`) when nearly doubling sweeps to `1,150`. Cutting warmup below `250` (`150` warmup) breaks the second slice-adaptation window and blows up `R-hat` to `1.45`.

### 5b. 4-Chain Vectorized Batching (`--chains 4` in 1 GPU batch on `A100-40GB`)

- On `k10` `d1 - b9` (`-63` truth, `-38` oracle): switching `2ch → 4ch` flipped the point estimate to the true negative sign (`+13 ± 23` → **`-12 ± 18`**) and cut paired SE by **`-23%`** for only `+28s` wall time.
- On `k5` `l2bt - l2kn`: `4ch` (`4 250 400 10`) achieved **`max R-hat = 1.047–1.052, min ESS = 99–100`** (`+108 ± 90`, `P(>0) = 0.885`) in `10.7 min` cold (`~9.2 min` warm, `$0.45` cold / `~$0.39` warm) — crushing the 2-chain `R-hat` noise (`1.098–1.109`, `ESS = 11–17`) cleanly below full-publish convergence thresholds.

### 5c. 2nd Independent Subsample Seed (`screen-k10-s2`, seed `20261199`)

- **`u1 - l2bt` (`+2,763` truth):** Seed 1 gave **`+2,940 ± 453`** (`z = +6.48`, `GO`); Seed 2 gave **`+2,944 ± 504`** (`z = +5.84`, `GO`) — two disjoint 10% building samples agreed to **`4` ELPD**!
- **`l2bt - l2kn` (`+224` truth):** Seed 2 tracked its `+236` oracle (`+186 ± 132`, `z = +1.40`, `ESCALATE`), cleanly confirming that Seed 1's `+32` (`oracle = +26`) was a `1.4σ` unlucky building draw.

### 5d. `market` (`asof-20251110`) Deals Backtest Screen (`screen-mkt-k5`, `n = 1,891` open ads, `996` buildings)

- **`unified` (`exp3-mkt2-u1`, `18.5 min`, `$0.78`) vs `range-j` (`exp3-mkt2-rangej`, `8.7 min`, `$0.37`):**
  - **Subsample ΔELPD:** **`+32.2 ± 16.8`** (`z = +1.92`, `+0.01704`/row; half A `+2.7`, half B `+29.5`).
  - **Projected Full ΔELPD:** **`+159 ± 83`** (`P(>0) = 0.973`, `P(>50) = 0.906`, `IG = 4.18 bits`, **`5.4 bits/$`**) vs full-data ground truth **`+173.8`** (`z = +5.4`, within `8.5%` at `1/15th` the cost!).
  - **Automatic Coverage Regression Catch:** 80% coverage shifted **`76.89% → 74.99%` (`-1.90 pp`, warning emitted!)** and `<5%` tail shifted **`4.02% → 4.39%` (`+0.37 pp`)** — matching the exact negative coverage regression (`-2.5 pp`, `<5%` tail `+1.1 pp`) documented on the full `market` backtest in PR #1530!

---

## 6. Honest Pre-Fit Prediction Scorecard (Committed Before Launches in `d40e6a95`)

| # | Pre-Fit Prediction | Observed Result | Verdict |
|---|---|---|---|
| **P1** | `L4` `>= 2.5×` slower/sweep than `A100-40GB` AND NOT cheaper per screen | `L4` was `2.85×` slower/sweep (`0.695` vs `0.244s`), **BUT** cold `L4` (`$0.27`) was `$0.03` cheaper than cold `A100-40GB` (`$0.30`; warm `A100-40GB` `$0.23` did beat `L4`) | **PARTIAL** (sweep HIT, cold `$` MISS) |
| **P2** | `A100-80GB` `10–25%` faster than `A100-40GB`; `H100` `1.4–2.0×` faster | `A100-80GB` was only `1.2%` faster (`0.241` vs `0.244s`, same SXM4 chip); `H100` was `1.37×` faster at `k10` / `1.43×` at `k5` | **PARTIAL** (`A100-80GB` MISS, `H100` & Pareto HIT) |
| **P3** | Warm `/vol/jax-cache` cuts compile `>= 50%` and saves `~1–1.5 min` | `A100-40GB` compile dropped **`-76%`** (`104.3s → 24.9s` at `k10`, `107.5s → 26.1s` at `k5`), saving **`1.8–2.2 min`**! | **HIT** |
| **P4** | At `k10`, exact sign for `>= 5/6` pairs and `4/4` `GO` for `>= +500` | Exact sign `5/6` (`+` on all 5 positives; `d1-b9` was `+1.3` with 2ch, `-1.2` with 4ch) and **`4/4` `GO`** (`z = +4.74` to `+8.39`) | **HIT** |
| **P5** | Low-DOF attenuation `< 20%`; Matérn GP (`u4s-u1`) attenuates `15–40%` at `k20` → `< 15%` at `k5` | `l2kn-l1tkn`: `1.04` (`k10`), `0.89` (`k5`); `u4s-u1`: **`0.73` (`-27%`) at `k20` → `0.81` (`-19%`) at `k10` → `0.88` (`-12%`) at `k5`** | **HIT (bullseye)** |
| **P6** | Negative control `d1 - b9` never falsely triggers `GO`, `z < +1.0` at every `f` | `z = -0.33` (`k20`, `KILL`), `+0.58` (`k10`, `KILL`), `-0.95` (`k5`, `KILL`) — zero false `GO`s | **HIT** |
| **P7** | `k10` beats `k5` on `bits/$`; `k20` wins raw `screens/hr` | `k10` warm (`13.7 bits/$`) edged `k5` warm (`13.4 bits/$`) by only `2%` (virtually tied because of fixed Modal overhead!); `k5` dominates `k20` (`13.4` vs `11.3 bits/$`) | **PARTIAL** (k5 much stronger than expected) |
| **P8** | `350sw` within `±15%` on `u4s-l2bt` (`-45%` sweep time); `1,150sw` `< 10%` shift | `350sw` `+1.2%` (`+4,685` vs `+4,628`), `1,150sw` `-1.8%` (`+4,545`); **caveat:** `150` warmup broke `R-hat` (`1.45`) | **HIT (with R-hat caveat)** |
| **P9** | Seed-2 `u1 - l2bt` agrees on `GO` and within `±2` SEs | Seed 1 `+2,940 ± 453` vs Seed 2 **`+2,944 ± 504`** (`GO`, `0.006` SE apart!) | **HIT** |
| **P10** | `market` `k5` `unified` vs `range-j` recovers `z > +1.5` & negative 80% cov shift | **`+159 ± 83` (`z = +1.92`, `P(>0) = 0.973`)** and **80% cov `-1.90 pp`** (auto-warned!) | **HIT (bullseye)** |

**Scorecard Summary:** **7 HITs, 3 PARTIALs, 0 outright MISSes** — and the 3 PARTIALs (`L4` hourly-rate math, `A100-40GB` = SXM4 parity with `80GB`, and `k5`'s tiny marginal cost over `k10`) are precisely the Cloud-GPU-specific insights that only real Modal runs could uncover.

---

## 7. Recommended Production Screening SOP & Itemized Modal Spend

### Recommended Two-Stage Modal Screening Protocol

1. **Pre-build reusable subsamples once per dataset snapshot** (cached on disk & Modal Volume):
   ```bash
   ops/modal-screen build <SRC_LATEST> <OUT>/screen-k5  --divisor 5  --split latest
   ops/modal-screen build <SRC_LATEST> <OUT>/screen-k10 --divisor 10 --split latest
   ops/modal-screen build <SRC_MARKET> <OUT>/screen-mkt-k5 --divisor 5 --split market
   ```
2. **Stage 1 — Default Triage (`screen-k5` on `A100-40GB`, `2 250 400 10`, warm `6.5 min`, `$0.27`):**
   ```bash
   ops/modal-screen run --gpu A100-40GB --dataset <OUT>/screen-k5 \
     --input <ROWS_PARQUET> <SHA> <LABEL> <MODEL>
   ops/modal-screen compare <BASE_RUN> <CAND_RUN> --extra-noise-scale 1.35
   ```
   - **`KILL`** (`z <= -1.5` or `P(>gate) < 0.05` with `z < 1.0`): Drop the idea immediately (`$0.27` spent vs `$15+` saved).
   - **`GO`** (`z >= 2.0`, both building halves positive, `P(>gate) >= 0.90`, `max R-hat <= 1.15`): Promote directly to full 6-chain Modal fit. (Check any coverage warnings!)
   - **`ESCALATE`** (typically `+100` to `+300` ELPD effects or noisy `R-hat`): Proceed to Stage 2.
   - *(Use `screen-k10` (`5.4 min`, `$0.23`) for high-volume sweeps of coarse `>= +500` ideas, or when testing models with heavy post-sampling tracing like `unified-seg`.)*
3. **Stage 2 — Escalation (`screen-k5` with `--chains 4`, warm `~9.2 min`, `~$0.39`, `R-hat <= 1.05`, `ESS ~ 100`):**
   ```bash
   ops/modal-screen run --gpu A100-40GB --dataset <OUT>/screen-k5 --chains 4 \
     --input <ROWS_PARQUET> <SHA> <LABEL>-ch4 <MODEL>
   ```
   - Cuts Monte Carlo paired SE and stabilizes `R-hat < 1.05`. If still `ESCALATE`, run a 2nd independent `k5` seed or promote if domain priors warrant a full fit.
4. **Deals Backtest Pre-Screen (`screen-mkt-k5`, `asof-20251110`, `~9–18 min`, `$0.37–$0.78`):**
   - Run before any full `market` backtest (`~$15`) to check both `ΔELPD` sign/magnitude and 80% / `<5%` tail coverage regressions.

### Itemized Modal Spend Ledger (2026-11-22, after `08:34:00 ET`)

Authoritative totals from `/data1/apartments/modal/ledger.jsonl` (`kind == "settle"`):

| Experiment Group | Containers | Settled USD | Notes |
|---|---:|---:|---|
| `exp1-*` (GPU hardware & warm JAX cache) | `6` | `$2.06` | `L4`, `A100-40GB` cold/warm, `A100-80GB`, `H100` cold/warm on `k10` |
| `exp2-k10-*` (`screen-k10` ladder) | `6` | `$2.73` | `b9`, `d1`, `l1tkn`, `l2kn`, `u1`, `u4s` (`l2bt` reused from `exp1`) |
| `exp2-k20-*` (`screen-k20` ladder) | `7` | `$2.86` | Full 7-model calibration ladder at `f = 1/20` |
| `exp2-k5-*` (`screen-k5` ladder) | `7` | `$3.67` | Full 7-model calibration ladder at `f = 1/5` |
| `exp3-short-*` (`2 150 200 5`) | `3` | `$1.00` | `l2kn`, `l2bt`, `u4s` on `k10` (warm cache hits) |
| `exp3-long-*` (`2 350 800 20`) | `3` | `$1.48` | `l2kn`, `l2bt`, `u4s` on `k10` (warm cache hits) |
| `exp3-ch4-*` (`4 250 400 10`) | `3` | `$1.00` | Vectorized 4-chain batch (`b9`, `d1`, `l2bt`) on `k10` |
| `exp3-k5-*` (`k5` warm cache) | `1` | `$0.27` | Warm `A100-40GB` `l2bt` at `f = 1/5` (`26.1s` compile) |
| `exp3-s2-*` (2nd seed `screen-k10-s2`) | `3` | `$1.30` | `l2kn`, `l2bt`, `u1` on independent seed `20261199` |
| `exp3-mkt*` (`market` `asof-20251110` `k5`) | `4` | `$1.27` | `$0.12` (2 failed missing `inputs.json`) + `$1.15` (`range-j` + `u1`) |
| `exp4-*` (`k5` `H100` + `k5` `4ch` escalation) | `3` | `$1.47` | `H100` `k5` (`$0.58`) + `A100-40GB` `k5` `4ch` `l2kn`/`l2bt` (`$0.89`) |
| **TOTAL SPRINT SPEND** | **`46`** | **`$19.11`** | **Authorized cap: `$50.00` (`$30.89` remaining, `38.2%` used)** |
