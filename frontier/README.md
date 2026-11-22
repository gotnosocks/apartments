# `rentfrontier` — Modeling Package Architecture

`frontier/src/rentfrontier/` contains **195 Python modules** spanning three model generations
(Gen 2 Frontier GPU Gibbs, Gen 3 B0/Building-Zones, Gen 4 Drift). Because saved fits and
datasets record code/module provenance, historical model files are kept alongside active
production code. This guide maps which modules are **live**, which are **active research**,
and which are **historical**.

For the mathematical structure, plate diagram, and full score lineage, see
[docs/model/lineage.md](../docs/model/lineage.md) and [docs/model/drift.md](../docs/model/drift.md).

---

## 1. Active Production Stack (Drift Line)

### Core sampler, runner & pooling
| Module | Role |
|---|---|
| `drift.py` | Core blocked collapsed-Gibbs sampler (unit OU drift, Student-t building levels, optional Student-t unit levels & lease-phase factors, held-scales option) |
| `drift_building.py` | `drift-building` (`--level-dof 4` default): adds quarterly AR(1) building paths; serves `/estimates`, `/price-now`, `/diagnostics` (`b9`/`n9`/`j9`) |
| `drift_building_bedtext_layout_range.py` | **Served `/deals` model** (`range-m3` / `range-j`): `drift-building` + `ad:bed_text_smaller` + layout previous-ad and range marks |
| `drift_scales.py` | Stored scale sets (`base-n9`, `base-j9`) for `--scales-fixed` $2 single-container fits |
| `drift_pool.py` | Pools multi-container runs into one posterior and checks the split R-hat / bulk ESS gate |
| `run.py` | Top-level CLI runner & model registry mapping model names to modules |
| `b0.py` | Common Gibbs entry points (`main_run`), convergence gate helpers, and noise utilities |
| `building_zones_kitchen_sink.py` | Base ~250-column as-of feature design inherited by every Drift model |
| `building_zones_gibbs.py`, `building_zones.py`, `whitened_zones.py` | Weekly random walk + season, 1 km whitened HSGP zone surfaces, building-level priors |
| `sizefill.py` | As-of size imputation (`asof_size`) used at design time |

### Scoring, publishing & Deals UI backend
| Module | Role |
|---|---|
| `drift_score.py` | Predictive density (elpd), MAE, coverage, and CDF place (`below_share`) from kept draws |
| `drift_quantiles.py` | Exact mixture-CDF root inversion (safeguarded Newton + bisection) for Deals intervals |
| `drift_deals.py` | Builds `/deals` (`deals.json`), backtest `validation.json` (all + uncautioned), and ad text caches |
| `cautions.py` | Publish-time Deals cautions (12 codes: `income`, `not_home`, `owners_only`, `takeover`, `short_lease`, `beds`, `rooms_up`, `net_ask`, `deposit_net`, `raised`, `thin_level`, `off_market`) |
| `drift_previous.py` | Fit-consistent strictly-earlier training `prev_ask` / `prev_day` lookup (shared by Deals & Diagnostics) |
| `drift_kept_report.py` | Post-fit diagnostic report of kept-draw R-hat > 1.05 and thin high-level buildings |
| `drift_estimates.py` | Publishes `/estimates` (`estimates.parquet`) from latest + market runs |
| `drift_today.py` | Publishes `/price-now` (`today.parquet`) for ~937k units *(currently Gaussian unit levels only)* |
| `drift_diagnostics.py` | Publishes `/diagnostics` (`ads.parquet`, `buildings.parquet`, `history.parquet`) |
| `descriptions.py`, `api_records.py` | Ad text and deposit extraction from scraped StreetEasy records |

---

## 2. Dataset Pipeline (`b0*` & Data Support)

### Active production chain (`ops/market-dataset` / `ops/deals-refresh`)
1. `b0data.py` — Converts pipeline parquet rows into the base B0 dataset (columns, as-of aggregates, text flags).
2. `b0trim.py` — Trims out-of-scope / malformed rows.
3. `b0nyc.py` — Filters to NYC listings against the NJ registry (`njregistry.py`, `njcity.py`).
4. `b0bedtext.py` — Adds bedroom-count text reader columns (`bed_text_smaller`, flex flags) used by `drift-building-bedtext*` and `l2bt`.
5. Support: `splits.py` (latest / market / whole-building splits), `market.py` (open-ad market & as-of backtest builders), `snapshots.py`, `registry.py`, `registry_extend.py`, `unit_features.py`, `unit_floor.py`, `features.py`, `ledger.py`, `corrections.py`, `cleaning.py`, `latest_ask.py`.

