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

## 3. Wave 1 Results (`screen-k5`, Commit `3f7e35d0`)

All 12 `A100-40GB` screening runs completed cleanly (`$7.14` across 12 runs, plus `$0.44` from an initial fast-fail missing `--input rows-b3ddebf19af1dc1e.parquet` = `$7.58` Wave 1 total). `b4-anchor` reproduced `w2-c1-compact` cleanly (`sub ΔELPD = +7.2 ± 5.2`, `z = +1.38`, `proj +37 ± 26`, `1.00×` sweep, `80%` cov `79.89% -> 79.87%`).

| Rank | Label | Single Change on `C1` | Pre-Fit Range | Realized Full ΔELPD ± SE (`×5.10`) | `z` (`2022+ z`) | Half A / B (sub) | Params (Δ) | `s/sweep` (rel) | `max R-hat` / `min ESS` | Cost | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | `b4-anchor` | `C1` (same-commit anchor) | `0` (`±40` vs `w2`) | `+37 ± 26` (vs `w2`) | `+1.38` (`+0.86`) | `-0.2 / +7.4` | `429 (+0)` | `0.651` (`1.00×`) | `1.085` / `24.0` | `$0.54` | Anchor OK |
| **1** | **`b4-bld-mo`** | **`+bld_monthly` (`12/yr`)** | `+250` to `+800` | **`+1,799 ± 318`** | **`+5.66`** (**`+2.84`**) | **`+158.9 / +194.0`** | **`429 (+0)`** | `1.230` (`0.53×`) | `1.160`* / `14.0` | `$0.79` | **BIG WIN (Wave 2)** |
| **2** | **`b4-bld-bimo`** | **`+bld_bimonthly` (`6/yr`)** | `+150` to `+450` | **`+854 ± 270`** | **`+3.17`** (`+1.47`) | **`+100.1 / +67.5`** | **`429 (+0)`** | **`0.724` (`0.90×`)** | **`1.085` / `26.7`** | `$0.63` | **GO (Pareto)** |
| **3** | **`b4-attr-chg`** | **`+attr_changes` (`1/2/3+`)** | `+30` to `+160` | **`+216 ± 56`** | **`+3.86`** (**`+3.82`**) | **`+23.0 / +19.5`** | `432 (+3)` | **`0.672` (`0.97×`)** | **`1.089` / `29.4`** | `$0.54` | **GO** |
| **4** | **`b4-u1-size`** | **`+u1_size_scale` (`>1k sqft`)** | `+40` to `+130` | **`+64 ± 74`** | `+0.87` (`+1.40`) | `+11.8 / +0.8` | `430 (+1)` | **`0.662` (`0.98×`)** | **`1.089` / `42.8`** | `$0.57` | **ESCALATE (Wave 2 mkt)** |
| 5 | `b4-changed-bed` | `+mark_changed_bed` | `+120` to `+240` | `-5 ± 47` | `-0.11` (`-0.09`) | `+6.0 / -7.1` | `430 (+1)` | `0.676` (`0.96×`) | `1.106` / `18.2` | `$0.60` | **KILL** |
| 6 | `b4-floor-unk` | `+mark_floor_unk` | `+100` to `+220` | `-8 ± 37` | `-0.20` (`+0.71`) | `-1.5 / +0.0` | `430 (+1)` | `0.672` (`0.97×`) | `1.101` / `7.9` | `$0.60` | **KILL** |
| 7 | `b4-sparse-ph` | `+mark_sparse_photos` | `+15` to `+75` | `-8 ± 67` | `-0.12` (`+0.51`) | `-11.3 / +9.7` | `430 (+1)` | `0.697` (`0.93×`) | `1.085` / `13.1` | `$0.56` | **KILL (`latest`)** |
| 8 | `b4-tenure` | `+mark_tenure` (`bld:coop` + scales) | `+110` to `+230` | `-20 ± 101` | `-0.20` (`+0.01`) | `-8.9 / +5.0` | `432 (+3)` | `0.675` (`0.96×`) | `1.136` / `18.5` | `$0.62` | **KILL (`latest`)** |
| 9 | `b4-floor1-mean` | `+floor1_mean` (`unit:floor_1`) | `+40` to `+110` | `-42 ± 30` | `-1.41` (`-0.51`) | `-2.9 / -5.3` | `430 (+1)` | `0.650` (`1.00×`) | `1.110` / `15.3` | `$0.60` | **KILL** |
| 10 | `b4-dof8` | `--level-dof 8` (`t(8)` vs `t(4)`) | `+20` to `+120` | `-57 ± 33` | `-1.76` (`-0.83`) | `+0.3 / -11.6` | `429 (+0)` | `0.619` (`1.05×`) | `1.125` / `13.7` | `$0.56` | **KILL** |
| 11 | `b4-townhouse` | `+mark_townhouse` (`small_lot_le4`) | `+55` to `+140` | `-138 ± 63` | `-2.19` (`-1.41`) | `-26.2 / -0.8` | `431 (+2)` | `0.652` (`1.00×`) | `1.211` / `4.3` | `$0.53` | **KILL** |

