# Unified Base-Refit Drift Model (`drift-building-phase-unitkn-unified` & `unified-seg`): Pre-Fit Predictions (2026-11-21)

Written BEFORE launching any Modal GPU fit.

## Motivation & Zero-Spend Sizing Summary
Joint cross-fitted sizing (`p2_joint_sizing.py` & `p2_panel_c.py` in `/data1/apartments/tmp/whole-dataset-audit-2026-11-21/`) evaluated our Phase 1 whole-dataset audit candidates on top of the queued base-refit bundle (`j1`'s 8 kept terms + `Y1` calendar-year noise + `j5` gap bins & flag-change counts) across three panels:

1. **`l2bt` all years (`189,647` held-out ads, `df=5`):**
   - `BASE (j1 + Y1 + j5)`: `+3,573.5` (SE `108.6`, A `+1,630.4`, B `+1,943.1`).
   - Added over `BASE`, leave-one-block-out:
     - `layout-range` (8 directional bed/bath change & range columns): **`+1,175.1` (SE `64.1`, z=`+18.3`)** (`+782` shift-only, `+418` scale-only).
     - `large_01br` + `size_imp_log_size_rel`: **`+212.1` (SE `26.9`, z=`+7.9`)** (`+127` shift, `+87` scale).
     - `bed_grp x era`: **`+212.4` (SE `29.2`, z=`+7.3`)**; `outer_boro x era`: **`+146.5` (SE `21.8`, z=`+6.7`)**.
     - Rejected (failed gate on `l2bt`): `rent_stabilized` (`+6.0`, SE `9.1`), `concession` (`+0.8` LOO, SE `11.7`).
2. **`l2bt` `2022+` (`129,861` held-out ads, `df=7`):**
   - `BASE (j1 + Y1 + j5)`: `+2,503.9` (SE `92.8`, A `+1,154.1`, B `+1,349.8`).
   - Leave-one-block-out: `layout-range` **`+621.0` (z=`+12.8`)**, `large_01br + size_imp_slope` **`+175.5` (z=`+7.1`)**, `bed_grp x era` **`+122.2` (z=`+5.3`)**, `outer_boro x era` **`+47.1` (z=`+3.7`)**.
3. **`range-j` Deals backtest (`9,346` open ads as of `2025-11-10`, `df=7`):**
   - `no_unit_history + thin_bld_bed` (`<5` prior same-bed training ads): **`+75.4` (SE `19.3`, z=`+3.9`, A `+34.6`, B `+40.8`)**, lifting `no_hist & thin_bed<5` 80% coverage from `68.1% -> 80.2%` and cutting `>95%` tail from `16.6% -> 6.2%`.
   - `j1` bath/floor/tier scale subset: **`+73.9` (SE `15.8`, z=`+4.7`)**.
   - Rejected on `range-j`: `concession` (`+2.1` LOO), `rent_stabilized` (`-0.2` LOO).

## Models Implemented
1. **`drift-building-phase-unitkn-unified`**:
   - Base: `drift-building-phase-unitkn-level` (`nu_u=3` collapsed Student-t unit levels, fixed row `nu=2`, collapsed building AR(1) paths + Student-t building levels `dof=4`, lease-phase level columns).
   - Mean upgrades: `same_bed_first=True` in `sizefill.asof_size`, `bedunit` (`ad:bed_text_smaller` + `uever`), `layout-range` (8 columns), `ad:size_imp_log_size_rel`, `ad:large_01br`.
   - Additive log-scale factors (`Design.phase_map`, compact observed cells): 6 lease phases + up to 12 calendar years (`Y1`, ref `2024`, dropping empty years automatically) + 6 strictly exogenous marks (`changed_counts`, `baths_2`, `baths_3p`, `floor_1`, `large_01br`, `thin_first_ad`).
2. **`drift-building-phase-unitkn-unified-seg`**:
   - Same as `unified`, plus quarterly Gaussian-process market-segment paths (`drift_building_phase_segment`, 8 `(zone, bed)` segments).

## Pre-Fit Predictions (Recorded Before Launch)

### On `latest` split vs `l2bt` (`189,647` all years; `129,861` `2022+`)
1. **`unified` held-out Δelpd vs `l2bt`:**
   - All years: **+1,500 to +3,200 elpd**, positive on BOTH halves A and B (note: real Bayesian refit will absorb some cross-fitted gain into building/unit scales, so ~50–80% of the +4,500 post-hoc sum is expected).
   - `2022+`: **+900 to +2,100 elpd**, positive on BOTH halves A and B.
2. **`unified-seg` held-out Δelpd vs `unified`:**
   - All years: **+200 to +550 elpd** (from 2020–21 and 2022–26 segment divergence).
   - `2022+`: **+80 to +220 elpd**.
3. **80% interval coverage by calendar year (`unified`):**
   - Moves 2020–2021 coverage from `0.730–0.738` to **`0.785–0.815`**; 2022 from `0.760` to **`0.790–0.815`**; 2024–2026 within **`0.790–0.815`**.
4. **Key fitted parameters (`unified`):**
   - `mark:changed_counts` scale: **`1.15 to 1.30`**; `mark:baths_2`: **`1.10 to 1.25`**; `mark:baths_3p`: **`1.30 to 1.65`**; `mark:large_01br`: **`1.15 to 1.35`**; `mark:thin_first_ad`: **`1.15 to 1.45`**.
   - `yr:2020` and `yr:2021` scales: **`1.18 to 1.32`** relative to 2024; `yr:2026`: **`0.93 to 0.99`**.
   - `ad:size_imp_log_size_rel` beta: **`-0.015 to -0.045`** (shrinking filled-size slope toward 0.8× stated slope).
   - `ad:beds_up_prev` / `ad:baths_up_prev`: negative (**`-0.015 to -0.045`**); `ad:beds_down_prev` / `ad:baths_down_prev`: positive (**`+0.015 to +0.050`**).
5. **Convergence & sweep speed:**
   - H100 sweep time for `unified`: **`0.85 to 1.35 s/sweep`** (2 chains), allowing `2,000–2,900` sweeps per 42-min container (`~1.0–1.5x` `l2bt`'s `0.76 s/sweep`).
   - 3 containers × 2 chains (6 chains pooled): passes strict convergence gate (**max split R-hat ≤ 1.01, min bulk ESS > 400** across all scalars, betas, and buildings).

### On `market` Deals backtest (`asof-20251110`, `9,346` open ads) vs `range-j`
6. **`unified` held-out Δelpd vs `range-j`:**
   - **+180 to +450 elpd** on `9,346` open ads (positive on BOTH halves A and B), combining `unitkn` Student-t unit levels + `bedunit` + `Y1` + `j1` bath/floor/large-01br scales + `thin_first_ad` scale.
7. **First-ad (`no_unit_history`, `n=3,168`) and thin-building (`no_hist & thin_bed<5`, `n=727`) calibration:**
   - `no_unit_history` 80% coverage improves from `75.8%` to **`78.5%–81.5%`**.
   - `no_hist & thin_bed<5` 80% coverage improves from `68.1%` to **`76.0%–82.0%`**, and `>95%` tail drops from `16.6%` to **`<9.0%`**.
8. **Deals low tail (`cdf < 0.05`):**
   - Stays well-calibrated (**`4.5% to 5.6%`** overall and on both `no_unit_history` and `has_unit_history`).

## Experimental Plan & Budget Cap
- Authorized Modal budget: **$100.00** (zero OxyLabs spend).
- Stage 1 (Cheap 2-chain H100 screening pilots, ~$6–$10 total):
  - Pilot A: `unified` on `market` (`asof-20251110`, 2 chains, ~25 min, ~$2.50) vs `range-j`.
  - Pilot B: `unified` on `latest` (2 chains, ~30–40 min, ~$3.00) vs `l2bt`.
  - Pilot C: `unified-seg` on `latest` (2 chains, ~35–45 min, ~$3.50) vs Pilot B.
- Stage 2 (Full 6-chain = 3×2-container pooled gate fits on the winning spec(s), ~$25–$40 total):
  - Gate Fit 1: 3 containers (`seed=1,2,3`) on `latest` vs `l2bt` (~$12–$15).
  - Gate Fit 2: 3 containers (`seed=1,2,3`) on `market` (`asof-20251110`) vs `range-j` (~$10–$14).
  - Optional Gate Fit 3 (if `unified-seg` beats `unified` cleanly and mixes well, or to test a further refinement discovered from Pilots A–C): ~$12–$15.
- All runs launched via `ops/modal-fit --outside-budget --gpu H100` from committed clean git SHAs; exact settled costs summed from `/data1/apartments/modal/ledger.jsonl` and strictly capped below $100.

---

## Stage 1 Screening Pilots (Commit `d96884ac`, 2 chains × 350w + 900d, H100)

Settled Modal spend through Stage 1: **`$10.66`** (`$0.82` early setup fixes + `$3.00` `u1-mkt-p3` + `$2.97` `u1-lat-p3` + `$3.87` `u1s-lat-p3`).

| Pilot | Model | Split | Baseline | Held-out Δelpd (SE, z) | Half A / Half B | Sweep s | Cost | Status / Diagnosis |
|---|---|---|---|---|---|---|---|---|
| `u1-mkt-p3` | `unified` | `market` (`asof-20251110`, `n=9,346`) | `range-j` | **`+176.8` (32.8, z=+5.4)** | `+126.8` / `+50.0` | `1.210s` | `$3.00` | Clean mixing except slow `phase_scale` (min ESS 79) |
| `u1-lat-p3` | `unified` | `latest` (`n=189,647` / `2022+ n=130,041`) | `l2bt` | **`+2,762.9` (149.2, z=+18.5)** / **`+1,845.3` (116.4, z=+15.9)** | `+1,281.1` / `+1,481.8` (`2022+`: `+845.1` / `+1,000.2`) | `1.176s` | `$2.97` | Clean mixing except slow `phase_scale` (min ESS 71, max rhat 1.032) |
| `u1s-lat-p3` | `unified-seg` | `latest` (`n=189,647` / `2022+ n=130,041`) | `l2bt` | **`+4,915.9` (181.0, z=+27.2)** / **`+3,097.6` (140.2, z=+22.1)** | `+2,401.8` / `+2,514.1` (`2022+`: `+1,496.7` / `+1,600.9`) | `1.357s` | `$3.87` | **+2,153 elpd over `unified` (+1,252 on 2022+)**, but failed mixing (`max_rhat=7.81`, `min_ess=1`) |

### Stage 1 Prediction Audit & Root-Cause Diagnosis
- **What hit:**
  - `unified` on `latest`: **`+2,762.9`** all years (predicted `+1,500 to +3,200`) and **`+1,845.3`** on `2022+` (predicted `+900 to +2,100`), both halves A & B strongly positive.
  - 80% coverage by year on `latest` (`l2bt -> unified`): `2020: 74.4% -> 79.3%`, `2021: 72.6% -> 77.9%`, `2022: 76.0% -> 77.1%`, `2024: 81.6% -> 80.6%`, `2025: 82.1% -> 81.3%`, `2026: 82.6% -> 81.5%`.
  - Sweep speed: `1.176–1.210 s/sweep` (predicted `0.85–1.35 s/sweep`).
- **What surprised (honest misses):**
  - `unified-seg` over `unified` was **`+2,153` all years (`+1,252` on `2022+`)**, **4×–5× LARGER** than our `+200 to +550` (`+80 to +220` on `2022+`) prediction! Quarterly `(zone × bed)` segment paths are by far the single largest remaining signal in the entire NYC dataset.
  - `u1-mkt-p3` on `market` was `+176.8` (just below `+180` lower bound), and `no_hist & thin<5` coverage moved from `68.1% -> 70.6%` (less than predicted `76–82%`) because `mark:thin_first_ad` had slow mixing without collapsed phase updates.
- **Exact root causes of `u1s-lat-p3` failure (`max_rhat = 7.81`) and `u1` slow `phase_scale`:**
  1. **Sum-to-zero segment nullspace:** All 8 segment columns satisfy $\sum_{k=0}^7 x_{kj}(i) \equiv 0$, so adding a common shift $c_j$ across all 8 segments leaves $X\beta$ invariant (`+0.077` identical chain-0 vs chain-1 offset across all 8 segments at `2021q1`), causing `gp_amp`/`gp_ls` funnel sticking (`rhat = 2.3–5.0`). **Fix:** Drop `REF_SEGMENT = "manhattan:1br"` in `identifiable_segment_paths` (preserves exact zero share-weighted mean across all 8 segments while giving full rank 7).
  2. **`2024q1` nugget trade-off:** Including the `2024q1` knot gave prior sd `0.1 * amp` at `x=0`, letting segment paths shift vertically against `level:outer:*` and `bed>=*` (`rhat = 1.76–2.79`). **Fix:** Drop `REF_QUARTER = "2024q1"` so every segment path is identically 0 on `2024-01-01`.
  3. **Slow `phase_scale` mixing (ESS 71–79 in 900 draws):** Updating `phase_scale` only conditionally on `lam` mixes slowly with `row_dof=2`. **Fix:** Generalized `phase_collapsed=True` in `drift.py` to support binary `phase_map` via an exact zero-`exp` systematic-scan coordinate slice update with `lam` integrated out.

---

## Stage 2 Screening Pilots (Pre-Launch Predictions, Identifiability + `phase_collapsed` Fix)

Launching two 2-chain screening pilots (`2 400 1000 10 --seed 21`, ~$3.50 each):
- `u2s-lat-p`: `drift-building-phase-unitkn-unified-seg` on `latest` vs `l2bt`
- `u2s-mkt-p`: `drift-building-phase-unitkn-unified-seg` on `market` (`asof-20251110`) vs `range-j`

### Stage 2 Pre-Fit Predictions
1. **Convergence fix (`u2s-lat-p` & `u2s-mkt-p`, 2 chains × 1000 draws):**
   - `max_rhat` across all scalars, betas, `seg:*`, `level:*`, `gp_amp[*]`, `gp_ls[*]`, and `phase_scale` drops from `7.81` to **`≤ 1.05`** in 2 chains (projected **`≤ 1.01`** and **`min bulk ESS > 400`** in a 6-chain 3×2-container pooled run).
   - `phase_scale` min ESS jumps from `71–79` to **`> 200`** even in 2 chains × 1,000 draws.
   - Sweep time for 7-segment `unified-seg` + binary `phase_collapsed`: **`1.20 to 1.65 s/sweep`**.
2. **`u2s-lat-p` held-out Δelpd vs `l2bt`:**
   - Retains **`+4,400 to +5,200` all years** and **`+2,800 to +3,400` on `2022+`** (positive on both Half A and Half B, proving the `+2,153` segment gain over `unified` was real, NOT an artifact of the unidentifiable nullspace).
3. **`u2s-mkt-p` held-out Δelpd vs `range-j` (`asof-20251110`, `n=9,346`):**
   - **`+200 to +420` elpd** over `range-j` (beating `u1-mkt-p3`'s `+176.8` by `+30 to +220` elpd from segment trajectories into late 2025, positive on both Half A and Half B).

### Stage 2 Pilot Results (`u2s-lat-p`, Commit `3e971ad3`, `$3.45` settled; `$14.11` cumulative)
- **`u2s-lat-p` (`latest`, 2 chains × 350w + 900d, `1.188 s/sweep`, `$3.45`):**
  - Held-out Δelpd vs `l2bt` ALL YEARS (`n=189,647`): **`+4,889.0` (SE `181.4`, z=`+26.9`; A `+2,379.3`, B `+2,509.7`)**.
  - Held-out Δelpd vs `l2bt` `2022+` (`n=130,041`): **`+3,096.7` (SE `140.5`, z=`+22.0`; A `+1,472.8`, B `+1,623.9`)**.
  - **100% of the `+2,126` elpd segment gain over `unified` held** under full-rank identifiable segment paths!
  - **Convergence breakthrough:**
    - 6 of 7 segment GPs passed cleanly in just 2 chains × 900 draws (`R-hat = 1.0003–1.0050`, `ESS = 613–1,331`); `level:outer:1br/3br+` dropped from `R-hat = 2.8` to `0.9998–1.0004` (`ESS = 461–506`); zero-`exp` binary `phase_collapsed` sped up sweeps from `1.357` to **`1.188 s/sweep`** while nearly doubling `phase_scale` min ESS (`71 -> 135`, `max_rhat = 1.027`).
    - **Sole remaining failure:** `gp_amp/gp_ls[seg:manhattan:2br]` (`R-hat = 4.68`, `ESS = 1`) — chain 0 at `(amp=0.030, ls=0.41 yr)` vs chain 1 at `(amp=0.091, ls=2.28 yr)` (exact same squared-exponential RBF + `0.01`-nugget double well observed in `docs/notes/unitkn-segment-k10-2026-11-14.md` on `manhattan:3br+`).
  - **Zero-spend proof of fix:** Evaluating the exact marginalized 1D `logp(ls)` profile across `ls ∈ [0.1, 20.0]` yr on all 14 segment-chain posterior means from `u2s-lat-p` showed RBF (`nugget=0.01`) is bimodal on `manhattan:2br` and `manhattan:3br+`, whereas **Matérn-3/2 with `nugget = 1e-4`** is **strictly unimodal on 14/14 profiles** (all peaks in `0.44–1.13 yr`, right in the center of `SEG_LS=(0.0, 0.5)`) AND achieves **`+13.9` higher total marginal log-evidence** than RBF.
- (`u2s-mkt-p` exited locally at `$0.00` due to concurrent code-dir extraction race; stagger same-SHA launches by ≥10 s.)

---

## Stage 3 Full 6-Chain Gate Fits (Matérn-3/2 Segment Paths + Identifiability + `phase_collapsed`)

Launching TWO full 6-chain (3 containers × 2 chains, `2 500 9000 25`, `budget_seconds=2520`, `--seed 1/2/3`, pooled via `rentfrontier.drift_pool`) gate runs (~`$11.50` each, ~`$23` total → ~`$37` cumulative out of `$100`):
1. **Gate Fit 1 (`latest`, `u3s-lat` = pool of `u3s-lat-a/b/c`):** `drift-building-phase-unitkn-unified-seg` vs `l2bt`.
2. **Gate Fit 2 (`market` `asof-20251110`, `u3s-mkt` = pool of `u3s-mkt-a/b/c`):** `drift-building-phase-unitkn-unified-seg` vs `range-j`.

### Stage 3 Pre-Fit Predictions (Recorded Before Launch)
1. **Strict convergence gate (`R-hat ≤ 1.01`, `bulk ESS > 400` on ALL scalars, betas, `phase_scale`, `gp_amp[*]`, `gp_ls[*]`, and buildings):**
   - **Both `u3s-lat` and `u3s-mkt` PASS the strict gate** (all 7 Matérn-3/2 segment GPs unimodal with `ls ∈ [0.40, 1.30] yr`, `gp_amp/gp_ls` `R-hat ≤ 1.005`, `ESS > 1,500`; `unit_sd` and `phase_scale` `ESS > 450` across ~9,700–11,500 pooled draws). If any single slow scalar (`unit_sd` or `phase_scale`) lands in `300–400` ESS, adding 1 container (`--seed 4`, ~$3.90) lifts it cleanly past 400 without discarding the first 3.
2. **`u3s-lat` held-out Δelpd vs `l2bt` (`latest` split):**
   - All years (`n=189,647`): **`+4,700 to +5,250` elpd** (`z > +25`, both halves A and B `> +2,200`).
   - `2022+` (`n=130,041`): **`+2,950 to +3,400` elpd** (`z > +20`, both halves A and B `> +1,400`).
   - Annual 80% coverage across `2014–2026` within `77%–82%` (specifically `2020–2021` improved from `72.6%–74.4%` to `78%–80%`, `2024–2026` `80%–81.5%`).
3. **`u3s-mkt` held-out Δelpd vs `range-j` (`market` `asof-20251110`, `n=9,346`):**
   - **`+200 to +420` elpd** (`z > +5`, positive on both halves A and B), improving on `u1-mkt-p3` (`+176.8`) via segment trajectories into late 2025.
   - `no_unit_history` (`n=3,168`) and `no_hist & thin<5` (`n=727`) both positive in Δelpd with lower `>95%` tail rate than `range-j`.

### Stage 3 Intermediate Results & Market Boundary-Knot Discovery (Commit `90628dc7`)
- **Matérn-3/2 (`nugget=1e-4`) completely solved segment GP convergence:** Across ALL three completed H100 containers (`u3s-lat-a`, `u3s-lat-c`, `u3s-mkt-c`), every single one of the 9 GP hyperparameters passed even in 2 chains (`max_rhat = 1.0009–1.0058`, `min_ess = 1,321–1,815`; `gp_amp[seg:manhattan:2br]` went from `R-hat = 4.68, ESS = 1` to **`R-hat = 1.0021, ESS = 1,815`**!).
- **4-chain partial pool (`u3s-lat-a + u3s-lat-c`):** Already at `max_rhat = 1.0154 (sigma[0])`, `min_ess = 389 (unit_sd)` across all 2,580 parameters. Three containers (`u3s-lat-b`, `u3s-mkt-a/b`) hit Modal's 3,600s standard container timeout (`exit=124`) during post-sampling diagnostics/saving (~676s for 1,905 `phase_scale` cells). Relaunched `u3s-lat-b2` (`seed 2`, `--large --gpu H100`, 12h timeout, identical `sampler_settings`) to complete the pre-registered 3-container 6-chain `u3s-lat` pool (`a + b2 + c`).
- **Right-boundary knot discovery on `market` (`u3s-mkt-c` vs `u1-mkt-p3` vs `range-j`):**
  - `u3s-mkt-c` achieved lower RMSE (`0.1059` vs `0.1070` `u1-mkt-p3` vs `0.1086` `range-j`) and beat `range-j` by `+138.3` elpd (SE `42.5`, A `+93.3`, B `+45.0`), but trailed `u1-mkt-p3` (`+176.8`) by `-38.5` elpd.
  - **Root cause (confirmed against `u3s-lat-a`'s true 2026 knots):** `quarter_starts(d)` creates a future knot `2026q1` (52 days after `2025-11-10`) with almost no training weight; the zero-mean GP shrinks `2026q1` back toward 0 (`seg:manhattan:3br+:2026q1 = -0.0105` vs true `+0.0306`, `-4.1%` error; `seg:manhattan:2br:2026q1 = -0.0054` vs true `+0.0162`, `-2.2%` error), even though `2025q4` was accurate to within `±0.004`. Simultaneously, absorbing 2020–24 segment variance slightly tightened 2BR/3BR+ `sigma`, nudging `market` 80% coverage down to `76.3%`.
- **Stage 3b Market Gate Fit (`u3-mkt` = 3-container 6-chain pool of `u3-mkt-a/b/c`, `drift-building-phase-unitkn-unified`, commit `90628dc7`, `2 500 1600 25`, seeds `1, 2, 3`):**
  - Launched 3 containers in parallel on standard H100 (`~50 min`, `~$3.60` each, `9,600` pooled draws).
  - **Pre-fit predictions for `u3-mkt` (6 chains pooled):**
    1. Passes strict convergence gate (`max_rhat ≤ 1.01`, `min_ess > 400` across all scalars, betas, and `phase_scale`).
    2. Beats `range-j` by **`+160 to +240` elpd** (`z > +4.8`, both halves A & B positive) on `9,346` open ads (`asof-20251110`), with positive Δelpd on `has_unit_history`, `no_unit_history`, and `no_hist & thin<5` (`<5%` tail `4.5%–5.8%`).

### Stage 3c Final Gate Fit on `latest` (`u4s-lat` = 3-container 6-chain pool, `2 500 2600 40 --budget-seconds 4500`, `--large --gpu H200`)
- **Diagnosis of `u3s-lat` (`1,375` draws/chain × 6 chains = `8,250` draws):**
  - `min_ess = 588 (unit_sd)` **PASSED** (`> 400`), all 9 GP hyperparameters passed overwhelmingly (`gp_amp max_rhat = 1.0015, min_ess = 5,554`; `gp_ls max_rhat = 1.0020, min_ess = 4,187`), `bld_sd max_rhat = 1.0029, min_ess = 1,673`.
  - Missed `R-hat ≤ 1.01` by just `0.0023` (`max_rhat = 1.0123` on `phase_scale[86]`, `1.0117` on `sigma[0]`, `1.0109` on `beta[seg:outer:3br+:2015q3]`) solely because `budget_seconds = 2520` cut sampling at `1,375` draws/chain (half of `l2bt`'s `2,800` draws/chain), leaving ~125 effective samples per chain on `sigma`/`phase_scale` (all 6 chains stationary and agreeing to 4 significant digits: `sigma[0] = 0.01456 ± 0.00015`, `phase_scale[86] = 1.850 ± 0.021`).
- **Pre-registered fix & launch (`u4s-lat-a/b/c`, 3 containers × 2 chains, seeds `1, 2, 3`, `2 500 2600 40 --budget-seconds 4500` on `--large --gpu H200`, ~$24 total → ~$90 cumulative out of $100):**
  - Added `--budget-seconds` CLI override in `drift.run_parser` (defaulting to `Settings.budget_seconds = 2520.0`).
  - Matches `l2bt`'s draw count (`2,600` draws/chain × 6 chains = `15,600` draws, 1.89× longer per chain than `u3s-lat`).
  - **Pre-fit predictions for `u4s-lat`:**
    1. **PASSES strict convergence gate** with comfortable margin: `max_rhat ≤ 1.008` (projected `~1.005–1.006`), `min_ess > 900` (projected `~1,100` on `unit_sd`).
    2. Retains the exact held-out Δelpd of `u3s-lat` over `l2bt` within MC error (`~+4,900` all years, `~+3,100` on `2022+`, both halves A & B strongly positive).
