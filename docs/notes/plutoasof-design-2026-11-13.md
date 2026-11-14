# P1: L1 reading MapPLUTO as of each ad's month (2026-11-13)

L1 reads every MapPLUTO field from release 26v2, published 2026-08-17, for every row. An ad
priced in 2015 therefore reads its building's class, floor count, year built and lot facts as
the city recorded them in 2026. The co-op column note (`docs/notes/coop-column-2026-11-13.md`)
found that L1's `bld:condo` marks 30,845 rows whose lot was not yet in their release. P1 is L1
with each row reading the release out in its month instead, by the rule `rentfrontier.b0coop`
follows. In this note I write P1 down before any launch. I have launched, queued and
scheduled nothing for it, and the launch waits for a sprint budget from Ben.

## How L1 reads MapPLUTO

I followed L1's design down its chain of modules. `drift_building_phase.design` calls
`drift_building.design`, which builds the kitchen sink. `building_zones_kitchen_sink.design`
first builds the as-of floor design (`building_zones_floor_asof`), whose building tables come
from `load_lots`, then rebuilds the elevator and floor columns in `asof_base` and appends the
lot columns. Every MapPLUTO value in the design comes from 26v2, by these routes:

| L1's columns | MapPLUTO fields | route in L1 |
|---|---|---|
| `bld:condo` | bldgclass | `building_attrs.attributes` on `load_lots`' lots: class R |
| `bld:elevator`, `bld:elevator_unknown` | bldgclass | `asof_base`: the building's earlier training ads first; where they state nothing, classes D, R4, R9 and RR read yes, and A, B, C, S, R2 and R3 read no |
| `unit:elev_f2` to `unit:elev_f64`, `unit:walkup_f2` to `unit:walkup_f6`, `unit:elev_top`, `unit:walkup_top`, the two floor-unknown columns | numfloors, bldgclass | `asof_base`: the floor count as the top floor, else the highest floor the building's earlier ads list; the elevator group from the row above |
| the five build eras, `bld:built_unknown` | yearbuilt | `building_zones_age` on the age snapshot (`building-age/20261021-3a64aa22`), its year built from `building_attrs.ATTRS`: 26v2's yearbuilt where it is 1800 or later |
| `bld:altered_2000_on` | yearalter1, yearalter2 | the same snapshot: an alteration year from 2000 up to the ad's year |
| `bld:retail`, `bld:retail_unknown` | retailarea, comarea | the same snapshot: the retail area, filled with the commercial area |
| `bld:log_units`, `bld:units_unknown` | unitsres | `building_zones_kitchen_sink.lot_table` |
| `bld:log_lot_front` | lotfront | `lot_table`, log 25 ft where blank |
| `bld:corner` | lottype | `lot_table`: lot type 3 |
| `bld:far_used` | builtfar, residfar | `lot_table`: built over residential FAR, clipped to 0 to 3, 1 where blank |
| `bld:landmark` | landmark | `lot_table`: any landmark name |
| `bld:multi_building` | numbldgs | `lot_table`: more than one building |
| `bld:class_C`, `bld:class_D`, `bld:class_S` | bldgclass | `lot_table`: the class's first letter |
| `bld:log_area_per_unit` | resarea, unitsres | `lot_table` |
| `bld:lot_unknown` | all of the above | `lot_columns`: the building's lot is missing from 26v2 |

The building's lot comes from the registry (`building_attrs.REGISTRY`), its position from the
registry and its height (`bld:log_height`, `bld:height_unknown`) from the building footprints.
The doorman and gym columns read the ads alone. P1 leaves all of these as L1 has them.

Before writing P1 I checked that the release file's 26v2 equals `building_attrs.PLUTO` on all
15 fields, that the age snapshot equals `building_age.building_table` run on 26v2, and that
ATTRS's year built equals 26v2's yearbuilt from 1800 on, for every NYC lot. So with every row
on 26v2 the routes above give L1's columns exactly.

## The change

