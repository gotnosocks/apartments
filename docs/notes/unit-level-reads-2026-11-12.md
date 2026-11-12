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
their neighbours, 43% of the held-out asks land above b9's 80% interval, against 10%
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

The readers proposed 23 actions. Each names its backing in `reads.jsonl`.

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
splits do not, and I would leave them out. None of these is applied here. They go to the
corrections ledger through a data PR with the usual provenance file.

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
   the 80% interval falls from b9's 0.43 to under 0.35 (55%). L1 has no Deals columns of its
   own, so b9 is the reference here.
4. 80% coverage on all held-out ads moves by less than 0.005 (75%).
