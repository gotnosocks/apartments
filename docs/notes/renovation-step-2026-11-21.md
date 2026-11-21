# A renovation step dated from the unit's own ads, sized on stored predictions (no fit)

`docs/TODO.md` lists a renovation step: a column that turns on at the first ad of a unit
whose text says renovated or gut renovated after an earlier ad of the unit lacked the words,
and stays on for the unit's later ads. The outlier sprint found ads switching the words on
at +0.009 to +0.012 over the model, and ads dropping them at zero. The TODO predicted a
coefficient of +0.005 to +0.010 and an elpd gain under 40. This note sizes the step on
l2bt's stored held-out predictions, beside the queued base-refit terms, with the method of
`docs/notes/text-columns-2026-11-21.md`, to decide whether it belongs on the base refit's
list.

No fit is run and no money is spent. The script and log go in `renovation-step-2026-11-21/`.

## Method

`j3_renov.py` takes `j2_text.py` unchanged in its base and scoring: the 129,861 held-out ads
of l2bt from 2022 on, each predictive a Student-t on its median with the scale from its
quartiles, the scale multiplied by exp(a · x) and the centre moved by b · x, a and b fitted
on one half of the buildings and scored on the other, with building-clustered SE. The base
is j1's eight kept terms.

The words are the `renovated` and `gut` flags of the outlier sprint's quality scan
(`tmp/outlier-sprint/qual/flags.parquet`), read from the description of each listing's
latest record. A unit's ads are the rows of l2bt's dataset with its `unit_id`, training and
held-out alike, ordered by `price_at`. For a held-out ad only ads of the unit priced
strictly earlier count as earlier, and their text is all the mark reads; no mark reads an
ask. In `j3_renov.py` and `j4_rewrite.py` an earlier ad with no flags row (2,671 dataset rows
have none) counts as lacking the words; `j5_gap.py` requires a flags row for the earlier ad
in the switch, with the same results.

- step: some ad of the unit up to and including this one has the words, and an ad of the
  unit priced before that one lacks them
- switch: this ad has the words and the unit's latest earlier ad lacks them (the step's
  first ad)
- worded, no bare ad before: this ad has the words and no earlier ad of the unit lacks
  them, for comparison only (a unit level carries a lasting premium)

Each is added alone beside the base with a scale and a shift. The step is the candidate;
the switch and the comparison mark only help read it.

## Predictions, written before the script was run

1. Shares among the held-out ads from 2022 on: the step 3% to 10%, the switch 1% to 4%.
2. Shift of the step on each half +0.005 to +0.010, as the TODO says; scale 0.97 to 1.05.
3. The switch's shift within 0.004 of the step's on each half: once renovated, a unit's
   later ads sit as far over its level as the first.
4. The comparison mark's shift within ±0.004 on each half: the unit level already carries
   a lasting premium.
5. Gain of the step over the base under 40 and positive on both halves; under 2 SE, so the
   step goes on the base refit's list as optional at most.
6. The low tail: fewer than 1% of the base's low-tail ads leave it with the step added.

## Second check, predictions written after the first runs

The first runs (`j3_first.log`, then `j3_renov.log` with controls added after it) gave the
switch +117 (SE 18), mostly by a wider scale, and wording for a dishwasher turning on +74
(SE 15) with the same scale near 1.10. Much of the switch's gain may belong to any rewritten
description. `j4_rewrite.py` counts, for each held-out ad, how many of the scan's 31 text
flags differ from the unit's latest earlier ad (every held-out ad of the split has one), and
adds three marks together: 1 flag changed, 2 changed, 3 or more changed. Predictions:

1. The scale rises with the count; 3 or more changed needs 1.10 to 1.25 on each half.
2. The three count marks together gain more than the switch alone (over 117).
3. Beside the count marks, the renovation switch keeps a shift of +0.004 to +0.008 on each
   half, a scale within 0.97 to 1.04 and a gain under 40.

## Results

