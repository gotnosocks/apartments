# Conference follow-ups, 2026-10-22

These are the free checks on thelio that Ben approved on 2026-10-22 alongside the follow-up fits. None of them spent Modal budget.

I scored the held-out rows with `conference-followups-2026-10-22/score.py`. It runs one model module against one saved run and works like `building-zones-floor-2026-10-21/heldout.py`:
- 400 draws per run, 100 per chain spread evenly.
- A Student-t log density for each held-out ad.
- Predictive quantiles from a t draw per posterior draw.
- Each ad's building and listing week, kept for clustered standard errors.

I then paired the runs with `conference-followups-2026-10-22/compare.py`. Both scripts ran as their own systemd units. Scoring needs about 5 GB, more than a light slot gives it.

## (a) Mundlak against floor on the latest split

Both fits use the same 1,706,837 training ads and score the same 189,649 held-out ads.

| fit | held-out elpd | RMSE | 50% | 80% | 90% | 95% |
|---|---|---|---|---|---|---|
| floor `building-zones-floor-b0-latest-6b5a5b4a-dense-w1000` | 149,303 | 0.1154 | 0.494 | 0.799 | 0.904 | 0.955 |
| Mundlak `building-zones-mundlak-b0-latest-a6d25054-dense-w1000` | 149,278 | 0.1154 | 0.494 | 0.798 | 0.904 | 0.955 |
| age `building-zones-age-b0-latest-f023987f-dense-w1000` | 146,358 | 0.1172 | 0.493 | 0.799 | 0.904 | 0.955 |

Mundlak minus floor comes to −25 elpd:
- The row SE is 24.
- Clustered by building, the SE is 29.
- Clustered by building and week, it is also 29.

At about one SE, the Mundlak fit predicts held-out ads as well as the floor fit. The Mundlak terms move unit coefficients toward their within-building values, and that leaves the forecast unchanged.

RMSE uses the median of the predictive mean. Coverage counts the held-out ads inside each central predictive interval.

## (b) Floor fit diagnostics, coverage and clustered SEs

The floor model runs on the blocked Gibbs sampler in `building_zones_gibbs.py`, not HMC. There are no divergences, E-BFMI or tree depths to report, and the paper's Section 7a should drop that item. The convergence checks for this sampler are R-hat and bulk ESS. They come from the fit's own summary (`docs/notes/building-zones-floor-2026-10-21.md`).

Held-out coverage on the latest split is 0.799 at 80% and 0.955 at 95%. The 50% and 90% figures are in the table above.

Floor minus age comes to +2,945 elpd under each way of clustering:

| clustering | SE | ratio |
|---|---|---|
| row (sd × √n) | 83 | 35 |
| building (36,242 clusters) | 172 | 17 |
| building and listing week (668 weeks), Cameron, Gelbach and Miller | 171 | 17 |

On its own, clustering by week gives an SE of 82, and the building-by-week cells give 84. Clustering by building is what doubles the SE. Adding the week dimension changes it by less than 1. The floor gain is about 17 two-way SEs.

## (c) HSGP settings per zone

The map uses a fixed lengthscale of 1.0 km (`whitened_zones.LENGTHSCALE`). I built each zone's box like this:
1. Rotate the buildings to the zone's angle.
2. Take the 0.1 to 99.9% quantile box.
3. Widen it by the boundary factor C = 1.5.

Each axis then gets ceil(1.75 · L / l) waves, where L = C · S is the widened half-width and S the half-width of the quantile box.

| zone | angle | widened half-widths L (km) | box (km) | waves | basis functions | smallest resolvable lengthscale (km) |
|---|---|---|---|---|---|---|
| Manhattan | 25.5° | 2.625 × 9.436 | 5.25 × 18.87 | 5 × 17 | 85 | 0.92 × 0.97 |
| not Manhattan | 39.0° | 5.672 × 6.262 | 11.34 × 12.52 | 10 × 11 | 110 | 0.99 × 1.00 |

The smallest resolvable lengthscale per axis is 1.75 · L / m, where m is the number of waves. The rule puts it at about 1 km by construction, in line with the fixed lengthscale.

The `gp_ls` in the fit summary belongs to the floor curves and is measured in log-floor units, not km. The floor-curve prior:
- amplitude² is InvGamma(2, 0.04);
- log lengthscale is Normal(log 0.7, 0.5);
- the nugget is 0.01.

The whitening uses sigma 0.19, nu 7 and amplitude 1.0 as its reference values.

## (d) The elevator floor curve at the top

The table gives posterior medians in log points × 100 against the floor-2 baseline, with 90% intervals and training-ad counts:

