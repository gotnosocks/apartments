# The units with the largest levels, read by hand (2026-11-12)

Before writing L1 with a Student-t unit level, I wanted to know what the units with the
largest lasting levels are. If most of them were coding errors, the heavy tail in u2a would
be the model absorbing bad data, and fixing the data would come first. I read 300 of
them. This note makes no fit and spends nothing on Modal. The scripts, the reader's
instructions, all 300 reads and the tallies are in `docs/notes/unit-level-reads-2026-11-12/`.

## Picking the units

u2a saved no per-unit levels, so I ranked units with a stand-in built from the asks alone
(`rank.py`). On the training rows of the served model's history (latest split), I removed
a repeat-ad month index from each log ask. For each unit I then took the mean of its
adjusted asks less the mean of the other units' asks in the same building, bedroom count
and year, and kept only groups with at least 3 other ads. I shrank that by n / (n + 1),
with n the unit's ad count. I ranked only units with a held-out ad, so each unit's ad on the
Deals page tests the ranking out of sample. This ranked 139,279 units. The absolute score has
a median of 0.029 and a 99th percentile of 0.205. The top 200 run from 1.154 down to 0.328,
and rank 2,000 is at 0.185. Of the top 200, 149 ask more than their neighbours.

I read the top 200 and a random 100 from ranks 201 to 2,000 (seed 20261112). For each unit,
`dossier.py` put together every ad of the unit and of the same building and bedroom count,
with the full text, the history of asks, the stated size, floor, amenity codes and links to
photos and floor plans. Twelve Sonnet subagents read 25 dossiers each against `READER.md`.
They had the links but opened no images, so no floor plan was read. A reader could propose a
correction only with independent backing: another ad for the same unit, a stated size, or
matching units in the same line. Being far from the neighbours did not count as backing.

## What the units are

| class | top 200 | ranks 201 to 2,000 | all |
|---|---:|---:|---:|
| real outlier: a quality the neighbours lack | 153 | 69 | 222 (74%) |
| pricing: a deep cut or an odd ask | 12 | 15 | 27 (9%) |
| miscoded bedrooms | 10 | 5 | 15 (5%) |
| other data: price typo, commercial, wrong building | 11 | 2 | 13 (4%) |
| unclear | 7 | 4 | 11 (4%) |
| shared label: two apartments under one unit id | 5 | 4 | 9 (3%) |
| regulated: rent stabilized or income restricted | 2 | 1 | 3 (1%) |

The real outliers break down as:

| code | units | asks above the neighbours |
|---|---:|---:|
| layout or size | 87 | 58 |
| penthouse or top floor | 57 | 57 |
| private outdoor space | 33 | 33 |
| duplex or triplex | 16 | 16 |
| view | 12 | 12 |
| other quality | 10 | 1 |
| renovation | 4 | 3 |
| basement garden, townhouse floor | 3 | 3 |

So the units far above their building are mostly the building's best apartments: the
penthouse, the unit with a terrace, the big corner layout. The units far below are more
mixed. Of the 90 below, 25 are pricing (14 deep cuts), 10 miscoded bedrooms, 29 a smaller
or worse layout, and 3 regulated.

## How the served model does on their held-out ads

The ranking used only training rows, so I could check each unit's held-out ad against the
served model's predictive (b9, `drift-building-b0-latest-67d14e17-b9`). These are the
columns of the Deals page.

| group | units | median log(ask / median) | in the 80% interval | above it | below it | median PIT |
|---|---:|---:|---:|---:|---:|---:|
| top 200, above neighbours | 149 | +0.068 | 0.44 | 0.43 | 0.13 | 0.81 |
| top 200, below neighbours | 51 | -0.020 | 0.73 | 0.06 | 0.22 | 0.36 |
| ranks 201 to 2,000, above | 61 | -0.003 | 0.66 | 0.18 | 0.16 | 0.49 |
| ranks 201 to 2,000, below | 39 | +0.005 | 0.67 | 0.15 | 0.18 | 0.54 |

b9 already takes most of the stand-in's gap away. A top-200 unit asks 0.36 above its
neighbours on the median and only 0.068 above b9's median. Still, for the top 200 above
their neighbours, 43% of the held-out asks fall above b9's 80% interval, against 10%
nominal, and the miss runs in the direction of the unit's past. b9 shrinks these units'
levels too far toward their building. Penthouses are 47% inside the interval, outdoor space
36%, view 42%. The ranks below 200 show no lean, and their coverage of 0.66 to 0.67 is about
what selection on extreme past asks would give.

