# L2 and the segment paths on the unitkn base, with GPU rehearsals (2026-11-14)

No fit ran for this note and no held-out ad was scored. The rehearsals below check the
sampler alone, and each model's predictions belong in its own fit note, written before its
fit is launched.

## The modules

L2 (`docs/notes/l2-phase-level-2026-11-13.md`) and the segment paths
(`docs/notes/segment-paths-2026-11-13.md`) were written on L1's base,
`drift_building_phase`. L1TKN (`drift_building_phase_unitkn`,
`docs/notes/l1-row-dof-fixed-2026-11-13.md`) replaces L1's normal unit levels with
Student-t levels at 3 degrees of freedom, draws the units' scale with the levels collapsed,
and holds the rows' degrees of freedom at 2. I composed each term with that base in a new
module, leaving every module of an earlier fit as it stands.

| CLI name | module | design | sweep |
|---|---|---|---|
| `drift-building-phase-unitkn-level` | `drift_building_phase_unitkn_level` | `drift_building_phase_level.design`, L1's columns with the six `phase:*` columns | `drift_building_phase_unitkn.run` |
| `drift-building-phase-unitkn-segment` | `drift_building_phase_unitkn_segment` | `drift_building_phase_segment.design`, with the quarter columns and the outer level columns | `drift.run` with unitkn's settings and the segment module's `gp_spec` |

Each module imports its parents' functions and constants and defines only its name, its
sweep and its run record. The names are registered in `rentfrontier.run`, `ops/modal/app.py`
and `ops/modal/cap.py`, where the stated rates are 1.5 and 2.4 seconds a sweep for a pair of chains,
the L1-base variants' rates scaled by unitkn's. `drift_today` refuses models with Student-t
unit levels, so neither name is registered there.

The tests, `frontier/tests/test_drift_building_phase_unitkn_level.py` and
`frontier/tests/test_drift_building_phase_unitkn_segment.py`, follow the unitkn test: each
checks the design against its parents' designs, the run record, a short run's hash, and
`drift_pool`'s resolution of the name. The 14 frontier tests of these files, `test_drift_pool`
and the unitkn test pass on CPU JAX in 132 s. The 65 root tests of `test_modal_ops_fit`,
`test_formatting` and `test_lint` pass.

## The rehearsals

Each run used `docs/notes/rehearsals-2026-11-14/rehearse.sh` as the earlier rehearsals did:
the 741-building subsample `k100-r8/base` (24,886 training rows, about 1 in 92 buildings)
with the latest split carried over, 2 chains, 500 warmup sweeps, 2,400 draws a chain, seed 1,
level prior at 4 degrees of freedom. The runs went through `ops/job gpu` one at a time as
`systemd-run --user` units, from commit 81a24575, except the `unitkn` reference run, from
d894d6ce. The unitkn module is the same at both commits.

| run | model | wall time | sweep | max RSS |
|---|---|---|---|---|
| `unitkn` | `drift-building-phase-unitkn` | 14 min 05 s | 0.249 s | 4.1 GB |
| `unitkn-level` | `drift-building-phase-unitkn-level` | 14 min 19 s | 0.251 s | 4.1 GB |
| `unitkn-segment` | `drift-building-phase-unitkn-segment` | 27 min 42 s | 0.492 s | 3.8 GB |
| `unitkn-segment-held` | the same, lengthscales held near 1 year by `hold.py` | 28 min 29 s | 0.510 s | 4.4 GB |

The tables below come from `docs/notes/unitkn-rehearsals-2026-11-14/gate.py`. A cell holds
split R-hat and bulk ESS over 4,800 draws, and a star marks a miss of the gate (R-hat above
1.01, or ESS at or under 400). The L1-base columns are the runs of
`docs/notes/rehearsals-2026-11-14/`. Quantities left out of a table pass in each of its runs.

### L1 and unitkn

| quantity | `l1` | `unitkn` |
|---|---|---|
| nu | 1.0111, 236* | held at 2 |
| tau | 1.0026, 328* | 1.0092, 306* |
| sigma[0] | 1.0064, 386* | 1.0005, 552 |
| sigma[1] | 1.0073, 360* | 1.0039, 456 |
| bld_sd[manhattan] | 1.0714, 30* | 1.0529, 44* |
| bld_sd[outer] | 1.0790, 18* | 1.0901, 14* |
| unit_sd | 1.0134, 435* | 1.0015, 423 |
| drift_sd | 1.0084, 528 | 1.0035, 440 |
| drift_tau | 1.0264, 304* | 1.0035, 518 |
| building_ar_rho | 1.0097, 465 | 1.0115, 508* |
| phase_scale[4] | 1.0137, 512* | 1.0015, 644 |
| coefficients over the gate | 0 of 207 | 0 of 207 |

