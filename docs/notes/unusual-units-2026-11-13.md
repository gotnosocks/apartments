# S14: penthouses, garden apartments and townhouse floors against L1's spread (2026-11-13)

S7 of the causal screens (`docs/notes/causal-screens-2026-11-13.md`) found that L1 prices
duplex ads right on average and misses their spread. Their clipped squared gap from L1's
median is 0.0114 against 0.0059 for the other held-out ads, and L1's 80% interval covers 0.719
of them. A multiplier on L1's noise scale and unit sd for duplex ads, picked on half of the
buildings, came out at 1.3 and 1.4 and gained 255 ± 30 elpd, and the same search on other ads
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
when the unit label matches. With counts, an ad that calls the unit a penthouse and also
mentions a penthouse lounge keeps its mark.

- Penthouse: the word penthouse. The exclusions are the plural, "at the penthouse level", and
  penthouse followed by an amenity or a style word (lounge, gym, roof deck, finishes,
  "penthouse-like", "penthouse residences"). The label matches when it starts with PH or
  contains PENT, as L1's `unit:penthouse` column does.
- Garden apartment: garden followed by level, floor, apartment, unit, duplex or a similar
  word, or a private, own or exclusive garden, backyard or rear yard. The exclusions are
  garden-apartment complexes, place names such as Carroll Gardens or Kew Gardens followed by
  those words, and a garden or yard shared with or open to the residents. The label matches
  GARDEN and its abbreviations.
- Townhouse floor: parlor floor, floor-through, an apartment in or of a townhouse, brownstone
  or row house, and townhouse or brownstone followed by apartment, unit, floor or a similar
  word. The exclusions are a brownstone-lined street, block or neighborhood, and "the charm of
  a brownstone". The label matches PARLOR.

Among the 1,790,425 listings of L1's dataset with a description over 80 characters, the marks
cover 1.95% for a penthouse, 3.66% for a garden apartment and 4.16% for a townhouse floor. The
penthouse mark comes in about equal parts from the label (1.22%) and the text (1.34%). The
garden and townhouse marks come almost entirely from the text, with the label adding 0.43% and
0.07%.

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
1.3 million listings, so even a rate of 1% there would double the garden and townhouse
counts, and the recall intervals stay wide.

## Counts and overlaps

L1's dataset has 1,896,471 rows and 189,647 held-out ads, each held-out ad from a different
unit.

| Mark | Rows | Share | Units | Held-out ads |
|---|---|---|---|---|
| Penthouse | 36,119 | 1.90% | 21,900 | 3,657 |
| Garden apartment | 66,120 | 3.49% | 44,464 | 6,643 |
| Townhouse floor | 74,645 | 3.94% | 48,622 | 7,982 |
| Duplex (S7) | 108,481 | 5.72% | 69,369 | 10,331 |
| Any of the first three | 164,992 | 8.70% | 105,531 | 16,999 |

Of the 3,657 held-out penthouse ads, 2,463 match by text and 1,194 by the label alone. On
held-out ads, S7's duplex pattern also marks 923 penthouse ads (25%), 1,933 garden ads (29%)
and 960 townhouse ads (12%). The townhouse pattern marks 1,105 of the garden ads (17%) and 146
of the penthouse ads, and the garden pattern marks 34 of the penthouse ads.

The table below puts each held-out ad once, under the set of marks it carries. The gap is the
log ask less L1's median, and the squared gap is clipped at 0.4 as in `s7b_spread.py`.

| Marks | Ads | Mean gap | Squared gap | 80% coverage |
|---|---|---|---|---|
| none | 165,685 | -0.0048 | 0.0057 | 0.803 |
| duplex | 6,963 | -0.0084 | 0.0096 | 0.732 |
| penthouse | 2,610 | 0.0028 | 0.0100 | 0.725 |
| penthouse, duplex | 869 | 0.0053 | 0.0140 | 0.685 |
| garden | 3,974 | -0.0016 | 0.0083 | 0.778 |
| garden, duplex | 1,532 | -0.0009 | 0.0131 | 0.698 |
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
SEs clustered by building. For the within-building columns it first subtracts each building's
mean over its held-out ads, as `s7c_unitkey.py` does. The rows without duplexes compare a
kind's ads that S7's pattern leaves unmarked with the other unmarked ads.

