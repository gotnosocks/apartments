# S14: penthouses, garden apartments and townhouse floors against L1's spread (2026-11-13)

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 prices
duplex ads right on average and misses their spread. Their clipped squared gap from L1's
median is 0.0114 against 0.0059 for the other held-out ads, and L1's 80% interval covers 0.719
of them. A multiplier on L1's noise scale and unit sd for duplex ads, picked on half of the
buildings, came out at 1.3 and 1.4 and gained 255 ± 31 elpd, and the same search on other ads
picked 1.0. D1 (`docs/notes/duplex-factor-2026-11-13.md`) puts that factor into the model.

In this screen I ask whether three other unusual kinds of apartment scatter wider in the same
way: a penthouse, a garden apartment and a floor of a townhouse or brownstone. It runs against
L1's saved fit, the pool `drift-building-phase-b0-latest-9a7830fb-l1`, and its dataset
`b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise`. Nothing is fit, and nothing goes to
Modal. The scripts are in `docs/notes/unusual-units-2026-11-13/` and write to
`/data1/apartments/tmp/sprint-20261113/unusual-units/`.

## Predictions, written before the readers and the scatter step ran

I wrote these after `u1_text.py` had matched the patterns and drawn the samples, and before
any reader returned or `u2_scatter.py` ran. At that point I knew only the share of listings
each pattern marks: 1.9% for a penthouse, 3.7% for a garden apartment and 4.2% for a
townhouse floor. L1 already has a penthouse label and a garden or ground label among its unit
columns, so it can price these kinds on average; the predictions are mostly about spread.

1. Precision against the readers is at least 0.85 for the penthouse pattern (70%), at least
   0.75 for the garden pattern (60%) and at least 0.75 for the townhouse pattern (55%).
2. Recall from the unmatched reads comes out over 0.6 for each pattern (50%), with an interval
   too wide to rule out 0.4 (80%).
3. Among held-out ads, S7's duplex pattern also marks 15% to 35% of the penthouse ads (65%),
   10% to 30% of the garden ads (60%) and 5% to 20% of the townhouse ads (60%). The townhouse
   pattern marks 15% to 40% of the garden ads (55%).
4. Each kind is within 1% of L1's median within building (75%), since L1 has the penthouse
   and garden labels among its columns and its unit level carries a unit's earlier asks.
5. Penthouse ads have a clipped squared gap 1.3 to 2.0 times that of the rest (65%), and L1's
   80% interval covers them 0.03 to 0.08 less often than the rest (60%). The multiplier comes
   out at 1.2 to 1.4 in both halves (55%), and its gain exceeds 2 SE (75%).
6. Garden ads have a squared gap 1.2 to 1.7 times that of the rest (60%), m of 1.1 to 1.3
   (60%), and a gain over 2 SE (65%).
7. Townhouse ads have a squared gap 1.1 to 1.5 times that of the rest (60%), m of 1.1 to 1.2
   (55%), and a gain over 2 SE (60%). Part of it comes from small buildings, whose ads scatter
   more in general: in S7's part C other ads in lots of 1 to 5 units had a squared gap of about
   0.008 against about 0.005 in lots of 100 or more.
8. Without the duplex ads, each kind keeps at least half of its excess squared gap over the
   rest (60%).
9. The null search on as many unmarked ads picks 1.0 in both halves and gains under 5 elpd for
   every kind (90%).
10. Adding a kind's ads to D1's duplex mark, with one multiplier for both, gains more than 2 SE
    over the duplex mark alone for the penthouse (60%), the garden apartment (50%) and the
    townhouse floor (45%), and under 150 elpd for each (80%).

## How I marked the ads

`u1_text.py` reads each listing's last description from the record table S7 used
(`outlier-sprint/s2/R/recs.parquet`), and the unit label from the ad's address through
`rentfrontier.unit_features.unit_label`. The records carry no title, so the patterns match the
description alone. For each kind the script counts the matches of a positive pattern and of an
exclusion pattern, and it marks a listing when the positive matches outnumber the exclusions or
when the unit label matches. Each exclusion covers a positive match, so it cancels only that
match. With counts, an ad that calls the unit a penthouse and also mentions a penthouse lounge
keeps its mark.

- Penthouse: the word penthouse. The exclusions are the plural, "at the penthouse level", and
  penthouse followed by an amenity or a style word (lounge, gym, roof deck, finishes,
  "penthouse-like", "penthouse residences"). The label matches when it starts with PH or
  contains PENT, as L1's `unit:penthouse` column does.