| floor | median | 90% interval | training ads |
|---|---|---|---|
| 36 | 10.97 | | 2,618 |
| 37 | 11.38 | | 2,252 |
| 38 | 11.69 | 11.33 to 12.10 | 2,109 |
| 39 | 11.83 | 11.41 to 12.27 | 1,870 |
| 40 | 12.93 | 12.54 to 13.34 | 1,833 |
| 41 | 12.44 | 12.01 to 12.88 | 1,667 |
| 42 | 12.30 | 11.84 to 12.74 | 1,668 |
| 43 | 13.19 | 12.71 to 13.60 | 1,407 |
| 44 | 13.89 | 13.35 to 14.38 | 1,194 |
| 45 | 13.84 | 13.35 to 14.37 | 1,229 |
| 46 | 14.44 | 13.94 to 14.97 | 1,045 |
| 47+ | 17.84 | 17.56 to 18.12 | 8,929 |

The floor snapshot holds 9,105 listings at floor 47 or above. Their median floor is 52, and the quartiles are 49 and 58. The 90th percentile is 64, the 99th is 78, and the highest is 104.

The 47+ node pools those floors. A median floor of 52 sits about 0.12 above floor 46 in log floor. From floor 43 to 46 the curve climbs about 18 points per unit of log floor. At that slope, 0.12 more log floor adds about 2.2 points, which covers most of the 3.4-point jump. The pooled node absorbs the remaining 1.2 points or so. Fit 8 raises the cap, and that tests this reading.

The posterior median falls between nine pairs of neighboring floors:

| pair | drop (points) | P(dip) |
|---|---|---|
| 11→12 | −0.05 | 0.70 |
| 13→14 | −0.04 | 0.61 |
| 18→19 | −0.08 | 0.71 |
| 21→22 | −0.04 | 0.60 |
| 30→31 | −0.03 | 0.56 |
| 34→35 | −0.12 | 0.70 |
| 40→41 | −0.49 | 0.92 |
| 41→42 | −0.14 | 0.67 |
| 44→45 | −0.05 | 0.54 |

Eight of the drops are under 0.15 points, with P(dip) between 0.54 and 0.71. The drop at 40→41 is half a point, with P = 0.92. Floor 40 sits half a point above its neighbors, so the mark there likely comes from a few large buildings with many ads on that floor. Follow-up (g) counts the buildings per floor.

## (e) The map amplitude against its prior

The map amplitude has a HalfNormal(0.3) prior (`two_zone.Priors.amp`).

| zone | posterior median | 90% interval | prior P(amp > median) | z |
|---|---|---|---|---|
| Manhattan | 0.916 | 0.77 to 1.09 | 0.0022 | 3.07 |
| not Manhattan | 0.360 | | 0.23 | |

The Manhattan amplitude sits deep in the prior's tail, so the data pulled it well past what the prior favored. Fit 3 refits with HalfNormal(1.0) to check whether the prior still holds it down.

## (f) The latest split and look-ahead

`splits.latest_split` (`frontier/src/rentfrontier/splits.py:66`) works per unit, not by calendar. It takes each unit with two or more listings and finds the unit's latest listing by `price_at`. Units whose two latest listings share a date drop out. From the remaining latest listings it draws 10% of all rows at random, with a fixed seed.

As a result:
- The held-out ads run from 2014-01-01 to 2026-10-16, the same span as training.
- Each of the 189,649 held-out ads shares its unit with at least one training ad.
- The gap back to the unit's previous ad has a median of 733 days, quartiles 382 and 1,219, and a minimum of 1.
- The weekly walk L(t) interpolates between training ads from the same weeks. It never forecasts past the end of training.

The paper should describe the split as a test of each repeated unit's latest ad, not as a forecast.

`b0.main_run` builds the design from every row and slices it afterwards (`b0.py:956-962`, `score` at `b0.py:1132`). No rents enter any feature. Several features, though, read other ads, held-out and later ones included:

| feature | source | verdict |
|---|---|---|
| unit size fill (`unit_features.sizes`, snapshot `unit-features/20261021-16cea7c`) | median over all of the unit's listings at any date, then the line's median, then the median per bedroom count | uses held-out and later ads. 15.7% of held-out ads take a unit fill, 7.0% a line fill |
| building top floor (`unit_floor.py:54`) | MapPLUTO `numfloors`, else the highest floor any of the building's ads lists | mostly external. 99.1% of held-out ads take PLUTO and 0.82% take the ads fallback |
| unit floor | the ad's own floor or unit label. A penthouse with no floor takes the building's top floor | own ad |
| Mundlak building means (`building_zones_mundlak.py:94`) | means over every design row in the building | uses held-out and later ads |
| `bld:elevator`, doorman flags, floor count (`building_attrs.py:31`) | share or median over all of the building's ads, else PLUTO | uses held-out and later ads |
| `bld:gym` (`building_gym.py`) | share over all of the building's listings | uses held-out and later ads |
| laundry, dishwasher | the ad itself | own ad |

The leak runs both ways. A held-out ad can feed its own row through its own description, and it can feed earlier training rows of its unit and building as well. None of this carries a rent. The same paths stay open on the whole-building split, but only within held-out buildings, since every ad of a held-out building is held out together. A leak-free version would rebuild the size fills and building shares from training ads only, with `sizefill.asof_size` reading earlier days, and rerun both splits.
