# A history sweep for commercial and placeholder ads (2026-11-20, no fit)

## Question

The TODO item asked for a sweep of the whole ads history with three marks, for commercial and
placeholder ads that stay in training without breaking R-hat:

- `ratio`: coded 0 or 1 bed with an ask over three times the area median (the median of the
  live rows of the same neighbourhood, year and bedrooms);
- `text`: the words "retail", "storefront", "office", "per sf" (and "per square foot") or
  "warehouse";
- `short`: a text of a few characters (five or fewer after stripping, or "Draft", "Desc" or
  "TBD").

How many rows does each mark find beyond the ledger's exclusions, how many of them are
commercial or placeholder ads, is there a rule with high enough precision to write, and do the
matches change the Deals page? No fit was run and no money was spent. Scripts and logs are in
`docs/notes/commercial-sweep-2026-11-20/`.

## Data

- Ads: every ad of the live build, `ads-417bbdf5ed03f5d3.parquet` (2,229,067), with the latest
  record's text from `records-941f4a6588cbd8cc.parquet` (`sw1_ads.py`, `sw2_texts.py`).
- Status, from the live Deals run `drift-building-bedtext-layout-range-b0-market-6cd1f12b-range-m3`
  (rows `rows-4f487ef77bb6ca61`): `train` is a training row (1,894,766); `live` is a Deals ad
  (6,502); `ledger` carries an active ledger exclude (2,550 ads, from 2,586 active excludes);
  `rule` was dropped by another pipeline rule (325,249).
- Held-out gaps: the latest-split run `drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`
  (189,647 held-out ads), gap = log ask minus the model's median. Its build is older than the
  live one, so a few rows the ledger now excludes are scored there.
- Halves: buildings cut in two by a hash of the building id with this note's seed
  (`sw3_counts.py`).

The two broad words were narrowed once, from the words around them with no ask loaded
(`sw3a_context.log`). An "office" counts only outside residential phrases such as home office,
leasing office, post office, management office or office nook. A "retail" counts only in a
phrase that offers retail space, such as "retail space", "for retail" or "retail/office".

## Counts by mark

From `logs/sw3_counts.log`:

| mark | all ads | training | Deals ads | ledger | other rule | training buildings |
|---|---|---|---|---|---|---|
| ratio | 1,140 | 1,004 | 4 | 128 | 4 | 536 |
| text, raw words | 239,263 | 207,040 | 1,196 | 155 | 30,872 | |
| text, narrowed | 73,999 | 61,186 | 294 | 100 | 12,419 | 16,546 |
| of which retail | 3,426 | 3,039 | 33 | 20 | 334 | |
| of which storefront | 1,484 | 923 | 40 | 14 | 507 | |
| of which office | 64,200 | 52,816 | 221 | 71 | 11,092 | |
| of which per sf | 136 | 111 | 1 | 1 | 23 | |
| of which warehouse | 5,882 | 5,177 | 12 | 1 | 692 | |
| short | 62,377 | 53,347 | 24 | 1,285 | 7,721 | 8,583 |
| any mark | 137,236 | 115,311 | 321 | 1,460 | 20,144 | |

The training column is what is new beyond the ledger. Among training rows, 197 carry both
the ratio mark and a text word, 778 the ratio mark alone (29 more with a short text), 60,989 a
text word alone and 53,318 a short text alone. The ledger already holds the clear cases of
each mark: 46 of its ratio matches and 77 of its text matches are excluded as nonresidential,
and 1,283 of its short matches as `bedrooms_unknown` (the blank-form excludes of the outlier
sprint). Short training rows carry every bedroom count (0 bed 8,340, 1 bed 18,600, 2 bed
16,004, 3 bed 7,866), and their texts are mostly ".", empty, "x" or "2br".

## Reader evidence

The following is reader evidence, stated as such. 150 training rows were drawn in strata
(`sw4_draw.py`, seed 20261120): 30 ratio with a text word, 40 ratio alone, 8 of each narrowed
word alone, and 20 short texts coded 0 bed and 20 coded 1 or more. Six Sonnet readers, 25 ads
each, read the whole text, the coded fields and label, up to four other ads of the same unit,
and for short texts three ads of other units of the building near in time
(`reader_prompt.txt`). No ask was shown, and dollar figures in texts were masked. Each answered
commercial, placeholder, apartment or unclear, with a quote.