### L2 on each base

| quantity | `l2` | `unitkn-level` |
|---|---|---|
| tau | 1.0049, 344* | 1.0004, 320* |
| sigma[1] | 1.0060, 385* | 1.0017, 502 |
| bld_sd[manhattan] | 1.0895, 12* | 1.0944, 16* |
| bld_sd[outer] | 1.0664, 17* | 1.0718, 19* |
| unit_sd | 1.0062, 854 | 1.0029, 322* |
| drift_sd | 1.0078, 580 | 1.0093, 363* |
| drift_tau | 1.0141, 445* | 1.0150, 416* |
| building_ar_sd | 1.0094, 311* | 1.0077, 492 |
| building_ar_rho | 1.0087, 323* | 1.0093, 582 |
| phase_scale[3] | 1.0271, 299* | 1.0070, 537 |
| coefficients over the gate | 0 of 213 | 1 of 213, `bed=4:full>=3` at 1.0125, 422 |

The six phase coefficients of `unitkn-level` pass with room: R-hat at most 1.0024, ESS 1,318
to 1,647, and the chains' medians within 0.11 sd of each other (`check.py`). The buildings'
levels on the 60 kept draws of a chain give 144 of 741 over 1.01 and 5 over 1.05, which
matches independent draws of that size (141.9 and 6.3).

### The segment paths on each base

| quantity | `segment-fixed` | `unitkn-segment` | `unitkn-segment-held` |
|---|---|---|---|
| tau | 1.0090, 382* | 1.0075, 318* | 1.0170, 307* |
| bld_sd[manhattan] | 1.0730, 21* | 1.0620, 23* | 1.0564, 28* |
| bld_sd[outer] | 1.0618, 28* | 1.0557, 36* | 1.0590, 32* |
| unit_sd | 1.0034, 478 | 1.0072, 292* | 1.0039, 242* |
| drift_sd | 1.0053, 553 | 1.0022, 355* | 1.0029, 262* |
| drift_tau | 1.0065, 327* | 1.0018, 527 | 1.0055, 466 |
| phase_scale[4] | 1.0060, 534 | 1.0124, 627* | 1.0022, 598 |
| phase_scale[5] | 1.0047, 597 | 1.0049, 605 | 1.0053, 331* |
| gp_amp, manhattan studio | 1.0078, 353* | 1.0079, 274* | 1.0025, 336* |
| gp_amp, manhattan 1br | 1.0064, 334* | 1.0094, 396* | 1.0206, 245* |
| gp_amp, manhattan 2br | 1.0004, 345* | 1.0045, 512 | 1.0216, 124* |
| gp_amp, manhattan 3br+ | 1.0142, 100* | 1.0242, 98* | 1.0173, 205* |
| gp_amp, outer studio | 1.0095, 125* | 1.0183, 73* | 1.0358, 133* |
| gp_amp, outer 1br | 1.0100, 328* | 1.0006, 304* | 1.0063, 144* |
| gp_amp, outer 2br | 1.0003, 974 | 0.9999, 999 | 1.0144, 173* |
| gp_amp, outer 3br+ | 1.0032, 480 | 1.0067, 505 | 1.0092, 294* |
| gp_ls, manhattan studio | 1.0425, 110* | 1.0614, 19* | held |
| gp_ls, manhattan 1br | 1.1125, 34* | 1.0829, 52* | held |
| gp_ls, manhattan 2br | 1.0413, 37* | 1.0681, 40* | held |
| gp_ls, manhattan 3br+ | 1.0318, 72* | 1.0124, 56* | held |
| gp_ls, outer studio | 1.2464, 3* | 1.0229, 21* | held |
| gp_ls, outer 1br | 1.0306, 44* | 1.0215, 112* | held |
| gp_ls, outer 2br | 1.0177, 89* | 1.0130, 142* | held |
| gp_ls, outer 3br+ | 1.0354, 82* | 1.0527, 71* | held |
| outer level columns, least ESS | 187 | 102 | 914 |
| coefficients over the gate | 216 of 640 | 214 of 640 | 88 of 640 |
| worst coefficient | `seg:outer:studio:2025q1`, 1.1925, 4 | `seg:manhattan:studio:2015q1`, 1.0452, 40 | `seg:outer:studio:2021q3`, 1.0265 |

On the unitkn base the worst lengthscale's R-hat falls from 1.2464 to 1.0829 and no path
splits its chains, while every lengthscale still misses and about a third of the
coefficients miss with them.

