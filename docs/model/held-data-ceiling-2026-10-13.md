# Held-data explanation ceiling for C's building terms (2026-10-13)

This note covers action 2 of the 2026-10-13 plan. The question is how much of the served fit C's
building terms could be explained by facts already held, using only data that is strictly as-of
and rent-blind. It is a free check on thelio: no refit, no Modal, and the served model is unchanged.

C is `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope` on `nb8-nostuy-v1`
(run `...-5c1e5c7e-...`). Its board new-building miss is 11.89%.

The scripts are `docs/analysis/scripts/held_data_ceiling.py` (steps `target`, `features`, `gate`,
`static`, `residual`, `control`), `held_data_ceiling_levels.py` and `held_data_ceiling_split.py`.
Their outputs are in `/data1/apartments/frontier/ceiling/2026-10-13/`.

## Method

1. **Targets.**
   - The static target: I ran C's 1,000 kept draws through `explain.log_terms` and summed the
     building terms (level, walk, bedroom premium, feature slopes) for every training row. For each
     building, I took the precision-weighted mean of its rows draw by draw, weighting each row by
     1 / (posterior variance of its building part). The mean and variance over draws give the
     target and its noise.
   - The residual target: the log ask minus the log predictive median of the new-building rung,
     read from action 1's per-row file (`newbuilding/...-45006f5/rows.parquet`).
   - My per-row building part matches that file's `building_part` on all 193,376 rows, with a
     maximum difference of 0.
2. **Features.** Every feature reads no rent and describes the listing as of its date.
   - Building facts, taken at the row's own value: PLUTO as-of (era, size, class, status), elevfill,
     lines, hpd, stabilized share, lister, retail, noise, trees, crime and petsfill.
   - Predicted size for case a rows only, meaning the size is unknown and nothing in the building
     states one.
   - For each ad-level column of the base set (coded fields, description flags, unit traits), the
     building's mean over ads dated strictly before this one, plus the log count of those ads. The
     leaky control uses the mean over all of the building's ads instead, including the row's own
     ad and later ones.
   - Coordinates, for the variants with coordinates.
   - The table has 214,887 rows and 235 columns.
3. **Models.**
   - WLS: weights are 1 / (posterior variance + residual between-building variance), and missing
     as-of means are filled with indicators.
   - LightGBM: 15 leaves, early stopping on a lot-grouped inner split.
   - Folds are 5, grouped by whole tax lot (5,415 buildings on 5,060 lots).
   - Intervals are 90% lot-cluster bootstraps.
   - The board miss is recomputed after shifting each row's predictive median by the out-of-fold
     prediction. The intervals are left as they are.

## Correctness gate

On the old level target (`kept["building"]`), with random building folds and all-row means, the
pipeline rebuilt from current code and data gives:

| Family | v1 | Now (seed 0) | 5 fold seeds |
|---|---:|---:|---:|
| hpd | 1.38% | 1.38% | 1.24 to 1.44 |
| elevfill | 2.42% | 2.42% | 2.42 to 2.53 |

Both are within 0.3 pp, so the gate passes.

## Static target (building's precision-weighted building part)

Explained share, lot folds:

| Variant | WLS | LightGBM |
|---|---:|---:|
| as-of, no coordinates | 35.2% [33.1, 37.4] | 41.7% [39.7, 43.7] |
| as-of, coordinates | 36.4% [34.4, 38.6] | 44.2% [42.1, 46.2] |
| leaky all-row means, no coordinates | 44.4% [42.4, 46.4] | 48.6% [46.8, 50.5] |
| leaky all-row means, coordinates | 45.4% [43.5, 47.3] | 50.9% [49.2, 52.9] |
| coordinates only | 1.0% [0.5, 1.3] | 9.9% [8.5, 11.3] |

On the old level target the same as-of set explains 29.3% (WLS). The as-of building means of the
ad-level fields explain 15.7% of it alone, and PLUTO explains 7.1%. These shares are large because
C's per-row coefficients leave the between-building part of those fields in the building terms.
Without building-mean columns, a random intercept takes up that part.

Families on the static target (WLS, lot folds, 50 permutations). Each one beats chance when its
share exceeds max(0, null 95th percentile).

