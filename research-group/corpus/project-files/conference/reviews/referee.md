# Skeptical referee review (reviewer subagent, 2026-10-22)

**Recommendation: major revision.** The floor result holds up. The headline table mislabels and rehabilitates a run that failed its own gate, the location "exception" doesn't show up where it should, and the abstract states coefficient precision that §6 and §7 say is false.

## Claims most likely to fall apart

1. **Table 1's model path.** The "+ gym −11 (3)" row was really "drop truck route, add gym", and that run failed the gate (R-hat 1.0149, ESS 415; gym note l.42–47). Under §4 it should not be in the table. The next row, "+32 (18)", also puts truck route back, and at 1.7 SE it is under the paper's own 2 SE bar, yet the terms are kept. Row 2 ("+9,818 (≈160)", 0.1244) isn't in any of the notes. Settle: relabel the rows, drop or rerun the failed fit, give an exact SE.
2. **"Only park frontage improves forecasts" (abstract).** The +187 (80) is 2.3 SE, but the park-facing ads themselves gain only +51.6 (SE 66.6). Most of the gain is on the other 179k ads, through shifted distance coefficients. It also fails the permutation null, which the abstract leaves out. It is the best of about five features tried on one building split, with 40 m picked after a residual screen of 30/40/60 m. Settle: a fresh split or repeated building folds, the permutation result in the abstract, and a correction for the number of features tried.
3. **Abstract precision ("±0.5", "6.26 to 6.39").** The audit finds biases of 0.1 to 0.7 points, larger than these interval half-widths, and coefficient coverage of 69 to 81%. Settle: widen the intervals using the audit or a bootstrap over buildings, or drop the interval claims from the abstract.
4. **RE-to-Mundlak "ranges".** §6 shows the random-effects ends are biased upward, so presenting both as equally plausible goes against the paper's own evidence. Report the Mundlak figure for unit terms.
5. **Floor curve shape.** "+13.8% at 40" is a local bump: floors 41 and 42 are lower (13.2, 13.1). Nine neighbouring-floor dips and a 4-point jump at the 47+ cap are artifacts of the nugget and the cap. "Calibrated" hides penthouse coverage of 78.8%, and 85 to 88% at floor 1, 40+ and top floors.
6. **Smooth distances "relabel the surface".** The +26 (116) and the −0.97 correlation are not in the notes. The location note says the coefficients are stable across single and combined fits, not "across splits". Settle: cite the run.

## Inconsistencies

- The floor gain breakdown (1,972 + 911 + 706 = 3,589) exceeds the 2,945 total; groups overlap and unknown-floor elevator ads lose 202.
- "Seven named location features": Table 2 lists six distances plus four step features.
- "Large park" in the abstract means ≥5 acres, but "big park" in §5.5 means 30+ acres.
- Retail shrinks by 56% under Mundlak, outside "a sixth to a half".
- The size bias is in elasticity ×100 next to laundry's bias in % rent; mixed units.
- Baseline RMSE 0.1172 in the notes, 0.1173 in Table 1.
- Table 1's coverage column mixes 68 and 400 draws.
- 92.7% coverage on the building split is over-coverage, so "calibrated" holds only for the latest split.

## What it does well

Predictions are written before each fit and misses are reported as misses, and the simulation audit is turned on the paper's own coefficients. Section 7's limitations are better than most.
