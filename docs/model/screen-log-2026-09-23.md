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
| per-building bedroom slope s_b·(min(beds,4)−1), τ ~ HalfNormal(0.1) (from-scratch session's ablation) | **+196.7 ± 29.1** (NUTS) | — | **accepted**; τ ≈ 0.11 |
| estimated ν, on the building-walk model | **+56.4 ± 22.2** (NUTS) | — | **accepted**; ν ≈ 1.9 (the earlier rejection, ν ≈ 4.3, predates the building walk) |
| bedroom slope + estimated ν | **+249.9 ± 35.6** (NUTS; +53.3 ± 22.3 over slope alone) | **+505.5 ± 40.5** | **accepted** for the next candidate; matches the from-scratch m5 (+501.9 ± 40.9 on units) |
| per-building size and 2+/3+ full-bath slopes + bedroom slope + estimated ν (from-scratch m6) | **+388.0** (Σ 6,251.7; unpaired) | **+756.3** (Σ 4,578.4; unpaired) | **accepted**; reproduces the from-scratch m6 (+400.1 ± 42.5 / +765.9 ± 55.5); ν ≈ 2.05–2.10 |
| quarterly citywide random walk | −0.3 (unpaired) | — | neutral |
| **full combined v2 spec** (m6 + ν + citywide walk with centered building walks + per-unit drift + as-of flags) | **+474.7 ± 43.5** (paired) | **+918.7 ± 58.6** (paired) | **candidate** for the combined v2 protocol fit; ν ≈ 2.0. Rows run: one building (110 W 26th) bimodal, R-hat 1.53; see note |
| quarterly citywide walk + building walks centered across buildings | +2.5 (unpaired) | +3.1 (unpaired) | **accepted as an efficiency change**: with the citywide walk, centering no longer biases 2021–22; sampling 1,403 s vs 1,846 s |

Building covariates come from archived StreetEasy building pages
(`data/model/building-covariates-20260923/buildings.csv`; 1,072 of 1,129
buildings with floors and units). The archive's `yearBuilt` is a placeholder
for most buildings (1910: 58%, 1900: 23%), so it is not used.

NUTS screens (Modal, 4 × 1,000/1,000) mix only loosely: R-hat 1.02–1.05 and
minimum ESS 56–153 on the slowest global scale. Paired ΔELPD is much less
sensitive than individual parameters, and these results reproduce the
from-scratch session's independent fits within one SE.

The m6 and citywide-walk screens (Modal runs `20260923T214835Z-nuts-m6-rows`,
`…214847Z-nuts-m6-units`, `…215613Z-nuts-cw2-rows`, `…215627Z-nuts-cwc2-rows`,
`…215639Z-nuts-cwc2-units`; commits 081a6d5 / c2d32d8) finished, but were
submitted without `--returned heldout.npz result.json`, so only the summed
ELPD survived, in the runner log. Their differences above are unpaired
(against the references' sums). The full next-candidate spec is being
rescreened with per-row scores (`nuts-cand2-{rows,units}`).

**110 West 26th Street (data finding, September 24).** In the full-spec rows
screen, this building's level, bedroom slope and size slope did not mix
(R-hat 1.53, ESS 7). The building mixes full-floor lofts of about 1,600 sq
ft, listed as studio through 3BR at $5,000–8,400, with small front/rear
units (5F, 5R, 3R, 3) listed as "1 bedroom" with no size at $2,395–2,595.
With size missing, the small units look like median-size one-bedrooms. With
ν ≈ 2, either group can be treated as outliers, which gives two posterior
modes. The unit-split screen mixed (R-hat 1.017). Remedies, if the protocol
fit shows it: size evidence for the split units (the descriptions say
"one bedroom" but give no area), or a unit-type flag for partial-floor
units in loft buildings.
