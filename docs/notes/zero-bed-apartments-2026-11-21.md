# Apartment ads coded 0 bed that state 2 or more bedrooms (2026-11-21, no fit)

## Question

The ratio read of `commercial-sweep-2026-11-20.md` coded 665 rows as apartments. 165 of them
are coded 0 bed, and the reads of 53 of those cite 2 to 5 beds from the text or the unit's
other ads. The TODO item asked four things:

1. Are the 53 rows ones the 2026-11-12 blank-form rules (`outlier-sprint-2026-11-11.md`)
   already cover and missed, or a different kind?
2. How large is the pattern on the whole history, and how often is the mark right?
3. Does the miscoding move the model's held-out errors?
4. Ledger bedroom sets from reads, a pipeline rule, or nothing?

No fit was run, no money was spent and nothing went into the ledger. Scripts and logs are in
`docs/notes/zero-bed-apartments-2026-11-21/`.

## Data

- Ads: the live build `ads-417bbdf5ed03f5d3.parquet` (2,229,067 ads), the build the ratio
  read drew from, with the latest record's lister, room count and text from
  `records-941f4a6588cbd8cc.parquet`. The brief named `ads-14f9e88d75290a0f`, a Nov 9 build
  older than the 2026-11-12 ledger sets; `z1_rows53.py` reads its bedrooms too, and all 53
  code 0 there as well. In both files `bedrooms` holds the typed value before ledger sets.
- Live Deals run `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3`: its rows
  give the training status and the strict text count of `rentfrontier.b0bedtext`
  (`bed_text`, `bed_text_more`).
- Ledger: every active entry on master, read with `pipeline/models/ledger/entries.read`.
- Held-out errors: the latest-split run
  `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt` (`pred_scores.npz`,
  189,647 held-out ads, built before the 2026-11-12 sets).
- Halves of buildings by the sweep's hash (`commercial-sweep-2026-11-20` plus the building).
- The scripts ran in `/data1/apartments/venvs/pipeline` inside the brief's
  `systemd-run --scope -p MemoryMax=3G` call, because the bridge-frontier venv has no duckdb
  and the ledger reader needs sqlglot.

No ask picks or codes any row below. The ratio read's own selection did use the ask (a ratio
over three times the area median), so the 53 serve only for question 1 and play no part in
the mark or the rule.

## 1. The 53 are mostly a different kind from the blank forms

`z1_rows53.py`. A count pattern over the reads' quotes and reasons finds exactly the 53 (30
on half A, 23 on B; 48 buildings, 49 units, first posted 2014 to 2026). None has a ledger
entry and all are training rows.

They are filled forms with long texts. 52 have a text of 80 characters or more, 37 have a
room count above 1, 22 have 2 or more full baths and 18 state a size. Only 13 carry the blank
form's defaults (1 bath, no half bath, no size, 1 room).

Against the 2026-11-12 classes:

- 30 fall in no 2026-11-12 class: 24 are "zero, other text" (the 2026-11-12 pattern finds no
  count) and 6 say "studio" somewhere in the text.
- 22 are in class S (a longer text naming 2 to 5 bed, no "studio") and 1 in P1. The pass
  looked at all 23 and left them. The page rule failed on 18 for lack of a counted ad of the
  page within 730 days, on 3 because the ask differed by more than 15%, and on 2 for other
  reasons. The building rule failed too (17 disagree, 4 too few ads, 2 none).

So 23 belong to a class the rules cover and failed both rules' conditions, and 30 are a kind
the rules never looked at. The strict parser of the live model codes only 15 of the 53 as
stating more bedrooms than coded; 35 get no own count from it. 39 units have another typed ad
coded 2 or more, 22 of them with every other ad at 2 or more.

One lister stands out: Centennial Properties NY posts 10 of the 53, 5 to 8 room duplexes with
2 baths typed as 0 bed, whose units' other ads code 2 or more two to nine times. The rest
spread over Compass (4), Nest Seekers (3), Corcoran (3) and 20 others.

## 2. The history: the text mark holds, the unit mark does not

### Counts

`z2_marks.py`, `z3_size.py`. Of 385,287 ads coded 0 bed, 323,784 are training rows of the
live run, and 323,704 of those carry no ledger entry. The forms of the mark, all from counts
and text:

- `T`: the strict parser reads 2 or more for the unit itself and every own stated size is
  above the code (`bed_text_more`, `bed_text` >= 2);
- `U_strict`: the unit has other typed ads and all of them code 2 or more;
- `U_clean`: some other ad of the unit codes 2 or more and none codes 1;
- `U_any`: some other ad of the unit codes 2 or more.

| form | rows | units | buildings | listers | half A | half B |
|---|---:|---:|---:|---:|---:|---:|
| `T` | 638 | 618 | 484 | 212 | 325 | 313 |
| `U_strict` | 3,115 | 3,115 | 1,913 | 671 | 1,559 | 1,556 |
| `U_clean` | 8,349 | 4,857 | 2,557 | 963 | | |
| `U_any` | 12,646 | 7,343 | 3,242 | 1,116 | 6,248 | 6,398 |
| `T` or `U_any` (the mark) | 13,089 | 7,771 | 3,484 | 1,151 | 6,468 | 6,621 |
| `T` and `U_any` | 195 | 190 | 178 | 102 | 105 | 90 |

The largest listers of the mark are Nooklyn (977), Rentopia (559), KCI (465), Moinian (419),
Compass (389) and Corcoran (326). 11,678 of the 13,089 fall outside the 2026-11-12 decision
groups; 8,554 say "studio" in the text. 45 of the 53 carry the mark.

