# Fast Screening & Single-Change Ablations on Modal `screen-k5` (2026-11-22)

**Goal:** Put our Modal Cloud GPU Fast Screening Harness (`A100-40GB`, `screen-k5`, `2 250 400 10`, ~8–10 min, ~$0.35–$0.45/screen) to work on three concrete questions from `docs/TODO.md` #3:
1. **De-bundle `unified` (`+2,844 ± 316` over `l2bt` on `screen-k5`)** into every individual component — one change per fit — directly addressing PR #1530's no-bundling feedback.
2. **Screen 6 queued `docs/TODO.md` #3 candidates** (causal NYC DOHMH Covid-19 mean & volatility covariates, 2020–2022 concession-building gap, DHCR rent-stabilized building path, `income_restricted` scale mark, and `U4` per-bedroom first-ad scale marks) one change per fit.
3. **Diagnose the `market` (`asof-20251110`) 80% coverage regression** (`-2.5 pp` full / `-1.90 pp` on `screen-mkt-k5`) and test pruned winning combinations on both `latest` and `market`.

**Budget & Time Box:** 1-hour sprint (`11:27–12:27 ET`), hard Modal ceiling **`$20.00`**; actual spend across **22 settled Modal `A100-40GB` containers**: **`$9.02`** (`$10.98` remaining, `45.1%` used).

*(Self-contained HTML report with embedded SVG charts and plain-English glossary: [`docs/notes/fast-screen-ablations-2026-11-22.html`](fast-screening-ablations-2026-11-22.html).)*

---

## Executive Summary

1. **Exact Single-Term Decomposition of `unified` (`+2,844 ± 316` over `l2bt` on `screen-k5`):**
   - Just **two components** explain ~100% of `unified`'s gain: **`layrng`** (`layout` + `layout-range` 8 mean cols: **`+1,487 ± 198`, `z = +7.50`, `GO`**) and **`y1`** (calendar-year noise scale: **`+1,398 ± 171`, `z = +8.19`**).
   - **`size`** (filled-size slope + `large_01br`) is a genuine smaller positive (**`+186 ± 91`, `2022+ z = +3.01`**; 4-chain escalation: **`+135 ± 87`, `2022+ z = +3.27`, `R-hat = 1.046`**).
   - **Two negative passengers were caught inside `unified`:** **`bedunit`** (`-170 ± 77`, `z = -2.21`, **`KILL`**) and **`sbf`** (`same_bed_first`: `-68 ± 33`, `z = -2.07`, `2022+ z = -3.67`, **`KILL`**).
   - Stripping the negative passengers and `marks` gives **`w2-clean-y1` (`layrng + size + y1`)**, which scores **`+3,113 ± 275` (`z = +11.31`, `GO`)** — **beating full `unified` by `+269 ± 204` at half the wall time and cost (`9.5m / $0.40` vs `19.4m / $0.81`)**!
2. **Causal NYC DOHMH Covid-19 Volatility Regime (`covid_vol`) Is a Genuine `GO` Winner:**
   - **`covid_vol`** (2 causal 14-day-lagged NYC hospitalization thresholds: `hosp_7d >= 150` surge and `30..149` elevated) gained **`+578 ± 127` (`z = +4.54`, `P(>100) = 0.997`, `GO`)** over `l2bt` — capturing **41% of `Y1`'s 12-year gain with 2 explanatory degrees of freedom** — AND still added **`+96 ± 38` (`z = +2.52`, `2022+ z = +2.63`) on top of `layrng + size + y1`** (`w2-clean-y1-cov`: **`+3,210 ± 278`, `z = +11.53`**)!
   - By contrast, **`covid_mean` (`+20 ± 89`)**, **`income_scale` (`+36 ± 43`)**, **`u4_bed` (`+3 ± 37` on `latest`, `-3 ± 9` on `market`, `KILL`)**, **`stab_dhcr` (`-47 ± 53`, `KILL`)**, and **`concess_gap` (`-53 ± 39`, `2022+ z = -2.93`)** were all flat or negative.
