# The segment paths on the unitkn base, rehearsed on 1 building in 10 (2026-11-14)

No fit ran for this note and no held-out ad was scored. The run below tests a single claim
from `docs/notes/unitkn-rehearsals-2026-11-14.md`: on the 1-in-92 subsample every segment
lengthscale, 5 of 8 amplitudes and about half the quarter coefficients of
`drift-building-phase-unitkn-segment` missed the gate, and that note put the misses down to
the subsample's few rows in each segment and quarter. If the claim held, a subsample ten
times larger would show the misses shrinking.

## The subsample

`docs/notes/rehearsals-2026-11-14/subsample.py 10 8` drew 6,857 of the 67,972 buildings
(seed 20261114) into `/data1/apartments/tmp/rehearsals-2026-11-14/datasets/k10-r8/`: 198,167
rows, 19,589 of them held out on the carried latest split, 178,578 for training. The table
gives each segment's training rows and the median weight of a quarter start
(`docs/notes/unitkn-rehearsals-2026-11-14/segments.py`, output in
`unitkn-segment-k10-2026-11-14/segments-k10.json`), with the medians of the smaller
subsamples and of the full data beside it.

| segment | training rows | median quarter weight | quarters under 100 | median at 1 in 92 | median at 1 in 50 | median, full data |
|---|---|---|---|---|---|---|
| Manhattan studio | 23,934 | 429 | 2 | 48 | 83 | 4,027 |
| Manhattan 1br | 40,393 | 740 | 2 | 97 | 153 | 7,230 |
| Manhattan 2br | 26,597 | 476 | 2 | 66 | 110 | 4,519 |
| Manhattan 3br+ | 11,012 | 203 | 4 | 22 | 41 | 2,054 |
| outer studio | 7,513 | 138 | 14 | 29 | 38 | 1,234 |
| outer 1br | 22,813 | 410 | 3 | 77 | 129 | 3,606 |
| outer 2br | 26,900 | 439 | 3 | 66 | 115 | 4,392 |
| outer 3br+ | 19,416 | 317 | 3 | 45 | 70 | 3,022 |

The quarters under 100 at 1 in 10 are the two ends of the range and, for outer studios, a
stretch of early quarters.

## The run

I ran `docs/notes/rehearsals-2026-11-14/rehearse.sh` through `ops/job gpu` on thelio's RTX
2060 (8 GB) at the settings of the 1-in-92 rehearsal: 2 chains, 500 warmup sweeps, 2,400
draws a chain, keep every 40th, seed 1, level prior at 4 degrees of freedom. A probe of 40
warmup sweeps and 80 draws first measured 2.885 s a sweep and a peak of 7,659 MiB on the
card, so the full 1-in-10 subsample and the full draw count stayed in.

Three attempts ended early before the run in this note finished:

- **`unitkn-segment-k10-budget440`.** `drift.Settings.budget_seconds` stops sampling after
  2,520 s, the limit set for Modal containers, and the first run stopped at draw 440 (2.714 s
  a sweep, max R-hat 1.2223, min ESS 4). From then on `rehearse.sh`'s `REHEARSAL_ENTRY` ran
  `unitkn-segment-k10-2026-11-14/nobudget.py`, which sets the budget's default to None in its
  own process and changes no file.
- **`unitkn-segment-k10-oomkilled`.** systemd-oomd killed the unbudgeted run near draw 1,800
  after 2 h 20 min, when another session's scoring job raised the memory pressure on
  `user@1000.service` past 50% for 20 s. The run had no checkpoints, so `nobudget.py` now
  also turns them on, one every eighth of the draws.
- **Two relaunches** were killed the same way during start-up while two more of the other
  session's jobs ran. I waited for those to finish and for the pressure to fall near 0.

The last launch started at 20:56 ET and finished after 2 h 35 min: 7,624 s of sampling,
3.105 s a sweep of 2 chains, peak GPU memory 7,711 MiB, peak resident memory 6.3 GB.
Another session's CPU job held the memory pressure at 25% to 35% for most of the run, which
accounts for the slower sweeps against the probe and the 440-draw run. The output is in
`/data1/apartments/tmp/rehearsals-2026-11-14/unitkn-segment-k10/runs/unitkn-segment-k10/`.

