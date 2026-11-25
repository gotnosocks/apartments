# Dual-Model Training Data Quality Sprint (2026-11-24)

Full interactive/visual report (self-contained HTML with embedded inline SVGs): [data-quality-sprint-2026-11-24.html](data-quality-sprint-2026-11-24.html).

## Summary

- **Ledger additions (`1,162` entries across `1,134` unique live kept rows; `0` overlap, `0` stale `when` mismatches, `139/139` pipeline tests passing):**
  - `pipeline/ledger/2026-11-24-queued-audited-imports.ndjson`: **404 entries** (`285` excludes + `119` zero-bed repairs) reconciling the previously audited Nov 20–21 candidate files.
  - `pipeline/ledger/2026-11-24-dual-model-dq-sprint.ndjson`: **758 entries** across `730` unique listings (`402` excludes + `356` peer-backed `set` repairs: `322` bathroom typo repairs, `28` unanimous `70-pine-street` `4br/3.5ba` feed-batch repairs, `5` tenfold/ask-pasted `square_feet` repairs, `1` standalone bedroom repair).
- **Upstream extractor & unit-key code fixes (`54/54` unit tests passing):**
  - `frontier/src/rentfrontier/b0bedtext.py`: fixed `wellbeats` (`146` FPs), `STUDIO_SIZE_OF` simile (`131` FPs), ordinal flex wording (`353` hits), and lead-line priority over building-wide inventory (`32/32` tests in `frontier/tests/test_b0bedtext.py`).
  - `pipeline/models/analysis/label_units.py`: added `label_key_v18` (strictly scoped to `unit-labels-v18`, freezing `v17`) for trailing `APT`/`UNIT` and `0phb -> PHB` (`22/22` tests in `pipeline/tests/test_label_units.py`).
  - Full-dataset audit of `b0textflags` (`1,901,222` rows): `shared_space` `30,296 -> 342` (`-30,032` FPs, `99.1%` legacy FP rate); `income_restricted` `1,732 -> 2,753` (`+1,198` gained, `-177` FPs).
- **Leak-free shared-row validation (`$0.00` Modal spend, paired 3-arm `T2_LightGBM_StudentT_LSS`, building-clustered SE):**
  - `onefit2026` (`149,539` shared clean closed held-out rows): Total `ΔELPD = +222.1 ± 413.0` (`z = +0.54`) = `-259.8 ± 493.4` (training cleaning) + `+482.0 ± 341.1` (text v2).
  - `asof2025` (`9,344` shared clean causal open ads on 2025-11-10): Total `ΔELPD = +11.7 ± 57.1` (`z = +0.21`) = `+50.6 ± 58.4` (training cleaning) + `-38.8 ± 39.7` (text v2).
