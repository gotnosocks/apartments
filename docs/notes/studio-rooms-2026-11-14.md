# S17: studios coded on units of 5 or more rooms (2026-11-14)

S16 split L1's studio-coded rows by their coded room count after its reads, and found that
the 70 held-out ads at 5 to 20 rooms outside its draw ask +0.085 ± 0.027 over L1's median,
with half inside the 80% interval (`blind-spots-2026-11-14.md`, follow-up 3). There are 905
such rows in L1's dataset. In this check I read 30 of them against the evidence a correction
needs, to find out whether the coded 0 is wrong and what could back a fix.

The check runs on L1's dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`, its
saved fit `drift-building-phase-b0-latest-9a7830fb-l1` and the latest split. Nothing is fit
and nothing goes to Modal. The coordinator barred floor plan fetches for this screen, so I
make no OxyLabs request of any kind and use plans only if one is already stored on disk.

## Predictions, written before any of the 905 rows was read

When I wrote these I had looked at no row of the 905 and drawn nothing. I knew S16's figures
by room count (489 rows at 5 rooms, 214 at 6, 53 at 7, 149 at 8 to 20; held-out ads outside
its draw at +0.086, +0.138, a single ad and -0.021); its 8 precision reads at 5 rooms (1
one-bedroom, 3 studios, 4 unclear); the sprint's finding that under 1% of ads typed as studios
carry more than 3 rooms; and L1's bedroom steps (+0.22 log for the first bedroom, +0.19 for
the second) beside a near-zero coefficient on `ad:extra_rooms`. About 167 listings have a
floor plan stored under `/data1/apartments/archive/floor-plans/`.

The sample takes 30 rows, stratified by room count (5, 6, 7, 8 or more) and by held-out
against training, so the shares below are weighted back to the 905 by stratum.

1. **Shares.** I expect 30% to 60% of the 905 to have 1 bedroom or more, with my point guess
   at 45% (60%). True studios, lofts with no walled bedroom included, come to 20% to 45%,
   guess 30% (55%). The rows I can't settle come to 15% to 35%, guess 25% (55%). Without a
   plan fetch, the unsettled share could run above that range.
2. **By room count.** The share with 1 bedroom or more is higher at 6 and 7 rooms than at 5,
   by at least 15 points (50%), and lowest at 8 or more rooms, where I expect whole buildings,
   townhouses and typed nonsense (60%).
3. **Evidence.**
   - The unit's other ads with a typed count of 1 or more, near in time and with the same
     room count, settle at least half of the settled rows (65%).
   - A stated size comes second. It argues for a bedroom only with other backing, since lofts
     and large studios run past 700 sq ft.
   - Units of the same line in the building settle a few rows where the unit page has no
     other ad.
   - At most 1 of the 30 rows has a plan stored on disk (80%).
4. **Reasons for the high room count.**
   - Among rows with a bedroom, the lister typed the room count and left the bedroom field at
     its default 0, or the feed dropped the count. This accounts for most of them (60%).
   - Among true studios, the room count includes alcoves, dressing rooms or a loft's zones,
     or belongs to the building or a whole house at 8 rooms or more.
   - Combined listings, two apartments under one ad, come to at most 2 of the 30 (65%).
5. **The gap after a fix.** Correcting the bedrooms of the rows with 1 bedroom or more would
   raise L1's median on those ads by about 0.2 log or more, but L1's unit level already absorbs
   part of the miscoding where the unit's earlier ads carry the same 0. So I expect the mean
   gap of the 70 held-out ads to move from +0.085 to between -0.03 and +0.04, guess +0.01, a
   shrink of at least half (60%). The held-out ads whose unit has an earlier ad coded 1 or more
   carry most of the gap: their mean gap is at least +0.15 against under +0.04 for the rest
   (55%).
6. **Rules.** A rule needing the unit's history (other ads of the unit page coded 1 or more,
   near in time, with a room count within 1 of the row's) marks 15% to 40% of the 905 rows,
   with every sample row it marks settled at 1 bedroom or more (55%). No room count threshold
   alone gives a precision of 0.8 or more on the sample (60%).