The base (j1's eight kept terms) gains +1,807 (SE 79). Every held-out ad from 2022 on has
an earlier ad of its unit in the dataset. Each mark alone over the base, cross-fitted, with
building-clustered SE (`j3_renov.log`; the controls below the line were added after the
first run, `j3_first.log`):

| mark | share of ads | gain over the base | by half (A, B) | scale (fit on A / B) | shift (fit on A / B) |
|---|---|---|---|---|---|
| step | 23.2% | +48.0 (11.6) | +17.3, +30.7 | 1.028 / 1.035 | +0.0028 / +0.0035 |
| switch | 7.9% | +116.7 (18.5) | +47.3, +69.4 | 1.081 / 1.098 | +0.0073 / +0.0079 |
| worded, no bare ad before | 18.6% | +18.2 (8.1) | +11.2, +6.9 | 0.967 / 0.966 | −0.0023 / −0.0009 |
| words dropped | 11.0% | +9.0 (5.4) | +3.4, +5.7 | 1.033 / 1.033 | −0.0003 / −0.0017 |
| dishwasher wording on | 7.1% | +73.8 (14.9) | +32.3, +41.5 | 1.092 / 1.107 | +0.0046 / +0.0048 |
| high ceilings on | 6.3% | +14.1 (6.9) | +4.8, +9.3 | 1.051 / 1.050 | +0.0011 / +0.0031 |
| view on | 4.0% | +10.5 (7.5) | +10.1, +0.4 | 1.102 / 1.048 | +0.0001 / +0.0020 |
| no fee on | 4.6% | −2.5 (7.7) | +5.1, −7.5 | 1.063 / 0.986 | +0.0054 / +0.0031 |
| exposed brick on | 1.9% | −14.7 (3.6) | −5.8, −8.9 | 1.079 / 0.964 | +0.0011 / +0.0015 |

The renovation words flicker: 23% of ads carry the step and 11% drop the words. A step that
stays on adds little shift (+0.003). The switch ad itself is +0.0075 over the model with a
scale near 1.09, but a dishwasher turning on in the wording carries the same wider scale.

The second check (`j4_rewrite.log`) counts the scan's 31 text flags that differ from the
unit's latest earlier ad. 37% of ads change none, 18% one, 13% two and 31% three or more.

| added beside the base | gain | by half (A, B) | scale (fit on A / B) | shift (fit on A / B) |
|---|---|---|---|---|
| three count marks | +253.6 (27.5) over the base | +132.3, +121.3 | | |
| … 1 flag changed | | | 1.021 / 1.019 | +0.0003 / −0.0005 |
| … 2 changed | | | 1.053 / 1.058 | +0.0005 / +0.0009 |
| … 3+ changed | | | 1.135 / 1.123 | +0.0025 / +0.0023 |
| switch, beside the counts | +53.6 (12.3) over the counts | +20.4, +33.2 | 1.023 / 1.045 | +0.0065 / +0.0073 |
| switch and dishwasher on | +67.2 (13.8) over the counts | +25.4, +41.8 | | |

- An ad whose description changed in three or more flags since the unit's last ad is about
  13% harder to price, and the scale rises in steps with the count. The gain is 9 SE and
  even by half.
- Short or blank texts do not drive it: in 17.4% of the 3+ group this ad's or the last ad's
  text is under 200 characters, against 12.4% of ads with no change. Its texts more often
  halve or double in length (41.5% against 7.4%), as a rewrite would (`j5_gap.log`).
- Beside the counts the renovation switch keeps its shift (+0.007) and loses most of its
  extra scale. A dishwasher turning on keeps +0.003.

## The low tail

Of 6,792 base low-tail ads, 17 leave with the step added. With the three count marks 321
leave and 377 join (about 5% each). Of those leaving, 307 have 3 or more flags changed
(2,322 to 2,015 below 5%); of those joining, 305 have none changed (2,317 to 2,622), since
the narrower scale there pushes their misses further out (`j5_gap.log`).

## Predictions scored

First check:

1. Shares: wrong. The step marks 23.2% (3% to 10% predicted), the switch 7.9% (1% to 4%).
2. Step: shift wrong (+0.0028 and +0.0035, under +0.005), scale right (1.028 and 1.035).
3. Switch within 0.004 of the step: wrong, just outside on both halves (0.0045 and 0.0044
   higher). The first worded ad is further over the model than later ones.
4. Comparison mark within ±0.004: right (−0.0023 and −0.0009).
5. Step gain: wrong. +48 is over 40 and over 2 SE (4.1); it is positive on both halves.
6. Low tail: right. 17 of 6,792 leave (0.25%).

Second check:

1. Scale rising with the count, 3+ at 1.10 to 1.25: right (1.135 and 1.123).
2. Count marks over 117: right (+254).
3. Switch beside the counts: shift right (+0.0065 and +0.0073), scale half right (1.023 in
   range, 1.045 just over 1.04), gain wrong (+54, over 40).

## What follows

The step as the TODO framed it does not go to the base refit: a lasting step carries
+0.003, and most of its gain is in the first worded ad. Two terms replace it on the base
refit's list. Both read only the text of this ad and the unit's ad before it:

- A scale term for the count of text flags changed since the unit's last ad (1, 2, 3 or
  more), +254 (SE 28) beside the base and +230 (SE 26) beside bins of the time since the
  unit's last ad (third check, below). It is the largest term found on stored predictions
  since j1's ten, and it moves about 5% of the low tail. The mark was built after the first
  run showed the switch's scale, so a fit should confirm it before Deals reads it.
