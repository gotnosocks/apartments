# What are the held-out ads whose counts changed? (2026-11-20, no fit)

The open item in `docs/TODO.md` asks for a read of the ads on pages whose previous ad has
another bedroom count. On history the group is known to be wide on both tails with no mean
shift (`docs/notes/history-scan-2026-11-18.md`): held-out ads of 2025 and 2026 whose
bedrooms or baths differ from a training ad of the same apartment are 6.9% below the model's
5% point and 6.5% above its 95% point, against 4.2% and 3.5% for the rest. Nobody had read
them. Are they a recount of the same rooms, a real alteration, another apartment under the
same unit key, a coding error, or nothing visible? And does one of these carry the tails?

No fit was run, nothing was fetched and nothing was published. The sample is drawn from the
historical held-out ads of the latest-split run (l2bt, 189,647 ads), following the owner's
rule to test on history. Scripts and logs are in `docs/notes/changed-counts-read-2026-11-20/`.

## Answer

- The changed-count ads are a mixture, and no reading carries the tails. Of 300 pairs read
  blind to rent, 30% are a recount of the same rooms, 12% another apartment, 12% a coding
  error, under 1% a real alteration, and 46% show nothing in the text. The shares in the
  low and high groups differ from the ordinary group's by at most 10 points, with standard
  errors of 4 to 7 points, and no difference has the same sign and size on both halves.
- What carries the tails is a mark from the coded counts and dates, with no text. Call a
  held-out ad fresh when the apartment's most recent training ad dated before it has other
  counts, and back when that ad already has its counts and the other counts are older. From
  2022 on, fresh ads (7.5% of held-out ads) are 10.5% and 11.6% below the 5% point by half
  and 9.7% and 10.0% above the 95% point. The scale factor they need is 1.35 and 1.40 (se
  0.02). Back ads are 5.9% and 5.8% low and 4.7% and 4.5% high with factors of 0.99 and
  0.98, close to the 5.0%, 3.6% and 0.92 of ads with unchanged counts.
- Most of the excess is in fresh ads whose counts are new to the unit: no earlier ad of the
  model unit has the held-out ad's bedrooms and baths. Those (2.9% of held-out ads) are
  13.6% and 14.1% low and 15.1% and 15.5% high, with factors of 1.68 and 1.71. Fresh ads
  whose counts the unit has had before are 8.7% and 9.9% low and 6.4% and 6.2% high, with
  factors of 1.15 and 1.19.
- The Deals backtest (range-j), whose model already has mean terms for changed counts,
  shows the same on few ads. Its 218 fresh ads need a factor of 1.45 (se 0.09) against 0.94
  for unchanged counts, and 1.56 (0.14) and 1.34 (0.11) by half. The 161 with counts new to
  the unit need 1.52 (se 0.13) and the 57 with counts the unit has had need 1.28 (se 0.14).
  The 177 back ads need 0.98.
- What follows is a candidate for the next base refit: a scale mark for an ad whose counts
  are new to the unit. The evidence is suggestive, since both halves were in view when the
  mark was chosen. The check owed is a market backtest at the next base refit, with the
  mark's form fixed beforehand. No unit-match rule, text mark or data change is proposed.

## Method

1. `build.py` rebuilds "counts changed" as in `history-scan-2026-11-18/baths.py`: the
   apartment is the unit id less its `~n` suffix within a building, and a held-out ad has
   changed counts when its bedrooms or baths differ from any training ad of the apartment.
   For each such ad it keeps the most recent training ad of other counts (the compared ad)
   and the most recent training ad of any counts (the previous ad), with coded counts, size,
   unit label, dates and text. 40,795 held-out ads have changed counts, 27,822 from 2022 on.
2. `stats.py` splits them by direction against the compared ad (bedrooms up, bedrooms down,
   baths only) and by fresh or back.
3. `sample.py` draws, from the ads of 2025 and 2026 with both texts, 100 below the 5%
   point, 100 above the 95% point and 100 between the 30% and 70% points, at most two per
   building (278 buildings), seed 20261120. Readers got the two ads' coded counts, size,
   label, first day and full text with dollar amounts masked. They got no rent, no gap and
   no group, and the pairs were shuffled over ten batches of 30.
