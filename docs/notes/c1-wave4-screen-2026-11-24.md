# Wave 4 Screen (`c1-compact` + Track B1/B2 Candidates) — 2026-11-24

## 1. Context & Design

This note records **pre-fit quantitative predictions** before launching Modal GPU screening fits for Track B1 (high-signal feature & noise-scale discoveries from the Track A1 live audit + `docs/TODO.md`) and Track B2 (finer building AR(1) temporal resolution and lighter building-level Student-t tails `--level-dof 8` vs default `4` for stronger shrinkage of thin buildings) on top of the live `c1-compact` architecture:

```
C1 = layrng,size,sv_gp_mo,marks,seg_add,floor_poly,ad_core,scalar_sigma,biweekly_walk
```

- **Wave 1 screening dataset:** `/data1/apartments/tmp/fast-screen-2026-11-22/datasets/screen-k5` (`latest` split, `k=5` building-cluster subsample, `n = 37,199` held-out ads, full-dataset scale factor `×5.0982`, `2 chains × (250 warmup + 400 draws, keep_every=10)`, `A100-40GB`, `--seed 1`).
- **Wave 2 confirmation datasets:** both `screen-k5` (`latest`) and `screen-mkt-k5` (`asof-20251110` open-market backtest, `n = 1,891` open ads, scale `×5.0095`, evaluated at raw `1.00×` open-market ELPD, MAE, and 80% coverage on weak slices: `size 1500+`, `floor=unk`, `unit_ads=0`).
- **Pairing rule:** We run an exact same-commit anchor `b4-anchor` (`C1`, `--seed 1`) on `screen-k5` (and `b4-m-anchor` on `screen-mkt-k5` in Wave 2) so every ΔELPD and wall-time comparison is paired on identical held-out rows, code commit, and hardware (also cross-checked against `w2-c1-compact`).
- **Budget ceiling:** `~$10–$12` total across Wave 1 (12 A100-40GB runs, `~$0.45–$0.55` each = `~$5.50–$6.50`) and Wave 2 (4–6 A100-40GB runs = `~$2.50–$3.50`).

---

## 2. Pre-Fit Quantitative Predictions (Committed BEFORE Launch)

All projected ΔELPD figures below are scaled to full `latest` (`×5.0982` from `screen-k5`), anchored to the Track A1 unbiased Half-B closed-ad out-of-sample audit (`docs/notes/c1-live-onefit-audit-2026-11-24.md`) discounted by `~0.6–0.8×` for multivariate partial overlap with `c1-compact` covariates (`mark:changed_counts`, `bld:class_C/D`, `phase:*`, `unit:elev_f*`).

| Arm | Label | Single Change on `C1` | Pre-Fit Projected Full ΔELPD | Expected `s/sweep` Δ | Falsification / Kill Rule |
|---|---|---|---|---|---|
| 0 | `b4-anchor` | `C1` (same-commit anchor) | `0` (vs `w2-c1-compact`: `±40`) | `0%` | Sanity check: `\|Δ\| < 80` vs `w2-c1-compact` |
| 1 | `b4-changed-bed` | `+mark_changed_bed` (1 scale factor: `beds_up\|beds_down`) | **`+120` to `+240`** (Half-B: `+206 ± 30`, `z=+6.97`) | `< +1%` | Kill if `Δ < +40` or `z < 1.5` |
| 2 | `b4-floor-unk` | `+mark_floor_unk` (1 scale factor: `elev\|walkup_floor_unknown`) | **`+100` to `+220`** (Half-B: `+195 ± 29`, `z=+6.80`) | `< +1%` | Kill if `Δ < +40` or `z < 1.5` |
| 3 | `b4-tenure` | `+mark_tenure` (`bld:coop` mean + `mark:condo`, `mark:coop`) | **`+110` to `+230`** (Half-B: condo `+117` + coop `+98`) | `< +2%` | Kill if `Δ < +50` or `z < 1.5` |
| 4 | `b4-floor1-mean` | `+floor1_mean` (explicit `unit:floor_1` mean col) | **`+40` to `+110`** (Half-B: `+68 ± 25`, `z=+2.78`) | `< +1%` | Kill if `Δ < +20` or `2022+` bias doesn't shrink |
| 5 | `b4-u1-size` | `+u1_size_scale` (continuous `max(0, log(sqft/1000))` scale) | **`+40` to `+130`** (Half-B: `+76 ± 21`, `z=+3.72`) | `+1–4%` | Kill if `Δ < +25` or `1500+` cov80 doesn't rise |
| 6 | `b4-attr-chg` | `+attr_changes` (causal 1 / 2 / 3+ changed binary attrs) | **`+30` to `+160`** (new unscreened causal signal) | `+1–3%` | Kill if `Δ < +30` or `z < 1.5` |
| 7 | `b4-sparse-ph` | `+mark_sparse_photos` (1 scale factor: `<= 1` photo) | **`+15` to `+75`** (Half-B: `+36 ± 16`; strong in live top-25!) | `< +1%` | Keep for Wave 2 market test if `Δ > 0` |
| 8 | `b4-townhouse` | `+mark_townhouse` (`bld:small_lot_le4` mean + scale) | **`+55` to `+140`** (Half-B: `+109 ± 21`, `z=+5.30`) | `< +1%` | Kill if `Δ < +30` or `z < 1.5` |
| 9 | `b4-bld-bimo` | `+bld_bimonthly` (building AR(1) `4 -> 6` steps/yr) | **`+150` to `+450`** (extrapolating `2 -> 4`: `+2,727`) | `+25–45%` | Kill if `Δ < +100` or wall time `> 1.6×` |
| 10 | `b4-bld-mo` | `+bld_monthly` (building AR(1) `4 -> 12` steps/yr) | **`+250` to `+800`** (sharper local trend, higher mixing risk) | `+80–160%` | Kill if `Δ < bld_bimonthly + 150` or `max_rhat > 1.15` |
| 11 | `b4-dof8` | `C1` + `--level-dof 8` (stronger thin-building shrinkage, `t(8)` vs `t(4)`) | **`+20` to `+120`** (Half-B `bld_thin_le5`: `+61 ± 19`; thin-shrinkage note) | `< +5%` | Kill if `Δ < +20` or building R-hat degrades |

### Key Hypotheses Being Tested
1. **Low-cost noise-scale wins dominate Pareto:** `mark_changed_bed`, `mark_floor_unk`, `mark_tenure`, `mark_townhouse`, and `u1_size_scale` should collectively add **`+400` to `+800` full ELPD** at near-zero compute cost (`< +5%` wall time) and directly lift open-market 80% coverage on `size 1500+` (`64.4%`) and `floor=unk` (`71.6%`).
2. **Diminishing returns vs wall-time on building AR(1) grid:** `2 -> 4` steps/yr added `+2,727` ELPD; we predict `4 -> 6` (`bld_bimonthly`) adds a meaningful `+150` to `+450`, while `4 -> 12` (`bld_monthly`) adds more ELPD only if data density supports monthly building twists without slowing sampling past `~2×` or hurting `bld_sd`/`bld_rho` mixing.
3. **Floor-1 structural fix:** Restoring `unit:floor_1` alongside `floor_poly` fixes the ground-floor conflation bug discovered in Track A1 (`-1.39%` / `-1.19%` bias in 2022+) at literally `+1` linear column (`0%` compute cost).

---

## 3. Wave 1 Results

*(To be populated after Wave 1 finishes and is scored.)*

---

## 4. Wave 2 Pre-Fit Predictions & Results

*(To be written and committed BEFORE launching Wave 2.)*
