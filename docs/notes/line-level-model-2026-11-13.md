# LN1: L1 with a level for each line of a building (2026-11-13)

Status: written, not fit.

The screen of 2026-11-12 (`docs/notes/line-level-screen-2026-11-12.md`) moved each of L1's
held-out predictions by the shrunk mean residual of other units' earlier held-out ads in the
same line, and gained 750 elpd (SE 83). Here I write out the model from the screen note's
proposal. In LN1 each unit's lasting level centers on its line's level, and the line levels are integrated out
with the units in the building's collapsed step. I have launched, queued and scheduled nothing
for it, and the launch waits for a budget from Ben. The scripts behind the counts and timings
are in `docs/notes/line-level-model-2026-11-13/`.

## The model

A line is the units of a building with the same bedrooms and full baths. LN1 keeps every
term of L1 and moves the center of each unit's lasting level from 0 to its line's level:

    u_j ~ Normal(l_line(j), unit_sd^2),    l_m ~ Normal(0, line_sd^2),    line_sd ~ HalfNormal(0.1).

The sampler is `frontier/src/rentfrontier/drift_line.py`, and
`frontier/src/rentfrontier/drift_building_phase_line.py` builds L1's design with each row's
line. `rentfrontier.run`, `ops/modal/app.py` and `ops/modal/cap.py` list it as
`drift-building-phase-line`. I left `drift.py`, `drift_building.py` and
`drift_building_phase.py` as they were, so L1's and the served fit's hashes stand.

### Lines

`drift_line.line_index` numbers the lines from the whole frame:

- A unit takes the (bedrooms, full baths) pair carried by most of its rows, and on a tie the
  pair of its latest row. Held-out rows count, since bedrooms and baths are columns of the
  row and carry nothing of its rent (`docs/leak-free-scoring.md`). A held-out ad's pair can
  still move a training unit to another line, which changes how training rows group but
  brings in no rent.
- As in L1, a row with no `unit_id` is a unit by itself, so it takes its own pair.
- Bedrooms are rounded and clipped at 0, as `b0.design` codes them, and a missing full-bath
  count gets the value -1.
- Training lines are numbered in sorted order of their keys. A row of a line with no training
  row carries -1.

Giving each unit one pair puts every unit in exactly one line. The collapse below depends on
it: units nest in lines and lines nest in buildings. A unit whose bedrooms changed between
ads keeps the pair of most of its ads. Keying lines on `data.unit_line_key` is a later
variant, and I have not built it.

### The sampler

`drift`'s building paths, drawn given the unit levels, left every chain creeping until the
building term was collapsed. A line ties a building's units together more tightly than the
building does, so I integrated the line levels out wherever `drift.make_sampler` integrates
out the buildings' levels and paths. With C mapping rows to lines and W the units' precision,
block-diagonal by unit, C'WC is diagonal: c_m sums W's row sums over line m's rows. The
collapsed step reads W through each building's sums H = B'WB and h = B'W tgt, and I correct
those in place:

    G_m = line_sd^2 / (1 + line_sd^2 c_m)
    H_pq -= sum over m of v_pm G_m v_qm,        h_p -= sum over m of v_pm G_m hl_m

Here v_pm sums W's row sums over the rows of cell p in line m, and hl = C'W tgt. Every line
belongs to one building, so the correction stays inside each building's block and
`drift`'s `cell_system` takes the corrected sums unchanged. The lines add

    sum over m of -log(1 + line_sd^2 c_m) / 2 + G_m hl_m^2 / 2

to the log density of a building's rows. Given a building's level and path, line m's level is
Normal(G_m (hl_m - c_m level - sum over p of v_pm path_p), G_m).

A sweep runs in this order:

1. theta is drawn as in `drift`, with u and the buildings' levels integrated out and the line
   levels held at their last draw.
2. The scale step adds log line_sd to `drift`'s coordinates, after the phases' log factors,
   and slice samples them with u, the levels, the paths and the lines integrated out.
   unit_sd and line_sd both carry the spread of a building's units, so they trade against
   each other, and the step's adapted directions move them together.
3. The slow columns are redrawn with the lines integrated out. Then `drift`'s slice updates
   draw each zone's spread and the path's scale and correlation, and a single draw gives every
   building's level and path, all on the corrected sums.
4. The line levels are drawn given the buildings' levels and paths, with u integrated out.
5. u is drawn given the lines, and the rest of the sweep is `drift`'s.

