# A noise scale by calendar year (Y1, 2026-11-12)

The outlier sprint found the served fit's 80% intervals covering 0.745 of the held-out asks
of 2020 to 2022, against 0.826 before and after, and found the same shortfall on training
rows of those years ("The years 2020 and 2021 on training rows" in
`docs/notes/outlier-sprint-2026-11-11.md`). L1 (`drift-building-phase`,
`docs/notes/lease-phase-noise-2026-11-12.md`) scales the noise by lease phase. Before
designing Y1 I checked whether L1's phases had already closed the gap.

## The check on L1's held-out ads (no fit)

I scored L1's pool (`drift-building-phase-b0-latest-9a7830fb-l1`) and c3ab
(`drift-building-b0-latest-ae875fc6-c3ab`) by the calendar year of each held-out ad's
price_at, on the 189,647 ads both hold out. The gain is L1's elpd less c3ab's, with the SE
clustered by building. The script is `docs/notes/year-noise-2026-11-12/by_year.py`.

| year | n | L1 gain | SE | 50% L1 | c3ab | 80% L1 | c3ab | 95% L1 | c3ab |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 1,033 | -12.4 | 5.1 | 0.544 | 0.556 | 0.779 | 0.788 | 0.922 | 0.931 |
| 2015 | 2,426 | -4.4 | 7.4 | 0.525 | 0.531 | 0.787 | 0.800 | 0.938 | 0.943 |
| 2016 | 3,292 | -20.9 | 8.4 | 0.518 | 0.522 | 0.781 | 0.795 | 0.935 | 0.944 |
| 2017 | 4,836 | -14.3 | 11.9 | 0.542 | 0.549 | 0.804 | 0.811 | 0.939 | 0.943 |
| 2018 | 6,939 | -6.2 | 10.6 | 0.555 | 0.558 | 0.821 | 0.832 | 0.954 | 0.961 |
| 2019 | 8,010 | +2.4 | 10.8 | 0.564 | 0.574 | 0.835 | 0.845 | 0.957 | 0.962 |
| 2020 | 15,778 | -120.2 | 17.4 | 0.450 | 0.458 | 0.734 | 0.745 | 0.911 | 0.923 |
| 2021 | 17,472 | -67.6 | 18.3 | 0.436 | 0.443 | 0.724 | 0.730 | 0.915 | 0.925 |
| 2022 | 12,760 | -38.9 | 15.0 | 0.456 | 0.462 | 0.755 | 0.766 | 0.924 | 0.935 |
| 2023 | 19,314 | +92.1 | 17.4 | 0.500 | 0.511 | 0.788 | 0.799 | 0.943 | 0.952 |
| 2024 | 26,316 | +184.5 | 18.9 | 0.532 | 0.540 | 0.816 | 0.825 | 0.953 | 0.960 |
| 2025 | 34,531 | +282.3 | 22.7 | 0.539 | 0.550 | 0.823 | 0.833 | 0.955 | 0.962 |
| 2026 | 36,940 | +278.3 | 23.9 | 0.551 | 0.563 | 0.829 | 0.842 | 0.957 | 0.964 |
| to 2019 | 26,536 | -55.9 | 23.7 | 0.548 | 0.554 | 0.812 | 0.823 | 0.947 | 0.953 |
| 2020 to 2022 | 46,010 | -226.7 | 30.3 | 0.446 | 0.453 | 0.736 | 0.745 | 0.916 | 0.927 |
| 2023 on | 117,101 | +837.2 | 47.4 | 0.535 | 0.546 | 0.818 | 0.828 | 0.953 | 0.961 |
| all | 189,647 | +554.6 | 63.2 | 0.515 | 0.524 | 0.797 | 0.807 | 0.943 | 0.951 |

The shortfall is still there. The 80% intervals cover 0.724 to 0.755 of the asks of 2020 to
2022, 0.06 to 0.08 under nominal, and the 50% intervals 0.44 to 0.46. L1 narrowed every
year's intervals by about the same share, so it made the gap a little worse. Against c3ab
it loses 226.7 elpd (SE 30.3) on the ads of 2020 to 2022 and gains 837.2 (SE 47.4) on those
of 2023 on, more than its whole gain. At 80%, the years 2023 to 2026 cover 0.788 to 0.829,
near nominal, and 2014 to 2016 cover 0.779 to 0.787, a little under it.

## The change

`drift-building-phase-year` multiplies L1's noise scale by a factor for the calendar year
of the row's price_at:

    s_i = sigma[group_i] * f[phase_i] * g[year_i]

f is L1's, with f = 1 at 10 to 13 months. The years run from 2014 to 2026. The 3,156
training rows of 2011 to 2013 join 2014, and a row after 2026 would take 2026's factor. I
fixed g = 1 for 2024, which has 122,144 training rows and 26,316 held-out ads and lies in
the steady years. Each of the other twelve log g takes a Normal(0, 0.3) prior, as L1's log
factors do.

