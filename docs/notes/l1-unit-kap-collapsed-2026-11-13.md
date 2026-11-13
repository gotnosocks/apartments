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

Step 2 leaves the kap's conditional given e unchanged, and step 3 then replaces u and s
entirely given the kap, so together they leave the joint conditional of (kap, u, s) and
L1T's posterior unchanged. This needs nu_u fixed, as here: a free nu_u moves after `draw_us`
and would leave the kap behind, and `make_sampler` refuses the pair. The new kap no
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

## The check on thelio

I ran L1T and this model on the CPU on the 1-in-90 sample of buildings from Y1's timing,
the latest split's 18,441 training rows and 10,135 units: 6 chains each, 300 warmup and
1,500 draws, seed 1 (`l1-unit-kap-collapsed-2026-11-13/sub_run.py`). The harness also
traces the mean of log lam over the rows (`x_mll`) and the variance of log kap over the
units (`x_vlk`). `l1-unit-kap-collapsed-2026-11-13/mix_stats.py` gives each quantity's
split R-hat and bulk ESS over the 6 chains, as the gate computes them, and tau = 9,000 /
ESS. The two runs agree on every value: unit_sd 0.047, drift_sd 0.027, drift_tau 2.6, nu
2.1 in both.

| quantity | L1T R-hat | ESS | tau | this model R-hat | ESS | tau |
|---|---:|---:|---:|---:|---:|---:|
| nu | 1.0659 | 59 | 152 | 1.0382 | 209 | 43 |
| unit_sd | 1.0350 | 204 | 44 | 1.0284 | 220 | 41 |
| drift_sd | 1.0120 | 493 | 18 | 1.0124 | 513 | 18 |
| drift_tau | 1.0016 | 846 | 11 | 1.0033 | 1,033 | 9 |
| sigma[1] | 1.0295 | 320 | 28 | 1.0184 | 520 | 17 |
| sigma[3] | 1.0275 | 303 | 30 | 1.0170 | 627 | 14 |
| mean log lam | 1.0620 | 64 | 140 | 1.0374 | 212 | 43 |
| variance of log kap | 1.0224 | 241 | 37 | 1.0136 | 534 | 17 |

The sample is much harder on nu than the full data, where L1T's nu has tau 17.7, but the
two runs share the data and the seed, so the ratios compare the sweeps. The collapsed kap
cut nu's tau by 3.5 times, the rows' mean log lam's by 3.3, the spread of the kap's by 2.2
and sigma's by 1.6 to 2.1. unit_sd's fell by only 8%.

unit_sd's slow part moves with nu: their block means correlate at 0.82, and unit_sd's
correlate with the rows' mean log lam at 0.82, with sigma[1] at 0.72 and with the spread
of the kap at 0.61. This is the choice of whether a big departure belongs to the unit or to
the ad. The scale step moves unit_sd, nu and sigma together, but holds the kap, and with
the kap held each step can go only a little way along this direction. Drawing the kap
afresh given e has freed the kap but not unit_sd. A move of unit_sd with every kap
integrated out would need its own exact draw of the kap after it, since the slice update
of the kap from the old values is valid only when nothing it depends on changed in
between. That is a larger change than this one: the scale step's density would integrate
each unit's kap numerically, and the kap would be drawn exactly afterwards from that
integral, or the two moved together in a Metropolis step. I have left it for its own note
and module.

### What the full fit should expect

I take the full pool's ESS to scale with tau: ESS_new = ESS_L1T x tau_L1T / tau_new, from
the ratios above. I take R-hat^2 - 1 to scale with tau too, since it measures the
variance between half-chains of their means. From L1T's pool:

| quantity | L1T R-hat | ESS | expected R-hat | ESS |
|---|---:|---:|---:|---:|
| nu | 1.0251 | 567 | 1.007 | 2,000 |
| unit_sd | 1.0187 | 449 | 1.017 | 480 |
| drift_sd | 1.0051 | 942 | 1.005 | 980 |
| sigma[1] | 1.0103 | 1,250 | 1.006 | 2,000 |

nu and sigma[1] would pass with room. unit_sd would still miss on R-hat. The ratio for
unit_sd is the least certain: on the full data its tau rose from L1's 11.4 to 27.3, so the
unit tail costs it more there than on the sample, and the full data's units have more ads
for the kap to read. I put the chance that the pool passes the gate at 25%.

## Cost

Alone on thelio's CPU, on the sample above with 6 chains, a sweep of L1T took 3.15 s
(60 warmup and 240 draws) and a sweep of this model 2.92 s (300 warmup and 1,500 draws).
The runs differ in length, so these don't show the new model to be faster, only that the
collapsed step, a few evaluations of an elementwise density for each unit and one more
`unit_W`, is small beside the rest of the sweep. On Modal L1T's containers swept
at 0.67 to 0.77 s and settled at $3.57 to $3.73. The sweep budget caps each container, so
`cap.py` estimates each at $4.19 and 3,560 s, the same as L1T, and I expect 3 containers to
settle at about $11.

## Launch plan (no fit is launched by this note)

With the gate's chance at 25% I do not recommend launching this model alone. If Ben
wants it run, it is L1T's plan with the model's name:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "l1tk1 1" "l1tk2 2" "l1tk3 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-unitk b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. The pool is compared with L1's,
`drift-building-phase-b0-latest-9a7830fb-l1`, on the held-out ads both share, as L1T's note
sets out.

## Predictions (written before launch)

These assume the launch above, 3 containers on the latest split, compared with L1 on
the shared held-out ads.

1. The pool passes the gate (25%).
2. nu's R-hat is at most 1.01 (80%).
3. unit_sd's R-hat is above 1.01 (70%).
4. If it passes, elpd gains over L1 by more than 2 SE (90%), within 300 of L1T's +4,095
   (80%), since the model is L1T's.