4. Ten Sonnet readers coded each pair with one of five codes, whether the two texts
   describe one physical apartment, the counts each text states, and a quote
   (`reader_prompt.txt`). The codes are
   in `changed-counts-read-2026-11-20/codes.csv`. `join.py` joins them to the key.
5. `mark.py` codes fresh and back on every changed-count held-out ad of l2bt and on the
   Deals backtest, taking the apartment's most recent training ad of any date. This is the
   first cut. The mark is binary, so no threshold was chosen on either half; both halves are
   shown. The halves are those of the history scan.
6. `prior.py` rebuilds the marks from training ads dated strictly before the held-out ad,
   `newseen.py` splits the fresh ads by whether the unit's earlier ads ever had the held-out
   counts and crosses the marks with other candidates, and `factor.py` gives the scale
   factor needed on the Deals backtest.

**Two unit keys.** The l2bt scripts (`build.py`, `stats.py`, `mark.py`, `prior.py`) call two
ads the same apartment when their unit ids agree after the `~n` suffix is stripped, within a
building. The backtest parts (`mark.py`, `factor.py`) use the model unit, the full unit id.
The split by counts new to the unit uses the model unit in both.

**The scale factor needed, m.** Each held-out ad has a place in the model's predictive
distribution, a value between 0 and 1. The scripts turn it into a Student t value with 4
degrees of freedom, u. For a group of ads, m is the multiplier that maximises the
likelihood of u / m as Student t with 4 degrees of freedom. A value of 1 says the model's
width fits the group, and 1.4 says the group needs a scale 1.4 times as wide. Its standard
error comes from 200 resamples of buildings. Ads with unchanged counts give 0.92 on l2bt
and 0.94 on the backtest, so the factor a mark would carry is the ratio to that base.

## Changed counts by direction, 2025 and 2026

Gap is the log ask less the model's median. Low and high are the shares below the 5% point
and above the 95% point. Pairs of values are half A and half B (`logs/stats.log`).

| ads | n | mean gap | low | high |
|---|---|---|---|---|
| counts as before | 27,182, 29,084 | -0.003, -0.004 | 4.1%, 4.2% | 3.5%, 3.4% |
| counts changed | 7,697, 7,508 | -0.003, -0.002 | 6.8%, 7.1% | 6.6%, 6.3% |
| bedrooms up | 3,278, 3,160 | -0.009, -0.009 | 7.1%, 7.2% | 4.2%, 4.7% |
| bedrooms down | 3,076, 2,921 | +0.005, +0.007 | 5.2%, 4.8% | 7.9%, 6.6% |
| baths only | 1,343, 1,427 | -0.004, -0.005 | 9.7%, 11.4% | 9.6%, 9.0% |

A unit listed with more bedrooms than before asks a little less than the model expects, and
one listed with fewer asks a little more, as the layout terms of the served Deals model
already encode. Ads whose baths alone changed are the widest.

The compared ad is far back: the median gap to it is 1,236 to 1,613 days by direction, and
the median gap to the previous ad is 458 to 708 days. The median change in log ask from the
compared ad is +0.36 for bedrooms up, +0.08 for bedrooms down and +0.17 for baths only (sd
0.24 to 0.29). The unit label differs between the two ads in 2.8% of pairs. Both ads state
a size in 1,359 of the 15,205 pairs, and the sizes are equal in half of those.

## The read

Codes by group, counts with the share of the group (`logs/join.log`):

| group | recount (a) | alteration (b) | other apartment (c) | coding error (d) | nothing (e) |
|---|---|---|---|---|---|
| low, 100 | 23 (23%) | 1 (1%) | 12 (12%) | 15 (15%) | 49 (49%) |
| high, 100 | 38 (38%) | 1 (1%) | 10 (10%) | 11 (11%) | 40 (40%) |
| ordinary, 100 | 28 (28%) | 0 | 15 (15%) | 10 (10%) | 47 (47%) |

By half of buildings:

