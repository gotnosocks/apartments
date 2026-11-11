# A Manhattan doorman premium in the building model (2026-11-11)

Ben asked on 2026-11-11 which feature the site's analyses point to as missing or wrongly
modeled. This note records the free checks behind the answer, the model change he approved
at 05:05Z, and the predictions written before its fit.

## Free checks on the served fit

The served model is `drift-building` (`drift-building-b0-latest-67d14e17-b9` on the latest
split). It gives each doorman class a single coefficient for the city: full 0.027, part 0.022,
virtual 0.002. I read the building levels and held-out ads in
`/data1/apartments/site/diagnostics/`.

1. **Levels by doorman class.** Full-doorman buildings in Manhattan sit at a mean level of
   +8.0% (+7.0% among buildings with 10 or more training ads). In the outer boroughs the
   mean is about 0.
2. **Explained share.** I refit the in-model building attributes to the levels zone by zone
   and scored them on grouped 5-fold building holdouts against 20 permutations. In Manhattan
   they explain 11.8% of the levels (the null's 95th percentile is below 0), and the doorman
   class alone explains 7.3%. In the outer boroughs they explain 2.8%. Place features
   outside the model explain 1.9%.
3. **New buildings.** Held-out Manhattan ads predicted from their area, with no building
   history, run 11% to 24% over the predicted median, and doorman buildings run highest.
4. **Proxies.** Over 14,806 Manhattan buildings with held-out ads, I adjusted the gap
   between no-doorman and full-doorman buildings for other attributes step by step:

   | adjusted for | gap |
   |---|---|
   | doorman alone | -8.3% |
   | plus build year, condo, class | -8.6% |
   | plus height, homes, area, gym | -7.3% |
   | plus in-ad amenities and finishes | -5.5% |

   About a third of the gap goes to things a doorman building tends to have. Two thirds
   stay with the doorman.
5. **Neighbourhoods.** Within Manhattan the gap varies more than chance allows (Q = 311 on
   29 df). It runs from about -3% in FiDi and Tribeca to +15% to +25% on the Upper East
   Side and in Soho. It correlates at -0.46 with the log of the local doorman share and at
   -0.17 with neighbourhood rent. Outside Manhattan Q = 21.9 on 6 df, pooled near 0.
6. **Time.** The held-out full-versus-none gap stays within 1.3 points of its mean from 2014
   to 2026, with no trend. Each building's quarterly path could absorb some of a trend.
7. **Local rarity.** A doorman × (local share minus its mean) term at 500 m takes Q from 311
   to 267: the premium is about 8.9% where 6% of nearby buildings have a doorman and about
   5.4% where 28% do. An era split leaves Q at 290.

So the doorman premium differs by zone, and within Manhattan it is larger where doormen are
rarer. Rarity alone would put the outer boroughs' premium highest, which they do not show.
The zone split is the smaller change, and it comes first.

## The model

`rentfrontier.drift_building_doorman` (`drift-building-doorman`) takes the building model's
design and adds a Manhattan copy of each doorman column, as `bld:doorman_full_manhattan`
and so on. The citywide coefficient reads as the outer boroughs' premium and the copy's as
Manhattan's difference from it. Everything else, including the Student-t building levels
(`LEVEL_DOF` 4), is the building model's.

## Fit and predictions (written before launch)

The fit is the latest split of b9, as three H100 containers of 2 chains,
`2 500 9000 40 --seed S --no-loo --no-heldout` with seeds 1 to 3, pooled by
`drift_pool` and scored by `drift_score` against b9 on the same held-out ads.

1. The pool passes the gate (70%).
2. Manhattan's full-doorman premium (citywide plus copy) is +6% to +10%, with the copy's
   90% interval above 0 (75%).
3. The outer boroughs' full-doorman premium is 0 to +3% (70%).
4. Held-out Manhattan ads of buildings with under 5 training ads have a median bias under
   +5%, against b9's (60%).
5. Held-out elpd gains over b9 but by less than 2 combined SE (55%). Almost every held-out
   ad has a unit history, so most of the gain shows in the area-basis and building-basis
   slices (266 and 1,990 ads), and I report those separately.
6. Median absolute error and 80% coverage move by under 0.001 and 0.005 overall (70%).
7. $11 to $12 for the three containers.

If the pool passes and wins, the market and backtest fits follow so Deals can switch.

**As launched.** From master `cb94a194`: `drift-building-doorman-b0-latest-cb94a194-d1a`
(seed 1) at 05:18Z and `d1b` (seed 2) at 05:25Z, on b9's input and dataset. Ben set a
$10 limit for the night at 05:07Z, and a third container would take the night's spend to
about $11, so the pool is two containers (4 chains) and seed 3 was not launched. Prediction 7
becomes $7 to $8 for the two containers. Four chains of b9's length give a least bulk ESS
near 900 if they mix as b9's did, which clears the gate's 400.