## The draw, the evidence and the reading

The scripts are in `studio-rooms-2026-11-14/`, and their outputs are frozen under
`/data1/apartments/tmp/studio-rooms-2026-11-14/`.

The pool holds 905 rows. S16 had drawn 12 of them for its reads, so I left those 12 out and
`s1_draw.py` drew 30 of the other 893 with seed 20261114: 5, 4, 1 and 4 held-out ads at 5, 6,
7 and 8 to 20 rooms, and 5, 4, 3 and 4 training rows. Each row carries its cell's size over its
take as a weight, from 1 to 88.2. The weighted shares below stand for the 893, and I score the
predictions' shares of "the 905" against them. The rule counts run over all 905.

`s2_evidence.py` wrote a dossier for each row from the ads file of the build behind L1's
dataset (`ads-3775f6d9b3e028ca.parquet`), the outlier sprint's records and the listing codes.
A dossier holds:

- the row's coded fields and text;
- the unit page's other ads, with the texts of the 5 nearest in time;
- units of the same line on other floors;
- a count of the building's ads with the same room count;
- any plan already stored on disk.

I masked dollar figures and put in no ask or L1 prediction. `s3_batches.py` split the rows
into 3 shuffled batches and recorded SHA-256s of 42 files in `evidence.json`.

The coordinator barred plan fetches for this screen, so I made no OxyLabs request of any
kind. Two rows had plans stored under `/data1/apartments/archive/floor-plans/`: row 8 (508
Broadway, unit 3), whose plan comes from a 2018 ad of its unit, and row 9 (393 West Broadway,
unit 3WO). I converted row 8's .webp plan to .png with Pillow from the `nj-root` venv so the
readers could open it.

Three Sonnet readers took 10 dossiers each with the prompt in `reader_prompt.txt`. I launched
each once, at 03:04 ET, and they ran side by side. All three finished within 2 minutes, wrote
30 lines between them and refused nothing. `s4_features.py` computed the fields of the
candidate rules over all 905 rows before I scored the reads, and `s5_score.py` scored them
into `scores.json`.

When the PR came up for review, I read row 25's dossier and changed its verdict from the
reader's `studio` to `unresolved`, leaning studio, in `s5_score.py`. Its ad of 2022 and its
ad of 2025, which codes 0, both describe two sleeping areas open to the living room below.
Two of its three ads from 2014 and 2015 code 2 and 1 bedrooms on 4 rooms, the second at the
same 1,201 sq ft, and line units 321, 421 and 521 code 1 to 2 bedrooms on 4 rooms. I told the
readers to settle a coded 0 as a studio only when nothing else contradicts it, and those ads
contradict it. All figures below include the change.

## Results

### Verdicts

| cell | rows outside S16's draw | read | bedrooms | studio | other | unresolved |
|---|---|---|---|---|---|---|
| 5 rooms, held-out | 42 | 5 | 2 | 1 | 0 | 2 |
| 5 rooms, training | 441 | 5 | 2 | 0 | 0 | 3 |
| 6 rooms, held-out | 14 | 4 | 0 | 2 | 0 | 2 |
| 6 rooms, training | 199 | 4 | 2 | 1 | 0 | 1 |
| 7 rooms, held-out | 1 | 1 | 1 | 0 | 0 | 0 |
| 7 rooms, training | 49 | 3 | 1 | 0 | 0 | 2 |
| 8 to 20 rooms, held-out | 13 | 4 | 0 | 3 | 1 | 0 |
| 8 to 20 rooms, training | 134 | 4 | 0 | 2 | 2 | 0 |
| all | 893 | 30 | 8 | 9 | 3 | 10 |
| share weighted to the 893, ± SE | | | .35 ± .14 | .16 ± .07 | .08 ± .04 | .42 ± .13 |

### Precision

I count a `bedrooms` verdict as a hit for "a studio coded on 5 or more rooms has more
bedrooms than coded", and a `studio` or `other` verdict as a miss.

The raw figures describe the sample. Held-out ads make 14 of its 30 rows but only 70 of the
893, so I weight each cell by its size for the pool. In both tables the first column counts an
unresolved row as a miss, and the second leaves it out. Raw intervals are 95% Wilson.