- Garden apartment: garden followed by level, floor, apartment, unit, duplex or a similar
  word, or a private, own or exclusive garden, backyard or rear yard. The exclusions are
  garden-apartment complexes, place names such as Carroll Gardens or Kew Gardens followed by
  those words, and a private garden or yard described as shared with or open to the
  residents. The label matches GARDEN and its abbreviations.
- Townhouse floor: parlor floor, floor-through, an apartment in or of a townhouse, brownstone
  or row house, and townhouse or brownstone followed by apartment, unit, floor or a similar
  word. The exclusions are a brownstone-lined street, block or neighborhood, and "the charm of
  a brownstone". The label matches PARLOR.

Among the 1,790,425 listings of L1's dataset with a description over 80 characters, the marks
cover 1.95% for a penthouse, 3.67% for a garden apartment and 4.16% for a townhouse floor. The
penthouse mark comes in about equal parts from the label (1.22%) and the text (1.34%). The
garden and townhouse marks come almost entirely from the text, and the label adds 0.12% and
0.02% beyond it.

In the first run of `u1_text.py` two exclusions were too broad. `spa` had no word boundary, so
"penthouse space" and "penthouse spans" counted as amenities, and a shared garden anywhere in
an ad could cancel a "garden level" match elsewhere in it. After the readers had read their
draws I fixed both, and two smaller exclusions that could match outside a positive mention.
The fixes add 55 penthouse marks and 92 garden marks among all the listings the script reads,
14 and 76 among those above. None of the 500 read ads changes its mark, so the reads stand on
the first run's draws, and the counts below come from the second run.

## Precision and recall

Sonnet readers labeled 500 ads in 20 batches of 25, from the description and the unit label
alone, with the prompt kept as `READER_PROMPT` in `u1_text.py`. They were shown neither the
draw nor the marks. The draw held 100 matched ads of each kind, 50 unmatched ads of each kind
with weaker words, and 50 ads with no mark and no weaker word of any kind. The weaker words
are:

- for a penthouse, a top floor or PH, plus the ads whose only penthouse mentions were excluded;
- for a garden apartment, garden, backyard, rear yard, ground floor or lower level;
- for a townhouse floor, brownstone, townhouse, row house or walk-up.

`u3_readers.py` scores the labels. Recall follows S7's method: the found ads are the matched
count times the precision, and the missed ads come from each unmatched part at its read rate.

| Pattern | Precision (95%) | Text matches | Label only | Recall (95%) |
|---|---|---|---|---|
| Penthouse | 0.94 (0.88 to 0.97) | 58 of 64 | 36 of 36 | no miss found (0.34 to 0.99) |
| Garden apartment | 0.81 (0.72 to 0.87) | 78 of 97 | 3 of 3 | 0.74 (0.38 to 0.83) |
| Townhouse floor | 0.83 (0.74 to 0.89) | 83 of 100 | none drawn | 0.63 (0.37 to 0.71) |

The label-only penthouses pass by the prompt's own rule, which counts a PH label as a
penthouse unless the text contradicts it. The six false penthouse matches are an amenity the
exclusions let through ("the newly renovated penthouse Dermot Ignite Lounge"), another unit in
the building ("one lucky resident will live in the penthouse") and "nearly penthouse level".
Most of the 19 false garden matches describe a building's private garden for its residents or
a backyard behind an upper-floor unit. Most of the 17 false townhouse matches are
floor-throughs in elevator buildings and lofts, which the prompt counts out.

The readers found 5 garden apartments among the 50 weaker garden ads, each with a private yard
or patio described without the words of the pattern, and 10 townhouse floors among the 50
weaker townhouse ads, mostly phrased as "brownstone 1 bedroom" or "apartment in brownstone on
8th Avenue". They found none of any kind among the 50 ads with no weaker word. That part holds
1.3 million listings, so a rate of 1% there would add about 13,000 missed ads to the roughly
53,000 garden apartments and 62,000 townhouse floors the patterns find, and the recall
intervals stay wide.

## Counts and overlaps

L1's dataset has 1,896,471 rows and 189,647 held-out ads, each held-out ad from a different
unit.

| Mark | Rows | Share | Units | Held-out ads |
|---|---|---|---|---|
| Penthouse | 36,133 | 1.91% | 21,911 | 3,659 |
| Garden apartment | 66,196 | 3.49% | 44,502 | 6,648 |
| Townhouse floor | 74,645 | 3.94% | 48,622 | 7,982 |
| Duplex (S7) | 108,481 | 5.72% | 69,369 | 10,331 |
| Any of the first three | 165,078 | 8.70% | 105,574 | 17,006 |