| half, group | n | a | b | c | d | e |
|---|---|---|---|---|---|---|
| A, low | 48 | 10 (21%) | 1 | 7 (15%) | 7 (15%) | 23 (48%) |
| A, high | 57 | 25 (44%) | 1 | 7 (12%) | 6 (11%) | 18 (32%) |
| A, ordinary | 49 | 15 (31%) | 0 | 5 (10%) | 6 (12%) | 23 (47%) |
| B, low | 52 | 13 (25%) | 0 | 5 (10%) | 8 (15%) | 26 (50%) |
| B, high | 43 | 13 (30%) | 0 | 3 (7%) | 5 (12%) | 22 (51%) |
| B, ordinary | 51 | 13 (25%) | 0 | 10 (20%) | 4 (8%) | 24 (47%) |

Share of a tail group less the ordinary group's share, with the standard error of the
difference in brackets:

| | a | c | d | e |
|---|---|---|---|---|
| low, all | -0.05 (0.06) | -0.03 (0.05) | +0.05 (0.05) | +0.02 (0.07) |
| high, all | +0.10 (0.07) | -0.05 (0.05) | +0.01 (0.04) | -0.07 (0.07) |
| low, half A; B | -0.10 (0.09); 0.00 (0.09) | +0.04 (0.07); -0.10 (0.07) | +0.02 (0.07); +0.08 (0.06) | +0.01 (0.10); +0.03 (0.10) |
| high, half A; B | +0.13 (0.09); +0.05 (0.09) | +0.02 (0.06); -0.13 (0.07) | -0.02 (0.06); +0.04 (0.06) | -0.15 (0.09); +0.04 (0.10) |

- No code differs between a tail and the ordinary group on both halves. The largest
  candidate is a recount among the high ads (+10 points, se 7), which is +13 on half A and
  +5 on half B, each inside one and a half standard errors. With 100 ads a group the read
  can detect a difference of about 15 points and cannot rule out smaller ones.
- A recount among high ads agrees with the direction table: 22 of the 38 are bedrooms
  down, a former flex or converted room no longer counted while the ask holds.
- Real alterations are rare (2 of 300), so walls and combinations do not explain the group.
- Another apartment under the same unit key is 12% of pairs and is no more common in the
  tails (10% and 12% against 15%). The readers said the two texts describe different
  apartments in 10, 10 and 14 pairs of the three groups. The unit labels differ in 9 of the
  300 pairs and none of those was coded as another apartment, so the label is no mark of it.
- Coding errors, where an ad's own text states another count than its coded field, are
  12% of pairs, a little more common in both tails on half B (+8 and +4 points, se 6) and
  flat on half A.
- Nearly half the pairs show nothing: one text is a building template, a disclaimer or a
  few words.

The one trait of the sample that does separate the groups is a field. The previous ad has
other counts (fresh) in 54 of the low ads, 63 of the high ads and 32 of the ordinary ads.
Within the back pairs no code separates the tails. Within the fresh pairs one does, weakly:
the "other apartment" code is less common in the tails than among the ordinary fresh ads
(difference -0.23, se 0.09, for the high ads and -0.15, se 0.10, for the low ads, on 63, 54
and 32 pairs; `logs/join.log`). So a fresh ad in a tail is, if anything, more often the same
apartment, and the other codes stay within their errors.

**Spot check.** I read 15 of the coded pairs in full against both texts (`spot.py`, seed 7:
4 a, both b, 3 each of c, d and e). I agree with the reader on 12. The other 3 are
defensible and could take another code: a studio loft with a "queen-sized bedroom" coded as
one bedroom (a, could be d); an owner "converting the layout into a true 2-bedroom" from a
three-bedroom that the earlier ad already offered either way (b, could be a); and a top
floor text with two baths against a third floor text with one (c, could be d).

## The mark: is the change fresh?

### First cut: the most recent training ad of any date

The first cut calls a changed-count ad fresh when the apartment's most recent training ad,
of any date, has other counts. l2bt, held-out ads from 2022 on, half A and half B
(`logs/mark_l2.log`):