## Diagnostics

**Gate: fail.** The highest split R-hat is 1.9547 and the lowest bulk ESS is 1, both on
`gp_amp[seg:manhattan:3br+]`. `unitkn-segment-k10-2026-11-14/counts.py` sorts the misses by
group:

| group | 1 in 92 (`unitkn-segment`) | 1 in 50 (`segment-k50`, L1 base, 1,200 draws) | 1 in 10 |
|---|---|---|---|
| lengthscales | 8 of 8 | 7 of 8 | 3 of 8 |
| amplitudes | 5 of 8 | 7 of 8 | 6 of 8 |
| quarter coefficients | 208 of 430 | 362 of 430 | 279 of 431 |
| other coefficients | 6 of 210 | 6 of 219 | 2 of 242 |
| other scalars | 6 of 28 | 22 of 29 | 2 of 28 |

Outside the segment paths, the 1-in-10 run misses only on `beta[bed>=3]` (1.1186, ESS 5),
`beta[level:outer:3br+]` (1.1422, 4), `bld_sd[manhattan]` (ESS 283) and `unit_sd` (1.0149).
The buildings' spread, at ESS 21 to 28 on the 1-in-92 subsample, mixes ten times better
here.

`docs/notes/unitkn-rehearsals-2026-11-14/lengthscale.py` gives each segment's log lengthscale
(in years) by chain:

| segment | mean, chain 1 / 2 | chain sd | sd given the coefficients | ls R-hat, ESS | amp R-hat, ESS |
|---|---|---|---|---|---|
| Manhattan studio | -0.72 / -0.72 | 0.12 / 0.11 | 0.07 | 1.000, 621 | 1.011, 663 |
| Manhattan 1br | -0.63 / -0.64 | 0.12 / 0.12 | 0.08 | 1.001, 931 | 1.005, 536 |
| Manhattan 2br | -1.00 / -0.99 | 0.10 / 0.12 | 0.07 | 1.001, 868 | 1.012, 654 |
| Manhattan 3br+ | -0.70 / +0.80 | 0.79 / 0.60 | 0.07 / 0.27 | 1.228, 3 | 1.955, 1 |
| outer studio | +0.92 / +0.84 | 0.29 / 0.31 | 0.15 / 0.13 | 1.010, 530 | 1.012, 301 |
| outer 1br | +0.89 / +0.87 | 0.32 / 0.33 | 0.16 / 0.18 | 1.004, 421 | 1.014, 282 |
| outer 2br | +0.99 / +0.94 | 0.32 / 0.34 | 0.14 / 0.18 | 1.007, 392 | 1.001, 666 |
| outer 3br+ | +0.36 / -0.20 | 0.44 / 0.72 | 0.10 / 0.09 | 1.115, 6 | 1.049, 34 |

Three patterns come out of the tables.

1. The claim holds for six of the eight paths' hyperparameters. For Manhattan studios, 1br
   and 2br the chain sd has fallen to within a factor of 1.5 of the conditional step, and
   the lengthscales pass with ESS 621 to 931. The outer studio, 1br and 2br lengthscales
   settle near 2.5 years and pass or sit at the 400 line, as do their amplitudes. The
   amplitudes that miss among these six do so by R-hat 1.011 to 1.014 or ESS 282 to 301.
2. Both 3br+ paths split their chains. In Manhattan 3br+ one chain holds a lengthscale near
   0.5 years and the other near 2.2 years, and the amplitude follows (correlation of the two
   logs +0.94 and +0.65). Outer 3br+ splits the same way less widely. A split between modes
   gets no better with more chains of the same length, and 11,012 training rows did not
   remove it.
