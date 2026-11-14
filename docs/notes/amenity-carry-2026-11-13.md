# Unit codes carried from a unit's earlier ads (2026-11-13)

S12 (`docs/notes/amenity-signs-2026-11-13.md`) found that unit codes such as hardwood floors
accrue over a unit's ads: a broker states a code on one ad and leaves it off another. I wrote
`rentfrontier.b0amenitycarry`, which gives each row the union of its own ad's unit codes and
the codes of its unit's earlier ads, and built a copy of L1's dataset with the new columns.
No model reads them yet.

## The codes as the designs read them

L1 and j9 take their unit codes from the listing-codes file (`building_zones_kitchen_sink.CODES`),
which holds each listing's latest StreetEasy record. The ads file dates every one of those
records to 2026-10-15 through 2026-10-17, so a 2015 ad's codes come from its page as
StreetEasy served it in October 2026. From that file the kitchen-sink design builds:

- `ad:<code>`, the row's own code, for each code of the lists `feat`, `private_outdoor`,
  `views` and `fireplace` held by at least 2,000 training rows. It leaves out dishwasher,
  washer-dryer and furnished, which it reads from the pipeline's fields. 19 codes pass, and
  gas fireplace (1,013 rows) doesn't.
- `ad:features_unstated`, for an ad whose record lists no features at all.
- `umean:ad:<code>`, the mean of each of those columns over the row and the unit's training
  rows priced on earlier days.
- `bld:<code>` for the building lists (`amen`, `parking`, `shared_outdoor`, `storage`): a code
  held by at least half of the building's listings that state amenities, among the row and the
  training rows priced on earlier days.

## The rule

For each row I collect its unit's earlier ads. These are the ads of the same (building,
unit_id) placed before the row in price_at, then audit_id order, as
`drift_building_phase.months_since_previous` orders them, and opened on an earlier day. An
ad's opening day is its `on_day` in the ads file the dataset's build read (the record's
onMarketAt, or its createdAt without one), or the UTC day of its price_at when that comes
first. Then I set `carry:<code>` to 1 when the row's own ad or any of its earlier ads states
the code. I never read an ad placed after the row, or one that opened on the same day or later.

The columns cover the 20 unit codes the design can read, gas fireplace included, and
`states_features`. I also wrote `carry:earlier_ads`, the number of earlier ads read. I left the
building lists as they are, since `bld:` already takes a majority over the building's earlier
ads.

## The build

    python -m rentfrontier.b0amenitycarry SRC OUT

I ran it inside `systemd-run --user --scope -p MemoryMax=3G`, in 14 s with a peak of 2.75 GiB,
from L1's dataset

    /data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise

into the same path with `-amenitycarry` at the end. The manifest's `amenity_carry` entry
records the source and its rows' SHA-256, the codes and ads files with their SHA-256, the rule,
and the rows holding and gaining each code.

Every row has an `on_day`. It falls on the price day for all but 20 rows, whose `on_day` comes
later and which open on their price day instead, so each row's opening day is its price day.
961,075 rows have an earlier ad, through 2,243,801 pairs of an ad and an earlier ad of its
unit, and in every pair the earlier ad opened on an earlier day.

370,405 rows (19.5%) gain at least one code, 86,430 of them on ads whose own record lists no
features. Every one of L1's 189,647 held-out ads has an earlier ad, and 80,370 of them (42%)
gain a code.

| Code | Rows stating it | Rows gaining it | of them, ads listing no features | of them, only from an ad still listed | L1's held-out ads gaining it |
|---|---|---|---|---|---|
| `feat:CENTRAL_AC` | 486,090 | 62,606 | 15,667 | 1,510 | 13,307 |
| `feat:FIREPLACE` | 85,218 | 34,639 | 9,029 | 578 | 7,208 |
| `feat:HARDWOOD_FLOORS` | 716,745 | 48,555 | 25,831 | 933 | 13,095 |
| `feat:LOFT` | 26,234 | 24,125 | 4,156 | 394 | 4,780 |
| `feat:PRIVATE_OUTDOOR_SPACE` | 496,092 | 114,840 | 25,882 | 1,647 | 24,255 |
| `feat:VIEW` | 411,186 | 67,569 | 13,987 | 1,065 | 17,956 |
| `fireplace:DECORATIVE` | 23,149 | 6,624 | 1,155 | 70 | 1,873 |
| `fireplace:GAS` | 1,013 | 356 | 32 | 3 | 111 |
| `fireplace:WOOD` | 2,821 | 801 | 71 | 9 | 268 |
| `private_outdoor:BALCONY` | 193,735 | 44,066 | 6,757 | 783 | 9,108 |
| `private_outdoor:GARDEN` | 142,386 | 62,461 | 9,990 | 1,061 | 13,113 |
| `private_outdoor:PATIO` | 80,727 | 62,369 | 5,948 | 1,006 | 11,595 |
| `private_outdoor:PRIVATE_ROOF_DECK` | 32,469 | 8,984 | 808 | 135 | 2,444 |
| `private_outdoor:ROOF_RIGHTS` | 78,741 | 23,799 | 2,232 | 258 | 5,877 |
| `private_outdoor:TERRACE` | 151,047 | 71,898 | 10,028 | 931 | 15,338 |
| `views:CITY` | 320,358 | 59,283 | 10,717 | 843 | 16,022 |
| `views:GARDEN` | 123,052 | 30,959 | 3,671 | 413 | 8,535 |
| `views:PARK` | 62,039 | 17,703 | 1,757 | 181 | 4,825 |
| `views:SKYLINE` | 149,569 | 37,621 | 4,264 | 469 | 10,293 |
| `views:WATER` | 48,488 | 13,022 | 1,498 | 183 | 3,386 |
| `states_features` | 1,456,019 | 86,430 | 86,430 | 2,203 | 16,373 |

