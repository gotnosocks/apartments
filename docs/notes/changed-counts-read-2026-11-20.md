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
- What carries the tails is the timing of the change, which the coded counts and dates give
  without any text. When the apartment's most recent training ad has other counts than the
  held-out ad ("fresh", 47% of changed-count ads from 2022 on), 10.1% of the ads are below
  the 5% point and 9.2% above the 95% point. When the most recent training ad already has
  the held-out ad's counts and the other counts are older ("back"), the shares are 5.8% and
  4.5%, close to the 4.9% and 3.5% of ads with unchanged counts. Both halves of the
  buildings agree, and so do 2022 to 2024 and 2025 to 2026.
- Fresh changes hold about 310 to 380 ads over the base rate in each tail of each half.
  Back changes hold about 55 to 75.
- The Deals backtest (range-j), whose model already has mean terms for changed counts,
  shows the same on few ads: 218 fresh ads are 10.6% low and 11.5% high with a gap sd of
  0.140, against 4.2%, 4.2% and 0.075 for unchanged counts; 177 back ads are 4.5% and 3.4%.
- What follows is a scale mark for a fresh change of counts as a candidate for the next base
  refit. No unit-match rule and no text mark is proposed.

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
   Deals backtest. The mark is binary, so no threshold was chosen on either half; both
   halves are shown. The halves are those of the history scan.

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
Within the fresh pairs and within the back pairs the codes again do not separate the tails
(`logs/join.log`).

**Spot check.** I read 15 of the coded pairs in full against both texts (`spot.py`, seed 7:
4 a, both b, 3 each of c, d and e). I agree with the reader on 12. The other 3 are
defensible and could take another code: a studio loft with a "queen-sized bedroom" coded as
one bedroom (a, could be d); an owner "converting the layout into a true 2-bedroom" from a
three-bedroom that the earlier ad already offered either way (b, could be a); and a top
floor text with two baths against a third floor text with one (c, could be d).

## The mark: is the change fresh?

l2bt, held-out ads from 2022 on, half A and half B (`logs/mark_l2.log`):

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
  ad. Those are narrower (8.1% and 7.8%) and still about twice the base rate.
- The model's bedroom text marks cover few fresh ads (678 with flex or fewer bedrooms in
  the text, 136 with more), and the 12,247 with neither are 9.4% and 10.5% low and 9.1% and
  9.2% high by half. So text wording does not replace the mark.

Deals backtest, range-j, 9,346 held-out ads (`logs/mark_bt.log`):

| ads | n | mean gap | gap sd | low | high |
|---|---|---|---|---|---|
| counts as before | 5,783 | +0.003 | 0.075 | 4.2% | 4.2% |
| changed, back | 177 | -0.006 | 0.090 | 4.5% | 3.4% |
| changed, fresh | 218 | +0.014 | 0.140 | 10.6% | 11.5% |
| no unit history | 3,168 | +0.023 | 0.134 | 4.7% | 9.4% |

By half the fresh ads are 13.7% and 6.9% low and 11.1% and 11.9% high on 117 and 101 ads,
so the high tail agrees and the low tail is too small to call on half B alone.

## What follows

- **Model.** A unit whose latest training ad has other counts than the ad being priced
  behaves like a unit the model knows less about. Its level was learned on another layout,
  and the mean terms for changed counts move the centre while leaving the width alone. The
  candidate for the next base refit is a scale mark for a fresh change of counts, coded from
  the counts and dates of earlier ads (about 10% of held-out ads from 2022 on, 3.5% of the
  backtest's ads with unit history). Its expected size is a scale of about 1.5. A fit is not
  proposed now; the mark goes on the list for the next base refit with its prediction
  written first.
- **Deals.** Until then, a deal on a unit with a fresh change of counts is as uncertain as a
  deal on a unit with no history. The backtest counts are small (218 ads), so this is a
  caution to weigh when the next Deals change is planned.
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
- "Previous ad" is the apartment's most recent training ad by date. In the latest split a
  training ad can be dated after the held-out ad (34% of fresh ads from 2022 on).
- The fresh mark was found by looking at both halves at once. It is binary and was chosen
  before the read, in the direction split of step 2, with no threshold fitted. The backtest
  is the only check on a second model, and it is small.
- The latest-split model has no mean terms for changed counts. The backtest's model has
  them, and the width remains there.