Of the 3,659 held-out penthouse ads, 2,467 match by text and 1,192 by the label alone. On
held-out ads, S7's duplex pattern also marks 924 penthouse ads (25%), 1,936 garden ads (29%)
and 960 townhouse ads (12%). The townhouse pattern marks 1,105 of the garden ads (17%) and 146
of the penthouse ads, and the garden pattern marks 34 of the penthouse ads.

The table below puts each held-out ad once, under the set of marks it carries. The gap is the
log ask less L1's median, and the squared gap is clipped at 0.4 as in `s7b_spread.py`.

| Marks | Ads | Mean gap | Squared gap | 80% coverage |
|---|---|---|---|---|
| none | 165,682 | -0.0048 | 0.0057 | 0.803 |
| duplex | 6,959 | -0.0084 | 0.0096 | 0.732 |
| penthouse | 2,611 | 0.0028 | 0.0100 | 0.725 |
| penthouse, duplex | 870 | 0.0053 | 0.0140 | 0.685 |
| garden | 3,976 | -0.0016 | 0.0082 | 0.778 |
| garden, duplex | 1,535 | -0.0008 | 0.0131 | 0.698 |
| garden, townhouse | 709 | 0.0042 | 0.0112 | 0.762 |
| garden, townhouse, duplex | 394 | 0.0415 | 0.0210 | 0.670 |
| townhouse | 6,214 | -0.0032 | 0.0078 | 0.819 |
| townhouse, duplex | 519 | 0.0233 | 0.0172 | 0.699 |
| penthouse, townhouse | 97 | -0.0164 | 0.0105 | 0.773 |
| penthouse, townhouse, duplex | 47 | 0.0091 | 0.0249 | 0.660 |
| penthouse, garden | 25 | 0.0530 | 0.0148 | 0.680 |
| penthouse, garden, duplex | 7 | -0.0789 | 0.0202 | 0.714 |
| penthouse, garden, townhouse | 2 | 0.1666 | 0.0454 | 0.500 |

## Spread against the rest

`u2_scatter.py` compares each mark's held-out ads with the held-out ads it leaves out, with
SEs clustered by building. The rows without duplexes compare a kind's ads that S7's pattern
leaves unmarked with the other unmarked ads, and the duplex row without penthouses does the
same for the penthouse mark.

For the within-building columns I keep only the buildings with at least two held-out ads.
With n held-out ads in a building, an ad's gap less the building's mean has (n-1)/n of the
ad's variance about that mean, so I multiply its square by n/(n-1). Where a building's ads
have unequal variances, the rescaled square estimates their average, so with two ads it can
understate the wider one and the within-building excesses lean low. For the gap itself I
subtract the mean of the building's other held-out ads. My first run squared the demeaned gap
as `s7c_unitkey.py` does, which puts every ad alone in its building at zero. Among held-out
ads, 32.5% of the townhouse ads and 22.8% of the garden ads are alone in their building,
against about 6% of the others, so that run made both kinds look no wider than their
neighbors within building.