| Ads | n | Gap less rest | Same, within building | Squared gap, on and rest | Squared, within building | 80% coverage, on and rest |
|---|---|---|---|---|---|---|
| Penthouse | 3,657 | +0.0078 ± 0.0020 | +0.0083 ± 0.0017 | 0.0112, 0.0061 | +0.0042 ± 0.0004 | 0.715, 0.799 |
| by text | 2,463 | +0.0138 ± 0.0026 | +0.0135 ± 0.0022 | 0.0125, 0.0061 | +0.0049 ± 0.0005 | 0.704, 0.799 |
| by label only | 1,194 | -0.0047 ± 0.0028 | -0.0025 ± 0.0025 | 0.0085, 0.0061 | +0.0026 ± 0.0005 | 0.739, 0.799 |
| without duplexes | 2,734 | +0.0073 ± 0.0022 | +0.0080 ± 0.0019 | 0.0101, 0.0059 | +0.0037 ± 0.0004 | 0.726, 0.803 |
| Garden | 6,643 | +0.0066 ± 0.0014 | +0.0044 ± 0.0009 | 0.0105, 0.0061 | +0.0003 ± 0.0002 | 0.751, 0.799 |
| without duplexes | 4,710 | +0.0043 ± 0.0015 | +0.0040 ± 0.0010 | 0.0088, 0.0059 | -0.0001 ± 0.0002 | 0.775, 0.802 |
| Townhouse | 7,982 | +0.0061 ± 0.0012 | +0.0033 ± 0.0006 | 0.0095, 0.0061 | -0.0009 ± 0.0001 | 0.797, 0.797 |
| without duplexes | 7,022 | +0.0021 ± 0.0012 | +0.0025 ± 0.0006 | 0.0082, 0.0058 | -0.0010 ± 0.0001 | 0.812, 0.801 |
| Duplex (S7) | 10,331 | +0.0019 ± 0.0012 | +0.0006 ± 0.0008 | 0.0114, 0.0059 | +0.0021 ± 0.0002 | 0.719, 0.802 |

The duplex row repeats S7's numbers, so these scripts agree with S7's. Penthouse ads scatter
wider within their own buildings, by about twice the duplex excess, and L1's interval covers
0.715 of them. Garden and townhouse ads scatter wider overall, and within their buildings they
scatter no more than the other ads there. Their excess comes from the buildings they are in,
where the ads tend to miss L1's median in the same direction, and L1's intervals already allow
for those buildings: townhouse ads are covered at the same rate as the rest.

The penthouse ads split by how they matched. L1 has the PH label among its columns, and the
label-only ads are close to its median. Ads that call the unit a penthouse in the text ask
1.4% more than L1's median within building, and they carry most of the extra spread.

## The multiplier on the noise scale and unit sd

As in `s7d_scale.py`, I multiply L1's noise scale and unit sd by m for the marked ads, pick m
on one half of the buildings, score it on the other half, and sum the gains in elpd over both
halves. The null runs the same search on as many held-out ads drawn from those with none of
the four marks.

| Ads | n | m by half | Gain ± SE | Null m by half | Null gain |
|---|---|---|---|---|---|
| Penthouse | 3,657 | 1.3, 1.4 | 104 ± 19 | 1.0, 1.0 | 0 |
| by text | 2,463 | 1.4, 1.4 | 100 ± 18 | | |
| by label only | 1,194 | 1.1, 1.3 | 8 ± 7 | | |
| without duplexes | 2,734 | 1.3, 1.3 | 65 ± 14 | 1.0, 1.0 | 0 |
| Garden | 6,643 | 1.2, 1.2 | 66 ± 15 | 1.0, 1.0 | 0 |
| without duplexes | 4,710 | 1.1, 1.1 | 13 ± 6 | 1.0, 1.0 | 0 |
| Townhouse | 7,982 | 1.1, 1.0 | -3 ± 4 | 1.0, 1.0 | 0 |
| without duplexes | 7,022 | 1.0, 1.0 | 0 | 1.0, 1.0 | 0 |
| Any of the three, without duplexes | 13,631 | 1.1, 1.1 | 29 ± 9 | 1.0, 1.0 | 0 |
| Duplex (S7) | 10,331 | 1.3, 1.4 | 255 ± 31 | | |

