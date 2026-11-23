# One full fit on the one-fit split (2026-11-23)

The k5 screens (`one-fit-protocol-2026-11-22.md`) chose variant D, now
`splits.one_fit_split` (`--split onefit`, master b7f7036d). This note covers the first full
fit on that split: does one fit pass the gate at full length, at about the cost of one of the
three it replaces?

## Fit

- Code: b7f7036d. Model: `drift-building-phase-unitkn-ablate --variant
  layrng,size,sv_gp_mo,marks`, the u5-svgpmo candidate unchanged.
- Data: `b0-ddd2fe8f5da041b8-alldata-dense-nyc-asof-20251110-bedtext`, the same dataset the
  u5-svgpmo market fit used. Its open ads carry their final asks.
- Split `onefit` holds out 143,120 of 1,763,952 rows: the 9,346 open ads and 133,774 latest
  rows a year or more old from apartments with no open ad. The market split held out only the
  open ads.
- Shape: 2 Modal containers (H200, `--large --no-summary`) × 2 chains × (500 warmup + 2,600
  draws), keep every 30, seeds 1 and 2. The draw-count check on the u5-svgpmo-lat traces
  passed at 4 × 2,600 (R-hat 1.0076, ESS 680). It failed at 6 × 1,600.
- Labels: `u5-of-a` and `u5-of-b`. The gate is judged on the 4 chains combined, as for the
  3-container fits.

The one change from the u5-svgpmo market fit is the split. The chain and draw counts are set by
the draw-count check, not tested here.

## Predictions (written before launch)

1. Gate: the 4 chains combined pass (max split R-hat ≤ 1.01, min bulk ESS > 400). P ≈ 0.75.
   If they fail, the first suspect is `drift_tau` or `sigma[0]`, the slowest scalars in the
   screens.
2. Time: about 4,000 s of fit per container (u5-mkt: 1.5 s a warmup sweep and 1.23 s a draw
   on H200, with 7% fewer training rows here). Wall about 4,200 s.
3. Cost: about $7.5 a container, $15 for the fit. Today's three fits per model (latest,
   market and backtest, 3 containers each) cost about $45 to $55.
4. Open-ad elpd against the u5-svgpmo market fit, paired on the 9,346 open ads: between −100
   and +20 nats, central −50. At k5 the loss was −11.6 ± 5.8 on 1,891 ads, about −0.006 a
   row. Median absolute error within 0.002 of the market fit. 80% coverage within 0.01.
5. Validity on the old latest rows (`drift_deals.validate` read on the held-out latest rows):
   monotone, Spearman ≥ 0.9 for days on market and for share cut, as at k5 (0.98 and 1.00).

## Result (2026-11-23 03:30 ET)

Pooled run `drift-building-phase-unitkn-ablate-b0-onefit-b7f7036d-u5-of` (`drift_pool`, from
`-u5-of-a` and `-u5-of-b`). Scores: `/data1/apartments/tmp/one-fit-2026-11-22/full_score.json`.

| | u5-svgpmo market fit (3 containers, 6 × 1,800) | one fit (2 containers, 4 × 2,600) |
|---|---|---|
| gate | pass, R-hat 1.0069, ESS 810 | **pass, R-hat 1.0072 (phase_factor[35]), ESS 788 (unit_sd)** |
| open ads: elpd (9,346) | 10,249.7 | 10,224.8 (**−24.9 ± 8.7 paired**) |
| open ads: median abs error | 0.0464 | 0.0464 |
| open ads: RMSE | 0.1015 | 0.1016 |
| open ads: coverage 50/80/90/95 | 0.504/0.788/0.889/0.951 | 0.498/0.788/0.889/0.951 |
| open-ad validity, Spearman days / cut | 1.00 / 1.00 | 1.00 / 1.00 |
| old latest rows (133,774): elpd | not held out | 165,191; median abs error 0.0413; 80% coverage 0.797 |
| old-row validity, Spearman days / cut | – | 0.99 / 1.00 |
| fit time per container | ~3,357 s | 3,961 s |
| cost | ~$19 (3 × $6.3) | **$14.46** (2 × $7.23) |

Each container alone missed ESS 400 (347 and 404); pooled, the four chains pass with room.
After the fit, each container's `variance` post step failed (`model.MODELS` has no ablate
model). The exit code 1 comes from that, not from the fit.

Predictions scored:

1. Gate passes: **right.**
2. ~4,000 s a container: **right** (3,961 s).
3. ~$15: **right** ($14.46).
4. Open-ad elpd between −100 and +20, central −50: **right**, −24.9 ± 8.7, smaller than the
   k5 rate (−0.0027 a row against −0.006). Median error and coverage are unchanged.
5. Monotone validity on the old latest rows: **right** (0.99 and 1.00).

So one $14.5 fit gives what three fits gave (selection rows, the Deals fit, validity) for
25 nats on 9,346 open ads, about 0.003 a row. That is under 3 SE, and smaller than most
term changes the project tests. Today's three fits per model cost about $45 to $55.

## What it leaves

- The selection rows here are the old latest rows of the market dataset, not the latest
  split of the newest dataset. A model compared on them is compared on ads at least a year
  old. The k5 table (`one-fit-protocol-2026-11-22.md`) showed selection keeping its z on
  them.
- The pages still read three runs. Wiring Deals, Today and Diagnostics to one run's two
  subsets is in the competitor thread's PR #1538 (for `unified` and `onefit`).
