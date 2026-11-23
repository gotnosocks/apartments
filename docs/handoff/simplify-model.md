# Simplify-model thread (branch `t3/simplify-model-fit`)

Ben, 2026-11-22: make the drift model smaller, simpler and cheaper to fit while keeping held-out
elpd, median error, coverage and the gate. Up to $50 on Modal. Mid-turn: the three fits a model
needs (latest, market, as-of backtest) multiply cost by 2 to 3; he is open to changing the model
to need one. That is the top item.

## State (2026-11-22 23:00 ET)

- One fit instead of three: `docs/notes/one-fit-protocol-2026-11-22.md`. A/B/C scored. Holding
  out the latest rows costs Deals 36 to 53 nats on 1,891 open ads at k5, because the latest
  split takes 27–29% of the last year's closed ads. Variant D (hold out only latest rows a year
  or more old) launched as `of-d-old` (`modal-fit-20261122-225042-8797`); score with
  `scratchpad/onefit_score.py of-a-mkt of-d-old` (copy in this note's history if the scratchpad
  is gone).
- Cost arms: `docs/notes/cost-arms-2026-11-22.md`, model `drift-building-phase-unitkn-cost`
  (bld_semi, bld_annual, no_slow). First launch failed on argument parsing (fixed in bdb61181);
  relaunched as `modal-fit-20261122-2248{40,55}`, `-224911`. Anchor `of-c-both`.
- Draw count on the last served-candidate full fit (u5-svgpmo-lat, 6 chains × 2,600): the gate
  still passes at 6 × 2,000 (max R-hat 1.0091, min ESS 777) and at 4 × 2,600 (1.0076, 680);
  fails at 6 × 1,600 (1.0129). So a full fit could use 2 containers instead of 3 (−33%) or
  2,000 draws (−23% of sampling), each with a thin margin on one trace.
- Large H200 containers reserve 8 CPUs and 192 GiB (`ops/modal/app.py`), about $1.90 of
  $6.45 an hour; peak memory is not recorded. A smaller reservation is a candidate saving.
- The message to the competitor thread (tmp-95) did not deliver (permission modes differ).

## Next

Score D and the cost arms, write both notes' results, then a Ben-facing HTML report and a PR
(reviewer on the default model: it touches model and ops code).