- The renovation switch, a shift and scale on the ad whose text first says renovated after
  the unit's last ad did not, +54 (SE 12) beside the counts.

DOB alteration filings by BIN, which the TODO names as a dating source, stay untested.

## Third check, predictions written after review

Review found that the count of flags changed rises with the time since the unit's last ad
(median 573 days with none changed, 1,090 with 3 or more), so a staler last ad could give
the same wider scale. `j5_gap.py` adds five bins of days since the unit's last ad (under
180, 180 to 364, 1 to 2 years, 2 to 4 years, over 4 years; the first is the reference) as
scale and shift marks, then the count marks beside them. It also requires a flags row for
the earlier ad in the switch, logs the text-length check and counts low-tail moves by group.
Predictions:

1. The gap bins alone gain over the base, with a scale rising with the gap.
2. Beside the gap bins the count marks keep at least half their gain (over 127), and the
   scale for 3 or more changed stays at 1.08 or more on each half.
3. Beside the gap bins and the counts, the renovation switch keeps a shift of +0.004 to
   +0.008 on each half.

## Third check results

`j5_gap.log`. Gains are cross-fitted; scales and shifts are fitted on half A, then on B.

| marks | gain (SE) | by half | scale, 3+ changed | switch shift |
|---|---|---|---|---|
| gap bins over the base | +138.0 (21.7) | +77.5, +60.5 | | |
| count marks over the gap bins | +230.1 (26.4) | +115.3, +114.8 | 1.129 / 1.122 | |
| switch over the gap bins and counts | +54.5 (12.3) | +20.9, +33.5 | 1.124 / 1.112 | +0.0066 / +0.0074 |

- The gap bins narrow every ad more than 180 days after the unit's last ad (scales 0.88 to
  0.95, against ads within 180 days). The narrowing is about even from half a year to four
  years and eases after four.
- Beside the bins the counts keep 91% of their gain, and the scales for 1, 2 and 3 or more
  changed hardly move (1.023 / 1.024, 1.051 / 1.061, 1.129 / 1.122). The count of changed
  flags is not a stand-in for a stale last ad.
- The switch keeps its shift and gain beside both.

## Predictions scored (third check)

1. Gap bins gain, with a scale rising with the gap: half right. They gain +138 (6 SE), but
   the scale falls from under 180 days to 180 to 364 days and stays near flat after.
2. Counts keep over 127 and 3+ stays at 1.08 or more: right (+230; 1.129 and 1.122).
3. Switch shift +0.004 to +0.008 on each half: right (+0.0066 and +0.0074).

The gap bins are a candidate of their own for the base refit (+138, SE 22), built after
review, so a fit confirms them too. Their gain comes from ads relisted within half a year
of the unit's last ad (about 8% of ads), which need a scale about 12% wider than the rest.
