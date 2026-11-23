# First Unified Live Production Fit: `c1-compact` on `--split onefit` (2026-11-23)

Committed before launching the Modal fit (`ops/modal-fit`) per `CLAUDE.md`. This run is the
first single-fit production deployment intended to serve **all four live site sections**
(`/deals`, `/estimates`, `/price-now`, `/diagnostics`) from one converged model run, retiring
the split between `range-m4` (held `base-n9` scales on `/deals`), Nov 10 `b9`/`n9` (on
`/estimates`, `/price-now`, `/diagnostics`), and Oct 17 `m7`.

## Design & Launch Plan

- **Model:** `drift-building-phase-unitkn-ablate`
- **Variant (`c1-compact`):** `--variant layrng,size,sv_gp_mo,marks,seg_add,floor_poly,ad_core,scalar_sigma,biweekly_walk` (`429` explicit parameters, `4` GPs; passed 4-chain gates on both `latest` and `unified` in PR #1538).
- **Dataset:** `/data1/apartments/frontier/datasets/b0-b157a29e19aa837a-alldata-dense-nyc-market-bedtext` (`scoring_day = 2026-11-23`, parent rows `/data1/apartments/pipeline/datasets/rows-b157a29e19aa837a.parquet`, registry `/data1/apartments/external/registry/20261123-1f0c240-extend-180210/registry.parquet`).
- **Split (`--split onefit`):**
  - Total rows: `1,901,222`
  - Training rows: `1,745,472`
  - Held-out rows: `155,750` = **`6,200` live open market ads** + **`149,550` closed ≥1-year-old latest ads** (used for both held-out accuracy scores and leak-free Deals outcome validation via `drift_deals.validate(..., subset="closed")`).
- **Shards:** 2× `H200` (`--large --lean --no-summary --no-loo --no-heldout`, 48 GiB RAM, `$5.30/h`), `2 chains/shard = 4 chains total`, `warmup = 500`, `draws = 2600`, `keep_every = 30`, `seeds 1, 2`, `--budget-seconds 4800`.
- **Labels:** `c1-live-of-a`, `c1-live-of-b` → pooled via `rentfrontier.drift_pool` into `drift-building-phase-unitkn-ablate-b0-onefit-<sha>-c1-live-of`.

## Pre-Fit Quantitative Predictions

1. **Convergence gate (4 chains × 2,600 draws):** **PASS** (`max split R-hat ≤ 1.01`, `min bulk ESS > 400`, expected `R-hat 1.005–1.009`, `ESS 550–850` on `unit_sd` / `drift_sd`).
2. **Wall time & Modal cost (`--lean` H200):** `52–68 min/shard`, **`$9.50–$12.50` total** for both containers combined.
3. **Closed ≥1-yr held-out scores (`n = 149,550`, natural `1.00×` posterior):**
   - ELPD per row: **`1.20 to 1.30`** (total `~180,000–194,000`; `u5-of` scored `165,191 / 133,774 = 1.235/row`).
   - Median absolute error (log): **`0.0395 to 0.0425`** (`u5-of` had `0.0413`).
   - 80% interval coverage: **`79.0% to 81.0%`** (`u5-of` had `79.7%`).
4. **Closed-heldout Deals outcome validation (`drift_deals.validate` on `149,550` rows):**
   - Strictly monotone days on market and price-cut share across tenths (`Spearman ≥ 0.95` on both).
5. **Live `/deals` table comparison vs `range-m4` (`6,200` open ads as of `2026-11-23`):**
   - Cautioned share between **`23% and 28%`** (`range-m4` has `1,577 / 6,200 = 25.4%`).
   - Rank correlation (Spearman of `below_share` across the 6,200 open ads) vs `range-m4`: **`0.88 to 0.96`** (meaningful movement from Student-t unit levels, `sv_gp_mo`, and `marks`, while broadly agreeing on clear bargains).

## Acceptance & Publish Rule

Publish `/deals`, `/estimates`, `/price-now`, and `/diagnostics` from `c1-live-of` (backing up each existing live directory under `/data1/apartments/tmp/site-backup-before-c1-onefit-20261123/`) **only if** the 4-chain pooled fit passes the convergence gate (`max R-hat ≤ 1.01`, `min ESS > 400`), closed-heldout 80% coverage lies in `[0.78, 0.82]`, and closed-heldout validity is monotone (`Spearman ≥ 0.90`).
