# Filling in unit size, 2026-10-21

Size against the bedroom median led the residual screen (`residual-screen-2026-10-21.md`), and
only 26% of training ads state a size. Before any model uses size, I counted how far other
listings could fill it in. I took the frontage run's 1,706,837 training rows on the latest split
and the pipeline rows `rows-edc83b49f9bacd8c`, kept sizes between 100 and 10,000 sq ft, and
added two layers:

- (b) the median size over every listing of the same unit, from any date. I matched a unit on
  its building and its label from the ad's URL, upper-cased, with punctuation and an `APT` or
  `UNIT` prefix removed.
- (c) the median over other units of the same building, line and bedroom count. The line is
  the letter of a label like `4B` or `B4`, or the last two digits of a label like `412`. I left
  out penthouse, garden, parlor and basement labels and the building's top two floors, where
  setbacks change the plan.

Nothing here changes a model or runs a fit. The scripts are in `size-coverage-2026-10-21/`,
and the tables are on the data page at https://claude.ai/artifact/18EAWB1h8yYdZPvtGsTHod.

## Coverage

| ads | (a) stated | (b) + same unit | (c) + same line |
|---|---|---|---|
| all, 1,706,837 | 26.2% | 39.1% | 45.0% |
| Manhattan | 29.3% | 41.8% | 49.7% |
| Brooklyn + Queens | 21.8% | 35.2% | 38.3% |
| studio | 25.1% | 38.4% | 47.8% |
| 1 bed | 28.6% | 41.5% | 48.9% |
| 2 bed | 25.5% | 38.3% | 42.8% |
| 3 bed | 23.4% | 35.7% | 38.1% |
| 4+ bed | 24.7% | 37.0% | 38.1% |

Counted by unit (878,377 building and label pairs, each scored on its first training ad), the
layers reach 25.9%, 32.4% and 38.2%. (b) adds less per unit than per ad, which fits units with
many ads being likelier to have stated a size on one of them. Line matches add the most in
Manhattan and for studios and 1-beds, and only 3 points in Brooklyn + Queens. I have not split
the cause by label type.

18.4% of the ads still missing after (c) have a floor plan attached. Reading every plan would
bring coverage to 55.1% at most.

## Holdout

For each ad stating a size, I hid that ad's size and imputed it from the remaining listings.
Errors are absolute log differences.

| imputed from | ads | median | 90th percentile | within 10% |
|---|---|---|---|---|
| (b) other listings of the unit | 283,736 | 0.000 | 0.105 | 88.7% |
| (c) where (b) has nothing | 46,384 | 0.001 | 0.144 | 84.4% |
| (b), then (c) | 330,120 | 0.000 | 0.112 | 88.1% |

The zero medians mean brokers often copy the same figure from ad to ad, so the 90th percentile
is the more useful number: one imputed size in ten misses by about 12% or more.

## Skew

| group | ads | leftover median | Manhattan | 3+ bed |
|---|---|---|---|---|
| state a size | 446,823 | +5.5 | 65.4% | 15.9% |
| no size | 1,260,014 | -4.4 | 56.1% | 18.2% |
| no size, filled by (b) or (c) | 320,514 | -1.0 | 63.6% | 13.6% |
| still missing | 939,500 | -5.5 | 53.5% | 19.8% |

The leftover is in log points against the zone mean. Ads stating a size sit 10 points above
the rest across the city, but within the same building the gap is 0.9 points. Size is stated
mostly in buildings that rent above the model. Within a building, an ad stating its size rents
less than 1 log point more. The ads still missing after (c) lean toward Brooklyn + Queens and larger units.

## Next steps

A size term would use the stated or imputed size against the bedroom median, with an
imputation flag and a flag for size unknown. Because of the building-level skew, the unknown
flag would take up the difference between buildings that state sizes and those that don't,
and the size slope would come from within-building variation. Floor plans are the next layer
to read, on Sonnet or Haiku. Both wait on Ben's fit hold.
