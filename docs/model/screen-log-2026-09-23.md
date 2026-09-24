# Screening log, September 22–23

Every candidate screened against the promoted model on the declared splits,
with its verdict. Row split: 10% of rows from repeat-listed units (seed
20260922). Unit split: every listing of ~10% of units, with the new unit's
effect integrated over its prior. Unless noted, baselines include the
half-year building walk and screens are conditional MAP. See
[fast screening](fast-screening-2026-09-22.md) for method limits.

| candidate | row split | unit split | verdict |
|---|---|---|---|
| bedroom-group time curves (random walk) | +30.0 ± 9.5 (NUTS) | — | **promoted** |
| bedroom-group linear trends | +6.0 ± 5.1 (NUTS) | — | rejected |
| building random walk, half-year knots | +825.5 ± 45.0 (NUTS) | +379.5 ± 39.3 | **promoted** September 23 |
| building linear slope | +307 | — | superseded by walk |
| building drift + iid building shocks | +732 to +756 | — | not better than walk |
| separate 4+ bedroom time group | −2 | — | rejected |
| estimated Student-t ν | −12.5 ± 14.8 | — | rejected (ν ≈ 4.2–4.5) |
| four unit attributes, unit-level flags | +60.9 ± 15.6 | +142.9 ± 23.2 | **withdrawn**: later ads' text carried backward |
| **four unit attributes, as-of flags** (own ads at or before each listing) | +9.0 ± 19.5 | **+121.2 ± 22.4** | **accepted**: helps new units, neutral for repeat units |
| same, per-advertisement text flags | +16.5 ± 16.6 | +105.0 ± 20.8 | replaced by unit-level |
| convex large-area hinge | +9.8 ± 14.6 | +18.8 ± 13.4 | not credible; revisit later |
| size × time, in-unit laundry × time | −23.1 ± 8.8 | +12.7 ± 4.2 | rejected (inconsistent) |
| building covariates (log floors, log units, unknowns) | cMAP −17.8 ± 4.7; **NUTS +1.5 ± 2.3** | cMAP +25.0 ± 7.9 | neutral on repeat units; σ_building 0.273 → 0.239. R-hat 1.32: row-level covariates nearly collinear with zero-sum building effects; put them in the building-level mean if revisited |
| building-level residual scales | +45.4 ± 29.0 (NUTS) | — | suggestive (1.6 SE); σ_unit 0.082 → 0.070; compare with price-level noise |
| per-unit linear drift (free scale, HalfNormal(0.01)) | cMAP erratic (−16.7 to +52.2); **NUTS +50.6 ± 7.5** | — | **accepted** for the next combined fit; σ 0.050 → 0.049 |
| price-level residual scale | -17.7 ± 13.4 (NUTS) | — | rejected |

Building covariates come from archived StreetEasy building pages
(`data/model/building-covariates-20260923/buildings.csv`; 1,072 of 1,129
buildings with floors and units). The archive's `yearBuilt` is a placeholder
for most buildings (1910: 58%, 1900: 23%), so it is not used.
