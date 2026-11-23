# Simplify-model thread (branch `t3/simplify-onefit-2`)

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

- 2026-11-23: the competitor's one-fit full fit (`...-b0-unified-7c95e5b8-c1-compact-uni-{a,b}`,
  compact model, open + 2% latest, 2 containers × 2 chains × 2,000 draws) passes the gate on
  its 4 chains combined (`scratchpad/combine_gate.py`): max R-hat 1.0096, min ESS 642. Each
  container took ~3,050 s, so about $11 for the fit, against ~$28 for one 3-container fit
  before and three fits per model.

- 2026-11-23 03:30 ET: the full onefit fit passes. `...-b0-onefit-b7f7036d-u5-of` (pooled
  from `-a`, `-b`; u5-svgpmo model; 2 containers × 2 chains × 2,600): R-hat 1.0072, ESS 788,
  open ads −24.9 ± 8.7 against the 3-container market fit, median error and coverage the
  same, validity monotone on 133,774 old rows, $14.46. Note `docs/notes/onefit-full-2026-11-23.md`.
  Each container's `variance` post step fails on ablate models (`model.MODELS` KeyError);
  harmless, the fit is complete. Modal spend so far about $19 of $50.

- Fewer draws on the u5-of traces (4 chains): 2,600 pass (1.0072/788), 2,300 pass, 2,000
  pass (1.0087/576), 1,800 FAIL (R-hat 1.0123 unit_sd), 1,600 pass (1.0085/427). R-hat near
  1.01 is noisy in the draw count, so keep 2,600: a failed fit costs more than the ~$2.5 saved.
- serve/master had stopped following master (all `apartments-*` timers disabled since about
  the Nov 15 cutover). Moved it to origin/master by hand 2026-11-23 03:40 ET; check it before
  each launch (`git -C /data1/apartments/serve/master log -1`).

- 2026-11-23 04:40 ET: memory probe (`...-fe4930e7-mem-probe`, $1.09) peaked at 14.8 GiB
  (`ru_maxrss`) on the full onefit design. #1541 merged: `ops/modal-fit --large --lean`
  reserves 48 GiB for a baseline's fit with no in-container scoring ($5.30/h on an H200 in
  place of $6.45; about $2.6 off a two-container onefit fit). Use `--lean` on drift fits.
- 04:46 ET: probe `chains4-probe` (4 chains in one lean container, 20 + 20 sweeps) against
  mem-probe's 1.610 s a 2-chain sweep. If r = 4-chain/2-chain sweep time is at most 1.7, run
  full onefit fits as one 4-chain container. Note `docs/notes/four-chains-one-container-2026-11-23.md`.
  Result: r = 1.94 (3.131 s against 1.610 s), so keep two containers; the lean container ran
  in 15.3 GiB. Modal spend about $22 of $50.

- 05:25 ET: H100 lean probe: h = 1.117 against the H200 (`docs/notes/h100-lean-2026-11-23.md`);
  same cost a sweep within noise, so stay on H200s (H100 as a fallback). Modal spend about
  $23 of $50. Cost levers left: design prep (about 350 s a container, paid twice), warmup.

- 05:45 ET: where a lean container's 4,037 s goes (`u5-of-a` `result.json`): prepare 190, compile
  119, warmup 666 (500 sweeps), sampling 2,836, the rest about 225. A prepare or compile cache
  saves nothing, because both containers run them at the same time. Warmup 300 in place of 500
  would save about $0.8 a fit (the scales are flat from sweep 100; `amp` and the phase factors
  settle by about sweep 200); try it on the next onefit
  fit that runs anyway. A lean onefit fit costs about $11.9. The `variance` post-step failure
  appears only on `u5-of`; the later probes ran no post step, so nothing to fix. A message to
  the session `tmp-95` about #1538 was held undelivered (permission modes differ).

## Next

Pages read one run: PR #1538 (competitor, `feat/simplify-model-discovery`) wires Deals,
Today and Diagnostics for `unified` and `onefit`. Watch it; if it stalls, build the onefit
part here. Read-only check of #1538 for onefit (2026-11-23 03:40 ET): subsets right, master's split
untouched, no leak. But its `drift_deals.validate` still reads the open ads, which have
outcomes only on a backtest dataset, so a onefit run on today's market data gets no validity
table. Once #1538 merges: make validate read a onefit run's closed held-out rows (first ask,
days on market and cuts from the ads table, as `scratchpad/onefit_score.py` did; 0.99/1.00
on u5-of). Also `drift_deals.py:686` labels a onefit summary "unified", and
`test_unified_split.py` never tests onefit. Then candidates for less cost: the 192 GiB container reservation, and the
`variance` post step's failure on ablate models.