| ads | n | mean gap | gap sd | low | high |
|---|---|---|---|---|---|
| counts as before | 48,948, 53,091 | -0.006, -0.006 | 0.071, 0.071 | 4.9%, 5.0% | 3.6%, 3.4% |
| changed, back | 7,450, 7,311 | -0.005, -0.005 | 0.075, 0.077 | 5.9%, 5.7% | 4.6%, 4.4% |
| changed, fresh | 6,553, 6,508 | -0.003, -0.003 | 0.105, 0.109 | 9.6%, 10.6% | 9.0%, 9.3% |

The same by period, both halves together:

| ads | 2022 to 2024: n, low, high | 2025 and 2026: n, low, high |
|---|---|---|
| counts as before | 45,773, 5.9%, 3.5% | 56,266, 4.2%, 3.5% |
| changed, back | 5,489, 7.3%, 4.2% | 9,272, 4.9%, 4.6% |
| changed, fresh | 7,128, 10.1%, 9.0% | 5,933, 10.1%, 9.3% |

Fresh changes by direction, 2022 on, half A and half B:

| direction | n | mean gap | low | high |
|---|---|---|---|---|
| bedrooms up | 2,582, 2,543 | -0.019, -0.024 | 10.6%, 13.1% | 5.4%, 5.3% |
| bedrooms down | 2,564, 2,429 | +0.013, +0.018 | 6.9%, 5.6% | 11.1%, 11.4% |
| baths only | 1,407, 1,536 | -0.005, -0.003 | 12.8%, 14.5% | 11.8%, 12.6% |

- The gap sd of a fresh change is about 1.5 times that of unchanged counts on both halves
  (0.105 and 0.109 against 0.071). A back change is 1.06 to 1.09 times.
- The width does not fade with the time since the previous ad: the low and high shares are
  12.2% and 9.6% within a year and 11.0% and 12.1% after four years.
- In 4,424 of the 13,061 fresh ads the most recent training ad is dated after the held-out
  ad. Those are narrower (8.1% and 7.8%) and still about twice the base rate. The next
  section drops them from the mark.
- The model's bedroom text marks cover few fresh ads (678 with flex or fewer bedrooms in
  the text, 136 with more), and the 12,247 with neither are 9.4% and 10.5% low and 9.1% and
  9.2% high by half. So text wording does not replace the mark.

### Strictly earlier ads only

In the latest split a training ad of the apartment can be dated after the held-out ad. The
Deals page only has earlier ads when it prices an open ad, so a mark that looks at later ads
could not be coded there. The strictly-prior definition replaces the first cut: an ad is
fresh when the apartment's most recent training ad dated strictly before it has other
counts, back when that ad has its counts and an older one differs, and same otherwise. Every
held-out ad of l2bt from 2022 on has an earlier training ad of its unit. Half A and half B,
with m the scale factor needed (`prior.py`, `newseen.py`, `logs/newseen.log`):

| ads | n | low | high | m |
|---|---|---|---|---|
| same | 50,165, 54,309 | 5.0%, 5.0% | 3.6%, 3.5% | 0.92, 0.92 |
| back | 7,915, 7,775 | 5.9%, 5.8% | 4.7%, 4.5% | 0.99, 0.98 |
| fresh | 4,871, 4,826 | 10.5%, 11.6% | 9.7%, 10.0% | 1.35, 1.40 (se 0.02) |

- The strictly-prior fresh group is smaller than the first cut's (9,697 ads against 13,061)
  and a little wider. The 3,369 ads that leave it, fresh only by a later training ad, need
  factors of 1.14 (2,412 now same) and 1.15 (957 now back).
- On 2025 and 2026 alone the fresh factors are 1.34 and 1.35 (se 0.03) against 0.88 for
  same and 0.96 and 0.95 for back.

### Counts new to the unit

A strictly-prior fresh ad is one of two kinds. Either no earlier training ad of the model
unit has the held-out ad's bedrooms and baths (counts new to the unit), or an older ad of
the unit had them and the most recent one differs (counts seen before). Half A and half B
(`logs/newseen.log`):