Loft, patio, garden and terrace gain the most against the rows stating them, from 44% of
garden's to 92% of loft's.

## Where the carried codes come from

Every record was fetched in October 2026, after every ad in the dataset opened. For an earlier
ad closed before the row's ad opened, the fetch came after it closed, and I haven't checked
whether StreetEasy edits a closed ad's page. For an earlier ad still listed when the row's ad
opened (no off day, or one on or after the row's opening), a code could have been added after
that day. 40,461 pairs have such an earlier ad, and 7,828 rows gain a code only from one. The
fifth column of the table counts them for each code.

L1 already reads the union. A positive `umean:ad:<code>` marks a code stated on the row's own
ad or on a training ad of its unit priced on an earlier day. `count.py` in
`docs/notes/amenity-carry-2026-11-13/` takes the union over the earlier training ads alone, and
it matches the union over every earlier ad on every row, training and held-out. Since the
opening day comes to the price day, `carry:<code>` is 1 on exactly the rows where L1's
`umean:ad:<code>` is above zero, for the 19 codes L1 reads, and `carry:states_features` is 1
where `umean:ad:features_unstated` is below 1. j9's design builds the same unit means on its
own dataset. So for
either line the column holds L1's unit mean cut at zero, and adds only that form.

## Against S12's accrual

S12 found that each later ad of a unit asks about 0.75% less than the market index (E8), and
that hardwood accrues over a unit's ads, so its own term takes up that drift in estimates
comparing an ad with its unit's mean. The union accrues faster than the own code. By the
row's count of earlier ads:

| Earlier ads | Rows | Codes stated, own | Codes, carried | Hardwood, own | Hardwood, carried | Patio, own | Patio, carried |
|---|---|---|---|---|---|---|---|
| 0 | 935,396 | 1.87 | 1.87 | 32.2% | 32.2% | 4.6% | 4.6% |
| 1 | 398,097 | 1.82 | 2.31 | 34.7% | 37.4% | 4.5% | 7.9% |
| 2 | 236,234 | 1.92 | 2.71 | 41.8% | 46.3% | 3.9% | 10.2% |
| 3 | 142,823 | 2.04 | 3.07 | 48.9% | 55.4% | 3.6% | 12.0% |
| 4-5 | 130,864 | 2.17 | 3.47 | 56.3% | 65.2% | 3.2% | 14.0% |
| 6+ | 53,057 | 2.41 | 4.22 | 66.4% | 78.1% | 2.7% | 17.6% |

The codes counted are the 20 unit codes. Across the 961,075 pairs of a unit's consecutive ads,
the own hardwood code switches on 187,158 times and off 39,707 times, and the carried one
switches on 174,890 times and never off. Patio's own code switches off more often than on
(26,145 against 15,503), and the carried one switches on 13,766 times. Within a unit, then, a
carried code is a step up in ad order.

On L1's held-out ads, with the gap as log ask less L1's median, in percent, and SEs clustered
by building:

| Earlier ads | Ads gaining a code | Their gap | Other ads | Their gap |
|---|---|---|---|---|
| 1 | 23,227 | -0.12 ± 0.07 | 53,810 | -0.27 ± 0.04 |
| 2 | 19,504 | -0.68 ± 0.06 | 25,064 | -0.45 ± 0.05 |
| 3 | 14,414 | -0.72 ± 0.07 | 13,805 | -0.60 ± 0.06 |
| 4-5 | 15,558 | -0.72 ± 0.06 | 12,040 | -0.39 ± 0.06 |
| 6+ | 7,667 | -0.79 ± 0.08 | 4,558 | -0.33 ± 0.09 |
| All | 80,370 | -0.55 ± 0.03 | 109,277 | -0.37 ± 0.03 |

An ad gains a code when it leaves out a code its unit's earlier ads stated. With two or more
earlier ads, those ads ask 0.12 to 0.46 points further below L1's median than the others, and
with one earlier ad 0.15 points less far below. For hardwood alone the figures are -0.73 ±
0.07 against -0.42 ± 0.02. So at two or more earlier ads an omitted code comes with a lower
ask than L1 expects. A sparser re-listing would do that, where a hidden feature would push the
ask up, but I haven't tested why.

In a fit reading the carried codes I'd have to keep apart:

1. the drift over a unit's ads. The carried code rises with the count of earlier ads and only
   steps up within a unit, so its term would take up the per-ad drift even more than the own
   code does, unless a count of earlier ads or L1's lease phases stand beside it;
2. the unit's feature and the ad's omission. Read in place of the own code, the carried code
   would fold the omission, with its lower ask, into the unit's feature;
3. the unit means L1 reads already. The column is L1's `umean:` cut at zero, so beside L1's
   design it adds only the jump from no earlier statement to one.

The only part with a form L1's linear design lacks is the omission flag itself (own code 0,
carried 1). I haven't put it in a fit, and with a count of earlier ads it would need its
predictions written down first. The columns wait for that, and no fit reads them.