I added the bedroom and bath columns (`bed>=`, `full>=`, `bed=`, `bath_unknown`) to L1's slow
columns. They are nearly constant within a line, so given the line levels their coefficients
would trade against the lines' mean and mix slowly. A column constant within a building
trades against the building's level, and step 1 integrates that out, so the lines leave
those columns alone. A column varying within a line, such as a unit's floor or flags, couples
to the lines only weakly.

### The prior on line_sd

line_sd takes HalfNormal(0.1), the prior of unit_sd and drift_sd. Lines of a building with
the same columns rarely differ in rent by more than 10 to 20%, as its units rarely do, and a
scale of 0.1 puts most of the prior below 0.2 and leaves 0 open. A line's level and a unit's
lasting level both describe the spread of a building's units, and giving the two scales one
prior leaves their split to the data.

### Predictions

A held-out row's location and `pred_unit_sd` follow its case:

1. Its unit has training rows. The row takes `drift`'s location, whose unit part is now the
   unit's draw about its line, plus its line's level in each draw.
2. Its unit is new and its line has training rows. The row adds its line's level, and its
   unit part keeps the variance unit_sd^2.
3. Its line is new. The row adds 0, and line_sd^2 joins unit_sd^2 in `pred_unit_sd`.

`drift_score` reads these as it reads L1's, and `drift_pool` takes `drift_line`'s
diagnostics, which add line_sd to the gate's scalars. `drift_today` prices LN1's apartments
at the current date. For each kept draw it rebuilds the building path and the apartment level
from the building's training rows, as it does for L1, and integrates the line levels out with
them. Two rows of one line covary by an extra line_sd^2. I add that block to the covariance
of the building's rows through Woodbury's identity, so the matrices I invert stay the size of
an apartment's rows or a building's quarters, plus a scalar for each line. Each apartment
takes the line `line_index` gave it in the fit, and the three cases above carry over:

1. An apartment with training rows takes its line's level given the building's rows, jointly
   with its own level and the path.
2. A new apartment of a line with training rows takes the same conditional level.
3. An apartment of a new line adds 0 to the location, and line_sd^2 joins its variance.

## Lines in L1's dataset

`count_lines.py` reads L1's dataset under the latest split (`count_lines.txt`):

| quantity | value |
|---|---:|
| training rows, held-out rows | 1,706,824, 189,647 |
| buildings with training rows | 67,972 |
| training lines | 155,525 |
| lines per building: mean, median, 90th, 99th percentile, largest | 2.29, 2, 4, 7, 15 |
| units per line: mean, median, 90th, 99th percentile, largest | 6.0, 2, 13, 62, 761 |
| lines holding a single unit | 61,917 (39.8%), with 4.8% of the training rows |
| (line, quarter) pairs, against (building, quarter) cells | 856,710, against 617,858 |
| ordered pairs of pairs inside a line | 14,205,336 |

In a line of a single unit the line's level and the unit's add up to one level with variance
line_sd^2 + unit_sd^2, so the line changes that unit's prior and nothing else. Every held-out
row of the latest split has a unit with training rows, so the comparison with L1 exercises
only the first case above, and the tests cover the other two. 181,989 held-out rows (96%)
belong to lines with at least two training units, and 7,658 to lines of one.

## Tests

`frontier/tests/test_drift_building_phase_line.py` runs 15 tests on the CPU in about 4
minutes:

- `line_index` on a 12-row frame: the most common pair, a tie going to the latest row,
  held-out rows counted, rows with no `unit_id`.
- `line_layout`'s placement of each pair inside its building's block.
- The building rows' log density with the lines integrated out, against a dense Gaussian,
  with Gaussian building levels and with Student-t levels at 4 degrees of freedom.
- The corrected cell system, the lines' conditional, and the slow columns' system and draw,
  each against the dense conditional.
- The scale step's density against the dense one as each scale moves, with and without the
  phases.
- With line_sd near 0 the step is L1's: the corrected sums equal L1's cell sums, the lines'
  log density term is 0, the cell draws are identical, the slow system matches to 1e-10, and
  the scale density is L1's plus line_sd's prior.
- Predictions in all three cases against the dense predictive given the line draws.
- A run on a simulated design of 6,000 rows with line_sd 0.15 and unit_sd 0.06 recovers both
  inside its draws' 0.1% to 99.9% range, and its held-out squared error is under 0.97 times
  plain `drift`'s.
- The sha256 of a small phased run's traced and kept draws, written into the test.
- The registration in `rentfrontier.run` and `drift_pool`, and the spec's identity with L1's.