| fresh ads | n | low | high | m |
|---|---|---|---|---|
| counts new to the unit | 1,857, 1,966 | 13.6%, 14.1% | 15.1%, 15.5% | 1.68, 1.71 (se 0.04) |
| counts seen before | 3,014, 2,860 | 8.7%, 9.9% | 6.4%, 6.2% | 1.15, 1.19 (se 0.02) |

The candidate is mostly "counts new to the unit". Those 3,823 ads are 39% of the fresh ads
and 2.9% of held-out ads from 2022 on, and they need a scale about 1.85 times the base
(1.70 against 0.92). The fresh ads with counts seen before need about 1.28 times the base,
which is above the back ads (0.99) and far below the first kind.

### Fresh is separate from the other candidates

All from `logs/newseen.log`, strictly-prior marks, 2022 on, low and high shares:

- **Thin same-bedroom history in the building.** In buildings with 20 or more training ads
  at the held-out ad's bedroom count, fresh ads are still 10.7% low and 9.5% high with a
  factor of 1.35, against 0.90 for same ads there. On the first cut's mark the same row
  is 9.5%, 8.8% and 1.28 against 0.89. With under 5 such ads the fresh factor is 1.54
  against 0.98, so thin building history adds to the mark and does not replace it.
- **Few ads of the unit.** The fresh factor is 1.33 with one training row of the model
  unit, 1.39 with two, 1.48 with three or four and 1.33 with five or more, against 0.88 to
  0.93 for same ads.