*\*`b4-bld-mo`'s `1.160` R-hat was on `beta[seg:zone:outer:2017q2]` (the usual short-screen segment GP knot), NOT on building AR(1) scales. Direct paired comparison `b4-bld-mo` vs `b4-bld-bimo`: **`+185.4 ± 43.9` (`z = +4.22`, projected `+945 ± 224` full ΔELPD, `2022+ z = +2.14`)**!*

### Key Scientific Takeaways & Honest Prediction Scorecard
1. **Building AR(1) temporal resolution blew past our pre-fit range (`+854` bimonthly, `+1,799` monthly vs predicted `+150–450` / `+250–800`) at MUCH lower speed penalty than expected!**
   - `bld_bimonthly` (`6/yr`) adds `+854 ± 270` (`z = +3.17`, `0` extra params) for only **`+10%` sweep time** (`0.90×`, `max R-hat = 1.085`, `min ESS = 26.7`).
   - `bld_monthly` (`12/yr`) adds **`+1,799 ± 318`** (`z = +5.66`, `2022+ z = +2.84`, half A `+159` / half B `+194`, `0` extra params) for **`1.89×` sweep time** (`1.48×` wall time, `$0.79` vs `$0.54`). In the old Nov 10 model `bld_monthly` could not fit the hour; on `c1-compact` it runs comfortably and is the single largest model-structure improvement available.
2. **Within-unit `attr_changes` (`1 / 2 / 3+` changed binary attributes since prior training ad) was a clean `GO` (`+216 ± 56`, `z = +3.86`, `2022+ z = +3.82`, half A `+23.0` / half B `+19.5`):**
   - Learned strictly monotone noise multipliers: `1.128×` (1 changed), `1.177×` (2 changed), `1.277×` (3+ changed) — zero speed hit (`0.97×`), better `unit_sd` ESS (`29.4` vs `24.0`), and exact `80.03%` 80% coverage!