`drift-building-phase-plutoasof` (`frontier/src/rentfrontier/drift_building_phase_plutoasof.py`)
builds L1's design, then rebuilds every column of the table with L1's own functions. Each of
those functions takes a building and its lot; P1 hands them a key of lot and release instead,
so a building's rows can read different releases. The rule for each row:

1. the building's lot is its BBL in the registry, as in L1;
2. the row reads the latest release in the all-lots release file
   (`plutoreleases/20261017-2c61ff1-all-lots4`) published at least 7 days before the first
   day of its price month. Release 22v2 carries no publication date, so no row reads it. This
   is `b0coop`'s rule, and a test checks that the two pick the same release for every month;
3. where the lot is missing from that release, every field reads blank, as for a building with
   no lot in L1. Such a row gets `bld:lot_unknown`, `bld:built_unknown` and
   `bld:retail_unknown`, no condo, and no class to fall back on for the elevator.

Releases 09v1 to 12v2 leave residfar blank on every lot, so they never recorded it. A row
reading one of them reads residfar from 26v2. In L1's dataset 19 rows read those releases (11v1
to 12v2), so this changes almost nothing.

`features.released_lots`, which the `nb5-plutoasof-v3` feature sets read, keeps 26v2's value
in three more cases: a lot missing from its release, the year built, and any release published
before 26v2's year built. Each of those hands an earlier row a value from a later release,
which the ad's own month could not have known, so P1 drops all three. I expect two costs from
that, and the counts below give their size. A condo building whose billing lot appeared after
its first ads reads a missing lot on those ads. A building put up after its release still reads
the lot's earlier facts, often a vacant lot or the building it replaced.

`drift_today` prices an apartment with its last ad's row, so in P1 the apartment reads the
release its last ad read. I added P1 to its models and wrote this down in its docstring.
Reading the release out on the pricing day would mean rebuilding these columns for every
apartment, and I left that out.

`frontier/tests/test_drift_building_phase_plutoasof.py` runs on synthetic lots and buildings.
It checks the release each month reads against `b0coop`, that no row reads a later release or
22v2, and the week's edge (2026-08-31 reads 22v3, 2026-09-01 reads 26v2). It checks a lot
missing from its release, a building with no lot, and the residfar fallback. With every row on
26v2 the design equals L1's, every column and count. With rows on four releases each row's
columns equal L1's functions run on its own release's lots. A small run's draws are checked
against a sha256.

## Rows that change

`docs/notes/plutoasof-design-2026-11-13/count.py` builds only the columns of the table, once
with every row on 26v2 and once with each row on its own release, in four parts by building,
each in a 3 GB scope. The counts are in `counts.json` beside it. Every row of L1's dataset
has a lot in the registry, and the earliest rows read 11v1, so every row reads a release.
32,774 rows (1,320 held out) read a release that doesn't hold their lot. 16,649 rows read 26v2
itself, and the rest spread over 13v1 to 26v1.

A row counts under a feature when any of its columns differ. The latest split holds out one ad
of each unit, so on held-out ads the units equal the rows.

| feature | rows | units | buildings | held-out ads | their buildings |
|---|---|---|---|---|---|
| condo (class) | 30,846 | 23,635 | 1,429 | 1,193 | 274 |
| elevator (class fallback) | 6,977 | 5,729 | 1,015 | 172 | 123 |
| floor columns (floor count, class) | 14,836 | 12,311 | 2,584 | 352 | 233 |
| year built (eras, unknown) | 126,496 | 85,816 | 10,104 | 4,375 | 2,269 |
| alteration year | 87,453 | 60,616 | 5,345 | 3,576 | 1,177 |
| retail | 67,438 | 47,917 | 3,414 | 2,970 | 744 |
| unit count (`bld:log_units`) | 178,059 | 116,999 | 6,985 | 8,616 | 2,024 |
| `bld:units_unknown` | 18,981 | 14,884 | 1,312 | 683 | 250 |
| lot front | 80,027 | 54,838 | 2,589 | 3,231 | 724 |
| corner | 12,943 | 8,607 | 332 | 705 | 130 |
| FAR used | 242,327 | 162,704 | 14,206 | 12,007 | 4,008 |
| landmark | 2,877 | 2,110 | 108 | 143 | 33 |
| more than one building | 37,476 | 25,809 | 1,576 | 1,420 | 434 |
| class C | 19,721 | 14,616 | 1,778 | 725 | 400 |
| class D | 13,795 | 10,427 | 615 | 470 | 164 |
| class S | 6,028 | 4,454 | 716 | 256 | 176 |
| residential area per unit | 278,319 | 180,621 | 15,666 | 14,084 | 3,553 |
| `bld:lot_unknown` | 32,335 | 24,742 | 1,543 | 1,256 | 296 |
| any column | 517,539 | 322,924 | 30,082 | 26,379 | 8,089 |