| sample rows | over all rows read | over settled rows | unresolved |
|---|---|---|---|
| 5 to 20 rooms | 8/30 = 0.27 (0.14 to 0.44) | 8/20 = 0.40 (0.22 to 0.61) | 10 of 30 |
| 5 rooms | 4/10 = 0.40 (0.17 to 0.69) | 4/5 = 0.80 (0.38 to 0.96) | 5 of 10 |
| 6 or more rooms | 4/20 = 0.20 (0.08 to 0.42) | 4/15 = 0.27 (0.11 to 0.52) | 5 of 20 |
| 6 and 7 rooms | 4/12 = 0.33 (0.14 to 0.61) | 4/7 = 0.57 (0.25 to 0.84) | 5 of 12 |
| 8 to 20 rooms | 0/8 = 0 (0 to 0.32) | 0/8 = 0 (0 to 0.32) | 0 of 8 |

The weighted shares are stratified means over the cells, with SEs from the within-cell
variance. On settled rows the share is a ratio of two such means, with a linearized SE.

| pool rows, weighted | share of all rows | share of settled rows | unresolved share |
|---|---|---|---|
| 5 to 20 rooms | .35 ± .14 | .59 ± .12 | .42 ± .13 |
| 5 rooms | .40 ± .22 | .96 ± .04 | .58 ± .22 |
| 6 or more rooms | .29 ± .14 | .36 ± .16 | .22 ± .13 |
| 6 and 7 rooms | .44 ± .22 | .67 ± .27 | .34 ± .20 |
| 8 to 20 rooms | 0 | 0 | 0 |

The settled share goes from 0.40 raw to .59 weighted because 5 of the 8 bedroom reads are
training rows, weighted 16.3 to 88.2, while 7 of the 12 studio and commercial reads are
held-out ads, weighted 3.25 to 8.4. At 5 rooms the settled share rests on 5 rows. Its
single studio is a held-out ad weighted 8.4, against 88.2 for the two training rows read as
bedrooms, so I would not lean on its SE of .04.

If every unresolved row held a bedroom, the precision over all 30 would come to 18 of 30
(0.60). The readers leaned toward bedrooms on 3 of the 10 unresolved rows and toward a studio
on 3, row 25 among them, and leaned neither way on 4.

### By room count

At 5 rooms the readers found bedrooms on 4 rows and a studio on 1, and left 5 unresolved
when the unit's history ran out. At 6 and 7 rooms they found 4 rows with bedrooms and 4
studios, and left 4 unresolved; with row 25 moved, that comes to 3 studios and 5 unresolved.
At 8 to 20 rooms they settled all 8:

- 5 studios coded with 12 to 15 rooms, where the unit's other ads give the apartment 1 to 3
  rooms, so I read those room counts as feed errors;
- 3 commercial spaces: a former dental office, a storefront and a restaurant.

S16 found no gap at 8 to 20 rooms, in line with these reads.

### Evidence

For each settled row I count every kind of backing in the reader's list, so a row can add to
several kinds. The scoring of prediction 3 below uses the same counts.

| kind of backing | bedrooms (8) | studio (9) | other (3) | settled (20) |
|---|---|---|---|---|
| the unit's other ads | 5 | 9 | 1 | 15 |
| units of the same line | 5 | 3 | 0 | 8 |
| a stated size | 4 | 5 | 0 | 9 |
| a stored plan | 1 | 0 | 0 | 1 |
| the row's own text | 5 | 8 | 2 | 15 |

On the bedroom reads, the unit's other ads backed rows 1, 17, 20, 21 and 23, and units of the
same line backed rows 0, 1, 18, 21 and 23. On rows 0 and 18 the line units and the ad's text
carried the read alone, and a stated size always came with another kind. Row 9's stored plan
shows two guest rooms and a master bedroom, all walled, beside a den.

On the 9 studio reads, the unit's other ads agreed with the 0, mostly as ads coded 0 with 1 to
3 rooms and the same studio text. On row 25 they split by date, and I moved it to unresolved.
Of the 3 commercial reads, row 13 rests on its text and another ad of the unit offering the
same dental office, row 26 on its text alone and row 27 on a unit label of `storefront`.

