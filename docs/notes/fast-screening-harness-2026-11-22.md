# Fast Screening Harness on Modal Cloud GPUs (2026-11-22)

**Goal:** Maximize **information gain per unit time** (and per dollar) for drift-model feature & structural iteration by building, benchmarking, and empirically calibrating a reusable **Modal Cloud GPU Fast Screening Harness** (`rentfrontier.screen` + `ops/modal-screen` + persistent XLA compilation cache on `/vol/jax-cache`).

**Scope & Constraints:**
- Target hardware: **Modal Cloud GPUs** (`L4`, `A100-40GB`, `A100-80GB`, `H100`), NOT local `thelio` RTX 2060.
- Sampler speedups (`double-pass`, `slow_within`, tracing 24 factors) are intentionally **deferred** to a separate project; this study measures pure screening-harness leverage on the current sampler as-is.
- Authorized Modal spend ceiling: **`$50.00`** (strictly tracked via `/data1/apartments/modal/ledger.jsonl` after `2026-11-22T08:34:00-05:00`).

---

## 1. Ground-Truth Calibration Ladder & Zero-Spend Oracle Power Analysis

We calibrate the screening harness against **7 known full-data `latest`-split model pairs** on `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-bedtext` (`1,896,471` total rows, `189,647` held-out ads across `36,207` buildings), spanning negative, small-medium, medium, large, and huge true effects:

| Pair (Candidate vs Baseline) | Regime | Full-data ΔELPD | Full SE | Full z | ΔELPD / row |
|---|---|---:|---:|---:|---:|
| `d1 - b9` (doorman interaction) | **NEGATIVE (reject)** | `-63.0` | `12.2` | `-5.18` | `-0.00033` |
| `l2bt - l2kn` (`bedtext` flags) | **SMALL-MED** | `+223.6` | `38.5` | `+5.80` | `+0.00118` |
| `l2kn - l1tkn` (lease-phase levels) | **MEDIUM** | `+519.6` | `29.9` | `+17.40` | `+0.00274` |
| `u4s - u1` (Matérn-3/2 segment GPs) | **LARGE** | `+2,334.4` | `112.4` | `+20.76` | `+0.01231` |
| `u1 - l2bt` (`unified` bundle) | **LARGE** | `+2,762.9` | `149.2` | `+18.52` | `+0.01457` |
| `l1tkn - l1` (Student-t unit + fixed ν=2) | **HUGE** | `+4,105.6` | `172.6` | `+23.78` | `+0.02165` |
| `u4s - l2bt` (`unified-seg` vs `l2bt`) | **HUGE** | `+5,097.3` | `179.1` | `+28.47` | `+0.02688` |

### Zero-Spend Oracle Stratification & Power Analysis (200 random seeds)

Before spending `$0.01` on Modal, we evaluated `200` random building subsamples at `f ∈ {1/20, 1/10, 1/5}` using the full-data oracle `pred_scores` (isolating pure building-sampling variance before small-sample estimation attenuation):

- **Size-decile stratified equal-probability sampling** (`stratify="size"`, 10 bins ordered by building row count, nested across `f` at fixed seed) preserves exact unbiasedness (`E[ΔELPD_sub / f] = ΔELPD_full`) while cutting subsample row-count CV (`4.86% → 4.35%` at `1/20`, `3.24% → 3.06%` at `1/10`, `2.39% → 1.84%` at `1/5`).
- **Oracle detection power (sign accuracy / `|z| >= 2` rate / median `z`):**
  - **`f = 1/20` (5%, ~95k rows):** `>= +500` effects have `100%` sign accuracy and `96.5%–100%` `|z|>=2`; `+224` (`l2bt-l2kn`) has `90%` sign / `23%` `|z|>=2` (`med z = +1.35`); `-63` (`d1-b9`) has `83%` sign (`med z = -1.08`).
  - **`f = 1/10` (10%, ~190k rows):** `>= +500` effects have `100%` sign & `100%` `|z|>=2` (`med z = +5.49` to `+8.89`); `+224` has `97.5%` sign / `43%` `|z|>=2` (`med z = +1.88`); `-63` has `98.0%` sign (`med z = -1.57`).
  - **`f = 1/5` (20%, ~379k rows):** `+224` reaches `100%` sign & `73%` `|z|>=2` (`med z = +2.67`); `-63` reaches `99.5%` sign & `66.5%` `|z|>=2` (`med z = -2.38`).

---

## 2. Pre-Fit Predictions (Committed Before Launching Any Modal Container)

All predictions below are recorded **before** launching any Modal GPU fit for Experiments 1–3. They will be scored honestly in Section 6 after all runs settle.