| Ads | n | Gap less rest | Same, within building | Squared gap, on and rest | Squared within building, on and rest | Difference within building | 80% coverage, on and rest |
|---|---|---|---|---|---|---|---|
| Penthouse | 3,659 | +0.0078 ± 0.0020 | +0.0098 ± 0.0021 | 0.0112, 0.0061 | 0.0103, 0.0055 | +0.0048 ± 0.0004 | 0.715, 0.799 |
| by text | 2,467 | +0.0139 ± 0.0026 | +0.0165 ± 0.0027 | 0.0125, 0.0061 | 0.0114, 0.0055 | +0.0059 ± 0.0006 | 0.704, 0.799 |
| by label only | 1,192 | -0.0049 ± 0.0028 | -0.0036 ± 0.0030 | 0.0085, 0.0061 | 0.0081, 0.0055 | +0.0026 ± 0.0006 | 0.739, 0.799 |
| without duplexes | 2,735 | +0.0073 ± 0.0022 | +0.0094 ± 0.0022 | 0.0101, 0.0059 | 0.0094, 0.0054 | +0.0040 ± 0.0005 | 0.726, 0.803 |
| by text, without duplexes | 1,702 | +0.0137 ± 0.0029 | +0.0169 ± 0.0029 | 0.0113, 0.0059 | 0.0104, 0.0054 | +0.0050 ± 0.0006 | 0.716, 0.803 |
| Garden | 6,648 | +0.0066 ± 0.0014 | +0.0072 ± 0.0016 | 0.0105, 0.0061 | 0.0083, 0.0056 | +0.0027 ± 0.0003 | 0.751, 0.799 |
| without duplexes | 4,712 | +0.0043 ± 0.0015 | +0.0065 ± 0.0017 | 0.0087, 0.0059 | 0.0073, 0.0054 | +0.0019 ± 0.0003 | 0.775, 0.802 |
| Townhouse | 7,982 | +0.0061 ± 0.0012 | +0.0071 ± 0.0012 | 0.0095, 0.0061 | 0.0080, 0.0056 | +0.0025 ± 0.0003 | 0.797, 0.797 |
| without duplexes | 7,022 | +0.0021 ± 0.0012 | +0.0051 ± 0.0013 | 0.0082, 0.0058 | 0.0072, 0.0054 | +0.0019 ± 0.0002 | 0.812, 0.801 |
| Duplex (S7) | 10,331 | +0.0019 ± 0.0012 | +0.0007 ± 0.0012 | 0.0114, 0.0059 | 0.0093, 0.0054 | +0.0039 ± 0.0002 | 0.719, 0.802 |
| without penthouses | 9,407 | +0.0013 ± 0.0013 | -0.0002 ± 0.0012 | 0.0110, 0.0059 | 0.0089, 0.0054 | +0.0036 ± 0.0002 | 0.722, 0.803 |

The duplex row repeats S7's squared gap and coverage, so these scripts agree with S7's. Every
kind scatters wider than the rest within its buildings. In the squared gap the excess is
+0.0048 for penthouses and +0.0039 for duplexes, and +0.0027 and +0.0025 for garden and
townhouse ads. Without the duplexes the garden and townhouse excess falls to +0.0019 each.

Coverage differs between the kinds. L1's 80% interval covers 0.715 of the penthouse ads
and 0.719 of the duplex ads, against about 0.80 for the rest, while it covers the townhouse
ads at the rest's rate and the garden ads without duplexes at 0.775. To find out why, I read
the width of L1's own 80% interval for each mark in `u4_width.py`, and the squared gap over the
squared width, ad by ad.

| Ads | Width, on and rest | Ratio | Squared gap over squared width, on and rest | Difference |
|---|---|---|---|---|
| Penthouse | 0.184, 0.173 | 1.06 | 0.279, 0.187 | +0.092 ± 0.010 |
| without duplexes | 0.179, 0.172 | 1.04 | 0.267, 0.184 | +0.084 ± 0.011 |
| by text, without duplexes | 0.184, 0.172 | 1.07 | 0.288, 0.184 | +0.105 ± 0.015 |
| Garden | 0.203, 0.172 | 1.18 | 0.229, 0.188 | +0.042 ± 0.006 |
| without duplexes | 0.196, 0.171 | 1.14 | 0.211, 0.184 | +0.026 ± 0.007 |
| Townhouse | 0.216, 0.171 | 1.26 | 0.185, 0.189 | -0.004 ± 0.004 |
| without duplexes | 0.212, 0.170 | 1.25 | 0.172, 0.186 | -0.014 ± 0.004 |
| Duplex (S7) | 0.199, 0.172 | 1.16 | 0.259, 0.185 | +0.074 ± 0.005 |
| without penthouses | 0.199, 0.172 | 1.16 | 0.254, 0.184 | +0.070 ± 0.005 |

L1 already gives a townhouse ad an interval a quarter wider than the rest's, and a garden ad
without a duplex mark one about a seventh wider. Measured against those intervals, the
townhouse ads scatter no more than the rest and the garden ads without duplexes 14% more. The
penthouse and duplex ads get intervals only 4% to 16% wider, and against them they scatter 38%
to 57% more than the rest. So garden and townhouse ads do scatter wider within their
buildings, and L1's intervals for them are already wider by about as much. A multiplier on
L1's noise for them has little left to correct.

The penthouse ads split by how they matched. L1 has the PH label among its columns, and the
label-only ads are close to its median. Ads that call the unit a penthouse in the text ask
1.7% more than L1's median within building, and they carry most of the extra spread.

## The multiplier on the noise scale and unit sd

As in `s7d_scale.py`, I multiply L1's noise scale and unit sd by m for the marked ads, pick m
on one half of the buildings, score it on the other half, and sum the gains in elpd over both
halves. The null runs the same search on as many held-out ads drawn from those with none of
the four marks.

