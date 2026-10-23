# Park frontage by line, by floor and against placebo frontages: results, 2026-10-23

I ran the design of `park-placebo-predictions-2026-10-23.md` as written there after review (commit 4b1ea29f). The script is `park-placebo-2026-10-23/park_placebo.py`, and its output is `park-placebo-2026-10-23/results.json`. Every fit is OLS on log latest ask, with month and bedrooms-by-full-baths fixed effects, standard errors clustered by building and ISO week, and 200 permutation draws (seed 20261023). Coefficients are percent premiums, 100 (exp(b) - 1), with 95% intervals. Differences between fits are in log points, or in percent points where I set them against a permutation null drawn in percent points. The whole run took 11 seconds on CPU.

## Results

Objection 8, inside buildings (building fixed effects, floor bins as controls). The null shuffles view marks a unit at a time within the building, or line marks among the building's lines.

| fit | ads | buildings | premium | 95% interval | null 2.5 to 97.5 |
|---|---|---|---|---|---|
| 1, ad's view mark, park-facing | 58,888 | 1,118 | +6.7% | 5.0 to 8.5 | -0.5 to 0.6 |
| 1, line's view mark, park-facing | 19,558 | 311 | +10.5% | 7.5 to 13.5 | -1.9 to 1.6 |
| 2, ad's view mark, 40 to 200 m | 252,085 | 8,131 | +4.0% | 3.1 to 5.0 | -0.4 to 0.5 |

The line mark sits 3.5 log points above the ad mark, and the park-facing view mark sits 2.5 log points above the nearby one.

Objection 9, floor (building fixed effects, floors 0 to 2 as the base). The first column is the park-facing flag against nearby buildings' floor gradient. The second is the view mark within park-facing buildings, whose base-floor premium is +3.1% (1.5 to 4.7).

| floors | park-facing by floor | view mark by floor |
|---|---|---|
| 3 to 5 | +1.9% (0.8 to 3.0) | +2.4% (0.6 to 4.2) |
| 6 to 10 | +2.0% (0.6 to 3.5) | +4.7% (2.0 to 7.5) |
| 11 to 20 | +3.0% (1.4 to 4.6) | +5.8% (2.5 to 9.2) |
| 21 up | +8.9% (5.4 to 12.6) | +8.0% (2.8 to 13.5) |
| 11 up, pooled | +4.9 log points (3.0 to 6.8) | +6.3 log points (3.1 to 9.6) |

Across buildings (150 m cell fixed effects, cells holding both kinds of building). The null shuffles the front flag among buildings of a cell.

| fit | ads | buildings | front premium | 95% interval | null 2.5 to 97.5 |
|---|---|---|---|---|---|
| 3, park-facing, non-view ads | 104,661 | 3,827 | +9.2% | 6.4 to 12.1 | -2.3 to 2.7 |
| 5, park-facing, all ads | 119,577 | 3,972 | +12.8% | 9.8 to 15.8 | -3.1 to 2.9 |
| 5, prestige avenues | | | +22.1% | 16.1 to 28.5 | -6.0 to 5.6 |
| 5, other park-facing | | | +10.5% | 7.3 to 13.8 | -3.0 to 3.5 |
| 6, rail | 5,874 | 151 | +4.9% | -1.6 to 11.7 | -5.4 to 5.8 |
| 6, cemetery | 352 | 62 | -6.4% | -13.1 to 0.8 | -11.1 to 12.5 |
| 6, expressway | 52,793 | 2,119 | +3.8% | 0.2 to 7.5 | -5.7 to 4.8 |

The prestige avenues sit 10.0 log points (4.3 to 15.7) above the other park-facing buildings. In percent points the gap is 11.7, against a null running from -6.8 to 6.4. The other buildings keep 0.499 of the avenue gap in log terms. The park gap of fit 5 exceeds the rail gap by 7.3 log points (SE 3.5), the cemetery gap by 18.6 (SE 4.0) and the expressway gap by 8.3 (SE 2.2), with the two SEs combined as if independent.

