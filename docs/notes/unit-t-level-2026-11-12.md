# A Student-t lasting level for each unit (U2, 2026-11-12)

The own-history check (`docs/notes/own-history-2026-11-12.md`) set the next ad's deviation
from b9's median against the unit's own deviation in its training ads. The least-squares
weight on the unit's own deviation climbs from 0.09 for deviations under 0.05 to 0.47 for
those over 0.5, and it climbs within every bedroom count. A normal prior on the unit's
lasting level shrinks every deviation by the same share, so that pattern points to a
heavier tail than the normal allows. U2 lets the tail be heavier and lets the data set how
much.

## The change

`drift-building-unitt` gives unit k's lasting level s_k a mixing scale kap_k of its own:
s_k has variance `unit_sd^2 / kap_k`, and kap_k ~ Gamma(nu_u / 2, rate nu_u / 2), so s_k is
Student-t with nu_u degrees of freedom and scale `unit_sd`. nu_u takes a Gamma(2, rate 0.1)
prior, the one the rows' noise nu takes, with mean 20 and 95% of its mass between about 2.4
and 56. Everything else is c3's model, `drift-building` with `--level-dof 4`.

I added the sampler's parts to `drift.make_sampler` behind a `unit_t` flag:

1. The scale step and the u step read each unit's variance `unit_sd^2 / kap_k` in W, the
   Kalman filter and the predictions.
2. u is drawn with every s_k by Matheron's rule (`draw_us`).
3. Given s, nu_u is drawn by a slice update with the kap integrated out, then each kap_k
   from its Gamma conditional, then `unit_sd` and all kap together along the orbit
   `(unit_sd, kap) -> (g unit_sd, g^2 kap)`, which keeps every `unit_sd^2 / kap_k`. g^2
   has a Gamma conditional there and is drawn exactly.
4. The scale step moves nu_u too, with the kap carried along as the rows' lam are carried
   with their nu. In the trial fits nu_u and `unit_sd` trade against each other, and the
   Gibbs step alone left nu_u with a bulk ESS of 45 to 73 in 600 draws.

A held-out ad of a unit with training ads uses its unit's kap_k. An ad of a unit with none
uses a kap drawn from the prior at each sweep. The run traces `unit_dof`, and the gate
checks it with the other scalars. With `unit_t` off, a run of `drift-building` draws arrays
identical to master's, pinned by the sha256 test from #1330.

On a synthetic design of 1,586 units with planted Student-t(2.5) levels of scale 0.25, two
chains of 1,200 draws gave nu_u a median of 2.15 (98% interval 1.67 to 2.64, R-hat 1.025,
bulk ESS 121). With planted normal levels, 600 draws gave a median of 17 (4.8 to 59).

## The fit

The dataset is c3's, `/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`,
and the base is c3, `drift-building-b0-latest-ae875fc6-c3` (6 chains of 3,400 draws). The
plan is three H100 containers, each `2 500 9000 40 --seed S --level-dof 4 --no-loo
--no-heldout` with `--input /data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet`
and seeds 21, 22 and 23, pooled by `drift_pool` into 6 chains. I compare the pool with all
of c3 on the held-out ads, with the SE clustered by building.

On the CPU a sweep took 0.289 s against the building model's 0.215 s on a design of 16,897
rows and 5,112 units, 34% more. c3 swept 3,900 times in its 2,520 s budget, so each
container here should stop near 2,900 sweeps, about 2,400 draws a chain and 60 kept.
`cap.py` states a rate of 1.1 s a pair of chains and estimates $4.19 and 3,560 s a
container, inside the hour. c3's containers settled at $3.63 to $3.69 with the same budget,
so I expect $10.9 to $11.3 for the three.

U1, the unit's size, has not run. The sprint's plan (item 10 in
`docs/notes/outlier-sprint-2026-11-11.md`) put U2 on U1's winner and predicted degrees of
freedom over 8 and an elpd move under 100 there. On c3's base the levels still carry what
size would explain, so I expect a heavier tail and a larger gain than that.

## Predictions (written before launch)

1. The pool passes the gate, `unit_dof` included (55%).
2. nu_u's posterior median is under 8 (65%), and between 2.5 and 6 (45%).
3. `unit_sd`, now the Student-t's scale, falls from c3's 0.059 to between 0.035 and 0.055
   (65%).
4. `drift_sd` and the four `sigma` move by less than 5% each (60%).
5. elpd on the shared held-out ads gains over c3 by more than 2 SE (65%), and by 100 to 600
   (50%).
6. The median's error falls by 0.0001 to 0.0010 from c3's 0.04035 (55%).
7. Coverage of the 80% interval stays within 0.005 of c3's 0.8102 (70%).
8. $10.5 to $12 for the three containers (80%).