3. The quarter coefficients miss more often than on the 1-in-92 subsample, and in every
   segment, including the three whose hyperparameters mix well. In Manhattan 1br the
   coefficients from 2014 through 2020 miss (R-hat 1.02 to 1.11, ESS 4 to 47) and those from
   2021q3 on pass. `unitkn-segment-k10-2026-11-14/offsets.py` averages each segment's
   pre-2021 coefficients: within a chain the average loses its autocorrelation by lag 40
   (0.07), yet the two chains' means differ by 5 to 8 thousandths of log rent against a
   chain sd of 6 to 9, the same direction in seven of the eight segments. A slow offset
   shared by the early quarters of most segments holds each chain in its own place over all
   2,400 draws. Its size correlates +0.46 with the Manhattan 2br and 3br+ amplitudes; the
   run does not show what else it trades against.

## Time and cost on the full data

The full data has 1,706,824 training rows, 9.6 times this run's. On the RTX 2060 the sweep
grew from 0.492 s at 1 in 92 to 3.105 s at 1 in 10 (6.3 times the time for 7.2 times the
rows), so a full-data sweep would take near 30 s on this card. The H100 rate comes better
from L2's Modal fit on the same base: its containers swept the full data in 0.75 s
(2,544 s of warmup and sampling for 3,380 sweeps), and the segment paths doubled the sweep
in both 1-in-92 rehearsals (0.249 s to 0.492 s on unitkn, 0.256 s to 0.499 s on L1). That
puts the segment model near 1.5 s a sweep on an H100, under `ops/modal/cap.py`'s stated
2.4 s.

- At 1.5 s, 2,900 sweeps (500 warmup and 2,400 draws) take about 73 min a container, and
  three containers in parallel fit the 2-hour window for full fits. The 2,520 s sampling
  budget stops each container near 1,180 draws, so a pool of three gets about 7,100 draws.
- `cap.py` prices a container as 800 s plus sweeps at the stated rate, at $4.363 an hour on
  an H100: 2,900 sweeps at 2.4 s come to $9.40 a container and $28.20 for three. With the
  budget in force a container stops near 3,300 s, about $4 and $12 for three, as L2's
  containers settled at $3.62 to $3.81.

## Chances at the gate on the full data

I put a 3-container pool of the model as written at about 10%, down from 35%. The six paths
whose hyperparameters improved would likely pass on 1,200 to 7,000 rows a quarter, but both
3br+ paths hold two modes on 11,000 to 19,000 rows, and the quarter coefficients missed more
often at ten times the rows, through an offset between chains that more rows did not shrink.

Two variants could plausibly pass, each untested:

- **Hold the 3br+ lengthscales** at a single value each, or give 3br+ no path of its own.
  This removes the split modes, and the early offset correlates with the 3br+ amplitude.
- **Hold all eight lengthscales at their 1-in-10 posterior means** (about 0.5 years in
  Manhattan, 2.5 years in the outer boroughs) in place of the 1-year value of
  `docs/notes/unitkn-rehearsals-2026-11-14/hold.py`. On the 1-in-92 subsample the 1-year
  hold let the Manhattan coefficients pass and left misses on the outer paths, whose rows
  pointed elsewhere.

Neither addresses the early-quarter offset directly, so a 1-in-10 rehearsal of either
should come before a Modal fit.

## Files

- `docs/notes/unitkn-segment-k10-2026-11-14/nobudget.py`: the entry script that lifts the
  sampling budget and turns on checkpoints.
- `docs/notes/unitkn-segment-k10-2026-11-14/counts.py`: gate misses by parameter group.
- `docs/notes/unitkn-segment-k10-2026-11-14/offsets.py`: the chains' offsets in the early
  quarter coefficients.
- `docs/notes/unitkn-segment-k10-2026-11-14/segments-k10.json`: rows and quarter weights.
- Runs under `/data1/apartments/tmp/rehearsals-2026-11-14/`: `unitkn-segment-k10`,
  `unitkn-segment-k10-budget440`, `unitkn-segment-k10-oomkilled`, and the probes
  `probe-unitkn-segment-k10` and `probe-unitkn-segment-k10-a`.
