# Chelsea row-level review of the bedroom-time fit

September 22–23. Reads the promoted fit
`chelsea-bayesian-product-scope-bedroom-time-20260922` row by row. Deviation =
unit effect + residual (log). Report-only; no source values were changed.
Candidate rows are in
`data/model/point-analysis-20260922/source-review-candidates.csv`.

## Structure the model was missing

- **Building drift over time.** Within a building, era means vary with an
  excess SD of 3.4% beyond noise. This is now modeled; see the
  [building-drift experiment](../model/building-drift-experiment-2026-09-23.md).
- **Unit drift.** For the same unit, the SD of its residual change grows with
  the gap between listings: 0.11 within a year, 0.145 after more than ten years.
  Relistings within a year sit 1.5% below the model (a price-path effect).
- **Noise by segment.** Residual SD is ~0.075 up to the 9th fitted-rent decile
  and 0.116 in the top decile. Building-level noise scales are being screened.

## Omitted unit attributes (description and label evidence)

Share of extreme positive deviations (> +40%) against all rows:

| signal | share of highs | overall | mean deviation when present |
|---|---|---|---|
| unit label starts `PH`/`penthouse` | — | 1,001 rows / 486 units | +15.4% |
| "penthouse" only in text (mostly building lounges) | — | 576 rows | +2.4% |
| duplex/triplex wording | 19.6% | 3.6% | +4.1% |
| explicit *private* outdoor wording | — | 5,671 rows | +3.9% |

Screen results are in the building-drift report.

## Source/scope candidates for review

- **Shared bath / SRO wording**: 62 rows in 7 buildings, mean deviation −16.8%.
  Examples: 335 W 29th St "private studio apt with shared bathrooms" at
  $950–$1,300 (2019–2020); 336 W 19th St "(SRO) single room occupancy apartment
  with shared bathroom" ($1,440, 2022); 131 W 15th St "renovated SRO studio loft
  (sharebath & toilet)". These are not self-contained apartments. The broader
  "room/roommate" wording is mostly false positives ("great for roommates").
- **Extreme deviations above 60%**: 107 rows. Examples: a "studio with 3 baths"
  at $28,681 at 134 W 29th St (2010); three $999–$1,610 studios at
  225 W 23rd St (2026-03, consecutive listing IDs); a $13,000 1BR at
  305 W 20th St (2023).
- **Possible unit identity duplicates**: 291 rows share building, month,
  layout, rent and exact square footage with a different unit. Most are
  legitimately stacked line units (5F/6F, 701/801). About 21 groups (~45 rows)
  have label variants that are probably one apartment, e.g. `ph`/`ph1`,
  `5b`/`unit5b`, `2f`/`2f1`, `7e`/`7ee`, `4`/`4g` (the last at OHM,
  three consecutive months). They should go to the canonical-unit identity
  review; they are too few to move coefficients.