## Against the predictions

1. Fit 1, ad-level view mark at 2% to 6% with an interval excluding 0, beyond the null: miss. The estimate is +6.7% (5.0 to 8.5), clear of the null but above the range.
2. Fit 1, line mark above the ad mark, at 3% to 9%: miss. It comes out above the ad mark, but at +10.5% it is above the range too.
3. Fit 2, nearby view mark at 1% to 5% and below fit 1: hit, at +4.0%, 2.5 log points under fit 1.
4. Fit 3, non-view gap at 1% to 3.5%: miss, at +9.2%. So the implied view share of 8% to 76% has no meaning here, because the gap exceeds the model's whole building premium of 3.8 to 4.2.
5. Fit 4, park-facing premium on floors 11 up above floors 0 to 2 by 1 to 5 points, interval excluding 0: hit, at 4.9 log points (3.0 to 6.8).
6. Fit 4, view mark's pooled 11 up interaction positive: hit, at 6.3 log points (3.1 to 9.6).
7. Fit 5, prestige avenues at 4% to 9%: miss, at +22.1%.
8. Fit 5, other park-facing buildings at 1.5% to 4.5% with an interval excluding 0: miss. The interval excludes 0, but the estimate is +10.5%.
9. Fit 6, rail at -4% to +2% with an interval including 0: miss. The interval includes 0, but the estimate is +4.9%.
10. Fit 6, cemetery at -6% to +3%: miss, at -6.4%. I said I wouldn't read it as a test, and its SE came out near 4 points.
11. Fit 6, expressway at -4% to -0.5%, below the park gap by more than 2 SE: miss. It sits 3.7 SE below the park gap, but the estimate is +3.8%, above 0.

That gives 3 hits and 8 misses. The prestige criterion of fit 5 lands between its two thresholds: the other buildings keep 0.499 of the avenue gap in log terms (0.47 in percent terms). That falls just short of the half I set as counting against prestige, and well above the quarter I set as counting for it, so I score it as neither. The closing condition doesn't apply: the line coefficient is +10.5%, far from zero.

I made no change to the design after seeing results.

## Reading

Inside buildings the predictions got the direction right and the size too small. A unit marked as facing the park asks 6.7% more than other units in its building, and a view line asks 10.5% more. The ad-level view premium grows with height, and so does the premium of the park-facing building as a whole: on floors 21 up it carries +8.9% over nearby buildings' gradient. I didn't interact the line mark with floor. A premium that rises with floor and sits in the lines facing the park looks like a view, and these fits don't support reading it as prestige alone.

Across buildings every gap is far larger than the model's +4.2. A cell fixed effect compares a park-facing building with whatever stands behind it, with no control for age, size, elevator or doorman, so these gaps carry building quality along with the park. The placebos point the same way: buildings on rail land and on expressways ask more than their neighbors, not less. Many expressway buildings stand on the Hudson and East River waterfront, and the rail group includes 35 Hudson Yards, so their premium may come from water views and new construction. I read fits 3, 5 and 6 as differences in housing stock. Park frontage exceeds each placebo by 7 to 19 log points: rail by 7.3 (z 2.08), expressway by 8.3 (z 3.73) and cemetery by 18.6 (z 4.64). These z values combine the two SEs as if independent, although the park and placebo samples share ring buildings and week clusters. The placebos also sit in different neighborhoods from the parks (Bushwick, Prospect Heights, the waterfront), so the gaps between them still carry housing-stock differences, and I don't read them as the park's effect.

The prestige avenues ask twice the gap of other park-facing buildings, and the other buildings keep about half of it. With the cross-building fits mixing building quality in, I don't take that split as evidence for or against prestige. The within-building fits answer objection 8, and they come out in favor of a view premium, larger than I predicted.