## Sorting the misses

### The subsample's

- **The zone spreads.** `bld_sd` misses in every run on either base, at R-hat 1.05 to 1.09
  and ESS 14 to 44. The L2 note traced this to the slice window `SPREAD_WIDTH` = 0.05, which
  spans six posterior sds on the full data and 0.6 on the subsample, and L2 passed on both
  spreads with the window at 0.5. The unitkn modules leave that step as it is.
- **ESS a little under 400.** tau misses on ESS alone in all seven runs (306 to 382, R-hat at
  most 1.017), and L1's container `l1a` gave it ESS 2,158 on the full data. unit_sd, drift_sd
  and drift_tau move as a block and fall on both sides of 400 across the runs: unitkn passes
  all three (423, 440, 518), `unitkn-level` gives 322, 363 and 416 with drift_tau at R-hat
  1.0150, and `l2` gave 854, 580 and 445 with the same R-hat miss. The single coefficient
  miss of `unitkn-level`, `bed=4:full>=3`, sits at 1.0125 with ESS 422. A rehearsal has
  4,800 draws from a pair of chains. A full fit pools the chains of its containers, and L1's pool
  passed where `l1a` alone missed on unit_sd.

Neither group separates the unitkn base from L1's, or L2 from its base. Fixing the rows' nu
removes L1's miss on nu and lifts sigma over 400 in every unitkn run.

### The segment model's

The lengthscales, the paths' amplitudes and the paths' quarter coefficients miss on both
bases, and the next section looks at them.

## The segment paths' lengthscales

### Rows in each segment

`segments.py` counts each segment's training rows and the weight its rows put on each of the
54 quarter starts. The subsample columns come from `k100-r8/base`, and the full-data columns
from L1's dataset on the latest split (1,706,824 training rows).

| segment | rows, subsample | median quarter weight | quarters under 20 | rows, full data | median quarter weight | least |
|---|---|---|---|---|---|---|
| manhattan studio | 2,578 | 47.9 | 3 | 226,414 | 4,027 | 59.3 |
| manhattan 1br | 4,983 | 96.9 | 2 | 399,146 | 7,230 | 104.0 |
| manhattan 2br | 3,486 | 66.3 | 3 | 257,940 | 4,519 | 60.9 |
| manhattan 3br+ | 1,194 | 22.0 | 21 | 114,322 | 2,054 | 24.9 |
| outer studio | 1,882 | 29.2 | 14 | 65,872 | 1,234 | 9.8 |
| outer 1br | 4,201 | 77.2 | 3 | 203,543 | 3,606 | 35.6 |
| outer 2br | 3,953 | 66.3 | 4 | 253,167 | 4,392 | 35.3 |
| outer 3br+ | 2,609 | 45.0 | 9 | 186,420 | 3,022 | 16.9 |

The full data has 35 to 96 times the subsample's rows in a segment. There, the quarters with
little weight are the two at the ends of the range, and every other quarter carries a weight of at least 100
in each segment. On the subsample a quarter of outer studios or
Manhattan 3br+ has about 20 to 30 rows, and the paths' amplitudes are 0.01 to 0.03 in log
rent, so a quarter's coefficient is known about as loosely as the path is wide.

### The prior against the amplitude

`lengthscale.py` compares each chain's draws of log lengthscale with the Normal(0, 0.5)
prior, and with the density from which `drift.update_gp` draws it in a sweep: the density
given the path's 53 coefficients, with the amplitude integrated out.

| segment | mean of log ls, chains 1 and 2 | sd | sd within a sweep | correlation with log amplitude |
|---|---|---|---|---|
| manhattan studio | -0.27, +0.02 | 0.50, 0.48 | 0.09 | +0.40, +0.43 |
| manhattan 1br | +0.08, -0.01 | 0.38, 0.50 | 0.10 | +0.34, +0.30 |
| manhattan 2br | -0.85, -0.87 | 0.58, 0.46 | 0.08 | +0.24, +0.31 |
| manhattan 3br+ | -0.14, -0.10 | 0.57, 0.64 | 0.08 | +0.47, +0.63 |
| outer studio | -0.64, -0.41 | 0.75, 0.72 | 0.10 | +0.34, +0.44 |
| outer 1br | -1.06, -1.04 | 0.17, 0.25 | 0.07 | +0.38, +0.32 |
| outer 2br | -0.97, -0.92 | 0.25, 0.23 | 0.08 | +0.23, +0.35 |
| outer 3br+ | -0.51, -0.47 | 0.34, 0.41 | 0.08 | +0.22, +0.09 |