On every null the total at m = 1.1 is already negative, from -16 to -62 elpd, so the search
picks 1.0 in both halves.

A shared mark in D1 would give the duplex ads and a kind's ads one multiplier. The last column
subtracts the gain of the duplex mark alone, ad by ad, with its SE clustered by building.

| Duplex ads together with | n | m by half | Gain ± SE | Over duplexes alone |
|---|---|---|---|---|
| Penthouse | 13,065 | 1.3, 1.4 | 314 ± 34 | +59 ± 16 |
| Garden | 15,041 | 1.3, 1.3 | 245 ± 33 | -10 ± 19 |
| Townhouse | 17,353 | 1.2, 1.2 | 165 ± 21 | -90 ± 16 |

Alone, the garden ads gain at m = 1.2, and most of that gain comes from the garden duplexes. At
the duplex multiplier the other garden ads lose what the garden duplexes add. The townhouse
ads lose at any m above 1.0, and a shared mark with them costs 90 elpd.

## Predictions scored

1. Precision came out at 0.94, 0.81 and 0.83 against thresholds of 0.85, 0.75 and 0.75. All
   three held.
2. Recall came out with no miss found for penthouses, 0.74 for gardens and 0.63 for
   townhouses, each with a lower bound under 0.4. Both parts held.
3. The duplex pattern marks 25%, 29% and 12% of the penthouse, garden and townhouse ads, and
   the townhouse pattern 17% of the garden ads. All held.
4. Within building the gaps are +0.8%, +0.4% and +0.3%. Held, although the penthouses matched
   by text are at +1.35%.
5. The penthouse squared gap is 1.83 times the rest's (held). Coverage falls by 0.083, just
   past the 0.03 to 0.08 range (missed). The multiplier came out 1.3 and 1.4 (held), and
   104 ± 19 is over 2 SE (held).
6. The garden ratio is 1.73, just past 1.7 (missed). The multiplier of 1.2 and the gain of
   66 ± 15 held.
7. The townhouse ratio is 1.57 (missed), the multiplier came out 1.1 and 1.0 (missed), and the
   gain is -3 ± 4 (missed). I expected small buildings to account for part of the excess, and
   they account for all of it: within building the townhouse ads scatter less than the rest.
8. Without duplexes the kinds keep 82%, 65% and 69% of their excess squared gap. Held.
9. Every null picked 1.0 in both halves and gained 0. Held.
10. Added to the duplex mark, penthouses gain 59 ± 16 (held), gardens -10 ± 19 (missed) and
    townhouses -90 ± 16 (missed). All three are under 150 (held).

I expected the townhouse floors to widen like the duplexes, and they do not. I also expected
the garden apartments to keep more of their gain once the duplexes were taken out.

## Conclusion

Penthouses should join the duplexes in D1's widened noise. They scatter wider within their own
buildings, L1's 80% interval covers 0.715 of them, the search picks the duplex multiplier for
them on both halves, and a shared mark gains 59 ± 16 elpd over the duplexes alone, while the
null picks 1.0. The gain comes from ads that call the unit a penthouse in the text (100 ± 18
alone); the PH label alone adds 8 ± 7. Garden apartments and townhouse floors should stay out.
Their extra spread is the spread of the small buildings they are in, which L1 already allows
for, and a shared mark with them loses 10 and 90 elpd.

D1 is written and waits for the sprint budget with its predictions committed. Adding the
penthouses is a second change, so I would launch D1 as it stands and follow it with D2: D1's
model with the widened set made of the duplex and penthouse ads. D2 needs a `penthouse` column
built from `u1_text.py`'s pattern in a copy of L1's dataset, as `rentfrontier.b0duplex` built
`duplex`. With the costs from D1's note, D2 would run about $11.50 on three H100 containers,
with a sweep 2% to 6% slower than L1's and 50 to 60 minutes per container. In this screen the
penthouse ads add about 59 elpd on L1's held-out ads beyond the duplex mark.

Left open:

- The text penthouses also ask 1.4% more than L1's median within building, so a text
  penthouse column in the mean, beside the PH label, may gain on its own. I did not score it.
- The recall intervals are wide, since a random draw of 50 ads cannot bound the rate among
  1.3 million listings.
- The shared-mark search used the whole penthouse mark. A mark from the text alone would
  likely gain a little more and is the cleaner definition for D2.