The 10 unresolved rows lack backing for different reasons:

- rows 3, 5 and 19 have other ads of the unit, but over 24 months away or with another bath
  count;
- on row 2 the same text is coded 0 in 2017 and 2025 and 1 bedroom in 2020 and 2023;
- row 8's stored plan shows three walled rooms, but it comes from a 2018 ad, and the current
  text describes an open plan with a bedroom and an office;
- row 16's text says three bedrooms twice, with nothing outside the ad to back it;
- rows 14, 15 and 24 have no other ad and no matching line unit, and the descriptions of rows
  15, 19 and 24 run to a single character;
- on row 25 the unit's ads of 2022 and 2025 describe open sleeping areas, while its ads of
  2014 and 2015 and its line units code 1 to 2 bedrooms.

### Reasons for the room count

The readers coded all 8 bedroom rows as a bedroom field left at 0. Of the 9 studios, they
coded 1 as loft zones, 1 as a studio counting extras and 7 as unclear, mostly rows with a
room count matching nothing in any ad of the unit. Row 25, now unresolved, carries the other
loft-zones code. No row was a combined listing.

### My checks of the readers' calls

I read the dossiers of rows 0, 1, 2, 6, 9 and 18 and looked at row 9's plan myself. I agree
with all 6 verdicts. On review I also read row 25's dossier and changed its verdict, as
described above. The counts hold less firmly than the verdicts:

- row 0 could have 1 or 2 bedrooms: its unit's 2020 ad codes 1, and the building's page for
  unit 3, likely the same floor-through, codes 1 and 2;
- row 1 could have 1 or 3: with the same text, its 2020 ad codes 1 and its ads from 2024 on
  code 3;
- row 18 could have 2 or 3: its ad offers a flex third room, and the line codes 3.

### Candidate rules

I counted each rule over the 905 rows. The held-out column gives all 82 held-out ads, with
those outside S16's draw in brackets. Gaps are L1's mean on the held-out ads outside S16's
draw, with SEs clustered by building. The contrast is the marked mean less the unmarked mean,
with a building-clustered SE from a regression of the gap on the rule.

| rule | rows | held-out | units | buildings | 5 rooms / 6+ | gap, marked | gap, unmarked | contrast | sample rows marked |
|---|---|---|---|---|---|---|---|---|---|
| 5 rooms | 489 | 48 (42) | 413 | 307 | 489 / 0 | +0.086 ± 0.035 | +0.083 ± 0.043 | +0.003 ± 0.054 | 10: 4 bedrooms, 1 studio, 5 unresolved |
| 6 or 7 rooms | 267 | 19 (15) | 238 | 165 | 0 / 267 | +0.173 ± 0.070 | +0.061 ± 0.029 | +0.112 ± 0.073 | 12: 4 bedrooms, 3 studios, 5 unresolved |
| H1: a unit ad within 730 days coded 1+ | 243 | 24 (20) | 228 | 161 | 139 / 104 | +0.185 ± 0.063 | +0.045 ± 0.025 | +0.140 ± 0.066 | 4: 4 bedrooms |
| H2: H1 with rooms within 1 | 163 | 17 (15) | 154 | 113 | 98 / 65 | +0.203 ± 0.067 | +0.053 ± 0.025 | +0.150 ± 0.065 | 2: 2 bedrooms |
| H3: every unit ad within 730 days coded 1+ | 163 | 9 (8) | 162 | 128 | 92 / 71 | +0.149 ± 0.090 | +0.076 ± 0.027 | +0.073 ± 0.087 | 2: 2 bedrooms |
| an earlier unit ad coded 1+, any distance | 284 | 26 (26) | 256 | 175 | 171 / 113 | +0.083 ± 0.039 | +0.086 ± 0.037 | -0.003 ± 0.054 | 9: 5 bedrooms, 1 studio, 3 unresolved |
| a line unit coded 1+ with rooms within 1 | 480 | 44 (37) | 393 | 253 | 335 / 145 | +0.148 ± 0.039 | +0.014 ± 0.032 | +0.133 ± 0.051 | 14: 5 bedrooms, 3 studios, 6 unresolved |
| a stated size of 900 sq ft or more | 206 | 13 (13) | 183 | 139 | 80 / 126 | +0.029 ± 0.040 | +0.098 ± 0.032 | -0.069 ± 0.050 | 4: 1 bedroom, 1 other, 2 unresolved |
| a text over 80 characters without "studio" | 525 | 48 (37) | 427 | 313 | 279 / 246 | +0.171 ± 0.041 | -0.012 ± 0.021 | +0.182 ± 0.047 | 17: 7 bedrooms, 1 studio, 3 other, 6 unresolved |

