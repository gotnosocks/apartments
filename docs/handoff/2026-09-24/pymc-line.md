# Hand-off: PyMC model line (Model Improvement session), September 22–24

## (a) Goals and how they changed
- Started as "improve the model". Then: test whether find_MAP and data subsets work as quick screens, and run the screen → promote cycle autonomously (Sept 22).
- Sept 23: "iterate more quickly" (research-backlog E1–E7).
- Sept 24: one master and one leaderboard for both lines.
  - No new code-hash protocols or `_vN` copies; combined v2 was allowed as the single last bridge.
  - The primary axis is row-split ΔELPD.
  - Modal was approved, then stopped; local compute only.
  - Then a pause on new experiments. Selecting a model for the app stays Ben's call.

## (b) Lineage
- **Selected fit** (`config/main-analysis.json`): `data/model/chelsea-bayesian-product-scope-structure-20260923`.
  - Spline floor design; bedroom-group random-walk time curves; per-building half-year random walk.
  - Student-t with ν = 5 fixed; 4 × (4,000 + 6,000). Reference ELPD: rows 5,863.7, units 3,822.1.
- **Promoted steps:**
  - bedroom-time curves: +30 ± 9.5;
  - building walk: +825 rows / +380 units.
- **Accepted in screens** (screen log):
  - as-of attribute flags (+121 units);
  - per-unit drift (+51 rows);
  - per-building bedroom slope + estimated ν (≈ 2): +250 / +506;
  - per-building size and 2+/3+ bath slopes (m6 port): +388 / +756;
  - quarterly citywide walk: neutral, but it makes building-walk centering safe;
  - per-building `size_missing` slope (+41 units).
- **Candidates:**
  - **cand2** (all of the above except `size_missing`): +474.7 ± 43.5 rows / +918.7 ± 58.6 units.
  - **cand3** (+ `size_missing`): +470.2 ± 44.3 / +959.8 ± 59.3. Both are screen-grade.
- **Combined v2** (`models/bayesian_combined_experiment.py`, graph v5) is the cand3 spec, the LAST code-hash protocol. It is merged (#4, #6) but **its fit never ran**: held at Ben's pause. It adds a leave-own-row-out fitted rent: PSIS, plus an exact unit-prior draw for units listed once.
- **Withdrawn:**
  - unit-level text flags: later ads carried backward (leak);
  - walk centering without a citywide walk: over-predicted 2021–22 by 1.7%;
  - cMAP results for noise and scale parameters: unreliable.
- **Rejected:** price-level noise; building covariates as row features (collinear with building effects); size × time.
- **Frontier comparison:** the from-scratch m8 + own-ad flags (Student-t unit effects + drift) passes its full gate at +601.7 / +932.7. vs cand3: rows +131.5 ± 28.2, units −27.1 ± 28.4.

## (c) Evaluation contract
- **Row split:** `models/bedroom_time_screen.split`, seed 20260922. 10% of rows, from repeat units only, keeping ≥ 1 training row per unit.
- **Unit split:** `models/structure_screen.split_units`, ~10% of units, keeping ≥ 1 training unit per building. The unseen unit effect is integrated with 200 draws. Drift is set to 0 for unseen units (slightly narrow intervals).
- **References:** `data/model/feature-screen-20260923/nuts-hwalk` and `nuts-hwalk-units`. `heldout.npz` holds `audit_id`, `lpd`, `error` and (from PR #6) `pit`.
- **Pairing:** `models/screen_compare.py`: sum ± sqrt(n)·sd.
- **Gate:** R-hat < 1.01, ESS > 400, no divergences. Screens (4 × 1,000/1,000) are screen-grade.
- **Coverage (cand3):** 95% intervals 94.6% / 93.3%; 80% intervals 79% / 80%.

## (d) Keep vs retire
- **Keep:**
  - `structure_screen.py` + `screen_compare.py`: the fastest honest screen; move them into one self-contained experiment script.
  - The split definitions and references.
  - `bayesian_report_cache` (memmap-streamed unit draws).
  - The PSIS/unit-prior LOO (`loo_quantiles`).
  - `reader_parity_check.py`.
  - Paired ΔELPD.
- **Retire:**
  - hash protocols and `_vN` module chains (graph v1–v5, location terms v1/v2, feature design v2, contract families);
  - `ruff.toml` extend-exclude growth;
  - cMAP screens (except mean-structure triage).
- **Replace:** page readers that re-derive μ per version with a summary-output reader (F6) shared by both lines.

## (e) Open problems and next 3
1. **Decision (Ben):** run combined v2 locally (~8 GB, 8 × 5,000 iterations, 3–5 h; recipe in `docs/model/combined-v2-bridge-2026-09-24.md`), or skip it and build F6 so that m8 can be selected.
2. Switch the page and review queue to `loo_fitted_rent` (the in-sample fitted rent is pulled toward the listing's own ask).
3. Data work: the 110 W 26th pattern (sized lofts and unsized small units both called "1BR"). Add size evidence or a partial-floor unit type. Also the in-ad edit caveat on text flags.

## (f) Lessons and pitfalls
- **Hashed files:** never edit a file hashed by a running or selected fit. Check byte-identity against `<fit>/protocol`.
- **Memory:**
  - ~11 parallel jobs rebooted the box via OOM; keep the total ≤ 10–12 GB.
  - Report stages exceed 6–9 GB; v1 was OOM-killed at 9 GB.
  - Launch via `systemd-run --user -p MemoryMax=…`, because session restarts kill nohup jobs.
  - `/tmp` is a 7.6 GB tmpfs with a quota: set `TMPDIR=/data1/...`. The full test suite must run per file (it accumulates memory).
- **Tests:** exact design reconstruction needs single-thread BLAS.
- **Sampler:**
  - With ν ≈ 2, NUTS is 2–4× slower.
  - Per-building slopes correlate with building levels.
  - Multimodality at 110 W 26th (R-hat 1.53); the frontier's Gibbs sampler needed mode-hop moves.
- **Leaks:** flags must be as-of or own-ad; the within-ad edit caveat remains.
- **Tooling:**
  - Modal screens need `--returned heldout.npz result.json`, and `--input <evidence dir>` for text flags. Forgetting `--returned` lost 5 screens.
  - `pgrep -f` matches its own shell.
  - `jj abandon` with broad revsets abandons other workspaces' working copies.

## (g) Paths
- **Workspace and history:** jj workspace `/home/ben/code/apartments-bedroom-time` (bookmark `bedroom-time-20260922`). Merged PRs #1, #2 and #4–#7; archive tags `archive/pr-N`.
- **Screen outputs:** `data/model/feature-screen-20260923/`.
- **Docs** (`docs/model/`):
  - `screen-log-2026-09-23.md`
  - `research-backlog.md`
  - `combined-v2-bridge-2026-09-24.md`
  - `unit-attributes-experiment-2026-09-23.md`
  - `building-drift-experiment-2026-09-23.md`
  - `fast-screening-2026-09-22.md`
- **Code** (`models/`):
  - `bayesian_combined_experiment.py`
  - `bayesian_structure_graph_v5.py`
  - `bayesian_location_terms_v2.py`
  - `structure_screen.py`
  - `screen_compare.py`
  - `bayesian_attribute_design_v2.py`
- **Large outputs:** `/data1/apartments/model-fits/`.