| Family | Share | 90% interval | Null 95% | Predicted |
|---|---:|---:|---:|---:|
| coded ad flags, as-of means | 21.2% | 19.3 to 23.4 | -1.09 | |
| description flags, as-of means | 9.8% | 8.5 to 11.2 | -0.14 | |
| PLUTO as-of | 9.2% | 7.8 to 10.8 | -0.14 | |
| finish words, as-of means | 7.6% | 6.3 to 8.8 | -0.01 | ~0.8 (0.1 to 2.5) |
| predsize case a | 7.2% | 6.0 to 8.4 | 0.03 | ~1.2 |
| stabilized share | 4.7% | 3.9 to 5.7 | 0.01 | |
| elevfill | 3.9% | 3.1 to 4.7 | -0.02 | ~2.2 |
| lister | 2.8% | 1.9 to 3.6 | -0.01 | |
| noise | 1.5% | 1.0 to 2.1 | -0.00 | |
| lines | 1.4% | 0.7 to 2.0 | -0.10 | ~1.9 |
| hpd | 1.3% | 0.9 to 1.9 | -0.01 | ~1.2 |
| petsfill | 1.3% | 0.8 to 1.8 | 0.04 | |
| earlier-ad count | 0.9% | 0.4 to 1.3 | 0.02 | |
| retail | 0.7% | 0.2 to 1.2 | -0.01 | |
| crime | 0.1% | -0.2 to 0.3 | -0.00 | beats chance by the rule, interval spans 0 |
| trees | -0.1% | -0.2 to -0.1 | 0.01 | does not beat chance |

I did not score two families from the plan:
- action 3's ever-coded amenity tier, because it has not been built;
- areatime, which is a model term with no columns.

The finish-word and predsize case-a families carry more than the plan expected. Both act mostly as
building descriptors: case a picks out buildings where no ad states a size.

## Residual target and board miss

Change in the board's new-building miss (pp) and drop in mean squared log error, lot folds:

| Variant | WLS miss | LightGBM miss | WLS SLE drop | LightGBM SLE drop |
|---|---:|---:|---:|---:|
| row target, as-of, no coordinates | -1.56 [-2.00, -1.11] | -1.97 [-2.29, -1.66] | 0.0105 | 0.0128 |
| row target, as-of, coordinates | -1.62 [-2.05, -1.19] | -2.33 [-2.68, -1.97] | 0.0106 | 0.0137 |
| row target, leaky, no coordinates | -1.69 [-2.15, -1.19] | -1.95 [-2.36, -1.57] | 0.0111 | 0.0132 |
| row target, leaky, coordinates | -1.73 [-2.18, -1.25] | -2.29 [-2.68, -1.92] | 0.0112 | 0.0142 |
| static target applied to rows, as-of, no coordinates | -1.39 [-1.74, -1.03] | -2.06 [-2.40, -1.73] | 0.0099 | 0.0128 |
| static target applied to rows, as-of, coordinates | -1.41 [-1.75, -1.08] | -2.21 [-2.53, -1.88] | 0.0100 | 0.0133 |
| static target applied to rows, coordinates only | -0.01 [-0.12, 0.10] | -0.57 [-0.82, -0.33] | 0.0002 | 0.0037 |

The residual's mean squared log error before any shift is 0.0404.

**Control: C's own columns.** I re-regressed the residual on C's own feature columns alone, then on
those columns plus the as-of set:

| Design | WLS miss | LightGBM miss |
|---|---:|---:|
| intercept only | +0.16 | |
| year dummies | +0.10 | |
| C's own columns + year | -1.25 | |
| C's own columns | -1.24 [-1.65, -0.85] | -2.06 [-2.44, -1.71] |
| own + all as-of | -1.75 [-2.22, -1.23] | -2.69 [-3.06, -2.34] |
| **as-of increment over own** | **-0.51 [-0.69, -0.33]** | **-0.62 [-0.78, -0.46]** |
| ad-level means increment over own + year | -0.25 [-0.38, -0.10] | |
| external families increment over own + year | -0.32 [-0.44, -0.19] | |
| all as-of increment over own + year | -0.51 [-0.69, -0.33] | |