### Experimental side-car dataset builders (not yet in the active chain)
| Module | Column / transformation added | Status |
|---|---|---|
| `b0closing.py`, `b0closingraise.py` | Reprice off-market / closing-raise asks | `b0closingraise` tested on Deals backtest (`cr-j`, Nov 20) and **rejected** (-59.1 elpd) |
| `b0ending.py` | `prev_ending` (`RENTED`, `DELISTED`, `NO_LONGER_AVAILABLE`, etc.) | Built on disk; unread by any model |
| `b0freetext.py` | `months_free_text`, `free_lease_months`, `ask_basis_text` (~112k text-only rows) | Built on disk; unread by any model |
| `b0textflags.py` | `income_restricted_v2`, `shared_space_v2`, AMI tier/band | Built on disk; unread (`I1` written, unfit) |
| `b0duplex.py`, `b0penthouse.py` | Text duplex and penthouse marks | Built for `D1` (written, unfit) |
| `b0outdoorsize.py` | Regex-extracted private outdoor square footage | Built for `drift-building-phase-outdoorsize` (unfit) |
| `b0coop.py`, `b0turnover.py` | As-of MapPLUTO co-op/condo class; 730-day building turnover | Built on disk; turnover mean term closed (no gradient on history) |
| `b0studiohistory.py` | Optional `studio-history-h1` recode (227 rows) | Written, off by default |
| `b0labeljoin.py`, `b0chains.py` | `unit-labels-v18` copy; repost chain collapse | Built on disk; unfit |
| `b0amenitycarry.py`, `b0income.py` | Carried unit codes; wider income flag | Superseded (`amenitycarry` duplicates `umean:`) |

---

## 3. Research Frontier Models (`drift_*.py` Variants)

| Module | Model name | Status |
|---|---|---|
| `drift_building_phase_unitkn_level_bedtext.py` | `drift-building-phase-unitkn-level-bedtext` (`l2bt`) | **Best latest-split model (elpd 237,654, gate pass)**; unserved |
| `drift_building_phase_unitkn_level.py` | `drift-building-phase-unitkn-level` (`l2kn` / `l2j` / `l2m`) | Latest & backtest pass; market missed `phase_scale[1]` (1.0108) |
| `drift_building_phase_unitkn.py` | `drift-building-phase-unitkn` (`l1tkn`) | Gate pass (elpd 236,911, +4,106 over L1) |
| `drift_building_phase.py` | `drift-building-phase` (`L1`) | Gate pass (elpd 232,806) |
| `drift_building_bedtext.py` | `drift-building-bedtext` (`heldbed-m`/`j`) | Served `/deals` Nov 17; superseded by `...-layout-range` |
| `drift_building_bedtext_layout.py` | `drift-building-bedtext-layout` (`layout-j`) | Gate pass; rejected (unmarked loss); superseded by `...-range` |
| `drift_building_phase_unitt.py`, `drift_building_unitt.py`, `drift_building_phase_unitk.py` | `L1T`, `U2`, `L1TK` | Intermediate steps toward `L1TKN` (gate miss / unlaunched) |
| `drift_building_unitkn.py` | `drift-building-unitkn` (phase-free) | Short/k50 ablation (-1,241 elpd vs L2) |
| `drift_building_phase_unitkn_level_bedunit.py` | `...-bedunit` | Short fit (-122 vs `l2bt`); dropped |
| `drift_building_phase_year.py` | `Y1` (year noise scale on L1) | Written, unfit; free check +1,174 elpd — needs `l2bt`-base port |
| `drift_building_phase_line.py`, `drift_line.py` | `LN1` (building × bedroom line level) | Written, unfit; GPU rehearsal hit `unit_sd` ridge |
| `drift_building_phase_duplex.py`, `..._income.py`, `..._outdoorsize.py`, `..._plutoasof.py`, `..._level.py` | `D1`, `I1`, `outdoorsize`, `P1`, `L2` (on L1) | Written, unfit |
| `drift_building_phase_segment.py`, `drift_building_phase_unitkn_segment.py` | Quarterly segment paths | Written, unfit; 1-in-10 rehearsal failed on 3+BR lengthscale modes |
| `drift_building_doorman.py`, `drift_local.py`, `drift_building_phase_unitkn_level_phase.py`, `..._slow.py` | Ablations / diagnostic variants | Dropped or diagnostic only |

---

## 4. Historical Generations (Retained for Reproducibility)

- **Gen 3 — B0 / Building-Zones (`building_zones*.py`, 33 files; `b0_1.py`–`b0_4.py`, `normal_walk.py`, `centered_walk.py`, `level_walk.py`, `total_walk.py`, `two_zone*.py`, `amp_joint.py`)**: Oct 18–24 progression from simple B0 to `building_zones_floor_asof3_cap64` (Fit 8), `unitmean` (Fit 4), and `kitchen_sink`. Keep intact because `drift.py` imports `building_zones_kitchen_sink.py` and `whitened_zones.py`, and historical notes reference these modules.
- **Gen 2 — Frontier GPU Gibbs & NUTS (`design.py`, `design_parts.py`, `gibbs.py`, `nuts.py`, `model.py`, `data.py`, `loo.py`, `leaderboard.py`, `autoselect.py`, `latestselect.py`, `newbuilding.py`, `dashboard.py`)**: Sep 24–Oct 17 multi-neighborhood frontier line (`m0`–`m8`, Design C).
- **Historical Feature & Utility Modules (`access.py`, `areas.py`, `building_*.py`, `crime.py`, `eastparks.py`, `exposure.py`, `frontage.py`, `garden.py`, `loud.py`, `nearby.py`, `nta.py`, `parks.py`, `quiet.py`, `retail.py`, `riverparks.py`, `transit.py`, `trees.py`, `clusterse.py`, `calibration.py`, `compare.py`, `draws.py`, `effects.py`, `explain.py`, `explained.py`, `rescore.py`, `simulate.py`, `summary.py`, `variance.py`, etc.)**: External spatial/amenity feature screens and statistical utilities from Sep–Oct.

---

## Running Tests

```sh
cd frontier && uv sync --extra dev
.venv/bin/python -m pytest tests/test_drift.py tests/test_drift_deals.py tests/test_drift_score.py -q
```