The table is `unitkn-segment`'s, and `segment-fixed` on L1's base gives the same pattern.

- For Manhattan studios, 1br and 3br+ the draws match the prior in mean and sd. The
  subsample's rows leave those lengthscales where the prior puts them.
- For outer 1br and 2br the draws settle near log -1, about 0.37 years, with an sd of 0.2 to
  0.3. Both chains agree, and the rows of the 1-in-50 subsample (`segment-k50`) put outer 1br
  at -1.35 with an sd of 0.15. The rows inform these lengthscales, and they put a 1-year
  value three or more sds away.
- The amplitude trades against the lengthscale only weakly: the correlations of the two logs
  run from +0.1 to +0.6.
- The step itself is narrow. Given the coefficients, log lengthscale has an sd of 0.07 to
  0.10, an eighth to a third of the chain's sd. A sweep redraws the coefficients
  given the lengthscale and then the lengthscale given the coefficients, so the pair moves
  as a random walk in steps of about 0.1 across a posterior 0.5 wide. In `segment-k50`, where
  Manhattan 3br+ had a chain sd of 0.27 against a step of 0.21, its lengthscale reached ESS
  712.

### The choice among the three parameterizations

- **A fixed lengthscale of 1 year.** `hold.py` sets the sd of the lengthscales' prior to 0.001
  in its own process and changes no file, so each lengthscale stays within 0.2% of a year.
  In that run the Manhattan paths' coefficients nearly all pass (4 over the gate), as
  do the outer level columns (ESS at least 914, from 102). Of the 88 coefficient misses
  left, 79 are outer studio, 1br and 2br coefficients, the paths whose rows prefer a
  lengthscale near 0.37 years, and the amplitudes miss more widely than before (ESS 124 to
  336). Holding the outer lengthscales at a year sets them against their rows without
  bringing the model through the gate on the subsample.
- **A joint draw of amplitude and lengthscale.** The step already integrates the amplitude
  out, and the two logs correlate weakly, so a joint draw of the pair would change little.
  The slow direction is the lengthscale against the 53 coefficients. A step that moves the
  coefficients with the lengthscale would need new code in `drift.update_gp`, which fits
  have hashed, and it is sampler work.
- **The model as written.** On the full data a quarter's coefficient rests on thousands of
  rows in place of tens, so the posterior of a lengthscale should narrow toward the width of
  the sweep's own step, as it did for Manhattan 3br+ between the two subsamples. The same
  argument covers the amplitudes, whose draws given the coefficients are exact.

No change came out as clearly right, so I wrote no further variant. The lengthscales'
misses on the subsample come mostly from the subsample, with the centered coefficient step
as the model's part of them. The rehearsal cannot show the full data's behavior for the
quarter coefficients, which also share each quarter's rows with the buildings' paths.

## Chances at the gate on the full data

These are estimates of the sampler's outcome for a pool of three containers, the sprint's
plan for each fit. They say
nothing about held-out scores.

- **`drift-building-phase-unitkn-level`: about 70%.** L1TKN's note put its own pool at 75%.
  L2 adds six columns whose coefficients mix at ESS above 1,300 here, and its rehearsal on
  this base differs from the reference's only around the 400 line on the unit and drift
  block.
- **`drift-building-phase-unitkn-segment`: about 35%.** The run adds 8 lengthscales, 8
  amplitudes and 430 quarter coefficients, each of which has to pass, and a third of them
  miss on the subsample. The row counts argue that most of this clears on the full data, and
  no run has tested that argument past the 1-in-50 subsample. A sweep also takes twice as
  long, so a container's window holds fewer draws.

A cheaper test than a full fit exists for the second: a rehearsal on a 1-in-10 subsample of
buildings would show whether the lengthscales' chain sd falls toward 0.1 and their ESS rises
with it.

## Files

- `frontier/src/rentfrontier/drift_building_phase_unitkn_level.py`,
  `frontier/src/rentfrontier/drift_building_phase_unitkn_segment.py` and their tests.
- `docs/notes/unitkn-rehearsals-2026-11-14/`: `gate.py` (the gate tables), `segments.py` (rows
  and quarter weights in each segment), `lengthscale.py` (the lengthscale table), `hold.py`
  (the held-lengthscale diagnostic).
- `docs/notes/rehearsals-2026-11-14/rehearse.sh` takes `REHEARSAL_ENTRY` for a diagnostic
  entry script such as `hold.py`.
- Runs under `/data1/apartments/tmp/rehearsals-2026-11-14/`: `unitkn`, `unitkn-level`,
  `unitkn-segment`, `unitkn-segment-held`.