The data already flags most of these qualities. Of the 57 penthouse units, 49 carry the
penthouse code and 54 the top-floor code. Of the 33 with outdoor space, 27 carry the private
outdoor code. Of the 87 layout or size units, 54 state a size and 73 have a size the model
reads. The model uses all of these columns and still prices the extreme units low. A
coefficient set across the whole city for "penthouse" stands in for the size of the premium
in an ordinary building, and the readers found these units are often much larger than that,
for example a 1,625 sq ft penthouse with a 516 sq ft terrace in a building of ordinary
2-bedrooms.

## Corrections the readers proposed

The readers proposed 23 actions. Each lists its backing in `reads.jsonl`.

- **Bedrooms, 13 units:** 1384631, 1480935, 2295085, 2385088, 2576730, 2911385, 3123968,
  3154147, 4352539, 4464832, 4658889, 4661198, 5184543. Each cites other ads of the same
  unit, and several also cite a stated size.
- **Baths, 1 unit:** 2851808.
- **Size, 1 unit:** 2934251. Both are backed by a later ad for the same unit.
- **Exclusions, 3 ads:**
  - 1519910, the sale of a nail salon business
  - 2791427, a $6,000 studio ad whose whole text is "test."
  - 2958909, a $9,999 ad for a unit whose other ads ask $4,100 and $4,650
- **Unit splits, 5 units:** 3564158 and 5088321 at medium confidence; 3329653, 4526133 and
  5159853 at low confidence.

The 13 bedroom changes and 3 exclusions meet the evidence rule as written. The low-confidence
splits do not, and I would leave them out.

### What went into the ledger

I checked each proposal against the rows of the 2026-11-09 pipeline build, the served
model's history and the ad texts in the dossiers. Five entries went into
`pipeline/ledger/2026-11-12-unit-level-reads.ndjson`:

- 1975451 and 2295085 set to 1 bedroom. Both ads come from Voro NYC with the same text, "Just
  one big open space", and code 2 bedrooms at 1,100 sq ft. The unit's four later ads
  (2381580, 2571982, 2611068, 4612929) code 1, two of them from Voro itself. The read named
  only 2295085, but 1975451 is the same ad a year earlier, so it gets the same set.
- 2934251 set to 2,000 sq ft. The record has no size, and the unit's 2021 ad 3596172 lists
  the same rooms and states "MASSIVE 2000 Sq. Ft.".
- 2791427 excluded as `malformed_ask`. The read's own ad is 3151154; the exclusion falls on
  the 2019 ad in its history, a $6,000 studio whose whole text is "test.". The unit's other
  ad asks $2,662, and the building's other studio ads of 2019 ask $2,245 to $3,095.
- 2958909 excluded as `malformed_ask`. The read's own ad is 5127509; the exclusion falls on
  the 2020 ad in its history, at $9,999 with a one-line text. The unit's other ads ask $4,100
  and $4,650, and the building's other 1-bedroom ads of 2019-07 to 2020-07 ask $3,100 to
  $3,800.

These cover 4 of the 18 proposals, and 1975451 comes on top of them. I left out the other 14:

- 1519910 (the nail salon) and 2851808 (2 full baths) are in
  `2026-11-11-outlier-sprint.ndjson` already.
- 1384631, 1480935, 2385088, 2576730, 3123968, 3154147, 4464832, 4658889, 4661198 and
  5184543 are flex layouts. Their texts give the count with an alcove, a convertible room, a
  home office, a den, a pressure wall or a tenant's wall ("three/four bedroom", "Flex 2",
  "converted to a two bedroom"). The unit's ads code the counts either way, except at
  4464832, where all three ads code 2 and the case for 1 rests on the text. Following
  the flex retract of 2026-10-17 (`2026-10-17-zz-unit-bedrooms-flex-retract.ndjson`), I set
  no count that depends on how such a room is counted. The 0 coded on 3123968 and 4661198 is
  wrong for an apartment with 2 baths and 3 windowed rooms, so those two may suit a
  `bedrooms_unknown` exclusion later.
