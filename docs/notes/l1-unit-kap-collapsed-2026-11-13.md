# L1T with the units' mixing scales drawn collapsed (2026-11-13)

L1T (`docs/notes/l1-unit-t-fixed-2026-11-12.md`) missed the gate on nu (R-hat 1.025) and
unit_sd (1.019). Its six chains agreed on every value but each one moved slowly, and its
held-out scores, as a free check, gained 4,095 elpd over L1 (SE 172). This note changes
how L1T's sweep draws the units' mixing scales kap and leaves the model as it is. The pool
can then be compared with L1 as a single change, L1T's Student-t unit level. No fit is
launched by this note.

## The diagnosis

I measured the integrated autocorrelation time (in draws, averaged over the six chains)
of the slowest scalars in L1's and L1T's pools:

| quantity | tau_int L1 | tau_int L1T |
|---|---:|---:|
| nu | 11.0 | 17.7 |
| unit_sd | 11.4 | 27.3 |
| drift_sd | 10.0 | 16.5 |

unit_sd slows down most, and nu follows it. I averaged each chain's draws over blocks of
200 and correlated the block means of nu with those of unit_sd: -0.43 in L1, +0.48 in L1T.
In L1T the two drift up and down together.

L1T's sweep draws u and every unit's lasting level s_k given the old kap_k, then each
kap_k from its Gamma conditional given s_k, then ss and the kap together along the orbit
that keeps ss^2 / kap_k. Most units have one to three ads, so s_k is barely pinned down by
the data, and a unit's kap_k and s_k hold each other in place from one sweep to the next.
A small kap_k lets s_k sit far out, and a far-out s_k keeps kap_k small. The 935,396 kap
then move slowly as a whole, and with them ss (unit_sd) and the share of each ad's
departure the row noise has to take, which nu measures. The scale step moves nu and the
three unit scales given the kap, so it can't break this up.

## The change

`drift-building-phase-unitk` (`frontier/src/rentfrontier/drift_building_phase_unitk.py`)
is L1T with `drift.make_sampler`'s new `unit_kap_collapsed`. Under it the sweep draws each
kap_k from its conditional given the rows' remainders e, with u and s_k integrated out,
and then u and s given the new kap:

1. The scale step, the buildings' levels and the collapsed paths are drawn as in L1T.
2. Each log kap_k gets a slice update on its collapsed density (`collapsed_kap`, slice
   width 2). The units are independent given e, so the update runs on all of them at once.
3. u and every s_k are drawn jointly by Matheron's rule given the new kap (`draw_us`).
4. ss and the kap move along the orbit, as in L1T. L1T's Gamma draw of the kap given s is
   skipped.

Steps 2 and 3 together draw (kap, u, s) from their joint conditional, since step 3
replaces u and s entirely, so the sweep leaves L1T's posterior unchanged. The new kap no
longer depends on the old s_k, which removes the coupling above.

The collapsed density comes cheaply from what the sweep computes already (`kap_logp`).
With v = ss^2 / kap_k and A the precision of the unit's rows at v = 0, the rows have log
density

    -log(1 + v a) / 2 + v b^2 / (2 (1 + v a)),   a = 1' A 1,  b = 1' A e,

up to a constant. `unit_W` already gives the unit's precision W at the current kap, from
which a0 = 1' W 1 = a / (1 + v0 a) and b0 = 1' W e = b / (1 + v0 a), so a and b follow
without a new inverse. The Gamma(3/2, rate 3/2) prior and the Jacobian of log kap add
3 l / 2 - 3 e^l / 2 at l = log kap. Each slice update evaluates this at a few points per
unit, then `unit_W` runs once more at the new kap before `draw_us`.

`drift.py` changes only behind the new argument, and with it left False the sweep draws
what it drew before. The sha256 pins of `drift-building`, L1, L1T and U2
(`frontier/tests/test_drift_building_phase.py`, `test_drift_building_phase_unitt.py`,
`test_drift_building_unitt.py`) pass unchanged.
`frontier/tests/test_drift_building_phase_unitk.py` checks `kap_logp` against differences
of `unit_loglik`, the Kalman filter's marginal likelihood, plus the prior, for units with
one row and with several, each moved alone by factors from 0.05 to 20. It checks that a
long run of the step alone, at fixed e, draws each unit's log kap with the mean and SD of
its density on a grid, that sweeps keep nu_u at 3 while the kap move, and it pins the
draws of a small run.

RESULTS_CHECK

## Launch plan (no fit is launched by this note)

LAUNCH_PLAN

## Predictions (written before launch)

PREDICTIONS