Answers: apartment 123, commercial 22, placeholder 2, unclear 3 (`answers.json`, `reads.csv`).
Every commercial code but one came from the ratio strata (16 of 30 ratio with a text word, 5
of 40 ratio alone, 1 of 8 storefront).

I checked 15 codes by hand against the batch texts: 8 commercial, unclear or placeholder codes
(C033, C034, C035, C046, C067, C092, C136, C137) and 7 apartment codes from the ratio strata
(C016, C030, C049, C074, C106, C129, C130). 13 agree and 2 are borderline. C033 ("Apt", with
every nearby ad of the building also "Apt" and 0 bed) could be a studio building's template,
so I would code it unclear. C074 ("LEGAL LIVE / WORK -- IDEAL SHOWROOM & OFFICE") is a
live/work loft, which the brief counts as an apartment, though its ad sells it for business
use. Several ratio-mark apartments are full-floor lofts of 2,000 to 4,000 square feet coded 0
or 1 bed, which is a bedroom-coding question for another note.

## Precision by mark and half

Weighted by stratum pool size, with Wilson intervals at the effective sample size
(`logs/sw5_score.log`, `precision.csv`):

| set | half A | half B | all |
|---|---|---|---|
| ratio, commercial or placeholder | 7 of 31, 0.16 (0.07 to 0.35) | 15 of 39, 0.28 (0.15 to 0.45) | 0.23 (0.14 to 0.35) |
| ratio with a text word | 5 of 13, 0.38 (0.18 to 0.64) | 11 of 17, 0.65 (0.41 to 0.83) | 0.53 (0.36 to 0.70) |
| ratio without a text word | 2 of 18, 0.11 | 4 of 22, 0.18 | 0.15 (0.07 to 0.29) |
| text, commercial | 0.005 | 0.002 | 0.004 (0 to 0.27) |
| text without ratio, commercial | 1 of 20 | 0 of 20 | 0.002 (0 to 0.26) |
| short, placeholder | 0 of 16 | 1 of 24 | 0.008 (0 to 0.14) |

Among ratio reads by ratio band, commercial or placeholder over reads: half A 3 of 21 at 3x
to 4x and 4 of 10 at 4x to 6x; half B 6 of 26, 5 of 9, 2 of 2 at 6x to 10x and 2 of 2 over
10x.

Rule form, chosen on half A: the best form on A is the ratio mark with a text word, at 0.38,
with 4x and over a close second at 4 of 10. On half B the same form gives 0.65. Both halves
leave a third or more of its matches as apartments, so no rule is written. The text and short
marks alone find almost no commercial or placeholder rows outside the ledger: the readers
coded 39 of 40 text-only reads and 38 of 40 short reads as apartments. Over the pools, the
ratio estimates imply about 105 commercial rows among the 197 ratio rows with a text word
(interval 71 to 138) and about 121 among the 807 ratio rows without one (56 to 234).

## Held-out gaps and Deals relevance

From `logs/sw6_relevance.log`. All held-out ads: median gap -0.0037, 5.9% below the 5% point,
4.7% above the 95% point.

Own gaps of marked held-out ads. The ratio mark selects on the ask, so its own gap is
circular; the other two do not use the ask.

| held-out ads | ads | median gap | below 5% | above 95% |
|---|---|---|---|---|
| text, training rows | 6,122 | -0.0035 | 6.4% | 5.5% |
| short, training rows | 6,185 | -0.0009 | 5.6% | 5.9% |
| short, now ledger-excluded | 59 | 0.0766 | 1.7% | 23.7% |
| text, now ledger-excluded | 4 | 0.6326 | 25% | 75% |
| ratio, now ledger-excluded | 3 | 1.0316 | 0% | 100% |

No confirmed read is a held-out ad of l2bt.

Other held-out ads in buildings that hold a marked l2bt training row, which is what an exclude
would move through the building's level:

