# Dual-Model Training Data Quality Sprint — Pass 2 (2026-11-25)

Pass 2 mined the brand-new post-Round-1 refits on `890efa6de1b99396` across both independent model families:
- **Bayesian HMC/NUTS (`dq-live-c2mo-of` live `onefit`, `dq-full-c2mo-p7` & `dq-c2mo-tf2b` `asof-20251110`):** all 35 remaining `kept/bld` R-hat > 1.05 buildings in `dq-live-c2mo-of`, all 27 in `dq-full-c2mo-p7`, all 222 `far_thin` buildings (`|level| > 0.5` on `< 10` training rows), live `/deals` top-120 uncautioned ads, and held-out `pred_loc` residuals (`155,425` rows).
- **Local `$0` CPU ensembles (`onefit2026_v2` & `asof2025_v2` `T4v2_SuperBlend_Kalman_GBDT`, `T2_LightGBM_LSS`, `stage0_oob` across all `1,900,538` rows):** dual-model concordant residual tails, full-corpus `stage0_oob` extremes, live `/deals` top-120 uncautioned ads, and full-corpus `b0textflags` FP/FN scans across all `1,900,538` descriptions.

## Summary of Pass 2 Changes (Commit `c1047849` on `t3/training-data-quality-sprint`)

### 1. Corrections Ledger (`pipeline/ledger/2026-11-25-dual-model-dq-pass2.ndjson` — `354` live entries, `0` stale, `0` overlap)
- **Wrong-borough / mis-geocoded Manhattan slug collisions (`65` excludes, `brooklyn_misjoin` / `location_conflict`):**
  - Eliminated the #1 root cause of negative `far_thin` (`level -0.70` to `-1.07`) and multimodal Manhattan buildings — outer-borough addresses sharing street names with Manhattan (`360-broadway-new_york` [Williamsburg rows driving bimodal `rhat=1.08` in both Bayesian fits], `299-broadway-new_york`, `38-cooper-square-new_york`, `39-broadway-new_york` [Astoria], `413-broadway-new_york`, `460-madison-avenue-new_york`, `510-west-21-street-new_york` [Inwood W 218th], `53-jackson-street-new_york`, `555-west-23-street-new_york` [Riverdale W 235th], `630-park-avenue-new_york`, `681-park-avenue-new_york`, `724-5-avenue-new_york`, `743-lexington-avenue-new_york`, `75-warren-street-new_york`, `884-madison-avenue-new_york`, `9-white-street-new_york`, `903-broadway-new_york`, `93-hudson-street-new_york`, `945-madison-avenue-new_york`, `962-madison-avenue-new_york`, `130-east-59-street-new_york`, `130-east-63-street-new_york`, `1411-broadway-new_york` [incl. literal `"WRONG BOROUGH"`], `145-east-18-street-new_york`, `147-grand-street-new_york`, `158-avenue-of-the-americas-new_york`, `194-broadway-new_york`, `2-howard-street-new_york`, `225-clinton-street-new_york`, `225-west-57th-street-new_york`, `238-east-26-street-new_york`, `28-grove-street-new_york`, `1227-broadway-new_york`).
- **Commercial, explicit short-term, room-share, 0-day rent-roll dump, and placeholder exclusions (`54` excludes):**
  - `22` verified commercial/retail/office/medical listings (`nonresidential`, incl. `1715063` `#1` worst concordant `onefit` outlier and `5` `full_baths == 0` commercial listings).
  - `11` verified explicit short-term-only rentals (`explicit_short_term_offer`, incl. `2439553` at `675-manhattan-avenue-brooklyn` which caused the `#1` worst building R-hat `2.991` in `dq-full-c2mo-p7`).
  - `6` verified per-room / per-person / SRO shared-bath-per-floor listings (`product_scope`).
  - `15` verified 0-day `NO_LONGER_AVAILABLE` rent-roll dumps (`2025-09-09` Milstein batch at `courtney-house` / `251-east-32` / `30-lincoln-plaza` and `2026-03-02` `225-west-23` batch) plus 1–2 letter spam ads (`911-dekalb-avenue-brooklyn` `rhat=1.176`).
