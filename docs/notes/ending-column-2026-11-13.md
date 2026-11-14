# The ending column (2026-11-13)

S3 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 leaves part
of the previous ad's ending in its residuals. After a delisting or a pause the unit's next ask
sits about 1% under L1's median, against 0.34% after a rental, and cells of phase by ending
gain 74 ± 19 elpd over cells of phase alone. A model that reads the ending needs it as a
column, so I wrote `rentfrontier.b0ending` to add it and built a copy of L1's dataset with the
column. No fit reads it yet.

## The build

    python -m rentfrontier.b0ending SRC OUT

I take each row's previous ad as L1's lease phase takes it
(`drift_building_phase.months_since_previous`). A unit is a (building, unit_id) pair, I order
its rows by price_at and then audit_id, and the row before is the previous ad. A unit's first
row and a row with no unit_id have none. I checked this on L1's dataset: the months from each
row back to its previous ad agree with `months_since_previous` on all 1,896,471 rows. I date the
opening of an ad as S3 did: its first `ACTIVE` status change, or its price_at when that comes
first or the ad has no `ACTIVE` change.

The script reads the records file of SRC's pipeline build, after checking it against the
SHA-256 in SRC's manifest, and keeps each listing's latest record by the later of
`collected_at` and `last_collected_at`, as `b0duplex` does. For a row with a previous ad, I
keep the previous ad's status changes dated strictly before the row's ad opened and drop the
rest, along with any change whose date doesn't parse. In what is left, the ending is S3's: the
first change to rented, in contract, no longer available, delisted or temporarily off market
after the last `ACTIVE` change. The column `prev_ending` then takes one of

| value | the previous ad |
|---|---|
| `none` | doesn't exist, or the row has no unit_id |
| `rented` | ended as rented or in contract |
| `no_longer_available` | ended as no longer available |
| `delisted` | ended as delisted |
| `temp_off_market` | ended as temporarily off market |
| `undated` | has no ending dated before the row's ad opened |

When the previous ad was still on the market as the row's ad opened, the row gets `undated`,
however the previous ad ended later. When the previous ad ended before the opening and came
back on the market afterwards, the row keeps the ending from before the opening. Each row
reads only status changes dated before its own ad opened, and no prices.

I ran it in a `systemd-run --user --scope` capped at 3G of memory, in 2 min 47 s, from L1's
dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-ending` at the end. Its memory peaked at 2.94 GiB, close to the cap,
so a rerun on a larger dataset needs a 4G scope. Every listing in the dataset has a record with a
time. Every previous ad's record lists status changes. The manifest's `ending` entry records the
source, its rows' SHA-256, the records file, the rule and the counts:

| `prev_ending` | all rows | L1's held-out ads |
|---|---|---|
| `none` | 935,396 | 0 |
| `rented` | 423,560 | 92,152 |
| `no_longer_available` | 348,877 | 57,765 |
| `delisted` | 98,956 | 22,424 |
| `temp_off_market` | 52,871 | 13,136 |
| `undated` | 36,811 | 4,170 |
| total | 1,896,471 | 189,647 |

Every held-out ad has a previous ad, since the latest split holds out the newest ad of units
with two ads or more. Of the 4,170 undated held-out ads, 3,850 opened within two months of the
previous ad.

## Against S3

S3's per-ad cells (`/data1/apartments/tmp/sprint-20261113/s3_cells.parquet`) cover the same
189,647 held-out ads. The column agrees with them on all but 241, which S3 left undated and
the column gives an ending: 47 rented, 93 no longer available, 35 delisted and 66 temporarily
off market. In every one of them the previous ad ended before the held-out
ad opened and came back on the market on or after the opening. S3 took the ending after the
last `ACTIVE` change of the whole history, which in these ads is dated after the opening, and
so counted them undated. The column reads only the changes before the opening and keeps the
earlier ending.

S3 also differs from the column in two inputs. It read a later records file, with every
record of a listing, and it broke ties in price_at by listing_id as a number where L1 breaks
them by audit_id as text. I ran S3's reading on the records of L1's build: it gives S3's five
counts exactly, and the previous ad is the same under both orders on every row. So neither
input changes a held-out count. Over all rows S3's reading leaves 39,000 undated against the
column's 36,811, and the 2,189 rows between them are ads like the 241, whose previous ad came
back on the market after they opened.

## The price path

S3 also read the previous ad's price path: raised at some point, cut by 5% or more by its end,
or flat. I left it out of the dataset. Its prices are the asks of the previous ad, which is a
row of the dataset itself, and the last of them is that row's target, so a column built from
them would carry one row's rent into another row's features (`docs/leak-free-scoring.md`).
The `prevprice` feature sets, which read the previous ad's repricing, are also blocked from
serving (`autoselect.BLOCKED`, Ben, 2026-10-07). In S3's rescoring
the path gains 67 ± 17 over phase alone and the ending 74 ± 19, while both together gain 56 ±
25, so the path adds nothing on top of the ending there.

## Scoring a fit that reads it

An ad's ending is an outcome dated after its ask. On a split where a held-out ad can come
before a training ad of the same unit, the training ad's `prev_ending` would hold that outcome
for the held-out ad. On the latest split every held-out ad is the newest of its unit, so a
training ad's column reads only the ending of another training ad. A fit reading
`prev_ending` should be scored there, and nothing enforces that yet, so the first model module
to read the column should refuse every other split.