- **Three or more baths.** Under three baths fresh ads are 10.4% low and 10.0% high with a
  factor of 1.36 (9.6% and 9.3% on the first cut's mark). The 362 fresh ads with three or
  more baths are wider still (27.1% low, factor 1.82).
- **First ads.** Every fresh ad has unit history, so this is a different candidate from the
  first-ad one of `docs/notes/first-ad-noise-inputs-2026-11-20.md`, which concerns units
  with no earlier ad.

### Deals backtest

Range-j, 9,346 held-out ads. The backtest is a market split, so every training ad is dated
before the held-out ads and the first cut and the strictly-prior marks agree
(`logs/mark_bt.log`, `logs/factor.log`):

| ads | n | mean gap | gap sd | low | high | m (se) |
|---|---|---|---|---|---|---|
| counts as before | 5,783 | +0.003 | 0.075 | 4.2% | 4.2% | 0.94 (0.01) |
| changed, back | 177 | -0.006 | 0.090 | 4.5% | 3.4% | 0.98 (0.07) |
| changed, fresh | 218 | +0.014 | 0.140 | 10.6% | 11.5% | 1.45 (0.09) |
| fresh, counts new to the unit | 161 | | 0.151 | 11.2% | 12.4% | 1.52 (0.13) |
| fresh, counts seen before | 57 | | 0.101 | 8.8% | 8.8% | 1.28 (0.14) |
| no unit history | 3,168 | +0.023 | 0.134 | 4.7% | 9.4% | 1.09 (0.03) |

- The factor for fresh ads under the Deals model is 1.45 (se 0.09) against 0.94 for
  unchanged counts, a ratio of 1.5. By half it is 1.56 (0.14) and 1.34 (0.11), on 117 and
  101 ads.
- By half the fresh ads are 13.7% and 6.9% low and 11.1% and 11.9% high, so the high tail
  agrees and the low tail is too small to call on half B alone.
- The split by counts new to the unit has the same order as on l2bt with wide errors: 1.52
  (se 0.13) on 161 ads against 1.28 (se 0.14) on 57. By half the first is 1.72 (0.22) and
  1.32 (0.14) on 84 and 77 ads. The backtest cannot tell the two kinds apart.

## What follows

- **Model.** A unit listed with counts it has never had behaves like a unit the model knows
  less about. Its level was learned on another layout, and the mean terms for changed
  counts move the centre while leaving the width alone. The candidate for the next base
  refit is a scale mark for an ad whose counts are new to the unit, coded from the counts
  and dates of the unit's earlier ads (2.9% of held-out ads from 2022 on, 2.6% of the
  backtest's ads with unit history). The wider form, any fresh ad, is 7.5% and 3.5%.
- **Expected size.** The earlier draft of this note said "about 1.5". That number is the
  ratio of two factors, fresh against unchanged counts: 1.45 against 0.94 on the backtest
  and 1.37 against 0.92 on l2bt. For counts new to the unit the ratio is 1.6 on the
  backtest (1.52 against 0.94) and 1.85 on l2bt (1.70 against 0.92).
- **Standing of the evidence.** The mark is suggestive. Both halves were in view when it
  was chosen, and the split by counts new to the unit was added in review with both halves
  in view as well, so the halves are no independent test. The check owed is a market
  backtest at the next base refit, with the mark's form (counts new to the unit, from the
  model unit's strictly earlier ads) fixed beforehand and its prediction written first. No
  fit is proposed now.
- **Deals.** Until then, a deal on a unit listed with counts new to it is at least as
  uncertain as a deal on a unit with no history (factors of 1.52 and 1.09 on the backtest).
  The backtest counts are small (161 ads), so this is a caution to weigh when the next
  Deals change is planned.
- **Unit matching.** No rule is proposed. Other apartments under one unit key are 12% of
  changed-count pairs, no more common in the tails, and the unit label does not mark them.
- **Data.** The readers found a coding error in 12% of pairs. Ad text does not override a
  coded field, and these are no more common in the tails than the sample can show, so
  nothing changes in the pipeline.
- **The 307 live ads** of the TODO item were left unread, by the rule to test on history.
  The historical read answers the question the item asked.

## Caveats

- The read covers 300 pairs of 2025 and 2026. Differences of shares under about 15 points
  between a tail and the ordinary group are within its error.
- Nearly half the pairs had too little text to code. An old ad's text can be cut or
  stripped after it is delisted.
- One reader coded each pair. My check of 15 pairs agreed on 12 and found 3 borderline.
- In the first cut, "previous ad" is the apartment's most recent training ad by date, and
  in the latest split a training ad can be dated after the held-out ad (34% of the first
  cut's fresh ads from 2022 on). The strictly-prior tables remove this.
- The building's same-bedroom ad count in the cross-tab uses training ads of any date.
- The mark is suggestive. It was found with both halves in view, first as fresh or back and
  then, in review, as counts new to the unit. It is binary with no threshold fitted. The
  backtest is the only check on a second model, it is small, and it cannot separate the two
  kinds of fresh ad. The check owed is a market backtest at the next base refit with the
  mark's form fixed beforehand.
- The scale factor assumes a Student t shape with 4 degrees of freedom for every group. It
  compares groups under one shape and is no estimate of a fitted model's scale term.
- The latest-split model has no mean terms for changed counts. The backtest's model has
  them, and the width remains there.

## A Deals caution was built and dropped

A Deals caution for ads whose bedroom and bath counts are new to the unit was built in
PR #1492 and dropped (closed, commits kept under the tag `archive/pr-1492`). The check is
`caution_overlap.py` with its log, rerun on the Deals backtest (run range-j) from the code
on master. Below, "another caution" means any code the page already sets.

| Group | Ads | Below the 5% point | Above the 95% point | Scale factor (se) |
|---|---|---|---|---|
| Marked, no other caution | 47 | 0.0% (0 ads) | 14.9% (7 ads) | 1.24 (0.12) |
| Marked, another caution (mostly `rooms_up` and `beds`) | 114 | 15.8% | 11.4% | 1.65 (0.14) |
| Unmarked, cautioned | 1,596 | 7.5% | 6.0% | 1.09 (0.04) |
| Unmarked, uncautioned | 7,589 | 3.8% | 6.0% | 0.97 (0.01) |

By half the 47 are 26 ads with factor 1.15 (0.22) and 21 ads with 1.33 (0.17). On the live
table (run range-m3) the mark was on 108 of 6,502 ads, 84 of them already cautioned. It would
have moved 24 ads out of the uncautioned list, one of them among the first 300. These live
counts come from the review of #1492, since its staging table is not kept.

The wide low tail of counts-new-to-the-unit ads is entirely among ads the page already
cautions, so a caution adds nothing for a page that ranks low places. The scale term for the
base refit stays a candidate. The existing `rooms_up` and `beds` marks are the natural form
for it, since the width is where they are set.