The 517,539 rows are 27% of the 1,896,471, and the 26,379 held-out ads 14% of the 189,647.
The held-out ads are each unit's latest ad, so more of them read a release close to 26v2.

By field, counting a blank against a value as a difference:

| field | rows | held-out ads | | field | rows | held-out ads |
|---|---|---|---|---|---|---|
| unitsres | 179,458 | 8,687 | | bldgclass | 127,475 | 5,323 |
| lotfront | 84,015 | 3,371 | | resarea | 207,067 | 9,944 |
| lottype | 47,591 | 2,051 | | numfloors | 92,418 | 3,185 |
| builtfar | 194,097 | 9,046 | | yearbuilt | 173,246 | 6,050 |
| residfar | 99,356 | 5,124 | | yearalter1 | 152,786 | 5,999 |
| landmark | 12,905 | 440 | | yearalter2 | 64,179 | 2,571 |
| numbldgs | 93,527 | 3,723 | | retailarea | 131,996 | 6,574 |
| | | | | comarea | 168,076 | 8,100 |

A changed field moves a column less often than it changes: a class from C1 to C7 keeps the
letter, and a landmark's name can change spelling.

I split the 173,246 rows whose yearbuilt differs from 26v2's by cause, with
`docs/notes/plutoasof-design-2026-11-13/yearbuilt.py` on `count.py`'s outputs:

| cause | rows | held-out ads |
|---|---|---|
| the lot is missing from the row's release | 32,118 | 1,250 |
| the release leaves the year blank or 0, and 26v2 gives one | 18,992 | 432 |
| 26v2's year falls in or after the release's year, so the building went up later | 3,685 | 123 |
| both give a year before the release's, and the years differ | 116,105 | 4,114 |
| 26v2 leaves the year blank or 0 | 2,346 | 131 |

So most of the change comes from revised years, and few rows come from new buildings. Among
the revisions the two years differ by a median of 16 (quartiles 6 and 33). In 65,167 of them
(2,279 held out) the release gives a round year of 1900 or later, mostly 1900, 1910 or 1920,
and 26v2 gives a year before 1900, such as 1887 or 1899. 61,338 of these rows read releases
from 13v1 to 18v2, and most of the rest 19v1 to 21v4. Later releases replaced many of the
decade estimates with dated years, so P1 hands these rows the older estimate. Only 314 rows
move the other way. These revisions make up nearly all of `bld:built_pre1900`'s 66,499
changed rows: 65,936 of them read their lot, and 563 read a missing lot. `bld:built_2010_on` changes on 21,372 rows of a missing lot and on
21,902 rows whose release holds the lot with another year or none.

The condo rows are almost all rows of a missing lot. Of the 30,846 rows whose `bld:condo`
differs, 30,788 read a release without their lot, and 58 read a lot that their release
classes otherwise. The co-op note found the same split: 30,788 missing, 57 with no class and
one row going the other way. The missing-lot rows read `bld:lot_unknown`, `bld:built_unknown`
and `bld:retail_unknown` together. 32,126 of the 32,335 rows whose `bld:lot_unknown` changes
are rows of this kind. The other 209 belong to buildings whose lot is missing from 26v2 and
present in an earlier release.