All 4 sample rows marked by H1 read as bedrooms (Wilson 0.51 to 1.00). The readers accepted
those same ads as backing, so the agreement partly restates the rule. H1 leaves out 4 of the
8 bedroom reads (rows 0, 9, 17 and 18). It marks 24 held-out ads, 20 of them outside S16's
draw, and those 20 ask 0.14 ± 0.07 more than the other 50, which still ask +0.045 ± 0.025
over L1's median. The line rule and the text rule give contrasts of 0.13 ± 0.05 and
0.18 ± 0.05, at lower precision: 5 of 14 and 7 of 17 over all rows read. Under the project's
rules an ad's words alone can't change a coded field, so the text rule could at most become
an additive feature. Ads stating 900 sq ft or more have a smaller gap than the rest, +0.029
against +0.098.

I chose H1 after scoring these 9 rules on the same 70 held-out ads whose gap led S16 to split
by room count, so its contrast is post hoc. The rule I wrote down before the reads was H2
(prediction 6). I prefer H1 because:

- it marks 243 rows against 163 and 20 of the 70 against 15, with about the same contrast,
  0.14 ± 0.07 against 0.15 ± 0.07;
- its 4 marked sample rows all read as bedrooms, and H2 drops 2 of them, rows 20 and 23,
  because the unit's ad coded with bedrooms gives 4 or 5 rooms against the row's 6 or 7.

Anyone judging a fit of an H1 rule has to keep that selection in mind. These 70 ads helped
pick the rule, so its gain on them will run higher than on fresh ads.

### The gap after a fix

The 20 held-out ads marked by H1 ask +0.185 over L1's median, and L1's step from 0 to the
unit's modal count averages 0.40 log on them. Taking the full step off their gaps would leave
them at -0.21 and the 70 at -0.029, and with H2 the 70 would go to -0.006. Since the marked
ads ask only about half the step over L1's median, I take it that L1's unit level, fit on the
unit's other ads, already carries part of the premium, and that the full-step figures
overshoot. If a fix brought the marked ads to the +0.045 of the unmarked ones, the 70 would
go to +0.045. Neither figure comes from a refit. On the sample, the readers' counts move the
14 held-out rows from a weighted +0.062 to -0.064, an overshoot of the same kind.

H1 marks 24 of L1's 189,647 held-out ads, so any fix moves L1's score on the latest split
very little.

## Predictions scored

1. **Shares.** Weighted to the 893, 1 bedroom or more comes to .35 ± .14, inside 30% to 60%
   and below my guess of 45%, a hit. Studios come to .16 ± .07, below 20% to 45%, a miss. The
   unsettled rows come to .42 ± .13, above 15% to 35%, a miss. My shares left no room for the
   .08 ± .04 of commercial space.
2. **By room count.** Bedrooms at 6 and 7 rooms against 5, by at least 15 points: .44
   weighted against .40 (raw 4 of 12 against 4 of 10), a miss. Lowest at 8 or more rooms: a
   hit at 0 of 8, though I found studios with stray room counts and commercial space there,
   and no whole building or townhouse.
3. **Evidence.**
   - Unit ads coded 1 or more settling at least half of the settled rows: a miss, at 5 of 20.
     The unit's other ads backed 15 of 20, mostly by agreeing with a studio.
   - Size second: among the four kinds of backing outside the ad's text, size came second at
     9 of 20 settled rows, but it settled none alone, and line units backed more of the
     bedroom reads (5 against 4). A partial hit.
   - Line units settling a few rows without the unit's history: a hit, on rows 0 and 18.
   - At most 1 row with a plan on disk: a miss, at 2.