An intercept makes the miss worse, so the own-columns gain does not come from a level offset. It
comes from the between-building relation of C's own columns to rent, which the per-row coefficients
fit within buildings and the building terms then absorb. A new building's predictive median, drawn
from the population with mean 0, misses that relation. A refit can only reach the gain by adding
columns that carry the building-level variation of those fields, such as building means. Adding
rows of the same columns again would not reach it.

**Implied fall in descriptive share.** Building, building over time and building slopes make up
19.9 pp of C's 26.1% descriptive share. If the static-target predictions were fitted, the share of
the row-level building part they explain would remove about this much:
- 6.4 pp [5.1, 7.6] with WLS, no coordinates;
- 8.2 pp [7.6, 8.8] with LightGBM, no coordinates;
- 6.5 pp (WLS) and 8.6 pp (LightGBM) with coordinates.

This is an approximation from variance shares, not a refit.

**predsize case a on size-unknown rows** (WLS on the predsize columns): +0.12 pp [-0.08, +0.27].

## Leak control

The leaky all-row-means variant exceeds the as-of variant on squared log error in every
configuration, and on the miss for WLS. On the miss with LightGBM it does not:
- row target, no coordinates: -1.95 leaky against -1.97 as-of;
- row target, coordinates: -2.29 against -2.33.

The differences are 0.02 to 0.04 pp, well inside the intervals, and the median miss is a noisier
statistic than the squared error. By the plan's rule this counts as a miss of the control for
LightGBM on the miss scale, so I base the decision below on the WLS numbers, where the control
passes. The leaky columns add only about 0.1 pp to WLS, so later ads hold little that earlier ads
do not.

## Predictions against results

| Prediction (written before the run) | Result | Hit or miss |
|---|---|---|
| No-coordinates ceiling -0.3 to -0.35 pp (-0.1 to -0.75) | -1.56 WLS, -1.97 LightGBM; increment over C's own columns -0.51 WLS, -0.62 LightGBM | miss |
| With coordinates -0.6 to -0.8 pp (-0.3 to -1.4) | -1.62 WLS, -2.33 LightGBM | miss |
| Coordinates' extra is location | WLS +0.06 pp, LightGBM +0.36 pp over no coordinates | the extra is small for WLS |
| Descriptive-share fall -0.7 to -0.9 pp, P(>= 2 pp) 0.07 to 0.1 | about -6.4 pp (WLS) | miss |
| elevfill ~2.2% | 3.9% | miss |
| lines ~1.9% | 1.4% | close, inside its interval |
| hpd ~1.2% | 1.3% | hit |
| predsize case a ~1.2% | 7.2% | miss |
| finish words ~0.8% (0.1 to 2.5) | 7.6% | miss |
| amenity tier 1.5 to 2.5% | not scored, action 3 not built | |
| predsize case-a offset -0.04 pp (0 to -0.15) | +0.12 pp [-0.08, +0.27] | miss (wrong sign, interval spans 0) |
| Expected answer: held data cannot reach 0.5 pp (P ~0.7) | it reaches 0.5 pp | miss |
| Gate reproduces v1 within 0.3 pp | 1.38 and 2.42 | hit |
| Leaky variant exceeds the as-of ceiling | yes on SLE and WLS miss; no on LightGBM miss, by 0.02 to 0.04 pp | partial miss |

## Decision

The rule for >= 0.5 pp with a bootstrap bound above 0.3 applies to two figures:
- the linear (WLS) as-of ceiling without coordinates, -1.56 pp [-2.00, -1.11];
- its increment over C's own columns, -0.51 pp [-0.69, -0.33].

The linear ceiling keeps well over 0.3 pp, so the plan's next step is to propose one fixed-part
feature-set fit (~$2.2) as its own action. I have not launched it. The candidate set is C's base
plus:
1. building means over strictly earlier ads of C's ad-level columns, with a missing indicator for
   a building's first ads (Mundlak-style between-building columns);
2. the external held families whose intervals exclude 0: stabilized share, elevfill, lister,
   noise, hpd, petsfill, lines and retail.

The own-columns result suggests the first group is the larger lever. A building-mean column lets
the fixed part price the between-building relation that the building terms now hold, and that
relation moves variation from descriptive building terms into explanatory columns. predsize gets
no fit: its case-a offset does not reach 0.1 pp and its interval includes 0.
