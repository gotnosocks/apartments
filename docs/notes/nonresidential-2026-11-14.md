# Nonresidential ads among the rental rows (2026-11-14)

S16 ranked nonresidential space fifth among its follow-ups (`blind-spots-2026-11-14.md`). Its
`nonresidential` pattern marks 334 held-out ads outside its draw, and on those L1's median
misses by -0.004 ± 0.008 on average, with a spread 1.14 times that of all held-out ads and 76%
of the asks inside the 80% interval. A storefront, an office or a medical suite advertised among
the rentals is a data error to correct, so in this check I count the candidates in L1's
dataset, read a sample of them, screen them against L1's held-out predictions, and write a rule
only if the reads and the evidence on each row support one.

The check runs on L1's dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, its
saved fit `drift-building-phase-b0-latest-9a7830fb-l1` and the latest split. Nothing is fit and
nothing goes to Modal. I make no OxyLabs request and fetch no photo or floor plan. The scripts
are in `nonresidential-2026-11-14/`, and their outputs go to
`/data1/apartments/tmp/nonresidential-2026-11-14/`.

## The earlier work

`n1_prior.py` gathers four earlier sets and counts each against L1's rows.

1. **The ledger.** It holds 129 excludes with the reason `nonresidential`, one per listing,
   across 9 files under `pipeline/ledger/`. Every entry cites the ad's text and a read, and 4
   also cite another ad of the unit.
   - The 118 entries decided before L1's build on 2026-10-23 had already removed their
     listings, so none of them is among L1's rows.
   - The other 11 come from the outlier sprint's files of 2026-11-11 and 2026-11-12. They are
     among L1's rows: 3 in training and 8 held out, 2 of those outside S16's draw.
2. **The sprint's screen.** Its narrowed commercial pattern (`outlier-sprint/nonres/
   screen2.py`) matched 693 listings, all among L1's rows: 618 in training and 75 held out.
   Most matches come from an "ideal for" phrase (431) or "space available" (93), and 18 are
   parking spaces. No rule came of it.
3. **S16.** Its pattern marks 3,462 rows (3,123 in training, 339 held out) on 2,490 units. Its
   reads found 7 nonresidential ads, 6 already in the ledger.
4. **S17.** It read 3 commercial units among studio-coded rows on 5 or more rooms. All 3 are
   among L1's rows and none is in the ledger.

## The candidates

`n2_candidates.py` reads the latest record of every listing in the sprint's copy of the feed
records, lowercases its description and folds its white space and dashes. It then matches the
patterns below and keeps the unit label the lister typed. I narrowed the text patterns once
before counting, after reading the text around sampled matches of each with no price or gap in
view. I dropped kitchen venting, "net lease" (residential ads use it for the net effective rent),
per-square-foot fees with no year, and "office use" (a spare room "perfect for office use"), and
I kept foot traffic, signage and white boxes only in their commercial phrasings.

| stratum | the signal | rows | held out | outside S16's draw | units | buildings |
|---|---|---|---|---|---|---|
| `label` | a unit label such as `#STORE`, `COMMERCIAL`, `#OFFICE`, `#PROF` | 129 | 3 | 3 | 119 | 111 |
| `zero_zero` | coded 0 bedrooms, 0 full and 0 half baths | 0 | 0 | 0 | 0 | 0 |
| `sf_year` | an ask per square foot per year, triple net, CAM charges | 13 | 2 | 2 | 13 | 9 |
| `zoned` | commercial or manufacturing zoning, a use group | 19 | 1 | 1 | 15 | 11 |
| `build_out` | build to suit, key money, a grease trap, frontage, heavy foot traffic | 184 | 21 | 19 | 143 | 108 |
| `medical_prof` | a medical or dental office or suite, professional use | 174 | 12 | 12 | 151 | 109 |
| `offer` | a retail, office or medical space for rent, "ideal for a salon" | 235 | 26 | 25 | 211 | 155 |
| `live_work` | live/work or work/live | 4,840 | 504 | 503 | 3,473 | 1,498 |
| `ground_retail` | ground-floor retail or commercial space | 711 | 48 | 47 | 490 | 59 |
| `words` | S16's kind of words (a storefront, retail space, office space) and nothing above | 19,818 | 2,006 | 1,999 | 15,795 | 5,743 |
| all | | 26,123 | 2,623 | 2,611 | 20,322 | 7,383 |

A row's stratum is its first pattern in the table's order, so the strata don't overlap. The
`zero_zero` stratum is empty because the pipeline drops ads coded with 0 bedrooms and 0 full
baths as `invalid_or_missing_layout` (4,851 of the 4,908 such ads in the build). The 17 rows of
L1 with 0 bedrooms and 0 full baths all carry a half bath.

### Backing apart from the row's own text

For each candidate I gather the evidence that doesn't come from its own description:

