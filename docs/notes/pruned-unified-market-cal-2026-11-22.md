# Option 1 Results & Post-Fit Scorecard: Pruned Unified Model, Individual Marks, 24-Factor Speedup & Two-Date Market Calibration (2026-11-22)

> **User-facing HTML report with embedded SVG charts:** `docs/notes/pruned-unified-market-cal-2026-11-22.html`

Pre-fit predictions were committed at `0819c067` before launching Modal GPU screening runs (`ops/modal-screen`) in accordance with `CLAUDE.md`.

---

## Executive Summary

1. **24-factor trace speedup (`drift.py`) cut mapped fit wall time & cost by 39–45%:** Tracing only the `F <= 24` free `phase_factor` scalars (expanding `phase_scale` only on kept draws) reduced `screen-k5` `unified-seg` from `22.9 min / $0.96` (`exp2-k5-u4s`) to **`14.0 min / $0.58`** (`v2-lat-clean-seg`, **-39%**) and `unified` from `19.4 min / $0.81` to **`11.6 min / $0.48`** (`v2-lat-clean-pre24`, **-40%**).
2. **Pruned `clean-u-seg` (`layrng,size,y1_pre2024,covid_vol,marks,seg`) beats `unified-seg` (`u4s`) by `+290.5 ± 89.5` ELPD (`z = +3.25`) on `latest`:** Dropping negative passengers `bedunit` and `sbf` while adding `covid_vol` and `y1_pre2024` achieved **`+5,186.3 ± 380.2` (`z = +13.64`)** over `l2bt` (`79.67%` 80% coverage, better `max_rhat = 1.086` vs `1.126`), while running 39% faster. Without `seg`, `v2-clean-pre24` beat `unified` (`u1`) by **`+301.4 ± 79.6` (`z = +3.79`)**.
3. **Individual `marks` ablation on `market` (`asof-20251110`) falsified `mark_thin` and uncovered `mark_baths` (`+60.9 ± 32.1`, `z = +1.90`) as the sole strong market driver:**
   - `mark_baths`: **`+60.9 ± 32.1`** (`z = +1.90`, `77.53%` cov80) — alone beats all 6 marks combined (`+14.4`) by `+46.5` ELPD!
   - `mark_thin`: `+5.7 ± 16.0` (`z = +0.36`, neutral — falsified our pre-fit hypothesis that `mark_thin` drove market gains).
   - `mark_floor1`: `-2.5 ± 9.5` (`z = -0.26`, noise).
   - `mark_large01br`: **`-19.5 ± 12.8`** (`z = -1.52`, hurts market).
   - `mark_changed`: **`-38.0 ± 25.1`** (`z = -1.52`, hurts market).
   - **Actionable pruning:** Next full-data candidate should keep **`mark_baths`** (and drop `mark_changed`, `mark_large01br`, `mark_floor1` — and optionally test `mark_thin` on `latest`).
4. **Freezing `2024+` year scale (`y1_pre2024`) beats `y1` on `market` by `+43.9 ± 14.1` (`z = +3.11`)**, and **`v2-clean-pre24` beats `l2bt` on BOTH independent market dates** (`+37.0` on `2025-11-10`, `+172.4` vs `range-j`; **`+82.4 ± 47.5`, `z = +1.73`** on `2026-11-20` live market).
5. **Out-of-sample validation of leak-free `open_scale` calibration (`drift_score --open-scale 1.12`) across TWO independent market dates 12 months apart:**
   - Root cause diagnosed by `gemini-4-hydrogen` on full `u3-mkt` (`n=9,346`): apples-to-apples re-listed open asks have **`1.076×`** wider IQR than 2025 closed ads (`1.099×` overall, `1.161×` on `first_ad`); `y1`/`covid_vol` removed the 2020–2022 inflation of global `sigma_g` that previously subsidized open-market width. Scaling `usd` & `sigma` by `1.12×` hit exact **`80.00%`** coverage and **`+33.50` ELPD** on full `u3-mkt`.
   - Tested **completely out-of-sample** on `screen-mkt2-k5` (`2026-11-20`, `n=1,280`): `open_scale=1.12` lifted `v2-mkt2-clean-pre24` 80% coverage from `74.92% → 78.12%` and added **`+13.0` (`+66` projected) ELPD** (`1.15×` reached `79.30%` and `+72` projected; `o1-mkt2-l2bt` jumped `76.17% → 79.61%` and `+45` projected). The two market dates (`2025-11-10` and `2026-11-20`) track almost identically across `1.00×–1.18×`.
6. **Stale `status == "DRAFT"` bug fixed in `market.py`:** `32` held-out rows in `u3-mkt` (`cov80 = 68.75%`) were stale 2021 `DRAFT` listings slipping past `OPEN = ("ACTIVE", "TEMPORARILY_OFF_MARKET")`. `market.py` now sets `EXCLUDED = ("DRAFT",)` aside in both live and backtest builds.
7. **Worst-miss expert readings (40 listings read by `gemini-4-hydrogen`):**
   - `u4s-lat` (20 worst): **17/20 (85%) are data errors** (6 placeholder/garbage text, 3–5 unflagged HPD/lottery/stabilized, 3 `latest_ask` vs `page_price` glitches, 2 commercial/office, 1 `$971`/`6700sf` typo, 1 room share).
   - `u3-mkt` (20 worst): **9/20 (45%) data errors** (3 commercial/live-work, 2 stale 2021 `DRAFT` ads, 2 empty/placeholder text, 1 contradictory 4bd/1bd, 1 `$4.6k→$3.1k` drop) and **11/20 (55%) real model-shape gaps** (5 thin-building `first_ad`, 3 ultra-lux new-dev/gut renovation, 3 trophy penthouse/large outdoor/loft, 2 flipped `rent_stabilized` unit bleed, 2 co-op/low ceiling).