4. **Reasons.**
   - A bedroom field left at 0 on most rows with bedrooms: a hit at 8 of 8, though the
     readers had little else to pick for a studio-coded ad with bedrooms.
   - Studios' room counts coming from alcoves, zones or a whole building: a miss. 7 of 9 are
     unclear, and at 8 or more rooms the counts match no layout.
   - At most 2 combined listings: a hit, at 0.
5. **The gap after a fix.**
   - The 70 moving to between -0.03 and +0.04: untested. The full-step arithmetic gives
     -0.029 to +0.038 across the history rules, inside my range, but it overshoots on the
     marked ads, and no refit backs it.
   - Held-out ads with an earlier unit ad coded 1 or more carrying most of the gap: a miss,
     at +0.083 ± 0.039 on 26 ads against +0.086 ± 0.037. Unit ads coded 1 or more within 730
     days on either side of the ad (H1) do better: the 20 ads they mark ask 0.14 ± 0.07 more
     than the other 50, though I found that rule after scoring 9 of them. Held-out ads
     in the latest split run from 2015 to 2026, so L1's unit level learns from the unit's ads
     on both sides of a held-out ad.
6. **Rules.**
   - The history rule with rooms within 1 (H2) marks 163 rows, 18.0% of the 905, and both
     sample rows it marks read as bedrooms: a hit, on 2 rows.
   - No room count threshold with a precision of 0.8 or more: a hit over all rows read, where
     the best is 0.40 raw and .44 ± .22 weighted, and a miss over settled rows, where the
     5-room band comes to 0.80 on 4 of 5 raw (0.38 to 0.96) and .96 ± .04 weighted.

## Recommendation

I recommend a B2-like rule needing the unit's history, with no correction overlay and no
rule keyed on the room count.

- I'd keep the room count out of the rule. Weighted to the 893, .35 ± .14 of the rows read
  as bedrooms and .42 ± .13 stayed unresolved. Over all rows read, every band stays at .44
  or below, and none of the 8 rows at 8 to 20 rooms read as bedrooms. On
  settled rows the weighted share comes to .59 ± .12, and to .96 ± .04 at 5 rooms, but the
  5-room figure rests on 5 reads, with .58 ± .22 of that band unresolved.
- H1 marks 243 rows in 228 units and 161 buildings. Of its 24 held-out ads, the 20 outside
  S16's draw ask 0.14 ± 0.07 more than the other 50 (+0.185 ± 0.063 against
  +0.045 ± 0.025), and all 4 sample rows it marks read as bedrooms. I chose it after scoring
  9 rules on the same 70 ads, so a fit of it has to be judged with that selection in mind.
  I would write it as an exclusion, as B2 is, rather than a recode, because unit histories
  disagree on the count (rows 0 and 1). It needs its own fit, with predictions written first.
- An overlay backed by evidence would add few rows beyond H1. Without plan fetches 10 of 30
  rows stay unresolved, and the bedroom reads outside H1 rest on line units or a single
  stored plan.
- The 3 commercial reads, .08 ± .04 of the 893 when weighted, add to S16's nonresidential
  misses. A screen for nonresidential ads at 8 or more rooms (labels like `storefront`,
  retail and office words) would be a separate data check.

## Refusals and limits

- The permission check refused four Bash commands, and I split each into plain steps:
  1. a heredoc writing a script and then running it, as too complex to verify;
  2. a loop over the venvs' Python binaries, because a command name was computed at runtime;
  3. a `sed` reading a dossier through a shell variable, because the variable could start
     with a dash;
  4. a line running the linter and then `git status`, as too complex to verify.
- Thirty reads give wide intervals. The raw figures describe the sample, and the weighted
  shares lean on training rows weighted up to 88.2; at 5 rooms the settled share rests on 5
  rows.
- The readers settled verdicts more firmly than counts, as my checks above show.
