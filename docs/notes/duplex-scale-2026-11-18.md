# Duplex ads after the image read: three free checks, no fit

Date: 2026-11-18. Cost: no Modal or OxyLabs money.

The image read (`docs/notes/deals-photos-2026-11-18.md`) found duplexes on both tails of
the base model's held-out ads and proposed a noise factor on rows carrying the text mark
`duplex`. Before writing a module I ran three checks on stored predictions. The scripts
are in `docs/notes/duplex-scale-2026-11-18/`. All three use the latest-split run
`drift-building-b0-latest-67d14e17-b9` with income ads left out, or the Deals model's
backtest and market runs (`range-j`, `range-m`).

## Size of the factor (`calib.py`)

I approximated each held-out predictive by a Student-t centred on its median, widened the
marked ads' distributions m times, picked m on one half of the buildings and scored the
other half.

| ads | n | 80% interval covers | below 10% point | m picked on each half | cross-fit elpd gain |
|---|---|---|---|---|---|
| duplex or penthouse | 12,024 | 73.3% | 14.4% | 1.1 and 1.1 | +92.2 (SE 12.7) |
| duplex alone | 10,323 | | | 1.1 and 1.1 | +76.2 (SE 11.8) |
| 10,000 unmarked ads | 10,000 | | | 0.9 and 0.9 | +30.4 (SE 11.5) |

At m = 1.1 the marked ads' 80% interval covers 76.5% and 12.6% of them fall below the 10%
point. At 1.3, the low end of the range the older design D1 found on another base
(`docs/notes/duplex-factor-2026-11-13.md`), the total is 49.3 elpd worse than no factor.
The approximation widens the whole predictive, while a factor in the model would widen the
ad noise alone, so a fitted factor would come out somewhat above 1.1.

## Marked ads in the Deals table (`deals.py`)

Backtest (`range-j`), open ads with no caution:

| ads | n | in the lowest tenth | in the highest tenth | lowest tenth: later cut | later raised | median days |
|---|---|---|---|---|---|---|
| duplex or penthouse | 515 | 47 (9.1%) | 26.8% | 21.3% | 12.8% | 40 |
| unmarked | 8,049 | 474 (5.9%) | 17.6% | 15.4% | 39.5% | 26 |

Marked ads placed in the lowest tenth were raised later a third as often as unmarked ones
and stayed listed two weeks longer, so they look less like bargains. That rests on 47 ads.
Splitting them further leaves 10 to 13 ads a cell (duplex on floor 1: 13 of 88 in the
lowest tenth, 2 raised; floor 2 or higher: 11 of 127, 3 raised; floor unknown: 13 of 174,
0 raised; penthouse without the duplex mark: 10 of 126, 1 raised).

On the market table (`range-m`, 5,626 ads with no caution) marked ads are 7.4% of all rows,
16 of the first 100, 11.2% of the first tenth and 13.5% of the last tenth.

## Floor (`floor.py`)

Mean log gap of the ask from the prediction, and the share of ads below the 10% point, for
floor-1 ads against all held-out ads (whose mean gap is about -0.005):

| half | building | floor 1, no mark | floor 1, duplex |
|---|---|---|---|
| read | walkup | -0.009, 11.8% (n 3,767) | -0.011, 15.0% (n 995) |
| read | elevator | -0.009, 13.2% (n 1,389) | -0.019, 21.3% (n 301) |
| unread | walkup | -0.009, 12.4% (n 3,810) | -0.018, 17.2% (n 1,153) |
| unread | elevator | -0.018, 16.0% (n 1,313) | -0.033, 25.1% (n 291) |

As single terms on the standardized gap, with the share explained against the 95% point of
100 shuffles:

| mark | read half | unread half |
|---|---|---|
| floor 1 | +0.00021 against +0.00002, pass | +0.00071 against -0.00001, pass |
| duplex on floor 1 | +0.00004, pass | +0.00046, pass |
| duplex | -0.00003, fail | -0.00003, fail |
| duplex on floor 6 or higher | +0.00005, pass | -0.00005, fail |

The duplex mark alone explains nothing as a mean term, as in the wording check of the
low-outlier note. Floor-1 ads ask about half a point to a point less than the floor curve
predicts on both halves, and floor-1 duplexes in elevator buildings 1.5 to 3 points less.
No ad in the file has a floor below 1, so basement and garden units are inside floor 1.

## Decision

No fit and no caution from these checks.

- A noise factor near 1.1 on 7% of ads moves a marked ad's place in the table by a few
  hundredths. Sampling it in a held-scales fit also needs a sampler change, since the held
  noise step draws the phase scale too. The gain of about 90 elpd does not change the
  Deals list enough to spend $4 on a backtest and a market fit.
- A caution hiding duplexes would hide 7.4% of the market on the evidence of 47 backtest
  ads. I left it out. If the next backtest repeats the low raise rate among marked ads in
  the lowest tenth, the caution is cheap to add in `rentfrontier.cautions`.
- The floor-1 step passes the chance check on both halves and is the lead to carry
  forward: a level for floor 1 beside the floor curve, with its own level for duplexes.
  It shifts those predictions by about 1%, so it belongs in the next fit of a base that is
  being refit anyway, with predictions first, and not in a fit of its own on the sprint
  budget.
