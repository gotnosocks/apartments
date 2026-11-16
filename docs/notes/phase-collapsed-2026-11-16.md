# Drawing the phase factors with the rows' mixing scales integrated out

The L2 market pool missed the gate on `phase_scale[1]`, the noise factor of a unit's first
ad, at R-hat 1.0108 (`docs/notes/l2-market-2026-11-15.md`). That note left a guess to check on
a subset. This note reads the sweep, proposes a sampler change for the check and records
predictions for it. It costs no Modal money.

## Reading the sweep

A row's noise is Student-t with nu = 2 and scale sigma[group] times the factor of its phase.
The sampler holds it as a Normal with variance (sigma f)^2 / lam_i. In L2's sweep
(`drift.make_sampler`):

1. The scale step slices the unit scales, the four sigma and the free factors together, with
   u, the buildings' levels and the paths integrated out. While it slices, every lam_i and
   every unit's kap_k stays at the state's value.
2. The noise step slices sigma given the rows' remainders with lam integrated out, then
   draws lam from its Gamma conditional.
3. `update_unit_t` moves `unit_sd` and the kap together along ss -> g ss, kap -> g^2 kap.

So sigma and `unit_sd` each get a second move with their mixing scales integrated out or
moved along with them. The factors get no such move. On the pooled market traces (6 chains x 2,360 draws) and on the k100
rehearsal of L2 from Nov 14 (2 chains x 2,400 draws), bulk ESS reads:

| Quantity | Market pool | k100 rehearsal |
|---|---|---|
| `unit_sd` | 890 | 323 |
| sigma, four groups | 1,457 to 1,860 | 501 to 636 |
| `none` factor | 1,386 | 517 |
| other factors | 1,451 to 1,834 | 539 to 650 |
| log sigma[g] + log `none` factor, g = 0..3 | 950, 909, 975, 1,381 | 308, 223, 246, 438 |
| the same sums for the other phases | | 269 to 681 |

The 1-in-100 subsample reproduces the pattern in 14 minutes on thelio: the noise of first ads
and `unit_sd` are slowest, and each factor alone mixes about as well as each sigma.

The table fits either of these readings:

- (a) The factors lack the move that sigma has. The noise step can then only move a first
  ad's noise, sigma[g] times the factor, through sigma[g], which every other phase of the
  group shares.
- (b) For a unit with a single ad, the row's noise and the unit's level are told apart only
  through lam_i, kap_k and u, and every step that moves a noise scale conditions on at
  least one of them. Under this reading the first ads' noise and `unit_sd` are slow together.

## The change

`drift.make_sampler` takes a new option, `phase_collapsed`. With it the noise step, after it
has drawn sigma, slices each free log factor from its own rows' Student-t density at that
sigma, under the factor's Normal(0, 0.3) prior, and then draws lam at the new factors. The
phases' rows are disjoint, so the factors are independent given sigma and the remainders, and
one `slice_vec` call draws them all. The step's key is folded in, so every other step keeps
the key it had. Without the option the sweep's draws are unchanged: the tests of the other models' recorded run
hashes pass on this branch.

The model `drift-building-phase-unitkn-level-phase` is L2 with the option. Its test runs the
noise step 6,000 times in a row and compares sigma and the factors with a random-walk
Metropolis chain on the same density written out in NumPy.

## The check

```sh
systemd-run --user --unit=frontier-phase-collapsed-k100 -p MemoryMax=10G \
  ops/job gpu docs/notes/rehearsals-2026-11-14/rehearse.sh \
  drift-building-phase-unitkn-level-phase k100-r8/base phase-collapsed-k100 500 2400 \
  phase-collapsed-k100
```

This is the Nov 14 rehearsal's call with the new model: 24,886 training rows, 2 chains, 500
warmup sweeps, 2,400 draws, seed 1. I compare bulk ESS with the table's k100 column. With
ESS near 300 from a single seed, a change under about 25% is within the estimate's error.

## Predictions (written before the run)

1. The lowest bulk ESS among the four sums log sigma[g] + log `none` factor rises from 223
   to at least 290 (40%). I lean to reading (b): sigma already has this move and each factor
   alone already mixes as well as sigma does.
2. The bulk ESS of `unit_sd` stays between 240 and 400 (70%).
3. The posterior means of `unit_sd`, the four sigma and the six free factors each sit within
   2 Monte Carlo standard errors of the Nov 14 rehearsal's (85% for all eleven together
   being within 3).
4. Sampling takes under 625 s, against 594 s (80%).

If 1 comes true, I write a note for a market refit of L2 with the option, about $11. If it
fails, reading (b) stands and the next check is a move of the first ads' noise against
`unit_sd` with lam and kap redrawn inside it.

## Results

The run finished at 09:17 ET on Nov 16 (`.../phase-collapsed-k100`), with 600 s of sampling
against the Nov 14 rehearsal's 594 s. Bulk ESS over 2 chains x 2,400 draws, seed 1 in both:

| Quantity | L2 | with the option |
|---|---|---|
| `unit_sd` | 323 | 204 |
| sigma, four groups | 565, 501, 583, 636 | 593, 524, 643, 681 |
| `none` factor | 517 | 654 |
| the other five factors | 539 to 650 | 763 to 918 |
| log sigma[g] + log `none` factor | 308, 223, 246, 438 | 353, 393, 299, 379 |
| the same sums for the other five phases, lowest and highest | 269, 681 | 516, 1,258 |
| `none` minus the mean of the other phases | 327 | 528 |

Split R-hat of the `none` factor went from 1.0042 to 1.0006, and the highest among its four
sums from 1.0090 to 1.0057.

1. Right, by a thin margin: the lowest `none` sum is 299. Three of the four sums rose and
   group 3's fell from 438 to 379.
2. Wrong: `unit_sd` came in at 204.
3. Right: all eleven means sit within 1.01 standard errors of the difference. `unit_sd` is
   0.04664 and 0.04661, the `none` factor 1.7245 and 1.7249.
4. Right: 600 s.

The step clearly helps the five later phases, whose noise roughly doubled in ESS. For the
first ads the gain is smaller, and the first ads' noise and `unit_sd` remain the slowest
quantities of the sweep, as reading (b) expects. An ESS near 300 from two chains carries
an error of a fifth or more, so the rise from 223 to 299 and the fall of `unit_sd` from 323
to 204 could each be seed noise. Before a market refit I repeat both runs at seed 2
(`REHEARSAL_SEED=2`, outputs `unitkn-level-s2` and `phase-collapsed-k100-s2`) and read the
two seeds together.

While tightening the chain test I found the slice steps' reach matters on tiny designs: at
12 widths of 0.02 to each side, the noise step's chain on 340 rows came out a tenth too
narrow in both sigma and the factors, and exact at 80 widths. A full dataset's log scales
spread by about 0.01, so the default reach covers them.
