# The duplex column (2026-11-13)

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 prices
duplex ads right on average, though their asks scatter about 35% wider than other ads' and
L1's 80% intervals cover 0.72 of them. The sprint's duplex fit scales the noise of those rows,
so its dataset needs S7's pattern as a column. I wrote `rentfrontier.b0duplex` to add it and
built a copy of L1's dataset with the column. No fit reads it yet.

## The build

    python -m rentfrontier.b0duplex SRC OUT

The script reads the records file of SRC's pipeline build, after checking it against the
SHA-256 in SRC's manifest. For each listing it keeps the latest record, by the later of
`collected_at` and `last_collected_at`, as `b0data` does for its text flags. A listing gets
`duplex` true when that record's description runs over 20 characters
(`b0data.MIN_DESCRIPTION`) and either

1. has the word duplex or triplex without calling the building a duplex or a two-family house,
   or
2. describes an apartment on two or three levels ("bi-level", "spans two floors", "internal
   staircase" and the like).

The patterns are S7's, and a test compares them with `s7_text.py`. A row's mark comes from
its own listing's text and from no price, so the column adds a feature and changes no coded
field. The unit flags withdrawn on 2026-09-23 took a unit's flag from any of its ads, so a
later ad's text marked the unit's earlier rows. Here each row reads its own listing alone.

I ran it under `ops/job light -m 4G`, in 3 min 17 s, from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-duplex` at the end. The manifest's `duplex` entry records the
source, its rows' SHA-256, the rule and the counts:

| rows | count |
|---|---|
| all, one listing each, every one with a record | 1,896,471 |
| with a description over 20 characters | 1,825,199 |
| marked duplex | 108,405 (5.72%) |

## Against S7's marks

S7's marks (`/data1/apartments/tmp/sprint-20261113/s7_text.parquet`) cover the same
1,896,471 listings, and the column agrees with them on all but 142:

- S7 marked 109 listings whose latest description has 6 to 20 characters. S7 used no length
  floor, and the column follows `b0data`'s.
- The column alone marks 33 listings. For these S7 picked a record with an empty or short
  description, since it ordered a listing's records by `last_collected_at` alone.

The duplex fit needs its module next: L1 with a factor on the noise of the marked rows, written
down with its predictions before any launch.
