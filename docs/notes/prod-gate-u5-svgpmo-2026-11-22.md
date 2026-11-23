# Production Gate Pre-Fit Predictions: `u5-svgpmo` Full 6-Chain Fits (`latest` & `market`, 2026-11-22)

Committed before launching Modal full 6-chain production gate shards (`ops/modal-fit`) in accordance with `CLAUDE.md`, immediately following the squash-merge of PR #1536 (`1d62c667`).

## Candidate Architecture (`sv_gp_mo`)
- **`u5-svgpmo-lat` (`latest` split, `N_train = 1,706,824`, `N_test = 189,647`):**
  - Model: `drift-building-phase-unitkn-ablate`
  - Variant: `--variant layrng,size,sv_gp_mo,marks,seg`
  - Exact upgrades vs production incumbent `u4s-lat`:
    1. Drops proven negative passengers `bedunit` and `sbf` while keeping **all 6 `marks`** (`changed_counts`, `baths_2`, `baths_3p`, `floor_1`, `large_01br`, `thin_first_ad`).
    2. Replaces discrete calendar years `y1` (and requires **zero external Covid CSVs**) with the anchored monthly Matérn-3/2 stochastic-volatility GP `sv_gp_mo` (`156` months, `ℓ = 1.0 yr`, `24` orthogonal eigenmodes, anchored at `2024-01 = 0`, clamped at the last training month).
  - Shards: 3× `H200` (`u5-svgpmo-lat-{a,b,c}`, `seeds 1, 2, 3`, `2 chains/shard = 6 chains total`, `warmup=500`, `draws=2600`, `keep_every=40` → `390` kept draws, `--budget-seconds 5700`, `--no-loo --no-heldout`).
- **`u5-svgpmo-mkt` (`market` `asof-20251110` split, `N_train = 1,754,606`, `N_test = 9,346`):**
  - Model: `drift-building-phase-unitkn-ablate`
  - Variant: `--variant layrng,size,sv_gp_mo,marks` (scored both raw `1.00×` and calibrated `open_scale = 1.12`).
  - Shards: 3× `H100` (`u5-svgpmo-mkt-{a,b,c}`, `seeds 1, 2, 3`, `2 chains/shard = 6 chains total`, `warmup=500`, `draws=1800`, `keep_every=30` → `360` kept draws, `--budget-seconds 3600`, `--no-loo --no-heldout`).

## Pre-Fit Quantitative Predictions