Y1 takes only the date from each row, so a row's rent still enters the fit only as its
target. Training rows by year:

| 2014 and before | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 96,646 | 109,905 | 118,344 | 141,521 | 162,105 | 147,785 | 196,335 | 176,243 | 116,806 | 125,471 | 122,144 | 111,154 | 82,365 |

### The sampler

The phases in `drift.py` take a single index per row. To cross two factor sets without a
second copy of that code, `Design` gains `phase_map`, a (phases, free factors) array of 0s
and 1s. With a map, a phase's factor is the product of the free factors its row marks, and
each free factor's row count in the scale density is the sum over the phases it enters. The
new model hands the sampler the 91 cells of phase and year as its phases, phase-major with
(10-13, 2024) first, and a map from each cell to its phase's factor and its year's. The
scale step's slice then moves 8 + 6 + 12 = 26 directions, against L1's 14.

The run keeps every cell's factor as `phase_scale` and each predicted row's cell as
`pred_phase`, so `drift_score` and `drift_pool` read it as they read L1, with no change.
Each free factor is a cell's own (a phase in 2024, or a year at 10 to 13 months), so the
gate's check of every cell covers every free factor. `drift_building_phase_year.factors`
splits a cell array back into the phases' and the years' factors.

With no map, the phase code runs as before. The sha256 test of `drift-building`'s draws
passes, and L1's tests pass.

### Cost

On the CPU, on the 18,441 training rows and 10,135 units of a 1-in-90 sample of buildings
(2 chains, 60 warmup and 60 draws, `docs/notes/year-noise-2026-11-12/time_sweep.py`), a
sweep of L1 takes 1.037 s and a sweep of Y1 1.482 s, 43% more. `cap.py` states 1.4 s a
pair of chains against L1's 1.0. L1's containers swept at 0.776 s on Modal, so Y1's
should take about 1.1 s, and the 2,520 s sweep budget then holds about 2,270 sweeps: 500
warmup and about 1,770 draws a chain, 44 kept, against L1's 2,720 draws and 68 kept.

The first try at this timing ran out of the 4 GB memory cap while compiling Y1's sweep.
`drift.slice_along` unrolled its loop over the slice directions in Python, so the compiled
sweep held one copy of the scale density for each direction. It now runs the directions
in a `jax.lax.scan`, with the same keys in the same order. The sha256 test of
`drift-building`'s draws still passes, so the draws are bit for bit the same, and the
compile of L1's sweep on this sample fell from 89 s to 35 s.

## Launch plan (no fit is launched by this PR)

Two containers, `2 500 9000 40 --seed S --level-dof 4 --no-loo --no-heldout`, seeds 1 and
2, on the same dataset,
`/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`,
pooled by `drift_pool`. I compare the pool with L1's pool on the held-out ads both share,
by elpd with the SE clustered by building, the median's error and the coverage of the 50%,
80% and 95% intervals, overall and by year (`python -m rentfrontier.drift_score RUN`, then
the script above with Y1's pool in place of c3ab). `cap.py` estimates each container at
$4.19 and 3,560 s, as for L1, since the sweep budget caps both. L1's settled at $3.84 and
$3.87.

The fewer draws are the main risk to the gate. L1's pool had its least bulk ESS at 788,
on `drift_tau`, from 4 chains of 2,720 draws. At the same mixing, 4 chains of about 1,770
give about 510, over the 400 the gate asks but with little room. If the pool misses on
ESS alone, a third container with seed 3 is the cheaper fix than a longer one.

## Predictions (written before launch)

1. The pool passes the gate (40%). The scale step has 26 directions against L1's 14, the
   year factors trade off with `drift_tau` and the building paths, and each chain keeps
   about a third fewer draws.
2. The factors of 2020 and 2021 lie between 1.15 and 1.45 (60%), and 2022's between 1.05
   and 1.30 (60%).
3. The factors of 2023, 2025 and 2026 lie within 0.10 of 1 (65%).
4. The factors of 2014 to 2019 all lie between 0.85 and 1.20 (55%).
5. Coverage of the 80% interval on the held-out ads of 2020 to 2022 moves from 0.736 to
   between 0.765 and 0.795 (60%), and on those of 2023 on by less than 0.010 (70%).
6. elpd on the shared held-out ads beats L1's pool by more than 2 SE (70%), and by 200 to
   800 (50%).
7. The "none" phase factor moves from L1's 1.636 by less than 0.10 (60%).
8. The median's error moves by less than 0.0005 (85%), and the two containers cost $7.0 to
   $9.0 (70%).