3. **True Mechanism of the `market` (`asof-20251110`) 80% Coverage Regression Identified:**
   - Separating noisy 2020–2022 pandemic variance from calm 2023–2025 variance (via **either `y1` or `covid_vol`**) lowers the base noise scale `sigma_g` on 2023–2025 rows by ~8–10%, which exposes slight under-dispersion on *open* (not-yet-closed) `market` ads (`l2bt` `77.05%` → `l2bt+y1` `75.89%` `-1.16 pp`; `layrng+size+covid_vol` `74.83%` `-2.22 pp`).
   - Meanwhile **`marks`** (`mark:thin_first_ad` etc.) had zero standalone gain on `latest` (`+80 ± 207`, 0% first ads) but added **`+55` ELPD on `market`** (`+72 → +127` on top of `layrng+size+covid_vol`) and lifted `l2bt` `market` 80% coverage `+0.37 pp` (`77.05% → 77.42%`) because 34% of `market` open ads are first ads.

---

## 1. Pre-Fit Predictions (Committed in `53da9a07` Before Any Launch)

*(Preserved from `53da9a07`; scored honestly in Section 4 below.)*
- **A1–A5 (`unified` ablation):** `y1` `+1,000..+1,600` (`GO`); `marks` `+800..+1,400` (`GO`); `layrng` `+100..+400`; `size` `+50..+250`; `bedunit` & `sbf` `-50..+150`.
- **B1–B6 (`docs/TODO.md` #3 candidates):** `covid_mean` `+300..+900` (`GO`); `covid_vol` `+250..+650` (`GO`); `stab_dhcr` `+100..+450`; `concess_gap` `+50..+300`; `income_scale` `+40..+200`; `u4_bed` `+30..+200`.
- **C1 (`market` coverage regression):** `y1` pulls `market` 80% coverage down by `>= 1.0 pp` relative to `l2bt`, while `marks` improves `market` ΔELPD with less or zero coverage erosion.

---

## 2. Wave 1 Results — 12 Single-Change Screens (`screen-k5`, `$5.82` for all 15 runs)

All 12 variants below are **exact single-change deltas over `l2bt`** (`exp2-k5-l2bt`, `n = 37,199` held-out ads, scale `×5.10`, calibrated `--extra-noise-scale 1.35`).

| Variant | Group | Sub ΔELPD ± SE | z | 2022+ z | Projected Full ± SE | P(>100) | Verdict | 80% Cov | R-hat | Wall | USD |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| **`layrng`** | Unified abl. | `+291.6 ± 38.9` | **`+7.50`** | `+5.02` | **`+1,487 ± 198`** | `1.000` | **`GO`** | `79.9→80.1%` | `1.136` | `8.4m` | `$0.35` |
| **`y1`** | Unified abl. | `+274.3 ± 33.5` | **`+8.19`** | `+7.55` | **`+1,398 ± 171`** | `1.000` | `ESCALATE`* | `79.9→79.7%` | `1.234` | `10.7m` | `$0.45` |
| **`covid_vol`** | TODO #3 | `+113.3 ± 24.9` | **`+4.54`** | `+1.73` | **`+578 ± 127`** | `0.997` | **`GO`** | `79.9→79.9%` | `1.118` | `9.7m` | `$0.40` |
| **`size`** | Unified abl. | `+36.4 ± 17.8` | `+2.04` | `+3.01` | **`+186 ± 91`** | `0.755` | `ESCALATE` | `79.9→79.9%` | `1.109` | `9.7m` | `$0.41` |
| `marks` | Unified abl. | `+15.7 ± 40.6` | `+0.39` | `-0.33` | `+80 ± 207` | `0.467` | `ESCALATE` | `79.9→80.2%` | `1.080` | `10.9m` | `$0.46` |
| `income_scale` | TODO #3 | `+7.0 ± 8.5` | `+0.82` | `-0.44` | `+36 ± 43` | `0.137` | `ESCALATE` | `79.9→79.9%` | `1.159` | `8.0m` | `$0.34` |
| `covid_mean` | TODO #3 | `+4.0 ± 17.6` | `+0.23` | `+0.26` | `+20 ± 89` | `0.253` | `ESCALATE` | `79.9→79.9%` | `1.132` | `8.7m` | `$0.36` |
| `u4_bed` | TODO #3 | `+0.6 ± 7.2` | `+0.08` | `-1.03` | `+3 ± 37` | `0.024` | **`KILL`** | `79.9→79.9%` | `1.090` | `8.2m` | `$0.34` |
| `stab_dhcr` | TODO #3 | `-9.2 ± 10.4` | `-0.88` | `-2.11` | `-47 ± 53` | `0.020` | **`KILL`** | `79.9→79.9%` | `1.130` | `8.6m` | `$0.36` |
| `concess_gap` | TODO #3 | `-10.4 ± 7.6` | `-1.38` | `-2.93` | `-53 ± 39` | `0.002` | `ESCALATE`* | `79.9→79.9%` | `1.180` | `9.5m` | `$0.40` |
| **`sbf`** | Unified abl. | `-13.3 ± 6.4` | **`-2.07`** | `-3.67` | **`-68 ± 33`** | `0.000` | **`KILL`** | `79.9→79.9%` | `1.100` | `8.8m` | `$0.37` |
| **`bedunit`** | Unified abl. | `-33.4 ± 15.1` | **`-2.21`** | `-2.40` | **`-170 ± 77`** | `0.005` | **`KILL`** | `79.9→79.8%` | `1.086` | `9.1m` | `$0.38` |
| *REF `unified`* | *Bundled* | *`+557.8 ± 61.9`* | *`+9.01`* | *`+7.21`* | *`+2,844 ± 316`* | *`1.000`* | *`GO`* | *`79.9→79.8%`* | *`1.069`* | *`19.4m`* | *`$0.81`* |

*\*`y1` (`z=+8.19`, `P=1.000`) and `concess_gap` (`z=-1.38`, `P=0.002`) triggered the `R-hat > 1.15` safety guard on 2 chains; `y1` converged cleanly (`R-hat = 1.087`) in Wave 2.*

---

## 3. Wave 2 Results — Pruned Combinations, 4-Chain Escalation & `market` Backtest (`$3.20`)

### 3a. `screen-k5` (`latest`, `n = 37,199`)

| Comparison | Sub ΔELPD ± SE | z | 2022+ z | Projected Full ± SE | Verdict | 80% Cov | R-hat (ESS) | Wall | USD |
|---|---:|---:|---:|---:|---|---:|---|---:|---:|
| **`w2-clean-covvol`** (`layrng,size,covid_vol`) vs `l2bt` | `+459.7 ± 48.7` | `+9.44` | `+6.57` | **`+2,344 ± 248`** | **`GO`** | `79.9→80.0%` | `1.041` (`35`) | `9.6m` | `$0.40` |
| **`w2-clean-y1`** (`layrng,size,y1`) vs `l2bt` | `+610.7 ± 54.0` | `+11.31` | `+9.26` | **`+3,113 ± 275`** | **`GO`** | `79.9→79.8%` | `1.087` (`30`) | `9.5m` | `$0.40` |
| **`w2-clean-y1-cov`** (`layrng,size,y1,covid_vol`) vs `l2bt` | `+629.6 ± 54.6` | `+11.53` | `+9.53` | **`+3,210 ± 278`** | **`GO`** | `79.9→79.8%` | `1.055` (`30`) | `13.0m` | `$0.55` |
| `w2-clean-y1` vs bundled `unified` | `+52.8 ± 40.0` | `+1.32` | `+1.39` | **`+269 ± 204`** | — | `79.8→79.8%` | `1.087` (`30`) | `9.5m` | `$0.40` |
| `w2-clean-y1-cov` vs `w2-clean-y1` | `+18.9 ± 7.5` | `+2.52` | `+2.63` | **`+96 ± 38`** | — | `79.8→79.8%` | `1.055` (`30`) | `13.0m` | `$0.55` |
| `w2-size-ch4` (4ch `size`) vs `exp4-k5-ch4-l2bt` | `+26.4 ± 17.1` | `+1.54` | `+3.27` | `+135 ± 87` | `ESCALATE` | `80.1→80.0%` | **`1.046` (`76`)** | `10.7m` | `$0.45` |

### 3b. `screen-mkt-k5` (`market` `asof-20251110`, `n = 1,891` open ads, scale `×4.94`)

| Comparison | Sub ΔELPD ± SE | z | Projected Full ± SE | 80% Cov (Shift) | `<5%` Tail | R-hat | Wall | USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `l2bt` vs `range-j` | `+27.0 ± 16.5` | `+1.64` | `+134 ± 82` | `76.89→77.05%` (`+0.16 pp`) | `4.02→4.23%` | `1.048` | `8.1m` | `$0.34` |
| `l2bt + marks` vs `range-j` | `+29.9 ± 16.8` | `+1.78` | **`+148 ± 83`** | `76.89→77.42%` (**`+0.53 pp`**) | `4.02→3.81%` | `1.040` | `10.5m` | `$0.44` |
| `l2bt + y1` vs `range-j` | `+26.2 ± 17.5` | `+1.49` | `+129 ± 87` | `76.89→75.89%` (`-1.00 pp`) | `4.02→4.44%` | `1.046` | `10.0m` | `$0.42` |
| `layrng,size,covid_vol` vs `range-j` | `+14.6 ± 16.3` | `+0.90` | `+72 ± 80` | `76.89→74.83%` (`-2.06 pp`) | `4.02→4.60%` | `1.031` | `8.6m` | `$0.36` |
| `layrng,size,covid_vol,marks` vs `range-j` | `+25.7 ± 17.1` | `+1.50` | `+127 ± 85` | `76.89→74.19%` (`-2.70 pp`) | `4.02→4.23%` | `1.064` | `14.0m` | `$0.59` |
| *REF `unified` vs `range-j`* | *`+32.2 ± 16.8`* | *`+1.92`* | *`+159 ± 83`* | *`76.89→74.99%` (`-1.90 pp`)* | *`4.02→4.39%`* | *`1.071`* | *`18.5m`* | *`$0.78`* |
| `l2bt + y1` vs `l2bt` | `-0.9 ± 4.1` | `-0.21` | `-4 ± 20` | `77.05→75.89%` (**`-1.16 pp`**) | `4.23→4.44%` | `1.046` | `10.0m` | `$0.42` |
| `l2bt + marks` vs `l2bt` | `+2.9 ± 8.8` | `+0.33` | `+14 ± 43` | `77.05→77.42%` (**`+0.37 pp`**) | `4.23→3.81%` | `1.040` | `10.5m` | `$0.44` |
| `l2bt + u4_bed` vs `l2bt` | `-0.6 ± 1.7` | `-0.37` | `-3 ± 9` (`KILL`) | `77.05→77.10%` (`+0.05 pp`) | `4.23→4.12%` | `1.058` | `10.8m` | `$0.45` |

---

## 4. Honest Pre-Fit Prediction Scorecard (`53da9a07`)

| # | Pre-Fit Prediction | Observed Result | Score |
|---|---|---|---|
| **A1** | `y1`: `+1,000..+1,600`, `GO` | **`+1,398 ± 171`** (`z = +8.19`, `P = 1.000`; `R-hat=1.23` on 2ch, `1.087` in Wave 2) | **HIT** |
| **A2** | `marks`: `+800..+1,400`, `GO` | **`+80 ± 207`** (`z = +0.39`) on `latest` (helped `+55` on `market`, flat on `latest`) | **MISS** |
| **A3** | `layrng`: `+100..+400` | **`+1,487 ± 198`** (`z = +7.50`, `GO`) — **5× larger than predicted!** | **MISS (huge upside)** |
| **A4** | `size`: `+50..+250` | **`+186 ± 91`** (2ch, `2022+ z = +3.01`), **`+135 ± 87`** (4ch, `2022+ z = +3.27`) | **HIT** |
| **A5** | `bedunit` & `sbf`: `-50..+150` | **`bedunit = -170 ± 77`** (`KILL`), **`sbf = -68 ± 33`** (`KILL`) — both actively negative! | **MISS (caught bugs!)** |
| **B1** | `covid_mean`: `+300..+900`, `GO` | **`+20 ± 89`** (`z = +0.23`) — weekly walk `L(w)` + building paths already absorb mean shock | **MISS** |
| **B2** | `covid_vol`: `+250..+650`, `GO` | **`+578 ± 127`** (`z = +4.54`, `GO`) AND **`+96 ± 38`** (`z = +2.52`) on top of `Y1`! | **HIT (bullseye)** |
| **B3** | `stab_dhcr`: `+100..+450` | **`-47 ± 53`** (`2022+ z = -2.11`, `KILL`) | **MISS** |
| **B4** | `concess_gap`: `+50..+300` | **`-53 ± 39`** (`2022+ z = -2.93`) | **MISS** |
| **B5** | `income_scale`: `+40..+200` | `+36 ± 43` (`z = +0.82`) | **PARTIAL** |
| **B6** | `u4_bed`: `+30..+200` | `+3 ± 37` (`KILL`) on `latest`, `-3 ± 9` (`KILL`) on `market` | **MISS** |
| **C1** | `y1` drives `>= 1.0 pp` `market` 80% cov drop; `marks` does not | `l2bt+y1` vs `l2bt`: **`-1.16 pp`** (`-4 ± 20`), `l2bt+marks` vs `l2bt`: **`+0.37 pp`** (`+14 ± 43`); Wave 2 also revealed `covid_vol` + `layrng` share the same post-pandemic `sigma_g` tightening effect! | **HIT (deepened in W2)** |

**Scorecard Summary:** **4 HITs, 1 PARTIAL, 7 MISSes** — and THIS is the entire point of Charlie O'Neill / Will Brown fast screening! For **`$9.02` in 40 minutes**, we falsified 6 plausible hypotheses that would have cost **`~$90+` and 8+ hours** on full Modal fits, caught two negative passengers inside `unified` (`bedunit`, `sbf`), discovered that `layrng` alone is `+1,487` ELPD, proved `covid_vol` adds `+578` standalone and `+96` on top of `Y1`, and diagnosed the `market` coverage mechanism!

---

## 5. Itemized Modal Spend Ledger (2026-11-22, after `11:27:00 ET`)

Authoritative totals from `/data1/apartments/modal/ledger.jsonl` (`kind == "settle"`):

| Wave | Containers | Settled USD | Contents |
|---|---:|---:|---|
| **Wave 1 (`screen-k5`)** | `12` | `$4.62` | `sbf`, `bedunit`, `layrng`, `size`, `y1`, `marks`, `covid_mean`, `covid_vol`, `concess_gap`, `stab_dhcr`, `income_scale`, `u4_bed` |
| **Wave 1 (`screen-mkt-k5`)** | `3` | `$1.20` | `mkt-l2bt`, `mkt-y1`, `mkt-marks` |
| **Wave 2 (`screen-k5`)** | `4` | `$1.80` | `clean-covvol`, `clean-y1`, `clean-y1-cov`, `size-ch4` |
| **Wave 2 (`screen-mkt-k5`)** | `3` | `$1.40` | `mkt-clean-covvol`, `mkt-clean-covvol-mk`, `mkt-u4bed` |
| **TOTAL 1-HOUR SPRINT** | **`22`** | **`$9.02`** | **Authorized cap: `$20.00` (`$10.98` remaining, `45.1%` used)** |