| buildings holding a training row with | buildings | other held-out ads | median gap | below 5%, A / B | above 95% |
|---|---|---|---|---|---|
| ratio | 544 | 4,357 | -0.0029 | 6.9% / 6.5% | 5.9% |
| ratio and a text word | 151 | 467 | -0.0050 | 9.1% / 10.1% | 7.1% |
| a confirmed commercial or placeholder read | 24 | 53 | 0.0146 | 6.7% / 2.6% | 3.8% |
| text | 15,961 | 74,561 | -0.0040 | 6.3% | 5.0% |
| short | 8,325 | 56,767 | -0.0033 | 6.2% | 5.2% |

All held-out ads by half: 6.0% / 5.8% below 5%. Buildings with a ratio row and a text word
hold an excess of low misses on both halves, 3 to 4 points (about 3 standard errors on the
pooled 467). The 24 buildings with a confirmed commercial read show no excess, so the excess
may come from buildings whose asks vary widely, such as loft buildings, more than from the
commercial rows raising the level.

Live Deals ads (6,502; 496 ask under the 80% interval's low end, 309 of them uncautioned;
4,687 in the default population of a unit basis or a building with five or more training ads,
uncautioned). "Top 300" is the first 300 of that population by cautious saving.

| buildings holding a live training row with | training rows | buildings | Deals ads | under lo80 | under lo80, uncautioned | top 300 |
|---|---|---|---|---|---|---|
| ratio | 1,004 | 536 | 171 | 14 | 9 | 9 |
| ratio and a text word | 197 | 152 | 22 | 2 | 1 | 1 |
| a confirmed read | 24 | 24 | 2 | 0 | 0 | 0 |
| text | 61,186 | 16,546 | 2,700 | 189 | 111 | 112 |
| short | 53,347 | 8,583 | 2,133 | 152 | 92 | 95 |

The one top-300 ad in a building with a ratio row and a text word is 5192126 at Archive Lofts,
asking $7,500 against a low end of $7,564, in a building of 25 training ads. Excluding the
ratio rows with a text word would change the page by at most a handful of ads.

## Why the earlier screen saw a near-zero gap

The outlier sprint's commercial screen (`outlier-sprint-2026-11-11.md`, and
`nonresidential-2026-11-14.md`: 2,611 held-out candidates, mean gap -0.0047) found its matches
near zero gap. This sweep gives three reasons:

1. The words match apartments. Readers coded the narrowed text marks commercial at a weighted
   0.004, and the held-out training rows with a text word score like all held-out ads (median
   gap -0.0035 against -0.0037).
2. The rows that do miss are already in the ledger. The marked held-out rows that the ledger
   now excludes miss high: median gaps of 1.03 (ratio), 0.63 (text) and 0.077 with 23.7% above
   the 95% point (short).
3. Commercial asks miss high, so they show at the top of the interval, away from the Deals
   page. Buildings with a confirmed commercial row hold no excess of low misses among their
   other held-out ads.

## What follows

- No pipeline rule. The best form, the ratio mark with a text word, reads 0.38 on half A and
  0.65 on half B.
- `candidate_rows.ndjson` holds 23 drafted excludes from the reads (22 `nonresidential`, 1
  `bedrooms_unknown` for C034, a building's inquiry line coded 0 bed), with `decided`,
  `source` and `when`. C033 is held back. 3 of the 23 are also among the 68 rows of
  `building-level-read-2026-11-20/candidate_rows.ndjson`. They are not imported: an import is
  a rule version that makes the served fit unservable until a refit, so it belongs with the
  next base refit.
- For more ledger rows, the yield is in the ratio mark: a hand read of the remaining
  167 ratio rows with a text word would find about half commercial, and the 767 ratio rows
  without one about one in seven.

## What was not verified

- The narrowed text marks were read on 40 rows over pools of 61,186; their interval runs to
  0.26, so a few hundred commercial rows among them cannot be ruled out.
- The 150 reads rest on one Sonnet reader per batch; my 15 checks found 2 borderline codes and
  no clear reversal.
- The low-miss excess in buildings with a ratio row and a text word was not traced to a cause,
  and no fit tested whether excluding those rows removes it.
- The Deals counts use an approximation of the page's default population (building training
  ads from `levels_live.parquet`); the page's own filter was not run.
- Ads with no ratio (no median for their cell, 314,052) carry only the text and short marks.
