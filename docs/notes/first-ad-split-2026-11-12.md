# The first-ad phase split in two (F1, withdrawn before any fit)

## Withdrawn for look-ahead

Ben withdrew F1 on 2026-11-12 at 16:24 ET, before any launch, and I removed the module,
its tests and its registry entries (#PRNUM). F1 sorts an ad with no earlier ad into
`first` or `only` by whether the unit gets listed again later. That isn't known while the
ad is live. A market ad scored on its day always reads as `only`, so in training the
label separates units by their future, and at prediction it carries no information. The
latest split hid the problem because none of its held-out ads falls in either phase.

A replacement noise factor for units with no history has to use only what is known when
the ad opens. `docs/TODO.md` lists candidates. The rest of this note is the design and the
predictions as written before the withdrawal.

F1 is `drift-building-phase-first`, the phase model L1 with its "none" phase split by
whether the unit has more ads in the dataset:

- `first` holds a unit's first ad when at least one more ad of the unit follows.
- `only` holds the unit's only ad, and every row with no unit_id.

Every other phase stays as L1 has it, with 10 to 13 months as the reference. The change
follows from `docs/notes/first-ads-and-quick-returns-2026-11-12.md`. Under L1 the "none"
factor came out at 1.64. Units with a single ad hold 57% of those rows and show 2.6 times
the later phases' share of rows beyond 6 scales, against 1.6 times for first ads with later
ads. If the outlying single ads drive the factor up, giving them a factor of their own
should leave the other first ads near the later phases.

A row counts its unit's ads over the whole frame, held-out rows included, as L1 reads the
previous ad over the whole frame. That is information about which ads exist later and
nothing about their prices. The latest split holds out the last ad of units with at least
two ads, so every held-out ad has a previous ad, and none falls in `first` or `only`. The
split reaches held-out ads only through `sigma`, the other phases' factors and the levels.

Whether an ad is `first` depends on the future: the unit gets listed again. Units first
listed near the end of the frame mostly land in `only` because the frame ends before they
can come back, so the `only` factor partly measures that cutoff. An open ad scored as of a
day has no later ad yet and lands in `only` too. Before reading the `only` factor as a
property of single-ad units, or putting F1 behind the Deals page, I would count units by
how close their first ad sits to the end of the frame.

## The fit

It runs the same as L1: two H100 containers of two chains each, at L1's settings, on the
closingraise dataset with the latest split, seeds 21 and 22, labelled f1a and f1b, then
pooled as `drift-building-phase-first-b0-latest-COMMIT-f1`. It is compared with L1's pool
on the same 189,647 held-out ads. `cap.py` takes the sweep at 1.1 s against L1's 1.0 s,
since the scale step gets a seventh free factor. That leaves fewer draws inside the 2,520 s
sweep budget. Ben approves Modal money a sprint at a time since 2026-11-12 12:27 ET, so the
fit waits for the next sprint's budget and launches with `--outside-budget`.

## Predictions (written before launch)

1. The pool passes the gate (55%).
2. The `only` factor lands above L1's "none" factor of 1.64, at 1.75 to 2.1 (60%).
3. The `first` factor lands between 1.15 and 1.45 (60%).
4. Every `sigma` rises by 2% to 8% against L1's, as the later phases take back some of
   the bulk the "none" factor had pulled from them (55%).
5. elpd on the shared held-out ads moves by less than 2 combined SE against L1 (65%). If it
   moves past that, it gains (75%).
6. 80% coverage on all held-out ads moves from 0.797 to between 0.797 and 0.805 (60%), and
   the median's error moves by less than 0.0002 (85%).
7. The two containers cost $7.5 to $9 in all.
