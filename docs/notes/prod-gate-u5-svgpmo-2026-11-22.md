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