### Reads

`z4_draw.py`, `z5_score.py`, `reader_prompt.txt`, `reads.csv`. Four strata of the mark: text
and unit (195), text only (443), unit with every other ad at 2 or more (2,985) and unit with
mixed counts (9,466). Ten ads were drawn from each, five per half, and shuffled into four
batches. Each block gave the ad's coded fields, day and whole text, and up to five other ads
of the unit, with dollar figures masked and no ask. Four Sonnet readers gave the ad's count
from its text, whether the other ads describe the same apartment, and a best count.

| stratum | pool | read | best count 2 or more | Wilson 95% | half A | half B |
|---|---:|---:|---:|---|---:|---:|
| text and unit | 195 | 10 | 10 | 0.72 to 1.00 | 5 of 5 | 5 of 5 |
| text only | 443 | 10 | 7 | 0.40 to 0.89 | 3 of 5 | 4 of 5 |
| unit, all 2+ | 2,985 | 10 | 1 | 0.02 to 0.40 | 0 of 5 | 1 of 5 |
| unit, mixed | 9,466 | 10 | 0 | 0.00 to 0.28 | 0 of 5 | 0 of 5 |

Weighted by the pools, the whole mark is right on 0.06 of rows (95% 0.00 to 0.23), `T` on
0.79 (0.58 to 1.00) and `U_any` on 0.04 (0.00 to 0.21).

The unit's other ads mostly describe another apartment. In the all-2+ stratum the readers
judged them a different apartment on 9 of 10, and 8 of the 10 ads call themselves a studio
or a 1 bed in their own text: a unit label reused across a studio and a larger layout, or
two apartments joined under one unit. The three misses of the text-only stratum are texts
that list the building's layouts or offer two layouts in one template (one of them unclear).
Where the reads agree with the mark, their count equals `bed_text` on all 10 ads of the text
and unit stratum.

## 3. Held-out errors: a small excess, mostly taken already

`z6_gaps.py`. Gap is the log ask less the predictive median on the l2bt held-out ads; SEs are
clustered by building. Ads named by the ledger since are reported apart.

| held-out ads, no ledger entry | ads | mean gap | SE | SD | over 97.5% | under 2.5% | 95% coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 189,425 | -0.004 | 0.000 | 0.078 | 0.024 | 0.030 | 0.945 |
| all coded 0 | 33,688 | -0.005 | 0.000 | 0.069 | 0.020 | 0.029 | 0.950 |
| `T` | 17 | +0.048 | 0.031 | 0.115 | 0.118 | 0.000 | 0.882 |
| `U_strict` | 6 | -0.033 | 0.036 | 0.080 | 0.000 | 0.000 | 1.000 |
| `U_any` | 1,168 | +0.009 | 0.003 | 0.087 | 0.052 | 0.027 | 0.920 |
| the mark | 1,179 | +0.009 | 0.003 | 0.087 | 0.052 | 0.027 | 0.920 |

On half A `T` has a mean gap of +0.081 (SE 0.053, 9 ads) and on half B +0.011 (SE 0.025, 8
ads), with 11% and 13% above the 97.5% quantile. `U_any` has +0.008 on A and +0.009 on B.
Only 6 held-out ads meet `T` and `U_any`.

The 126 held-out ads coded 0 that the ledger has named since have a mean gap of +0.157 (SE
0.028), 25% above the 97.5% quantile and 72% coverage. The 2026-11-12 work took the 0 bed
codes that moved the model most. What remains moves it little: a few dozen held-out ads with
a raised upper tail.

## 4. Recommendation: a narrow pipeline rule, for Data improvements

The rule's form was chosen on half A: on the reads `T` with `U_any` was right on 5 of 5, `T`
alone on 8 of 10 and the unit forms on 0 of 10. Half B gives 5 of 5, 9 of 10 and 1 of 10.

The rule: an ad coded 0 bed whose text states 2 or more bedrooms for the unit itself (the
`b0bedtext` reading, `bed_text_more` with `bed_text` >= 2) and whose unit has another typed ad
coded 2 or more takes the text's count. It reads no ask. `z7_rule.py` counts what it would
change: 196 ads, 195 training rows and 1 open Deals ad, over 190 units, 178 buildings and 102
listers. The counts set are 2 on 125, 3 on 57, 4 on 10 and 5 on 3, and they equal the unit's
lowest count of 2 or more on 151. The rule needs the strict text parser in the pipeline, or
it can run where the frontier dataset gains `bed_text`.

Left as they are:

- the 443 text-only rows: at 7 of 10 a rule would code about 130 of them wrongly. If Data
  improvements takes them up, a blind read of all 443 can draft ledger sets;
- the 12,451 unit-only rows: the unit's other ads describe another apartment far more often
  than the same one. That points to unit identity (labels reused across layouts) as the
  problem to study there, before any bedroom change;
- the 53 of the ratio read: chosen on the ask, so no rows are drafted from them; 15 of them
  meet `T`, and the 9 of those that also meet `U_any` fall under the rule.

No `candidate_rows.ndjson` was drafted.

## What was not checked

- Precision rests on 10 reads per stratum, one reader each, and no hand check of the reads.
  The rule's 10 of 10 has a Wilson lower bound of 0.72.
- The effect of the rule on a fit's elpd is not estimated; 195 rows of 1.9 million and 6
  held-out ads suggest a small one.
- Reasons for the unit-label reuse (lister, building type, years) were not studied.
