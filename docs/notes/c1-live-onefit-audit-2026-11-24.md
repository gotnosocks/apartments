# Post-Gate Audit & Worst-Miss Expert Read: `c1-live-of` (2026-11-24)

Standing post-gate audit (`CLAUDE.md`, `docs/expert-reads.md`, `docs/model/drift.md`) for the
first live unified single-fit production deployment
`drift-building-phase-unitkn-ablate-b0-onefit-00bc8849-c1-live-of` (`#1549`, serving `/deals`,
`/estimates`, `/price-now`, and `/diagnostics` from `1,745,472` train / `149,550` closed ≥1-yr
held-out / `6,200` open live market ads as of `2026-11-23`).

All scripts, blind batches, reader outputs, and confirmation JSON live in
`docs/notes/c1-live-onefit-audit-2026-11-24/`. **Modal spend: `$0.00`.**

---

## 1. Kept-Quantity Mixing & Far-Thin Building Audit (`kept_check.py`)

Compared with the retired `range-m3` / `range-m4` market fits, `c1-live-of` mixes substantially
cleaner on kept quantities across all `155,750` scored ads and `68,008` buildings:

| Metric (`R-hat > 1.05`, `\|level\| > 0.5 & train < 10`) | `c1-live-of` (4 chains × 2,600) | Previous `range-m3` reference |
|---|---:|---:|
| Scored ads with `pred_loc` R-hat > 1.05 | **13 / 155,750 (`0.008%`)** | 0 live / 2 backtest (of ~16k) |
| Buildings with level R-hat > 1.05 | **42 / 68,008 (`0.062%`)** | 51 live / 72 backtest |
| Buildings with level R-hat > 1.05 & scored ads | **21** | — |
| Far-thin buildings (`\|level\| > 0.5`, `<10` train ads) | **235** (61 with 80 scored ads) | 338 |

- Only **1** of the 13 ads with `pred_loc` R-hat > 1.05 sits near the low tail (`listing_id=4581268`,
  `below_share=0.011`, `rhat=1.082`); zero top live `/deals` ads have mixing trouble.
- The largest far-thin positive levels are genuine ultra-luxury hotels/condos (`the-st-regis-hotel`
  `+2.25`, `the-pierre` `+1.58`, `the-carlyle` `+1.44`, `220-central-park-south` `+1.17`) plus a
  handful of outer-borough small/loft buildings (`62-delevan-street-brooklyn`, `76-green-street-brooklyn`).

---

## 2. Live `/deals` Top-100 Comparison vs `range-m4`

- Default uncautioned pool (`unit_ads > 0` or `building_ads >= 5`): **`4,433`** ads.
- Overlap with `range-m4` top-100 uncautioned: **`73 / 100`** (`27` newly entered).
- Composition of `c1-live-of` top-100 uncautioned:
  - Bedrooms: `0BR: 15`, `1BR: 35`, `2BR: 29`, `3BR: 14`, `4BR: 6`, `5BR: 1`.
  - New units (`unit_ads == 0`): **`46 / 100`**; `floor == 1`: `8 / 100`; `months_free > 0`: `31 / 100`.
- Live open-market (`n = 6,200`) coverage weak spots:
  - **`bld_ads == 0`** (`n = 87`): bias `+0.1877`, MAE `0.2057`, 80% cov **`43.7%`** (new buildings).
  - **`size >= 1,500 sqft`** (`n = 295`): bias `+0.0538`, 80% cov **`64.4%`**.
  - **`top3_pred`** (`n = 438`): bias `+0.0532`, 80% cov **`64.8%`**.
  - **`unit_ads == 0`** (`n = 2,031`): 80% cov **`69.5%`** vs `76.3%–78.2%` for re-listed units.
  - **`floor == unknown`** (`n = 1,433`): 80% cov **`71.6%`**.

---

## 3. Blind Broker Reads (`docs/expert-reads.md`, Half-A Discovery Only)

Held-out buildings were split 50/50 by deterministic blake2b hash (`seed = 20261124`) into
**Half A (`75,418` closed ads)** for discovery/reading and **Half B (`74,132` closed ads)** held
back for unbiased confirmation. Three shuffled blind batches (140 ads total, rents/CDFs stripped)
were read by NYC broker reader agents:

1. **Closed 2022+ Half-A ask-far-below (`pit < 0.01`, `n=25`) vs controls (`0.25 ≤ pit ≤ 0.75`, `n=25`):**
   - Enriched in misses: **`flex_or_railroad_or_tiny_layout` (5 vs 0)**, **`rent_stabilized` (4 vs 0)**,
     `low_floor` (5 vs 2), `above_retail` (4 vs 2), `loud_street` (5 vs 3), `walkup` (4 vs 2).
   - 8 of 25 low misses (vs 11 of 25 controls) had no obvious broker catch.
2. **Closed 2022+ Half-A ask-far-above (`pit > 0.99`, `n=20`) vs controls (`n=20`):**
   - Enriched in misses: **`townhouse_or_full_floor` (6 vs 1)**, **`coop_or_condo_owner` (4 vs 2)**,
     **`large_terrace_or_yard` (4 vs 2)**, `no_photos_or_sparse` (6 vs 4).
3. **Live `/deals` top-25 uncautioned vs mid-table uncautioned controls (`n=25`):**
   - Enriched in top deals: **`sparse_text_or_no_photos` (6 vs 1)**, `condo_owner` (8 vs 5),
     `months_free_coded` (7 vs 5), `flex_bed` (4 vs 2), `walkup_high` (3 vs 1).
   - 8 of 25 top deals (vs 11 of 25 controls) were judged clean, standard apartments.

---

## 4. Unbiased Half-B Confirmation & Student-t ELPD Sizing (`confirm_half_b.py`)

