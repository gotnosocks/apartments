# The outer zone's map amplitude: diagnosis and a joint amplitude step, with predictions, 2026-10-23

`amp[outer]`, the outer zone's map amplitude, missed the R-hat gate of 1.01 in the as-of floor fit on real data (asof2, 1.0129) and in simulated-recovery fit 7 (1.0115, `simulated-recovery-asof2-2026-10-23.md`). In fit 6 and in the earlier floor fits it passed but carried the worst R-hat and the least ESS. I looked at it on CPU from the saved draws of those three runs. The script is `docs/notes/conference-followups-2026-10-22/amp_diag.py`, and its output is in `/data1/apartments/tmp/conference-followups/amp/diag.out`.

## Diagnosis

| run | chain medians of `amp[outer]` | IAT, sweeps | lag-1 | lag-5 | lag-20 |
|---|---|---|---|---|---|
| asof2, real data | 0.365, 0.378, 0.370, 0.371 | 7.0 | 0.74 | 0.21 | -0.03 |
| fit 6, simulated | 0.360, 0.369, 0.368, 0.364 | 6.6 | 0.71 | 0.17 | 0.01 |
| fit 7, simulated | 0.352, 0.361, 0.356, 0.356 | 6.4 | 0.70 | 0.17 | 0.00 |

IAT is the integrated autocorrelation time, from Geyer's initial positive sequence on the autocorrelations of the 1,000 traced draws, averaged over the four chains. `amp[manhattan]` has an IAT of 3.0 to 3.7 and a lag-1 autocorrelation of about 0.53 in the same runs.

The slow mixing doesn't come from another block. Over the draws, `amp[outer]` correlates with the outer zone's building spread, mean level, building sd and building variance by 0.06 or less in absolute value, and with the field's variance `zone_var_f[outer]` by 0.06 to 0.11. Within each run the chains agree on those quantities to the fourth decimal.

The field and the amplitude move very differently. The outer field's variance has a coefficient of variation of about 1% over the kept draws, while `amp[outer]` has one of 12% to 13%, and the ratio of the field's variance to amp squared varies by about 25%. So the data fix the map F = Bc w closely, and amp is tied to it only through the prior on the waves, w_j ~ Normal(0, amp^2 sd_j^2). Many of the outer zone's waves are short and barely touched by the data. Their w_j / sd_j follow amp through the prior, and the sweep's step 5 draws amp given w. Each draw of amp can then move only as far as the last draw of those waves allows, and the waves move only as far as the last amp allows. This is the slow pairing of a centred hierarchical parameter with weakly identified effects. The amp1 fit widened amp's prior from HalfNormal(0.3) to HalfNormal(1.0) and left `amp[outer]` second in R-hat, so the prior's scale isn't the cause. The two park-front fits mixed it well (R-hat 1.003 and 1.004, `building-zones-floor-asof2-2026-10-23.md`), which fits this reading if their park-front term took up some of the short outer waves' variation, though I haven't checked that.

## Change

`rentfrontier.amp_joint` adds a step that draws the amplitudes and the waves together, given the building levels. With the waves integrated out, the levels' density given the amplitudes is Gaussian with a 216 by 216 precision, so I slice-sample each zone's log amplitude on that density and then draw w given the new amplitudes. Nothing else in the model reads w, so the step is a block of the posterior. The sweeps of `building_zones_gibbs` and `building_zones_floor_asof2_unit` use it in place of step 5's amplitude draw when `Settings.joint_amp` is on, which `--joint-amp` sets for the `building-zones-floor-asof3-unitmean` and `building-zones-floor-asof3-periods` runs. It is off by default, so every earlier run and fit 8 sample as before.

`tests/test_amp_joint.py` checks the step against the amplitudes' posterior given the levels on a grid, on a toy of two zones with waves centred across both, and runs the Gibbs sweep with it. `test_recovers_a_planted_unit_sd` runs the unit sweep with and without it.

On the simulated design of `test_recovers_simulated_scales` (6,000 rows, three zones), `amp_toy_iat.py` in the same folder runs 4 chains of 2,000 draws after 300 warmup sweeps with each step:

| zone | truth | centred: IAT, median | joint: IAT, median |
|---|---|---|---|
| 0 | 0.8 | 4.81, 0.670 | 1.05, 0.670 |
| 1 | 0.4 | 12.23, 0.433 | 1.23, 0.432 |
| 2 | 0.5 | 7.11, 0.345 | 2.09, 0.335 |

The medians agree, and the IAT falls by a factor of 3 to 10. On that toy the sweep takes 0.103 s against 0.035 s on CPU, since the toy's rows cost little and the step's slice updates dominate. On the real design the sweep took about 0.8 s on the GPU in fits 6 and 7.

This is a change of sampler, not a reseed. The model and its posterior stay the same.

## Plan

If this is reviewed and merged before fit 4 starts, fit 4 (`building-zones-floor-asof3-unitmean`) and fit 5 (`building-zones-floor-asof3-periods`) run with `--joint-amp` at the merged commit, with the label suffix `jointamp`. Otherwise fit 4 runs as queued and only fit 5 gets the step. Fit 8 (`asof3-cap64`) runs as queued, so its `amp[outer]` gives one more run of the centred step on the same build.

## Predictions

For each of fits 4 and 5 run with the step, from its trace of 4 chains by 1,000 draws:

1. `amp[outer]` has an IAT of 3.5 sweeps or less, against 6.4 to 7.0.
2. `amp[outer]` has ESS of at least 1,100, against 591 to 609, and R-hat of 1.005 or less.
3. `amp[outer]` no longer has the run's worst R-hat or its least ESS.
4. `amp[manhattan]` has an IAT of 3.0 or less, against 3.0 to 3.7.
5. The run passes the gate on every quantity.
6. Its median `amp[outer]` lies between 0.32 and 0.42 and its median `amp[manhattan]` between 0.80 and 1.00, as in the centred runs on the as-of floor model (0.36 to 0.37 and 0.89 to 0.91 on asof2's real data).
7. Seconds per sweep rise by under 10% against fit 8's. The step adds about 60 factorizations of a 216 by 216 matrix per chain to a sweep over 1.9 million rows.

For fit 8, without the step: `amp[outer]` again carries the worst R-hat or the least ESS, with IAT between 5.5 and 8.

If prediction 1 fails while 6 holds, the slow mixing has a second cause in the levels themselves, and the next place to look is the outer zone's buildings with few rows, whose levels carry the waves' last draw into the next amplitude draw.