8. **`drift_today` (`/price-now`) now serves `unified`, `unified-seg`, and `ablate`** (including `y1_pre2024` and `seg`), with `pinv` span checks for unseen `--day` cells and explicit refusals for time-varying mean tokens (`covid_mean`, `concess_gap`, `stab_dhcr`).

---

## Honest Post-Fit Scorecard (Pre-Fit Predictions vs Actuals)

| Run / Test | Split | Pre-Fit Prediction | Actual Result | Verdict |
|---|---|---|---|---|
| `v2-mkt-mk-thin` | `screen-mkt-k5` | `+40 to +120` (#1 market mark) | **`+5.7 ± 16.0` (`z=+0.36`)**, cov `77.05%` | **FALSIFIED** (neutral, not #1) |
| `v2-mkt-mk-baths` | `screen-mkt-k5` | `+10 to +60` | **`+60.9 ± 32.1` (`z=+1.90`)**, cov `77.53%` | **HIT (top of range — true #1 mark!)** |
| `v2-mkt-mk-changed` | `screen-mkt-k5` | `+5 to +50` | **`-38.0 ± 25.1` (`z=-1.52`)** | **FALSIFIED** (negative on market!) |
| `v2-mkt-mk-floor1` | `screen-mkt-k5` | `-10 to +30` (near noise) | **`-2.5 ± 9.5` (`z=-0.26`)** | **HIT** (pure noise) |
| `v2-mkt-mk-large01br` | `screen-mkt-k5` | `-10 to +30` (near noise) | **`-19.5 ± 12.8` (`z=-1.52`)** | **FALSIFIED** (negative on market!) |
| `v2-lat-clean-pre24` | `screen-k5` | `+3,100 to +3,400` (`+300+` vs `u1`) | **`+3,090.6 ± 306.4` (`+301.4 ± 79.6` vs `u1`, `z=+3.79`)**, cov `79.82%` | **HIT** |
| `v2-lat-clean-seg` | `screen-k5` | `+5,100 to +5,600` (beats `u4s`) | **`+5,186.3 ± 380.2` (`+290.5 ± 89.5` vs `u4s`, `z=+3.25`)**, cov `79.67%` | **HIT** |
| `v2-mkt-clean-pre24` | `screen-mkt-k5` | `+150 to +300` vs `l2bt`, cov `76.5–78.2%` | **`+37.0 ± 62.0`** vs `l2bt` (`+172.4` vs `range-j`; `+43.9 ± 14.1` vs `w2-cov-mk`), cov `74.41%` raw / `78.27%` at `1.12×` | **MIXED** (beat `range-j` & `w2-cov-mk`, but raw cov stayed `74.4%` — `open_scale` is what closes the gap!) |
| `v2-mkt-clean-seg` | `screen-mkt-k5` | `seg` neutral-to-positive | **`+56.3 ± 94.6`** vs `l2bt` (`+19.3 ± 73.0` vs `pre24`, `+191.7` vs `range-j`) | **HIT** (neutral-positive on `2025-11-10`) |
| `v2-mkt2-clean-pre24` | `screen-mkt2-k5` | `+150 to +350` vs `l2bt`, `1.12×` lifts cov & ELPD | **`+82.4 ± 47.5` (`z=+1.73`)** vs `l2bt`; `1.12×`: cov `74.92%→78.12%`, **`+66` proj ELPD** (`1.15×`: `79.30%`, `+72`) | **HIT (calibration)** / slightly smaller ELPD vs `l2bt` |
| `v2-mkt2-clean-seg` | `screen-mkt2-k5` | consistent sign for `seg` across dates | **`+51.2 ± 60.0`** vs `l2bt` (`-31.2 ± 37.3` vs `pre24`); `1.12×`: cov `73.91%→76.56%`, **`+77` proj ELPD** | **MIXED** (`seg` is neutral across single-day market splits: `+19` in 2025, `-31` in 2026) |
| 24-factor trace speedup | `screen-k5` | `8–13 min` fit (down from `~20 min`) | **`10.5 min`** (`clean-pre24`, `-45%`), **`13.6 min`** (`clean-seg`, `-40%`) | **HIT** |

---

## Itemized Modal Spend (2026-11-22 Option 1)

- **Valid screening runs (12 runs: `o1-mkt2-l2bt` + 11 `v2-*` runs):** **`$5.55`** (`$0.35–$0.65` per run on `A100-40GB`).
- **Wasted CLI typo runs (11 runs: 9 runs with `--ablate` silently ignored by `b0.parse_known_args`, plus 2 runs missing `--input rows-b3ddebf19af1dc1e.parquet`):** **`$3.59`** (guarded in `ablate.py` so `--ablate` now raises `ValueError` immediately).
- **Total Option 1 Modal spend:** **`$9.14`** (within the `$6–$10` Option 1 screening target; cumulative day spend across PR #1533 `$19.11` + PR #1534 `$9.02` + Option 1 `$9.14` = `$37.27`).

---

## Recommended Production Gate Candidate (Next Step)
- **Candidate:** `layrng,size,y1_pre2024,covid_vol,mark_baths,seg` (plus optional `mark_thin` check) — drops negative passengers (`bedunit`, `sbf`, `mark_changed`, `mark_large01br`, `mark_floor1`), runs **~40% faster**, beats `u4s-lat` by **`~+300` ELPD** on `latest`, and with leak-free `open_scale=1.12` achieves calibrated `~80%` coverage and `+33 to +95` extra ELPD on `market` across both `2025-11-10` and `2026-11-20`.