- **its label**, typed by the lister in a field apart from the text;
- **another ad of the unit page** (the ads file's `unit_id`) with a strong text or a commercial
  label. The strong texts are the patterns from `sf_year` to `offer`. I count another ad's
  text only when it differs from the row's own, since a relisting often copies the text word
  for word. 244 candidate rows have such an ad, and 23 more have only a copy;
- **the lot**, when MapPLUTO, through the registry L1 reads, gives the row's lot no
  apartments (`unitsres` of 0).

The lot is weak on its own. Across all of L1's rows, 36,248 (1.9%) are on lots PLUTO gives no
apartments, mostly with land use 8 (public facilities) or 5 (commercial and office). Among the
candidates the share is 6.6% (1,729 rows), and 743 of those lots are parking facilities (land
use 10), which suggests new buildings on lots PLUTO still records as parking. I haven't
checked that.

### The draft rule

The draft marks a row with a signal of its own (a strong text or a commercial label) and at
least one independent kind of backing (its label, another ad of the unit page, or the lot).
Live/work, ground-floor retail and the broad words stay out of it. It marks 268 rows: 238 in
training and 30 held out, all 30 outside S16's draw, on 170 units in 136 buildings.

| kinds of evidence | rows |
|---|---|
| text and another ad | 157 |
| text and the lot | 41 |
| text and the label | 31 |
| text, the label and another ad | 12 |
| the label and the lot | 8 |
| the label and another ad | 8 |
| text, another ad and the lot | 6 |
| the label, another ad and the lot | 2 |
| text, the label, another ad and the lot | 2 |
| text, the label and the lot | 1 |

`n2b_overlap.py` matches the candidates against the earlier sets:

- Of the ledger's 11 listings among L1's rows, 8 are candidates (4 in `words`) and none is
  marked, since their units have no other ad with a strong text, no commercial label and a
  residential lot.
- Of S16's 7 nonresidential reads, 6 are candidates and none is marked.
- All 3 of S17's commercial reads are candidates, and 1 is marked.
- 271 of the sprint's 693 matches are candidates (152 in `offer`), and 61 are marked.

So the draft rule marks none of the ledger's 11 listings or S16's 7 reads. Three of the
ledger's listings match no pattern, and the others lack independent backing.

## Predictions, written before the draw, the reads and the screen

When I wrote these I had read the text around about 150 sampled matches while narrowing the
patterns, with no ask, prediction or gap in view, and I knew every count above. I had looked at
no gap of any candidate. I knew S16's figures for its pattern and its reads.

### The draw and the reads

`n3_draw.py` leaves out the candidates in S16's draw and draws 60 rows with seed 20261114,
from cells that split each stratum with an own signal by whether the draft rule marks it:

| cell | pool | reads |
|---|---|---|
| `label`, marked / unmarked | 64 / 65 | 4 / 4 |
| `sf_year` or `zoned`, marked / unmarked | 12 / 20 | 3 / 3 |
| `build_out`, marked / unmarked | 74 / 110 | 4 / 4 |
| `medical_prof`, marked / unmarked | 55 / 119 | 4 / 4 |
| `offer`, marked / unmarked | 63 / 172 | 4 / 4 |
| `live_work` | 4,840 | 8 |
| `ground_retail` | 711 | 5 |
| `words`, on an empty lot / other | 1,374 / 18,444 | 4 / 5 |

The pools are before dropping the 12 candidates in S16's draw. I weight each read by its
cell's pool over its cell's reads, so the shares below stand for the whole pool.

Sonnet readers take about 10 ads each, blind to the ask, L1's prediction and the cell. Each ad
shows its latest description with dollar figures masked, its unit label, its coded bedrooms
and baths, its room count and any stated size. A reader answers with one of: a residential
apartment, a commercial or nonresidential space, a live/work unit, or unclear, and quotes its
evidence.

Precision is the weighted share of reads answered commercial or nonresidential, with live/work
and unclear answers kept in the denominator. I give each share a Wilson interval at the Kish
effective sample size of its weights.

1. **Coded and strong strata.** Precision is about 0.85 for `label` (0.65 to 0.95, 70%), 0.6
   for `sf_year` and `zoned` together (0.35 to 0.85, 55%), 0.5 for `build_out`, 0.45 for
   `medical_prof` and 0.55 for `offer`, each within 0.25 of its guess (55%). Over the 754 rows
   with an own signal it comes to between 0.4 and 0.75, guess 0.55 (60%).
2. **The draft rule.** Its weighted precision is at least 0.75 (55%), and at least 0.15 above
   that of the unmarked rows with an own signal (55%).
3. **Broad strata.** `ground_retail` comes to 0.05 or less (75%), `words` to 0.08 or less
   (75%), and the words on an empty lot to no more than 0.1 above the other words (65%). For
   `live_work`, 0.1 or less is commercial (70%) and 0.2 to 0.5 is live/work (55%).
4. **The whole pool.** Weighted over all 26,123 candidates, precision is between 0.02 and 0.10,
   guess 0.05 (70%).

### The screen

`n5_screen.py` takes L1's held-out predictions from `pred_scores.npz` and leaves out S16's 400
drawn ads. The gap is the log ask minus L1's median, and the spread is the median absolute
deviation of the gap over that of all 189,247 held-out ads outside the draw (0.0404). In80 is
the share inside the 80% interval, against 0.798 for all of them. Standard errors are clustered
by building. The high-precision subset is the union of the read cells whose reads come to 0.8
or more.

5. **All candidates** (2,611 held-out ads): the mean gap lies within ±0.015 of zero, the spread
   between 1.05 and 1.25, and in80 between 0.74 and 0.80 (70%).
6. **`words`** (1,999): the mean gap within ±0.015 and the spread between 1.0 and 1.2, close to
   S16's pattern (70%). **`live_work`** (503): the mean gap within ±0.03 and the spread between
   1.1 and 1.4 (60%).
7. **Own signal** (62): the spread is 1.6 or more and in80 0.65 or less (60%). The mean gap is
   positive, guess +0.06, with an interval that includes zero (55%).
8. **The draft rule** (30): the spread is 1.6 or more and in80 0.65 or less (55%). Its standard
   error is 0.05 or more, too wide to give the gap a sign (65%).
9. **The high-precision subset**: the spread is 1.8 or more (55%).

### The rule

10. I write the rule only if the marked cells' weighted precision is 0.85 or more with a Wilson
    lower bound of 0.65 or more. I expect the reads to meet that (45%). If they fall short, I
    write no rule, and I may name a narrower set of evidence kinds whose reads are all
    commercial, flagged as post hoc.
