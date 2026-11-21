# Large units on held-out history: wording in the two tails, and finishes by building (no fit)

The TODO list asked for a read of floor plans and photos of large units, looking for the
qualities the record lacks: a second level, a full floor, a renovation. The recorded attributes
leave large units' persistent sd at 0.091, against 0.026 for mid-sized units. The image read of
2026-11-18 (`docs/notes/deals-photos-2026-11-18.md`) already holds 392 ads with 3 or more
bedrooms, all drawn for the low tail and its controls. Among them a plan on 2 or more levels is
on 37% of low ads and 13% of controls, which is the duplex finding already queued as a noise
factor. No one has read the high tail of large units. Before fetching images, this note scans
the ad text of every large held-out ad, in both tails, on the two halves of the buildings.

No fit was run and no money was spent. Scripts and logs are in `large-unit-text-2026-11-21/`.
They read and write scratch files under `/data1/apartments/tmp/large-units`.

## Evidence used

- The latest split's held-out history: each unit's latest ad, with the unit's earlier ads in
  training, scored by l2bt (`drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`)
  as in `docs/notes/history-scan-2026-11-18.md`. `gap` is the mean log error, `low` the share
  below the 5% point, `high` the share above the 95% point. Buildings are split into halves
  A and B by a hash, and both halves are printed at once.
- The ad's own description (`any-unit/texts.parquet`). Each mark reads the text and never the
  ask. Ads with 40 characters of text or fewer are left out of the gap tables.
- 29,080 held-out ads with 3 or more bedrooms: 1,411 high, 1,925 low, 25,744 in the 90%
  interval (`l3_words.log`).

## Wording among high, middle and low large ads

Shares by tail, half A / half B (`l3_words.py`):

| Mark | High | Middle | Low |
|---|---|---|---|
| full floor or floor-through | 5.8 / 5.0% | 4.5 / 5.0% | 4.4 / 5.1% |
| gut or new renovation | 15.7 / 15.2% | 15.2 / 15.1% | 13.0 / 13.5% |
| any renovation wording | 37.4 / 35.9% | 36.4 / 35.3% | 33.8 / 33.1% |
| duplex or two levels | 18.6 / 18.5% | 14.3 / 14.4% | 19.0 / 19.8% |
| townhouse or brownstone | 8.1 / 11.3% | 6.4 / 6.6% | 6.6 / 6.6% |
| private outdoor wording | 25.0 / 25.4% | 20.3 / 20.3% | 22.0 / 20.5% |
| luxury or named finishes | 31.1 / 29.5% | 23.3 / 23.6% | 24.2 / 21.8% |
| furnished | 5.2 / 4.5% | 3.1 / 3.0% | 2.5 / 3.4% |
| flex or convertible | 4.6 / 4.8% | 3.0 / 2.5% | 3.3 / 3.1% |

The three qualities the TODO item named come out as follows:

- Full floor: no excess in either tail.
- Renovation wording: no excess in the high tail, and a little rarer among low ads.
- Second level: duplex wording is in both tails, as S7 and the duplex scale note found. The
  queued duplex factor covers it.

Outdoor space and furnished are coded fields the model already reads, and townhouse wording
differs between the halves. The finish mark is the one steady excess with no term behind it.
It appears in the high tail only.

## Named finishes in large ads

The finish mark is "luxury", "marble", "chef's kitchen", or a named appliance (Sub-Zero,
Miele, Viking, Wolf, Bosch, a wine fridge). I read 30 random matches on the named words
(`l6_ctx.py`): 27 describe the apartment (marble baths, a chef's kitchen, Sub-Zero and Viking
appliances), and 3 describe a marble lobby or hallway. The later scripts drop marble lobby,
hall and entry wording.

Among 3+ bedroom ads, marked against unmarked, gap difference in log points, A / B
(`l5_split.py`):

| Split | Difference |
|---|---|
| 0 or 1 full bath | +0.013 / +0.010 |
| 2 full baths | +0.021 / +0.023 |
| 3 or more full baths | +0.014 / +0.028 |
| 3 bedrooms | +0.013 / +0.013 |
| 4 or more bedrooms | +0.012 / +0.028 |
| first ad to 2019 | +0.016 / +0.018 |
| 2020 to 2022 | +0.017 / +0.026 |
| 2023 on | +0.011 / +0.012 |
| named finishes, no "luxury" | +0.015 / +0.017 |
| "luxury" alone | +0.006 / +0.011 |

With the lobby wording dropped, named finishes alone give +0.014 and +0.017 at 3+ bedrooms,
+0.002 on both halves at 1 to 2 bedrooms, and −0.001 and −0.004 at 0 bedrooms
(`l7_refined.py`, first table).

### Within the building the excess goes away

Inside a building and size class with both marked and unmarked held-out ads, the marked 3+
bedroom ads sit +0.002 (A, 490 buildings) and −0.001 (B, 535 buildings) from the unmarked
ones on the named words, and +0.003 and +0.004 with "luxury" added. All are under one
building-clustered SE (`l8_within.py`). So the mark says little about one unit against its
neighbours. It says which buildings the model prices low for large units.

### The building's finish share

For each ad, the share of the other held-out ads of its building whose text names finishes,
in buildings with 4 or more held-out ads (`l9_bldshare.py`), with the gap by size class, A / B:

| Building share | 0 bedrooms | 1 to 2 | 3 or more |
|---|---|---|---|
| 0 | −0.005 / −0.003 | −0.004 / −0.004 | −0.011 / −0.012 |
| under 0.2 | −0.007 / −0.005 | −0.002 / −0.001 | −0.004 / −0.001 |
| 0.2 to 0.5 | −0.008 / −0.006 | −0.004 / −0.004 | +0.003 / +0.007 |
| over 0.5 | −0.009 / −0.008 | −0.003 / −0.003 | +0.006 / +0.010 |

At 3 or more bedrooms the gap rises by 1.7 and 2.2 points from share 0 to over 0.5, with about
5,000 and 1,600 ads a half at the two ends. At 1 to 2 bedrooms it is flat, and studios move a
little the other way. The model has one citywide bedroom step and one level per building, so
the step from a two-bedroom to a large unit is the same in every building. Buildings whose
ads name fine finishes charge more for the large units than that step gives.

Part of this is price. Within quartiles of l2bt's predicted rent, set by year
(`l10_tier.py`), large ads in buildings with share over 0.2 sit above those with share 0 by:

| Quartile | A | B |
|---|---|---|
| lowest | +0.004 | +0.003 |
| second | +0.018 | +0.024 |
| third | +0.008 | +0.016 |
| highest | +0.006 | +0.014 |

Each cell is 1 to 3 standard errors, and all eight are positive. About half of the band's
difference stays inside a price tier. The queued factor for the top 3% of predicted rents and
the level for four or more bedrooms take some of the rest.

## What follows

- A refit term, queued in TODO with the other base-refit terms: a level for 3+ bedroom rows
  that rises with the building's finish share. Compute the share from the building's ads
  dated before the row, so a later renovation's wording does not reach earlier rows. A more
  general form is a building-level deviation for large units, with a hierarchical prior whose
  mean the share predicts. About +0.01 to +0.02 at shares over 0.2 and −0.011 at share 0. In
  buildings with 4 or more held-out ads those are about 31% and 58% of large ads. Too small
  for a fit of its own: large ads in share-0 buildings are priced about 1% too high, which lifts them a little in the Deals
  ranking and no further.
- The image read of large units stays open in a narrower form. The text covers the three
  qualities named, and the high tail's photos (1,411 ads) have not been read. A read of them is
  worth its fetch only if the finish term leaves the high tail as it is.