## Cost

I timed the sweeps on the CPU with `docs/notes/plutoasof-design-2026-11-13/time_sweep.py`, on
the 18,441 training rows and 10,135 units of the 1-in-90 sample of buildings from Y1's timing
(2 chains, 60 warmup and 60 draws). I alternated the two models under `/usr/bin/time`, each in
its own 3 GB scope, while other threads' work came and went:

| run | seconds a sweep | warmup | draws | design | peak resident | load average after |
|---|---|---|---|---|---|---|
| P1 | 0.907 | 53.8 s | 55.0 s | 14.3 s | 3.04 GB | 6.8 |
| L1 | 1.225 | 76.5 s | 70.5 s | 9.8 s | 3.24 GB | 8.2 |
| L1 | 1.200 | 76.4 s | 67.6 s | 9.9 s | 3.22 GB | 9.6 |
| P1 | 0.819 | 51.8 s | 46.5 s | 14.5 s | 2.98 GB | 7.5 |
| L1 | 1.239 | 78.0 s | 70.6 s | 9.4 s | 3.25 GB | 10.8 |
| P1 | 1.253 | 77.9 s | 72.4 s | 14.6 s | 2.99 GB | 12.4 |

Another process held about one core through the second and third runs, which slowed both
of them. The last pair ran back to back at a similar load, and there P1's sweep took 1%
longer than L1's. P1 rebuilds L1's MapPLUTO columns from other releases, and the sampler runs
unchanged on a design of the same size, so I put the rest of the spread down to the load.
`cap.py` gives P1 L1's stated rate of 1.0 s a pair of chains.

The design takes about 5 s longer on the sample. On the full dataset the extra work is the
release reads (9.1 s in `count.py` on all 1,896,471 rows) and one rebuild of the MapPLUTO
columns (about 18 s over the four parts), so P1's prepare step should run about 30 s longer
than L1's 363 s on Modal. Both steps of `count.py` ran on the full rows inside 3 GB scopes,
and L1's host peaks near 9 GB on Modal, so P1 runs in the normal 40 GiB container.

L1's containers swept at 0.776 s on Modal, and at the same rate the 2,520 s sweep budget
holds the same 3,250 or so sweeps. `cap.py` estimates each container at $4.19, as for L1,
since the budget stops the sweeps. L1T's three containers settled at $10.94 in all, and the extra 30 s of
prepare adds about $0.03 a container, so I expect about $11.00 to $11.50 for three.

## Launch plan (no fit is launched by this note)

Three H100 containers on L1's own dataset, seeds 1 to 3, pooled by `drift_pool` into 6 chains,
as for L1T:

```sh
cd /data1/apartments/serve/master
D=/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise
IN=/data1/apartments/pipeline/datasets/rows-b3ddebf19af1dc1e.parquet
for j in "pa 1" "pb 2" "pc 3"; do
  read -r label seed <<<"$j"
  ops/modal-fit --outside-budget --gpu H100 --dataset "$D" --input "$IN" \
    --split latest --baseline drift-building-phase-b0-latest-9a7830fb-l1 COMMIT "$label" \
    drift-building-phase-plutoasof b0 2 500 9000 40 --seed "$seed" --level-dof 4 \
    --no-loo --no-heldout
done
```

COMMIT is the merge commit of the PR that adds the model. The release file is under
`/data1/apartments/external`, which `ops/modal/fit.py` syncs for every fit. The dataset is
L1's, so the held-out ads are L1's. I compare the pool with L1's pool,
`drift-building-phase-b0-latest-9a7830fb-l1`, on those ads: elpd with the SE clustered by
building, the median's error and the coverage of the 50%, 80% and 95% intervals
(`python -m rentfrontier.drift_score RUN`). I split each count between the 26,379 held-out ads
whose columns P1 changes and the rest, by joining `pred_scores.npz`'s listings to the rows
`count.py` marks.