Each candidate trait (from both the quantitative audit and the blind broker reads) was cross-fitted
for log-scale and shift on **Half A (`n = 75,418`)** and scored out-of-sample on **untouched Half B
(`n = 74,132`)** with building-clustered SEs (scaled `×2` to full closed panel):

| Candidate | Prev% | Scale (Half A) | Shift (Half A) | Full Est ΔELPD ± SE | z | Mechanism / Action |
|---|---:|---:|---:|---:|---:|---|
| **`changed_bed`** | 1.3% | **1.402×** | `+0.0092` | **`+205.8 ± 29.5`** | **`+6.97`** | Bedroom count changed since unit's last ad — still `1.40×` wider beyond `mark:changed_counts` → **screen in Wave B** |
| **`floor_unknown`** | 29.7% | **1.027×** | `-0.0051` | **`+195.4 ± 28.7`** | **`+6.80`** | Missing floor (`23.6k` ads in 2022+) needs its own scale mark → **screen in Wave B** |
| **`gap_gt_2yr`** | 49.5% | `1.008×` | `-0.0043` | **`+174.6 ± 31.3`** | **`+5.59`** | Gap-since-last-ad (`>2 yr` & `<=180d`) → **screen in Wave B** |
| **`tenure_condo`** | 17.7% | **1.051×** | `-0.0049` | **`+116.7 ± 30.6`** | **`+3.82`** | Owner-rented condos have wider ask dispersion → **screen in Wave B (`mark_tenure`)** |
| **`gap_le_180d`** | 11.7% | `1.002×` | `-0.0056` | **`+113.8 ± 21.8`** | **`+5.22`** | Short gap `<=180d` → **screen in Wave B (`gap_bins`)** |
| **`townhouse_units_le4`** | 13.5% | `0.974×` | `-0.0065` | **`+108.9 ± 20.5`** | **`+5.30`** | Small 1–4 family townhouses (6 vs 1 in blind high-miss read) → **screen in Wave B** |
| **`tenure_coop`** | 3.9% | **1.100×** | `-0.0079` | **`+97.7 ± 20.7`** | **`+4.73`** | Co-op rentals `1.10×` wider & `-0.8%` lower → **screen in Wave B (`mark_tenure`)** |
| **`u1_log_sqft_gt1k`** | 12.5% | **1.113×** | `-0.0169` | **`+76.3 ± 20.5`** | **`+3.72`** | Continuous `U1` size scale `max(0, log(sqft/1000))` → **screen in Wave B** |
| **`floor_1`** | 6.8% | `1.032×` | **`-0.0104`** | **`+68.3 ± 24.5`** | **`+2.78`** | Bug found in `apply_floor_poly`: floor 1 & unknown both map to `0.0`! Add `unit:floor_1` mean col → **screen in Wave B** |
| `months_free_gt0` | 10.0% | `0.987×` | `-0.0052` | `+62.1 ± 19.5` | `+3.18` | Secondary check |
| `bld_thin_le5` | 4.6% | `0.904×` | `-0.0104` | `+60.9 ± 19.3` | `+3.16` | Addressed by `--level-dof 8` (`level_dof8`) → **screen in Wave B** |
| `top3_pred` | 3.0% | `1.094×` | `-0.0122` | `+51.2 ± 19.2` | `+2.67` | Overlaps `u1_log_sqft_gt1k` |
| **`sparse_photos_le1`** | 10.0% | **1.075×** | `-0.0015` | **`+36.3 ± 15.9`** | **`+2.28`** | 6× enriched in live top `/deals` (`photos <= 1`) → **screen in Wave B** |
| `baths_3p` | 2.1% | `0.968×` | `-0.0156` | `+28.1 ± 13.5` | `+2.08` | Check with `floor_1` mean |
| `penthouse` | 1.2% | `1.191×` | `-0.0083` | `+21.5 ± 13.5` | `+1.59` | Low priority |
| `low_fl_retail` | 5.0% | `1.033×` | `-0.0084` | `+0.5 ± 18.9` | `+0.03` | Null on Half B — dropped |

### Key Structural Bug Found in `apply_floor_poly`
In `drift_building_phase_unitkn_ablate.py:435-438`, `apply_floor_poly` constructs `elev_floor`
exclusively from `unit:elev_f2..64`, so **floor 1** (`elev_floor = 0`) and **floor unknown** map to
the exact same zero vector `(0, 0, 0)`, removing any discrete ground-floor penalty! Adding an
explicit `unit:floor_1` mean indicator directly tests this `-1.04%` (`-1.3%` in 2022+) bias.

---

## 5. Modal Spend Ledger Reconciliation (Track A2)

Reconciled `/data1/apartments/modal/ledger.jsonl` from `2026-11-14` through `2026-11-23`:
- **250 settled runs, `$399.50` total**:
  - `2026-11-14`–`2026-11-20` (original causal sprint + `range-m2`/`m3`/`cr-j`): **33 runs, `$80.43`** (exact match to handoff).
  - `2026-11-22` (fast screening harness `#1533`, ablations `#1534`, Option 1 `#1535`, variance GPs `#1536`, unified/u5-svgpmo gates `#1531`/`#1545`, `c1-compact` sprint `#1538`, onefit protocol `#1537`): **207 runs, `$279.65`**.
  - `2026-11-23` (`u5-of` full onefit `$14.46`, container probes `$2.87`, `range-m4` `$2.28`, `c1-live-of` `$12.37` + `$0.56` `today_cpu`, plus carryover): **10 runs, `$39.42`**.
- **5 stale unsettled reservations** from aborted earlier launches (`u1-mkt-p`, `u1-lat-p`, `o1-lat-clean-pre24`, `o1-lat-clean-seg`, and the first `c1-live-of-today` attempt).