3. **Why 5 Half-B marginal noise-scale candidates (`changed_bed`, `floor_unk`, `tenure`, `townhouse`, `sparse_ph`) failed in joint `latest` refits — a crucial hierarchical-model lesson:**
   - **Unit-vs-observation variance confounding:** On `latest` (100% repeat-ad units), static building/unit-level traits (`mark:condo`, `mark:coop`, `mark:small_lot_le4`) mostly drive **unit-level** dispersion (`unit_sd`) rather than within-unit listing-to-listing volatility. Putting them into the observation-level noise scale trades off against `unit_sd` (spiking `unit_sd` R-hat to `1.136` and `1.211`) and yields zero or negative `latest` ELPD. In contrast, **within-unit change features** (`attr_changes`) vary across ads of the same unit and cleanly improve `latest` ELPD AND `unit_sd` ESS!
   - **`floor1_mean` sign cancellation (`+0.0045` instead of `-0.014`):** `floor_1_flag` combines elevator floor 1 (a ground-floor penalty) with walkup floor 1 (the *premium* ground floor with no stairs!). Pooling them into one mean column canceled opposite signs (`-42 ± 30`, KILL). Fixing elevator floor 1 properly requires an elevator-only indicator (`unit:elev_floor_1`), deferred to a future micro-test.
   - **`--level-dof 8` (`-57 ± 33`, `z = -1.76`, KILL):** The heavy-tailed `t(4)` building-level prior decisively beats `t(8)` across NYC's heterogeneous building stock.
   - **`u1_size_scale` (`+64 ± 74`, `2022+ z = +1.40`, `min ESS = 42.8`, `<5%` tail `5.80% -> 5.69%`, factor `2.255×` per log-unit above 1,000 sqft):** Promising small gain on `latest` with the best `<5%` tail and ESS of all 11 arms, and directly targets open-market `size 1500+` (`64.4%` 80% coverage in Track A1). Advanced to Wave 2!

---

## 4. Wave 2 Pre-Fit Quantitative Predictions (Committed BEFORE Launch)

Wave 2 runs **6 parallel `A100-40GB` screens (`~$3.60`)**: 2 combined stacks on `screen-k5` (`latest`, `--input rows-b3ddebf19af1dc1e.parquet`) and 4 paired open-market backtest arms on `screen-mkt-k5` (`asof-20251110`, `n = 1,891` open ads, `--input rows-ddd2fe8f5da041b8.parquet`) to verify whether our Wave 1 winners (`attr_changes`, `u1_size_scale`, `bld_bimonthly`, `bld_monthly`) add cleanly on `latest` AND carry directly onto open-market `/deals` predictions (including `size 1500+` 80% coverage and MAE)!

| Arm | Dataset | Label | Variant on `C1` | Pre-Fit Projected ΔELPD | Falsification / Promotion Criterion |
|---|---|---|---|---|---|
| 1 | `screen-k5` | `b4-c2-bimo` | `C1 + attr_changes,u1_size_scale,bld_bimonthly` | **`+900` to `+1,400`** full (vs `b4-anchor`; additive sum `+1,134`) | Promote fast-Pareto candidate if `Δ > +750`, `z > 3.0`, sweep `>= 0.85×` |
| 2 | `screen-k5` | `b4-c2-mo` | `C1 + attr_changes,u1_size_scale,bld_monthly` | **`+1,700` to `+2,400`** full (vs `b4-anchor`; additive sum `+2,079`) | Promote ceiling candidate if `Δ > b4-c2-bimo + 500` and wall time `< 1.6×` |
| 3 | `screen-mkt-k5` | `b4-m-anchor` | `C1` (same-commit market anchor) | `0` (vs `w2-m-c1-compact`: `±15` raw open-mkt ELPD) | Sanity check vs `w2-m-c1-compact` |
| 4 | `screen-mkt-k5` | `b4-m-attr-u1` | `C1 + attr_changes,u1_size_scale` | **`+10` to `+35` raw** (`+50` to `+175` scaled `×5.01`); `size 1500+` cov80 **`+4` to `+10 pp`** | Confirm `u1_size_scale` lifts large-unit market coverage without hurting MAE |
| 5 | `screen-mkt-k5` | `b4-m-c2-bimo` | `C1 + attr_changes,u1_size_scale,bld_bimonthly` | **`+15` to `+50` raw** (`+75` to `+250` scaled `×5.01`); MAE improves `-0.0002` to `-0.0008` | Confirm bimonthly building path helps live `/deals` open market |
| 6 | `screen-mkt-k5` | `b4-m-c2-mo` | `C1 + attr_changes,u1_size_scale,bld_monthly` | **`+25` to `+75` raw** (`+125` to `+375` scaled `×5.01`); MAE improves `-0.0004` to `-0.0012` | Confirm monthly building path wins on BOTH `latest` AND open market! |

---

## 5. Wave 2 Results

*(To be populated after Wave 2 finishes and is scored.)*

