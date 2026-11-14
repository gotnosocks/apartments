# The turnover column (2026-11-13)

Screen S13 (`docs/notes/turnover-screen-2026-11-13.md`) found that j9, the backtest of the ads
on the market on 2025-11-10, misses by building turnover. Within bins of a building's training
ads, j9's held-out ads in buildings whose other units rarely came up for rent ask 1.81 ± 0.26
points more over its mean location than those in fast-turning buildings. The screen's note
proposed a column. I wrote `rentfrontier.b0turnover` and built a copy of L1's dataset with two columns,
the parts of the screen's rate. No model reads them yet.

## The count

For each row I count the rows of the same building opened in the 730 days before the row's
price day, from the price day less 730 days up to the day before it, and take out the rows of
the row's own unit. That gives `bld_opened_730`. As in the screen:

- a row opens on its ad's `on_day` in the ads file the dataset's build read, or on the UTC day
  of its price_at when that comes first, as `b0amenitycarry.opening_days` dates it;
- a unit is the building and unit_id, and a row lacking a unit_id counts as a unit of its own
  (L1's dataset has none);
- I count every row of the dataset, training and held-out alike.

I build the count from opening days alone, without asks or rents, so a held-out ad adds only
its opening day to other rows' counts, and every ad in a row's count opened before the row's
price day. For a split this means:

1. The column comes out the same whichever rows a split holds out. A held-out ad adds its
   opening day to the counts of other units' rows, training and held-out, and its count includes
   other held-out ads opened before it. The screen counted turnover over training rows alone as
   a check, and j9's pooled contrast went from +1.81 ± 0.26 to +1.91 ± 0.26, so the gradient
   doesn't come from counting held-out ads.
2. A row's window follows its price day in the dataset it was built from. A backtest as of a
   date reads a dataset whose rows are priced as of that date, so it needs its own copy. All
   9,346 of j9's held-out ads are in L1's dataset, but L1 prices only 407 of them on the same
   day in the same building as j9's dataset does, mostly because L1 prices an ad at a later
   price change. Of those 407, 405 carry the same count in both datasets. Over all 9,346 the
   counts match on 3,993, differ by 1 at the median and by 8 at the 90th percentile.

## The units

`res_units_asof` holds `unitsres` of the building's lot in the MapPLUTO release out at the
row's price month, read as `b0coop` reads a row's class. I take the lot from the registry that
`building_attrs` reads (`building_attrs.REGISTRY`), keeping a building's first listed lot, and
read the latest release in the all-lots release file published at least 7 days before the
first day of the month of the row's price_at. A row reads only releases out before its month
began, and 22v2, which has no publication date, is skipped. The column is missing where the lot
is absent from that release or the release leaves `unitsres` blank. A release's zero stays
zero; the rate below treats zero as unknown, as the screen did.

I left the rate to a model.

## The build

    python -m rentfrontier.b0turnover SRC OUT

I ran it inside `systemd-run --user --scope -p MemoryMax=3G`, in 13 s with a peak of 1.95 GiB,
from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-turnover` at the end. The copy keeps L1's rows in L1's order, and
the source's rows file still matches its manifest's SHA-256. The manifest's `turnover` entry
records the source and its rows' SHA-256, the ads, registry and release files with their
SHA-256, both rules, the rows read from each release and these counts:

| rows | count |
|---|---|
| all | 1,896,471 |
| no other ads in the window | 141,110 (7.4%) |
| other ads in the window, quartiles | 5, 16 and 52; 143 at the 90th percentile |
| units read | 1,862,177 |
| of which zero | 48,352 |
| lot missing from its release | 32,774 |
| lot in its release with `unitsres` blank | 1,520 |
| building with no lot | 0 |
| units, median of rows read | 22 |

The rows read 39 releases, from 11v1 (2 rows) to 26v2, with 16v2 read most, by 167,297 rows.
The 32,774 rows whose lot is missing from their release are the same count the co-op column
reports, since both read the same lot in the same release.

## The rate

The screen's rate divides the count by two and by the units, for ads per residential unit and
year. Over L1's rows with other ads in the window and units above zero, it runs 0.065 at the
10th percentile, 0.136, 0.259 and 0.509 at the quartiles, and 1.17 at the 90th percentile. On
L1's held-out ads the same points are 0.072, 0.132, 0.244, 0.452 and 1.0. A rate above 1 means
more ads in a year than the lot has residential units, which mostly comes from a lot whose
units are recorded too low.

Cut at the screen's edges from j9 (0.123, 0.223 and 0.417), L1's rows fall into these bands:

| Band | Rows | Held-out ads |
|---|---|---|
| none | 141,110 | 10,301 |
| Q1 | 357,909 | 37,901 |
| Q2 | 359,777 | 43,800 |
| Q3 | 426,016 | 45,515 |
| Q4 | 537,876 | 47,590 |
| units unknown | 73,783 | 4,540 |

Against the single 26v2 file the screen read (`pluto/20261017-2c61ff1-all-lots4`), the as-of
units differ on 129,636 of the 1,811,999 rows with units in both (7.2%), by a factor of 2 or
more on 19,808 and by 10 or more on 4,653. 84% of the last group are condo lots, where a release
may give the whole building's units to the lot or a single unit's: Silver Towers reads 1,276
units in its own releases and 3 in 26v2, and Aire on West 67th Street reads 1 and 310. 14,640 of
the 48,352 rows reading zero units have units above zero in 26v2. With the screen's edges,
67,766 rows change band when the units come from each row's own release, 3,000 of them L1's
held-out ads.

## Against the screen on j9

`check.py` in `docs/notes/turnover-column-2026-11-13/` computes both columns on j9's own
dataset in memory, with the module's functions, and writes no dataset. It ran in a single
`MemoryMax=3G` scope in 22 s and saved its counts to

    /data1/apartments/tmp/sprint-20261113/turnover-column.json

The module's count equals the screen's on all 9,346 held-out ads in j9's dataset, and on every
row of L1's dataset when I apply the screen's counting function to all rows.

Every held-out ad reads 25v2, published 2025-07-03. 25v3 came out on 2025-10-27, so a row
reads it only from December 2025 on. Of the 8,963 held-out ads with units in both 25v2 and 26v2, 8,635
have the same units, 199 have more in 25v2 and 129 fewer. Another 137 ads have units in 26v2
and none in 25v2: their lot is missing from 25v2 (67 held-out ads in all) or 25v2 gives it zero.

The quartile edges of the nonzero rate move from 0.123, 0.223 and 0.417 to 0.123, 0.222 and
0.417. 232 of the 9,346 held-out ads change band: 135 move from a quartile to units unknown,
and 97 move between quartiles. With the screen's edges held fixed, 230 change band.

| Band | Screen (26v2 units) | Own release |
|---|---|---|
| none | 378, +5.59 ± 0.97 | 378, +5.59 ± 0.97 |
| Q1 | 2,183, +2.25 ± 0.29 | 2,152, +2.21 ± 0.29 |
| Q2 | 2,180, +1.17 ± 0.24 | 2,143, +1.21 ± 0.24 |
| Q3 | 2,208, +0.79 ± 0.26 | 2,150, +0.77 ± 0.26 |
| Q4 | 2,153, -0.72 ± 0.28 | 2,144, -0.67 ± 0.27 |
| units unknown | 244, +1.42 ± 0.91 | 379, +1.11 ± 0.90 |

Gaps are j9's log ask less its mean location, in percent, with SEs clustered by building. The
headline holds: the lowest quartile asks +2.21 ± 0.29 and the highest -0.67 ± 0.27, and the
pooled contrast within count bins goes from +1.81 ± 0.26 (9,018 ads) to +1.80 ± 0.26 (8,888).

## Turnover and tenure

I read each held-out ad's tenure from its own release, as the co-op column does, with
`b0coop.classes` on j9's rows. Low turnover goes with co-ops and condos:

| Band | j9 held-out ads | Rental | Condo | Co-op | L1 rows | Rental | Condo | Co-op |
|---|---|---|---|---|---|---|---|---|
| none | 378 | 75% | 14% | 12% | 141,110 | 89% | 6% | 5% |
| Q1 | 2,152 | 48% | 40% | 12% | 357,909 | 58% | 31% | 11% |
| Q2 | 2,143 | 70% | 28% | 2% | 359,777 | 76% | 21% | 3% |
| Q3 | 2,150 | 86% | 12% | 1% | 426,016 | 89% | 9% | 2% |
| Q4 | 2,144 | 90% | 10% | 1% | 537,876 | 94% | 5% | 1% |
| units unknown | 379 | 98% | 2% | 0% | 73,783 | 96% | 4% | 0% |

The L1 columns use the `coop` and `condo` columns of the co-op copy of L1's dataset and the
screen's edges. Over L1's rows, the median lot holds 172 residential units for a condo, 59 for
a co-op and 19 for a rental, and the median nonzero rate is 0.139, 0.082 and 0.313 ads per
unit and year.

Over all of j9's held-out ads, co-op ads ask +2.52 ± 0.63 over j9's mean location (400 ads),
condo ads +1.72 ± 0.31 (1,982) and rentals +0.82 ± 0.15 (6,964). Within rentals alone:

| Band | Rentals | Gap |
|---|---|---|
| none | 282 | +4.43 ± 0.96 |
| Q1 | 1,031 | +1.71 ± 0.41 |
| Q2 | 1,506 | +1.24 ± 0.27 |
| Q3 | 1,856 | +0.88 ± 0.30 |
| Q4 | 1,919 | -0.65 ± 0.28 |
| units unknown | 370 | +1.17 ± 0.92 |

The first quartile less the fourth comes to +2.36 ± 0.48 among rentals, against +2.87 ± 0.39
over all held-out ads. The pooled low-less-high contrast within count bins comes to +1.46 ±
0.28 among rentals (6,533 ads), against +1.80 ± 0.26 over all. By bin it runs +3.17 ± 0.94 at 5
to 19 training ads, +2.92 ± 0.48 at 20 to 99, and +0.17 ± 0.37 at 100 or more, where the
contrast over all ads is +1.11 ± 0.33. Keeping rentals alone takes about a fifth off the
pooled contrast, and most of it off the largest bin, while most of the gradient remains. A fit
reading the column should read `coop` and `condo` beside it, as the screen suggested.

## L1

With each row's own units, L1's held-out ads give much the same picture as in the screen: -0.49
± 0.05 in the first quartile, -0.61 ± 0.04 in the fourth, a first-less-fourth difference of
+0.11 ± 0.07, and a pooled contrast within count bins of +0.02 ± 0.04 (185,107 ads).

No model reads the column. The next step for it is the market-split backtest of L1's line
that the screen proposed. Since each row's count follows its price day, that backtest's as-of
dataset needs its own turnover copy, which the module builds in seconds.