- **Rule-2 peer-backed bathroom `set` repairs (`206` entries, backed by `other_ad` or `line_units`):**
  - `147` remaining `half_baths >= 3` repairs (`350 -> 203`, `-42%`), `6` `full_baths == 0` repairs (`27 -> 16`), `16` `full_baths IS NULL` repairs (`35 -> 18`), `35` `bedrooms <= 1 & full_baths >= 3` repairs (`166 -> 130`), plus live open stars **`5207594`** (`123-east-88-street-new_york` `1br/5ba -> 1br/1ba`, eliminating the `#1` CPU `SuperBlend` live fake deal at `cdf = 0.0009`) and **`5167879`** (`toren-condominium` Residence 309 `null -> 2 full / 0 half`).
- **Rule-2 peer-backed zero-bed `set` repairs (`29` entries, backed by `other_ad` or `line_units`):**
  - `28` `bedrooms == 0 & bed_text >= 2` multi-BR repairs plus live open **`5167879`** (`toren-condominium` Residence 309 `0br -> 2br`).

### 2. Unit Ledger (`pipeline/ledger/units/2026-11-25-dual-model-dq-pass2.ndjson` — `4` live entries, `0` stale)
- **`bridgeview-dumbo/26c` (`3` `split_unit` entries):** split broker-reused `1BR` (`4847202`, `$4,902`), `Studio` (`5077897`, `$4,100`), and live open `2BR` (`5205605`, `$7,337`) off the `$12,160–$12,677` Penthouse ads (`4440904`, `4581718`) — eliminating the `#1` Bayesian `dq-live-c2mo-of` live fake deal (`z = -11.3`).
- **`toren-condominium` (`1` `join_units` entry):** joined typoed page `3091` (live open `5167879`, `"Residence 309"`) with real unit `309` (`5118387`, `5189913`).

### 3. Upstream `b0textflags.py` & `cautions.py` Refinements (`142/142` frontier tests passing)
- `frontier/src/rentfrontier/b0textflags.py`: excluded the remaining `\bami\b` false positives (`Bon Ami Cafe`, `Ami Rothschild`, `Ami Ray`), guarded `income[- ]restrict` against `40x`/`times the rent`, guarded `in a shared home` against `"especially in a shared home"`, and added `shared <facility> (per|on each|on every) floor` and `(have|has|offering|renting) <N> rooms for rent` (`med_st0 = -0.80` to `-1.62`).
- `frontier/src/rentfrontier/cautions.py`: synced `cautions.TEXT["income"]` with `INCOME_V2`'s verified additions (`low/middle/moderate-income`, `income caps`, `HDC`, and the `ami`/`40x` guards) so live `/deals` does not leak moderate-income / HDC / income-cap listings.

## Rebuilt & Verified Datasets (`HASH = 6187fa654ce1fa3b`, `clean: true` at `c1047849`)

- **Pipeline:** `/data1/apartments/pipeline/datasets/rows-6187fa654ce1fa3b.parquet` (`1,974,034` rows; `ads-602a91eff4d7d892.parquet`; `records-e7c2563d3e0289fa.parquet` reused).
- **Market / `onefit` (`2026-11-23`, `1,900,419` rows, `6,199` open, `243` set aside; `100.0000%` snapshot coverage, `0` missing registry points):**
  - `/data1/apartments/frontier/datasets/b0-6187fa654ce1fa3b-alldata-dense-nyc-market-bedtext-textflags` (`rows_sha256: e66a0485d0b23fbf...`; `income_restricted_v2 = 2,747` `+1,198/-182`, `shared_space_v2 = 326` `+70/-30,006`)
  - `/data1/apartments/frontier/datasets/b0-6187fa654ce1fa3b-alldata-dense-nyc-market-bedtext` (`rows_sha256: c620b17cf23a628c...`)
- **Causal Backtest / `asof-20251110` (`1,761,378` rows, `9,301` open, `139,284` set aside; `100.0000%` snapshot coverage, `0` missing registry points):**
  - `/data1/apartments/frontier/datasets/b0-6187fa654ce1fa3b-alldata-dense-nyc-asof-20251110-bedtext-textflags` (`rows_sha256: e58715126c69b78b...`; `income_restricted_v2 = 2,116` `+854/-95`, `shared_space_v2 = 317` `+65/-27,046`)
  - `/data1/apartments/frontier/datasets/b0-6187fa654ce1fa3b-alldata-dense-nyc-asof-20251110-bedtext` (`rows_sha256: e98d93f45502c249...`)