`frontier/tests/test_drift_today.py` checks `drift_today`'s line block. It compares Sigma^-1
and the predictions in the three cases with the dense Gaussian conditional, on a toy layout
and on a small lined design built as above, and the prior draw's covariance with the lines
against the prior's. On the same draws and rows, an LN1 fit with line_sd at 0 prices the
apartments exactly as L1's step does, and an L1 fit never calls the line code.

`test_drift`, `test_drift_local`, `test_drift_building_phase`,
`test_drift_building_phase_duplex`, `test_drift_pool` and `tests/test_modal_ops_fit.py` pass
too.

To check that the sampler does not invent line spread, `small_spread.py` plants smaller
spreads on the same simulated design (2 chains, 150 warmup, 300 draws):

| planted line_sd, unit_sd | line_sd draws: 5%, 50%, 95% | unit_sd draws: 5%, 50%, 95% |
|---|---|---|
| 0, 0.06 | 0.003, 0.015, 0.029 | 0.015, 0.044, 0.063 |
| 0.03, 0.10 | 0.007, 0.033, 0.048 | 0.062, 0.089, 0.104 |

## The scales on the sample

With a second argument of 250, `time_sweep.py` runs each model for 250 warmup sweeps and 250
draws on the sample described under Cost. Each chain's mean:

| scale | L1 | LN1 |
|---|---|---|
| unit_sd | 0.060, 0.059 | 0.014, 0.015 |
| drift_sd | 0.040, 0.042 | 0.045, 0.045 |
| line_sd | | 0.133, 0.137 |
| buildings' spread, first zone | 0.114, 0.099 | 0.119, 0.105 |
| buildings' spread, second zone | 0.060, 0.060 | 0.054, 0.051 |

LN1 puts much more of the rent spread between a building's units. Its line_sd^2 comes to about
0.018, against about 0.005 for L1's unit_sd^2 + drift_sd^2, and the buildings' spread barely
moves. `short_runs.py` runs both models again for 150 and 150 sweeps and traces the line
levels. Their mean stays within 0.001 of 0, and in buildings with two or more lines their root
mean square about the building's mean comes to 0.112, so the spread lies between the lines of
a building. The fixed columns' coefficients move little between the two models: the bedroom
steps up to 3 bedrooms add to 0.579 in L1 and 0.568 in LN1.

`pairs.py` checks the split against the ads. It subtracts the fixed part from each training
ad's log ask, with L1's coefficients from the short run, and takes every pair of ads from one
building in one quarter. Two such ads share the building's level and nearly all of its path.
Half a pair's squared difference averages:

| pair of ads | each pair weighted equally | each building weighted equally |
|---|---:|---:|
| from one unit | 0.0018 | 0.0021 |
| from two units of one line | 0.0044 | 0.0047 |
| from two lines | 0.0112 | 0.0220 |

With each building weighted equally, ads of two lines differ by 0.017 more than ads of two
units of one line. That excess corresponds to a line_sd of 0.13, close to LN1's. With each pair
weighted equally, the 43 buildings of more than 40 units hold most of the pairs, and the
excess falls to 0.0068. By the building's count of units, the excess comes to 0.0174 in
buildings of up to 8 units, 0.0191 in those of 9 to 40 and 0.0094 in larger ones
(`pairs.txt`). L1's unit_sd^2 + drift_sd^2 comes near the figures weighted by pair, which the
largest buildings dominate. My reading is that L1 treats the wider gaps between the lines of
smaller buildings as outliers of its rows' Student-t noise, whose nu is near 1.8. Giving each
class of building size its own line_sd is a later variant, and I have not built it.

## Cost

`time_sweep.py` builds each model's design on the latest split's 18,441 training rows of the
1-in-90 sample of buildings from Y1's timing (10,135 units, 1,728 lines) and runs 2 chains of
60 warmup and 60 draws on the CPU. I ran the models one after another with a load average
under 4:

| run | seconds a sweep | setup | compile | peak resident |
|---|---:|---:|---:|---:|
| L1 | 0.805 | 1.36 s | 30.9 s | 3.22 GB |
| LN1 | 0.885 | 1.80 s | 32.5 s | 3.22 GB |
| LN1 with L1's slow columns | 0.907 | 1.74 s | 32.0 s | 3.23 GB |
| L1 | 0.807 | 1.38 s | 31.0 s | 3.23 GB |

