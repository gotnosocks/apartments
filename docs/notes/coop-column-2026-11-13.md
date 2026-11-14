# The co-op column (2026-11-13)

Part C of S5 in the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that j9's
held-out new units in co-op and condo buildings ask 1% to 4% more than j9 expects at every
count of training ads. j9 reads a condo flag and no co-op flag. I wrote `rentfrontier.b0coop`
to add a co-op column, and a condo column built the same way, and built a copy of L1's dataset
with both. No fit reads them yet.

## The classes

I count a lot as a co-op when MapPLUTO gives it one of the four co-op classes in the Department
of Finance's list:

    C6  walk-up co-op
    C8  walk-up co-op converted from a loft or warehouse
    D0  elevator co-op converted from a loft or warehouse
    D4  elevator co-op

These are `building_attrs.COOP_CLASSES` and S5c's classes. I left out three classes that look
close:

- R9, a condo whose units a co-op holds. `building_attrs` marks every class starting with R as
  a condo, and the column follows it, so R9's 6 buildings (877 rows) stay condos.
- A8, a bungalow colony on co-op land. No building in the dataset has it.
- CB and DB. They first appear in 24v1, and of the 26v2 lots of the dataset's buildings with
  them, 27 of 32 CB lots and 6 of 12 DB lots were C7 or D7 (walk-up or elevator apartments with
  stores) in 23v3, with no co-op class among them. So I count them as rentals. 11 of their
  1,661 rows are marked co-op, from an earlier release that gave their lot a co-op class.

## The release a row reads

j9 and L1 take a building's tenure from `building_attrs.ATTRS`, which sorts the lot's class in
MapPLUTO's 26v2 release, published 2026-08-17, for every row. An ad priced in 2015 reads a
class from 2026, and so do all of j9's held-out ads, which j9 predicts as of 2025-11-10.

For the new columns I read each row's lot in the release the plutoasof feature sets give a
listing (`features.released_lots`): the latest release in the all-lots release file published
at least 7 days before the first day of the month of the row's price_at. I never read a later
release, and I never read 22v2, which has no publication date. The lot is the building's BBL in
the registry that `building_attrs` reads. Then I sort the class as `building_attrs.attributes`
does: R first as a condo, then the four co-op classes. A row whose lot is missing from its
release, or has no class there, gets false in both columns.

I wrote `condo` beside `coop` so that a fit can read both flags from the same release. A fit
that reads `coop` alongside the design's `bld:condo` would mix 26v2's condo flag with the
point-in-time co-op flag.

## The build

    python -m rentfrontier.b0coop SRC OUT

I ran it inside `systemd-run --user --scope -p MemoryMax=3G`, in 6 s with a peak of 1.87 GiB,
from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-coop` at the end. The manifest's `coop` entry records the source and
its rows' SHA-256, the registry and release files with their SHA-256, the rule, the rows read
from each release and these counts:

| rows | count |
|---|---|
| all | 1,896,471 |
| with a class in their release | 1,863,533 |
| lot missing from their release | 32,774 |
| lot in their release with no class | 164 |
| building with no lot | 0 |
| marked co-op | 67,142 (3.54%), 35,187 units, 3,435 buildings |
| marked condo | 264,871 (13.97%), 124,687 units, 4,933 buildings |

## Against the 26v2 tenure

`count.py` in `docs/notes/coop-column-2026-11-13/` compares the columns with the tenure j9 and
L1 read.

- Co-op: 66,790 rows are co-ops in both. 1,418 rows in 62 buildings are co-ops only in 26v2;
  their own release mostly classed the lot D8, C4 or D1, apartment classes outside the co-op
  list, so these buildings became co-ops, or were reclassed as co-ops, after the ad. 352 rows in 24 buildings are co-ops
  only in their own release. 53 buildings have rows on both sides of a change.
- Condo: 30,845 rows in 1,428 buildings carry `bld:condo` and not the new `condo`, and every
  one of them reads no class: the lot is missing from the row's release (30,788) or has no
  class (57). One row goes the other way. Of the 32,774 rows whose lot is missing from their
  release, the lot first appears in a release published a median of 1.1 years after the row's
  month (quartiles 0.4 and 2.8 years), and 4,062 are in buildings that 26v2 dates to the ad's
  year or the year before. Most are condo billing lots numbered after the ad, for a building
  that then stood on another lot, and the release file has no record of which lot that was.

So j9's and L1's condo flag reads a later release on 30,845 rows (1.6%), and every other
PLUTO feature of theirs reads 26v2 as well.

## S5c's co-op ads

S5c called 402 of j9's 9,346 held-out new units co-ops, from 26v2. Read at each ad's own
price_at in j9's dataset, the rule marks 399 of them. All 402 are in L1's dataset, where the
column marks the same 399. The other three read 25v2, which classed their lots C4 (one ad) and
D8 (two). The rule marks one held-out ad that S5c called something else.

On L1's held-out ads the column marks 6,978 ads in 1,717 buildings. Their mean gap from L1's
median is -0.74 ± 0.14%, against -0.43 ± 0.02% for the other 182,669 ads, with SEs clustered by
building. The co-op excess S5c saw in j9's new units doesn't show in L1, whose unit levels
come from each unit's own ads, so a co-op term bears on the new-unit model of the j line more
than on L1.

The column waits for a j-line fit that reads `coop` and `condo` together, written down with its
predictions before any launch.