| Ads | n | m by half | Gain ± SE | Null m by half | Null gain |
|---|---|---|---|---|---|
| Penthouse | 3,659 | 1.3, 1.4 | 104 ± 19 | 1.0, 1.0 | 0 |
| by text | 2,467 | 1.4, 1.4 | 100 ± 18 | | |
| by label only | 1,192 | 1.1, 1.3 | 8 ± 7 | | |
| without duplexes | 2,735 | 1.3, 1.3 | 64 ± 14 | 1.0, 1.0 | 0 |
| by text, without duplexes | 1,702 | 1.4, 1.4 | 56 ± 15 | | |
| Garden | 6,648 | 1.2, 1.2 | 66 ± 15 | 1.0, 1.0 | 0 |
| without duplexes | 4,712 | 1.1, 1.1 | 13 ± 6 | 1.0, 1.0 | 0 |
| Townhouse | 7,982 | 1.1, 1.0 | -3 ± 4 | 1.0, 1.0 | 0 |
| without duplexes | 7,022 | 1.0, 1.0 | 0 | 1.0, 1.0 | 0 |
| Any of the three, without duplexes | 13,634 | 1.1, 1.1 | 29 ± 9 | 1.0, 1.0 | 0 |
| Duplex (S7) | 10,331 | 1.3, 1.4 | 255 ± 31 | | |
| without penthouses | 9,407 | 1.3, 1.3 | 217 ± 25 | | |

On every null the total at m = 1.1 is already negative, from -14 to -59 elpd, so the search
picks 1.0 in both halves. The null draws take their size from the marks, so they differ from
those of the first run, whose totals ran from -7 to -62.

A shared mark in D1 would give the duplex ads and a kind's ads one multiplier. The last column
subtracts the gain of the duplex mark alone, ad by ad, with its SE clustered by building.

| Duplex ads together with | n | m by half | Gain ± SE | Over duplexes alone |
|---|---|---|---|---|
| Penthouse | 13,066 | 1.3, 1.4 | 314 ± 34 | +59 ± 16 |
| Penthouse, by text | 12,033 | 1.3, 1.4 | 311 ± 33 | +55 ± 13 |
| Garden | 15,043 | 1.3, 1.3 | 245 ± 33 | -11 ± 19 |
| Townhouse | 17,353 | 1.2, 1.2 | 165 ± 21 | -90 ± 16 |

Alone, the garden ads gain at m = 1.2, and most of that gain comes from the garden duplexes. At
the duplex multiplier the other garden ads lose what the garden duplexes add. The townhouse
ads lose at any m above 1.0, and a shared mark with them costs 90 elpd.

### An interval on m for the text penthouses and the duplexes

D1 gives every marked row a single factor, so the penthouses fit in D1's mark only if their
factor could be the duplexes'. I put an interval on m for the text penthouses without duplexes
(1,702 ads in 1,092 buildings) and for the duplexes without penthouses (9,407 ads in 5,533
buildings). `u2_scatter.py` resamples each mark's buildings with replacement 2,000 times. In
each resample it records the m with the largest total over all the resampled ads, and the m
each half of the resampled buildings picks. The profile lists the m whose total is within 2
SEs of the best, with the SE of each total's difference from the best clustered by building.

| Ads | Best m | 95% of resamples, all ads | 95% of resamples, by half | Within 2 SEs of the best |
|---|---|---|---|---|
| Penthouse, by text, without duplexes | 1.4 | 1.3 to 1.4 | 1.2 to 1.5 | 1.2 to 1.5 |
| Duplex, without penthouses | 1.3 | 1.3 to 1.4 | 1.3 to 1.4 | 1.3 to 1.4 |

The intervals overlap at 1.3 and 1.4. Over all the resampled ads the text penthouses pick 1.4
in 1,144 of the 2,000 resamples and 1.3 in 797, and the duplexes pick 1.3 in 1,836 and 1.4 in
164. On a grid with steps of 0.1 I cannot tell the two factors apart. One multiplier for the
duplex ads and the text penthouses together, picked by half, comes out at 1.3 and 1.4 and gains
311 ± 33 elpd, 55 ± 13 more than the duplex mark alone.

I chose the penthouse pattern, and the split into text and label matches, after reading their
numbers on L1's held-out ads. A fit scored on the same split would come out with an
optimistic gain for them.

## Predictions scored