A sweep of LN1 takes 10% longer than L1's. The extra slow columns cost nothing I could
measure. Over 250 warmup and 250 draws, run alone later in the evening with other sessions'
work on the machine, L1 took 0.741 s a sweep and LN1 0.847 s, 14% more. The sample keeps whole
buildings, and a line's pairs of pairs number the square of
its quarters with rows, which the dataset's span bounds whatever the line's size. So the
correction's share of a sweep on the sample should carry over to the full data. On the GPU
its four index arrays of 14.2 million entries take 455 MB, and each evaluation of the scale
step's density forms a product of 114 MB a chain. The slow columns' system forms a
temporary array with a row for each of the 856,710 (line, quarter) pairs and a column for
each slow column, 6.9 MB a chain for each column, or about 275 MB at 40 columns. All of it
is small against an H100's 80 GB. The host's
setup grew by 0.44 s on the sample, which scales by the rows to about 40 s on the full data.

`cap.py` states 1.15 s a pair of chains against L1's 1.0. L1's two containers swept at 0.776 s
and 0.783 s on Modal, and at 10% to 14% more the 2,520 s sweep budget holds 2,830 to 2,930
sweeps: 500 warmup and 2,330 to 2,430 draws a chain, against L1's 2,720 to 2,760. The budget stops the sweeps,
so `cap.py` estimates each container at $4.19 and 3,560 s, as for L1 and D1. That is under the
hour's cap on the estimate (`PER_FIT_SECONDS`), and the longer setup adds under a minute to
the real run. I expect about $11.50 to $12.00 for three containers.

## Launch plan (no fit is launched by this note)

Three H100 containers on L1's dataset, seeds 1 to 3, pooled by `drift_pool` into 6 chains,
as planned for D1:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "lna 1" "lnb 2" "lnc 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-line b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR adding the model. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on the shared held-out ads: elpd with the SE
clustered by building, the median's error and the coverage of the 50%, 80% and 95% intervals
(`python -m rentfrontier.drift_score RUN`). I split each count between ads in lines of one
training unit and the rest, and score the Deals subgroup of the screen
(`docs/notes/line-level-screen-2026-11-12/pricier.py`).

## Predictions (written before launch)

The screen note's four predictions come first, refined with what I learned writing and timing
the model, then new ones. All are for the pool of three containers on the latest split against
L1's pool on the shared held-out ads. L1's numbers there: median error 0.04068 and 80%
coverage 0.797. In L1's pool unit_sd has a median of 0.060.

1. The fit passes the gate (50%; the screen gave 45%). The screen expected lines drawn given
   the units to creep, and the collapse removes that. On the sample both chains put line_sd
   within 0.004 of each other after 250 and 250 sweeps. unit_sd falls near its lower edge in
   LN1: in the 150-sweep run its chain means moved between 0.005 and 0.027 from one progress
   line to the next, and it trades against drift_sd and line_sd. L1's pool reached its largest
   R-hat, 1.0076, on unit_sd, and LN1's chains run 11% to 15% fewer draws. So unit_sd is the
   likeliest miss.
2. elpd gains over L1 by more than 2 SE (65%; the screen gave 60%), and by 150 to 600 (55%).
   The screen's +750 read held-out ads closer in time than any training ad, and L1's unit
   levels already carry part of each line.
3. In the Deals subgroup, the median signed error stays within 0.004 of L1's -0.0246 (70%).
4. 80% coverage on all ads moves by less than 0.005 (70%).
5. line_sd's posterior median falls between 0.10 and 0.16 (65%). The 250-sweep runs on the
   sample put it at 0.133 to 0.137, and the pairs at 0.13 with each building weighted equally
   and 0.097 in buildings of more than 40 units. The sample takes whole buildings at 1 in 90,
   so its mix of building sizes should match the full data's.
6. unit_sd's posterior median falls below 0.035 (75%). On the sample the 250-sweep runs put it
   at 0.014 to 0.015 and the 150-sweep run at 0.021, against L1's 0.059 to 0.060.
7. The median's error falls by 0.0001 to 0.0005 (60%). The screen's line shift from earlier
   ads moved it by 0.00017.
8. The 7,658 held-out ads in lines of a single training unit change elpd by less than 150 in
   either direction (65%). For each of them the line and the unit add up to one level, and
   only the scales' changes move it. Its prior variance grows from L1's 0.005 or so to about
   0.020, so each unit's own earlier ads count for more.
9. Each container stops its sweeps at the budget, runs 2,300 to 2,600 draws a chain and 55 to
   62 minutes, and the three settle between $11.00 and $12.50 (80%).
