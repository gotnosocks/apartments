# Simplify-model thread (branch `t3/simplify-model-fit`)

Ben, 2026-11-22: make the drift model smaller, simpler and cheaper to fit while keeping held-out
elpd, median error, coverage and the gate. Up to $50 on Modal. Mid-turn: the three fits a model
needs (latest, market, as-of backtest) multiply cost by 2 to 3; he is open to changing the model
to need one. That is the top item.

## State (2026-11-22 23:40 ET)

- One fit instead of three: done at screen size. Variant D (open ads plus latest rows a year
  or more old from apartments with no open ad) costs the open ads −11.6 ± 5.8 nats at k5,
  keeps median error and coverage, gives a monotone validity table on 26k rows, and selection
  on those rows keeps nearly all its z. Now `splits.one_fit_split` (`--split onefit`).
  Report: `docs/notes/one-fit-2026-11-22.html`; note `docs/notes/one-fit-protocol-2026-11-22.md`.
- The competitor thread (wt-simplify) has a `unified` split (open + 2% latest, no age filter)
  and full fits running (`c1-compact-uni-*`, 2 containers). Reconcile with it: keep the age
  filter. My message to that session never delivered (permission modes differ).
- Cost arms rejected (`docs/notes/cost-arms-2026-11-22.md`): coarser building paths cost
  500–1,400 nats; no_slow saves 5%.
- Gate on fewer draws (u5-svgpmo-lat traces): pass at 6×2,000 and 4×2,600; fail at 6×1,600.
- Container memory reservation (192 GiB, ~$1.90/h of $6.45/h) unmeasured: a candidate saving.

## Next

PR this branch. Then the plumbing so Deals, Today and Diagnostics read one onefit run's two
subsets, and one full onefit fit that passes the gate, unless the competitor's unified
plumbing lands first, in which case add the age filter to it.