1. Precision came out at 0.94, 0.81 and 0.83 against thresholds of 0.85, 0.75 and 0.75. All
   three held.
2. Recall came out with no miss found for penthouses, 0.74 for gardens and 0.63 for
   townhouses, each with a lower bound under 0.4. Both parts held.
3. The duplex pattern marks 25%, 29% and 12% of the penthouse, garden and townhouse ads, and
   the townhouse pattern 17% of the garden ads. All held.
4. Within building the gaps are +0.98%, +0.72% and +0.71%. Held, narrowly for the penthouses,
   and the penthouses matched by text are at +1.65%.
5. The penthouse squared gap is 1.83 times the rest's (held). Coverage falls by 0.083, just
   past the 0.03 to 0.08 range (missed). The multiplier came out 1.3 and 1.4 (held), and
   104 ± 19 is over 2 SE (held).
6. The garden ratio is 1.73, just past 1.7 (missed). The multiplier of 1.2 and the gain of
   66 ± 15 held.
7. The townhouse ratio is 1.57 (missed), the multiplier came out 1.1 and 1.0 (missed), and the
   gain is -3 ± 4 (missed). Within building the townhouse ads still scatter wider than the
   rest, 0.0080 against 0.0056, so their buildings explain only part of the excess, as I
   expected. L1's interval for them is a quarter wider than the rest's.
8. Without duplexes the kinds keep 82%, 65% and 69% of their excess squared gap. Held.
9. Every null picked 1.0 in both halves and gained 0. Held.
10. Added to the duplex mark, penthouses gain 59 ± 16 (held), gardens -11 ± 19 (missed) and
    townhouses -90 ± 16 (missed). All three are under 150 (held).

I expected the multiplier to help the townhouse floors as it helps the duplexes, and it does
not, since L1's intervals already cover them at the rest's rate. I also expected the garden
apartments to keep more of their gain once the duplexes were taken out.

## Conclusion

Penthouses scatter wider than L1 allows, as duplexes do, and L1's intervals already allow for
most of the wider scatter of garden apartments and townhouse floors. Within their own buildings the
penthouse ads exceed the rest's squared gap by 0.0048, against 0.0039 for duplexes. L1's 80%
interval covers 0.715 of them, the search picks the duplex multiplier for them on both halves,
and the null picks 1.0. The gain comes from ads that call the unit a penthouse in the text
(100 ± 18 alone), and the PH label alone adds 8 ± 7. For the text penthouses without
duplexes, the pick over all their ads falls between 1.3 and 1.4 in 95% of the building
resamples, the same range as the duplexes'. The picks within each half, and the picks within
2 SE of the best, range from 1.2 to 1.5. Either way the ranges overlap, so a single factor k
could cover both marks. Shared with the duplex mark, the text
penthouses add 55 ± 13 elpd and the whole penthouse mark 59 ± 16.

Garden and townhouse ads scatter wider within their buildings too, by about two thirds of the
duplex excess. L1's intervals for them are already 18% and 26% wider than the rest's, and
measured against those intervals the townhouse ads scatter no more than the rest. A multiplier
on L1's noise picks 1.0 for townhouses and 1.1 for gardens once the duplexes are out, and a
shared mark with the duplexes loses 11 and 90 elpd. Both should stay out of D1's mark.

D1 is written and waits for the sprint budget with its predictions committed. D2 would be D1's
model with the widened set made of the duplex ads and the text penthouses. It is a candidate
for the queue, and I do not propose a launch here. D2 needs a `penthouse` column built from
`u1_text.py`'s text pattern in a copy of L1's dataset, as `rentfrontier.b0duplex` built
`duplex`. With the costs from D1's note, D2 would run about $11.50 on three H100 containers,
with a sweep 2% to 6% slower than L1's and 50 to 60 minutes per container. In this screen the
text penthouses add 55 ± 13 elpd on L1's held-out ads beyond the duplex mark. I picked the
pattern on those ads, so D2's predictions should expect less on the latest split and say so.

I folded D2 into D1 before any launch (#1376). D1 now marks a row when its `duplex` or its
`penthouse` is true, and its note carries the revised predictions.

Left open:

- The text penthouses also ask 1.7% more than L1's median within building, so a text
  penthouse column in the mean, beside the PH label, may gain on its own. I did not score it.
- The recall intervals are wide, since a random draw of 50 ads cannot bound the rate among
  1.3 million listings.
- The grid of m steps by 0.1, so the intervals cannot separate two factors closer than that.