- 2911385 would go from 0 to 1 bedroom, but the unit's ads fall in two groups, all of them
  from Centennial up to 2020. The ads of 2014, 2016-02 and 2019 code 0 bedrooms and 1.5
  baths and ask $4,795 to $5,295 for a "5 room duplex". The ads of 2015 to 2018 code 1
  bedroom and 1 bath and ask $2,949 to $3,695. The 2016-02 ad rented at $5,295 in May, and
  the next ad asked $3,695 in September. The ads cited as backing likely describe another
  apartment under the label 1B.
- 4352539 would go from 1 to 2 bedrooms. Of the unit's three other ads, two code 1 and one
  codes 2. The only text naming "2 Separate Bedrooms" is a Compass ad that reads as copy for
  the new 9-unit building as a whole (city views, roof decks), while this ad describes a
  duplex with a backyard and a finished basement.

The unit splits stay out of the ledger as proposals. Each would need a `split_unit` entry in
`pipeline/ledger/units/` with backing of its own:

| unit's latest ad | ads to split off | confidence | backing the reader gave |
|---|---|---|---|
| 3564158 | 4127972 | medium | 4127972 codes 4 bed / 2 bath for 2E, the other ads 2 bed / 1 bath at 900 to 1,000 sq ft |
| 5088321 | 4489365, 4629636 | medium | those two describe a 2 bed / 2 bath penthouse at $12,160 to $13,500; 4775035 a 755 sq ft 1 bedroom; 22O to 24O ask $6,245 |
| 3329653 | 3244112, 3377158, 2892750 | low | 7C carries ads coded 0, 2 and 3 bedrooms in a 6-floor building |
| 4526133 | 2738598 | low | a 900 sq ft 2 bedroom of 2019 under 6B, later ads a 4 bedroom |
| 5159853 | 4689652 | low | a 2,124 sq ft loft of 2025 under LOFT, while the building listed LOFT1 and LOFT2 in 2026 |

## What this implies

**Ledger fixes.** About 6% of the units read carry a data error with backing, 14 of them in
the top 200. Across the 935,000 units of a fit, 18 fixes would not move a fit's score, so by
the rule against refitting for negligible data changes they don't need a fit of their own.
They should go into the ledger before the next dataset rebuild.

**A label-standard rule.** I looked for a cheap screen and found none. Units whose ads
disagree on the bedroom count catch 6 of the 24 miscoded or shared-label units, and flag 7 of
the 276 others. Most of the wrong bedroom counts sit in a single ad of a unit whose other ads
agree with each other, and the readers found them by reading the text and the stated size. I
don't propose a rule from this sample.

**A modeling change.** Three quarters of the extreme units are real, and the served model
under-predicts the ones above their building. Two changes would address that:

1. A heavy-tailed unit level. It lets a unit with a long record above its building keep most
   of that level, and leaves the shrinkage of ordinary units alone. That is U2, and L1 with
   the Student-t level.
2. Better measures of the qualities, in particular the size of private outdoor space, which
   the readers often quoted from the text and the model has no column for.

The first change addresses the pattern in the table directly, and the second would explain
part of it.

## Recommendation

Write the L1 plus Student-t fit, and don't wait for the data fixes. The fixes are too few to
change what the fit learns, and the cases behind the heavy tail are mostly real apartments
with real premiums.

u2a found the degrees of freedom near 2.2. They mixed slowly (ESS 65 on 2 chains) and moved
with the unit scale (correlation 0.78). Six chains of L1 plus t would likely miss the gate on
that one scalar. Two ways around it:

1. Fix the degrees of freedom at a round value such as 3, chosen as a prior. I would not read
   it off u2a, whose training rows include some of the latest split's held-out ads.
2. Sample it, and accept the risk of a gate miss.

I would fix it at 3. That keeps the fit one change from L1, a unit level with a fixed heavy
tail, and drops the slowest scalar from the sampler.

## Predictions for L1 with a Student-t unit level (before any launch)

These assume the degrees of freedom fixed at 3, on the latest split, compared with L1 on the
shared held-out ads.

1. The fit passes the gate (65%).
2. elpd gains over L1 by more than 2 SE (60%).
3. For the top 200 units above their building in this note, the share of held-out asks above
   the 80% interval falls from b9's 0.43 to under 0.35 (55%). L1 has no Deals columns,
   so b9 is the reference here.
4. 80% coverage on all held-out ads moves by less than 0.005 (75%).