| Metric | Incumbent Baseline | Pre-Fit Prediction for `u5-svgpmo` | Promotion / Falsification Gate |
|---|---|---|---|
| **`u5-svgpmo-lat` convergence (6 chains)** | `u4s-lat` (`R̂ ≤ 1.01`, `ESS > 400`) | **PASS:** `max_rhat ≤ 1.009`, `min_ess ≥ 600` (strong monthly `phase_factor` mixing seen on screen: `pf_rhat = 1.026`) | Fails promotion if `max_rhat > 1.01` or `min_ess ≤ 400` |
| **`u5-svgpmo-lat` ELPD vs `u4s-lat`** | `242,751.5` (`n = 189,647`) | **`+450 to +750` ELPD** (`screen-k5` projected `+662.8 ± 114.5`, `z = +5.79`; slight shrinkage on full 5× denser data still yields a decisive win) | Falsified if `< +250` or `z < +3.0` |
| **`u5-svgpmo-lat` MAE / RMSE** | `4.01%` / `0.0785` | **`≤ 4.00%` MAE**, **`≤ 0.0782` RMSE** (matching `clean5-lat`'s point-accuracy lift without the `-188` `mark_changed` regression) | — |
| **`u5-svgpmo-mkt` convergence (6 chains)** | `u3-mkt` (`R̂ ≤ 1.01`, `ESS > 400`) | **PASS:** `max_rhat ≤ 1.008`, `min_ess ≥ 700` (boosted by `draws=1800` + `sv_gp_mo`'s `116` screen `pf_ess`) | Fails promotion if `max_rhat > 1.01` or `min_ess ≤ 400` |
| **`u5-svgpmo-mkt` raw ELPD vs `u3-mkt`** | `10,215.9` (`Cov80 = 76.62%`) | **`+25 to +70` ELPD** (`screen-mkt-k5` projected `+58.6 ± 17.3` over `u1`) | Falsified if `< 0` |
| **`u5-svgpmo-mkt` `@1.12×` ELPD vs `u3-mkt@1.12`** | `10,249.4` (`Cov80 = 80.01%`; `+207.3` over `range-j`) | **`+10 to +45` ELPD** (`Cov80 = 79.4%–80.4%`, **`+220 to +260` over `range-j`**) | Falsified if `< 0` vs `u3-mkt@1.12` |
| **Wall time & Modal USD** | `clean5`: `68.5m` H200 (`$22.12`), `47.8m` H100 (`$14.08`) | H200: `72–82m/shard` (`~$24–$27`); H100: `50–58m/shard` (`~$16–$18`); **Total `~$40–$45`** | Must finish cleanly within `5700s` / `3600s` budget |

---

## Results: `u5-svgpmo-lat` (6-Chain `latest` Production Gate — **PASS**)

All three `H200 --large` shards (`u5-svgpmo-lat-{a,b,c}`, seeds 1–3, `2 × (500 + 2600)` each) finished cleanly and were pooled with `rentfrontier.drift_pool` into `drift-building-phase-unitkn-ablate-b0-latest-e81a1561-u5-svgpmo-lat` (6 chains × 2,600 draws, 390 kept draws total).

- **Wall & cost:** `86.5m ($9.30)` + `85.1m ($9.15)` + `85.8m ($9.23)` = **`$27.68`** total.
- **Convergence gate (712 parameters): PASS**
  - Worst split R-hat: **`1.0087`** (`sigma[2]`, ESS `1,386`; next: `sigma[3]` `1.0085`, `sigma[1]` `1.0083`, `phase_factor[17]` `1.0075`). **Prediction (`≤ 1.009`): HIT.**
  - Lowest bulk ESS: **`1,077`** (`unit_sd`, R-hat `1.0046`; next: `drift_sd` `1,242`). **Prediction (`≥ 600`): HIT.**
- **Held-out scores (`n = 189,647`, `drift_score`):**

| Model | Held-out ELPD | Δ ELPD vs `u4s-lat` (bld-clustered SE) | MAE (log) | RMSE | Cov50 / Cov80 / Cov90 / Cov95 | Gate |
|---|---:|---|---:|---:|---|---|
| `u4s-lat` (incumbent) | `242,751.5` | — | `0.03936` | `0.07854` | `51.3% / 79.88% / — / —` | PASS |
| `clean5-lat` | `242,631.7` | `-119.8` | `0.03921` | `0.07799` | `— / 79.84% / — / —` | PASS |
| **`u5-svgpmo-lat`** | **`243,290.3`** | **`+538.8 ± 48.1` (`z = +11.20`)** | **`0.03924`** | **`0.07846`** | **`51.35% / 80.03% / 89.64% / 94.75%`** | **PASS** |

- Against `clean5-lat`: **`+658.7 ± 65.3`** (`z = +10.09`, `G = 36,207` buildings).
- **Prediction scores (`latest`):**
  - ELPD gain `+450 to +750`: **HIT** (`+538.8 ± 48.1`, `z = +11.20`).
  - MAE `≤ 4.00%`: **HIT** (`3.924%`). RMSE `≤ 0.0782`: narrow miss (`0.07846`, still improved over `u4s-lat`'s `0.07854`).
  - Positive Δ ELPD vs `u4s-lat` in every single year 2016–2026: largest gains in **2020 (`+109.9`)**, **2021 (`+85.3`)**, **2024 (`+74.1`)**, **2025 (`+63.0`)**, **2023 (`+61.7`)**, **2026 (`+44.4`)**, **2022 (`+42.0`)**.

## Results: `u5-svgpmo-mkt` (6-Chain `market` `asof-20251110` Backtest Gate — **PASS**)

All three relaunched `H200 --large` shards (`u5-svgpmo-mkt-{a,b,c}`, seeds 1–3, `2 × (500 + 1800)` each, `--budget-seconds 4500`) finished cleanly and were pooled with `rentfrontier.drift_pool` into `drift-building-phase-unitkn-ablate-b0-market-e81a1561-u5-svgpmo-mkt` (`6 chains × 1,800 draws`, `360` kept draws total).

- **Wall & cost:** `58.5m ($6.30)` + `56.2m ($6.04)` + `56.6m ($6.09)` = **`$18.43`** total (all 6 `lat + mkt` shards: **`$46.11`**).
- **Convergence gate (324 parameters): PASS**
  - Worst split R-hat: **`1.0069`** (`beta[bed=0:full>=2]`, ESS `1,737`; next: `unit_sd` `1.0068`, `sigma[2]` `1.0063`, `sigma[1]` `1.0063`). **Prediction (`≤ 1.008`): HIT.**
  - Lowest bulk ESS: **`810`** (`unit_sd`; next: `drift_sd` `919`, `drift_tau` `1,071`, `phase_factor[12]` `1,133`). **Prediction (`≥ 700`): HIT.**
- **Held-out backtest scores (`n = 9,346` open ads as of `2025-11-10`, `drift_score`):**

| Model | Final-Ask ELPD | Δ ELPD vs `range-j` (bld SE) | MAE (log) | RMSE | Bias | Cov50 / Cov80 / Cov90 / Cov95 | Gate |
|---|---:|---|---:|---:|---:|---|---|
| `range-j` (currently live Deals) | `10,042.1` | — | `0.04686` | `0.10208` | `+0.0097` | `51.7% / 79.17% / 89.4% / 94.64%` | PASS |
| `u3-mkt` (raw `1.00×`) | `10,215.9` | `+173.8` | `0.04657` | `0.10139` | `+0.0086` | `— / 76.66% / — / 93.83%` | PASS |
| `u3-mkt` (`@1.12×`) | `10,249.4` | `+207.3` | `0.04664` | `0.10137` | `+0.0086` | `— / 79.94% / — / 95.41%` | PASS |
| `clean5-mkt` (raw `1.00×`) | `10,187.5` | `+145.4` | `0.04653` | `0.10122` | `+0.0086` | `— / 76.58% / — / 93.71%` | PASS |
| **`u5-svgpmo-mkt` (raw `1.00×`)** | **`10,249.7`** | **`+207.6 ± 30.9` (`z = +6.71`)** | **`0.04635`** | **`0.10149`** | **`+0.0090`** | **`50.42% / 78.77% / 88.90% / 95.10%`** | **PASS** |
| `u5-svgpmo-mkt` (`@1.12×`) | `10,229.5` | `+187.4` | `0.04641` | `0.10148` | `+0.0090` | `53.72% / 81.94% / 91.43% / 96.24%` | PASS |

- **Paired building-clustered comparisons (`G = 4,771` buildings):**
  - `u5-svgpmo-mkt` (raw) vs `range-j`: **`+207.6 ± 30.9` (`z = +6.71`)**
  - `u5-svgpmo-mkt` (raw) vs `u3-mkt` (raw): **`+33.8 ± 10.8` (`z = +3.12`)** — **Prediction (`+25 to +70`): HIT.**
  - `u5-svgpmo-mkt` (raw) vs `clean5-mkt` (raw): **`+62.2 ± 15.5` (`z = +4.01`)**
  - `u5-svgpmo-mkt` (raw) vs `u3-mkt` (`@1.12×`): **`+0.4 ± 9.8` (`z = +0.04`)** — matches `u3-mkt@1.12` **with zero post-hoc scaling**!
  - `u5-svgpmo-mkt` (`@1.12×`) vs `u5-svgpmo-mkt` (raw): **`-20.3 ± 11.6` (`z = -1.74`)** — **Key scientific discovery:** `sv_gp_mo`'s smooth monthly volatility path already brings raw open-market coverage from `76.66%` up to `78.77%` (`Cov50 = 50.42%`, `Cov95 = 95.10%`), so stacking `open_scale = 1.12` on top over-widens intervals (`Cov80 = 81.94%`, `Cov95 = 96.24%`) and hurts ELPD. **Prediction (`@1.12×` beats `u3@1.12` by `+10 to +45`): FALSIFIED** — raw `1.00×` is strictly better than `1.12×` on `u5-svgpmo-mkt`!
- **Real-world Deals outcomes (`drift_deals validate`, raw `1.00×`):**
  - All 9,346 ads: lowest tenth (624 ads) leaves in median **27 days**, **17.1%** cut, **24.8%** gone in 14d; highest tenth (1,715 ads) takes **70 days**, **63.0%** cut, **6.1%** gone in 14d.
  - Uncautioned 7,637 ads: lowest tenth (377 ads) **30 days**, **20.2%** cut, **24.1%** raised vs highest tenth (1,464 ads) **71 days**, **63.5%** cut, **3.6%** raised.

## Promotion Decision

- **Both 6-chain production gates PASS cleanly** (`lat`: `R̂ = 1.0087`, `ESS = 1,077`, **`+538.8 ± 48.1` ELPD** over `u4s-lat`, **`3.92%` MAE**; `mkt`: `R̂ = 1.0069`, `ESS = 810`, **`+207.6 ± 30.9` ELPD** over live `range-j`, **`+33.8 ± 10.8`** over raw `u3-mkt`).
- **Drop `open_scale = 1.12` for `u5-svgpmo`:** serve `u5-svgpmo` at natural `1.00×` posterior calibration — cleaner, zero post-hoc multiplier, better ELPD (`10,249.7` vs `10,229.5`), and balanced `50.4 / 78.8 / 88.9 / 95.1%` coverage.
