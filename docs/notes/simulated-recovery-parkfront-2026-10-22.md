# Simulated recovery of park frontage: results, 2026-10-22

I fit `building-zones-parkfront` on rents I drew from the park frontage fit's own medians
(`sim-parkfront-fitted-20261022`, made with `python -m rentfrontier.simulate make` at seed
20261023), at the code of #1227 (752f6fb4). I used the whole-building split and the night's
settings: 4 chains, 300 warmup, 1,000 sweeps with every 5th kept, seed 20261021, fit-only. The
run is `building-zones-parkfront-b0-buildings-752f6fb4-dense-w1000`. The `ops/modal-fit` log
gives 17.3 minutes for its fit stages and a Modal cost estimate of $0.72. The predictions are in
docs/notes/simulated-recovery-parkfront-predictions-2026-10-22.md, and the explainer is
https://claude.ai/artifact/TxV4ULdAbT2yc1V5p6wmo4.

In the folder `simulated-recovery-parkfront-2026-10-22`:

- `score.json` is the output of `python -m rentfrontier.simulate score`.
- `leak.py` compares the fitted map and the fitted building levels with their truths over
  buildings with training rows, for park-facing buildings and the others in each zone. Its
  output is `leak.json`. `leak-source.json` is the same check run on the source fit itself,
  where the building levels match the truth exactly and the map differs only by taking the
  median of the surface instead of the surface of the median.

All numbers are in points of log rent x100.

## Against the predictions

| prediction | result | |
|---|---|---|
| passes the gate, in 16 to 24 minutes | max R-hat 1.005, min ESS 761 (`amp[outer]`), 17.3 min | held |
| 90% interval of `bld:park_front` covers 3.46, median within 0.6 | 3.54, interval 2.75 to 4.27 | held |
| the six smooth location terms cover their truths | all six covered, and `bld:log_height` too | held |
| 90% coverage across all scalar terms between 80% and 97% | 69% (87 of 126) | missed |
| park-facing map error less the zone's other buildings, under 0.5 | -0.04 (Manhattan), 0.00 (outer) | held |
| park-facing building-level error, under 0.5 | 0.11 (Manhattan), 0.02 (outer) | held |

The chains agree on the park term: their medians are 3.55, 3.51, 3.50 and 3.63.

## The park step

The fit returns 3.54 for a planted 3.46. Over park-facing buildings with training rows, the
fitted map and building levels together come out 0.005 above their truths in Manhattan (514
buildings, 45,249 rows) and 0.10 above in the outer zone (488 buildings, 8,807 rows). The map
error at park-facing buildings differs from the error at the zone's other buildings by -0.04 and
0.00, and the building-level error differs by -0.10 and -0.08. So when rents carry a 3.5-point
step at the first row facing a large park, the model puts it in the column and not in the map or
the building levels.

The smooth terms come back as well. Big-park distance returns -1.96 for a planted -1.87, park
distance 0.33 for 0.36, and water, the loosest again as in #1215, -1.46 for -1.68 with an
interval from -2.75 to -0.26. Both map amplitudes cover the source fit's values.

## The coverage miss

39 of the 126 scalar terms fall outside their 90% intervals, a coverage of 69%, against 82% in
the location recovery (#1215). The misses are almost all unit-level terms with very narrow
intervals: the bedroom and bath steps, the floor curves and floor flags, size, laundry and the
dishwasher. For example, `bed>=1` returns 22.75 for a planted 22.85 with an interval 0.09 wide,
and `unit:log_size_rel` returns 25.84 for 25.38 with an interval 0.20 wide. 36 of the 39 misses
are off by under 0.5 points. The largest is `bed=5:full>=3`, 1.0 points off, followed by
`bld:condo` at 0.52. The location recovery missed many of the same terms, so I read this as
intervals on the row-level terms running too narrow in both recoveries, worse on this draw. I
haven't checked whether the whole-building split, the source fit or the simulation seed accounts
for the difference between 82% and 69%. None of the missed terms is a location column.

## Reading it

When rents carry a step of the size the park frontage fit found, the model recovers it and
doesn't hide it in the map or the building levels. This recovery doesn't test the opposite case,
whether the model would find a step in rents without one. This recovery and the held-out result in
docs/notes/building-zones-parkfront-2026-10-22.md (+187, SE 80) both support the column. The
explained-share test is still short of its null, so the column doesn't meet the evaluation rules'
bar for a building-level feature yet.

## Selection

The fit ran on simulated rents, so it doesn't bear on serving, and the served model stays as it
is.