### Experiment 1 — Modal Cloud GPU Hardware & Persistent JAX Cache (`screen-k10`, `l2bt`, `2 250 400 10`)
- **P1 (L4 FP64 penalty):** Because `drift.py` runs in `float64` and NVIDIA `L4` has 1:64 FP64:FP32 throughput, `L4` will be **`>= 2.5x` slower per sweep** than `A100-40GB` and will **NOT** be cheaper per screen despite its `2.07x` lower hourly rate (`$1.213/hr` vs `$2.513/hr`).
- **P2 (A100-40GB vs A100-80GB vs H100 Pareto frontier):** `A100-80GB` (SXM4, higher memory bandwidth) will be `10–25%` faster per sweep than `A100-40GB`, while `H100` will be `1.4x–2.0x` faster per sweep than `A100-40GB` — making **`A100-40GB` or `H100`** the Pareto winner on `screens/$` and `H100` the winner on `screens/hr` (since fixed stage + compile overhead dilutes `H100`'s sweep-speed edge on short `650`-sweep screens).
- **P3 (Persistent JAX XLA cache on `/vol/jax-cache`):** A warm repeat run of `l2bt` on the same GPU and dataset (`screen-k10`, `--seed 2`) will cut `first sweep (compile)` by **`>= 50%`** (e.g., from `~60–120s` cold down to `< 30s` warm), cutting total wall time per screen by `~1–1.5 min`.

### Experiment 2 — Subsample Size (`f = 1/20, 1/10, 1/5`) × Ground-Truth Calibration & Attenuation
- **P4 (Sign & ranking preservation):** At `f = 1/10` (`screen-k10`), the fitted screen will recover the **exact sign** (`+` vs `-`) for at least **5 of 6** calibration pairs, and **100% (4/4)** of pairs with `|ΔELPD_full| >= 500` will receive a **`GO`** verdict (`z >= 2.0`, both halves positive, `P(>100) >= 0.90`).
- **P5 (Small-sample estimation attenuation — structural vs local features):** Comparing fitted `ΔELPD_sub / f` against oracle `ΔELPD_sub / f` on the exact same held-out buildings:
  - Low-DOF global features (`l2kn - l1tkn`, `l2bt - l2kn`) will show **small attenuation (`< 20%`)** at `k10` (`fitted / oracle ∈ [0.80, 1.20]`).
  - High-DOF hierarchical/GP features (`u4s - u1` Matérn-3/2 segment GPs, `u1 - l2bt` 24 phase scales + global bundle) will show **measurable downward attenuation (`15%–40%` at `k20`, narrowing to `< 15%` at `k5`)**, because sparser buildings/quarters shrink the 9 segment GP paths and 24 phase scales slightly toward zero.
- **P6 (Negative control `d1 - b9`):** On `screen-k20` and `screen-k10`, `d1 - b9` (`-63` full-data) will **NOT** falsely trigger `GO` (verdict will be `KILL` or `ESCALATE`, with `z < +1.0` at every `f`).
- **P7 (Information Gain per Minute optimum):** **`f = 1/10` (`screen-k10`)** will beat `f = 1/5` (`screen-k5`) on **Information Gain per dollar (`bits/$`)** and beat both `1/20` and `1/5` on **usable decision throughput** for general screening, while `f = 1/20` will win raw `screens/hr` for coarse `>= +500` screening and `f = 1/5` will be needed only for escalating marginal `100–300` ELPD effects.

### Experiment 3 — Draw-Budget Sweep, Seed Stability & `market` Deals Backtest Screen
- **P8 (Draw-count stability):** Cutting draws from `2 250 400 10` (`650` sweeps) down to `2 150 200 5` (`350` sweeps) on `k10` will preserve `ΔELPD` within **`±15%`** for large effects (`u4s - l2bt`) while cutting sweep time by `~45%`, whereas doubling to `2 350 800 20` (`1,150` sweeps) will change `ΔELPD` by `< 10%` at `~1.7x` sampling cost — showing diminishing returns past `2 250 400 10` for screening.
- **P9 (Seed stability):** An independent 2nd seed (`screen-k10-s2`) on `u1 - l2bt` will agree with `screen-k10` in verdict (`GO`) and within `±2` combined sampling SEs on projected `ΔELPD_full`.
- **P10 (`market` `asof-20251110` backtest screen at `f = 1/5`):** `unified` vs `range-j` (`drift-building-bedtext-layout-range`) on `screen-mkt-k5` (`~1,870` held-out open ads) will recover positive `ΔELPD` (`z > +1.5`, full-data ground truth `+173.8`, `z = +5.4`) and flag the same 80% coverage shift direction (`< 0`) observed on the full `market` backtest.

---

## 3. Experiment 1 — Modal Cloud GPU & Persistent JAX Cache Results

*(To be filled after Experiment 1 settles.)*

## 4. Experiment 2 — Subsample Size × Ground-Truth Calibration & Attenuation

*(To be filled after Experiment 2 settles.)*

## 5. Experiment 3 — Draw-Budget Sweep, Seed Check & `market` Screen

*(To be filled after Experiment 3 settles.)*

## 6. Prediction Scorecard

*(To be scored honestly after Experiments 1–3 settle.)*

## 7. Recommended Screening SOP & Itemized Modal Spend

*(To be completed before PR hand-off.)*
