# S15: income-restricted units against L1 (2026-11-14)

In an income-restricted unit a program sets the rent: a housing lottery, an AMI band, an HPD
or HDC unit, Mitchell-Lama, a 421-a affordable unit. L1 reads the old text flag
`income_restricted`, and the text-flag screen (`docs/notes/text-flags-2026-11-13.md`, #1378)
found it poor: its precision against readers was 0.907 and its recall 0.547. The rewrite,
`income_restricted_v2`, came out at 0.986 and 0.961. On L1's held-out ads of the latest
split, the 122 ads that only the new flag marks ask 0.107 ± 0.027 under L1's median.

In this screen I ask how much L1 would gain on its held-out ads by reading the new flag in
place of the old one. It runs against L1's saved fit, the pool
`drift-building-phase-b0-latest-9a7830fb-l1`, and the copy of its dataset with the new
column,
`/data1/apartments/frontier/datasets/b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc-closingraise-textflags`.
Nothing is fit, and nothing goes to Modal. The scripts are in
`docs/notes/income-flag-2026-11-14/` and write to `/data1/apartments/tmp/income-flag-2026-11-14/`.

## What I knew before writing the predictions

From the text-flag note, over the 1,896,471 rows of L1's dataset and its 189,647 held-out
ads:

| Flag | Rows | Held-out ads |
|---|---:|---:|
| old `income_restricted` | 1,703 | 207 |
| `income_restricted_v2` | 2,739 | 275 |
| both | 1,568 | 153 |
| old only | 135 | 54 |
| new only | 1,171 | 122 |

On the held-out ads, the gap of the log ask from L1's median, with SEs clustered by building:

| Ads marked by | Ads | Buildings | Mean gap (SE) |
|---|---:|---:|---|
| both | 153 | 103 | -0.020 (0.013) |
| old only | 54 | 2 | +0.006 (0.003) |
| new only | 122 | 67 | -0.107 (0.027) |
| neither | 189,318 | 36,172 | -0.004 (0.0002) |

L1's coefficient for the old flag is -0.083 (-0.089 to -0.077) over the 272 kept draws, which
its predictions use. Nothing else in this note was computed when I wrote the predictions.

## The screen

`f1_screen.py` emulates L1 reading `income_restricted_v2` in place of `income_restricted` on
the held-out ads:

1. For each of L1's 272 kept draws, I take each held-out ad's location `pred_loc`, subtract
   that draw's coefficient for the old flag where the old flag is set, and add a shift δ
   where the new flag is set. The unit sd, the noise scale and nu stay as L1 drew them.
2. I rescore each ad's log predictive density on the 48-node grid for the Student-t's mixing
   scale, as `causal-screens-2026-11-13/common.Draws` does, and take its gain over L1's
   density on the same grid. An ad that neither flag marks gains 0.
3. δ runs over a grid from -0.30 to +0.05 in steps of 0.01. As S14 picked its multiplier, I
   split the buildings in two halves by the hash `common.heldout` uses, pick the δ with the
   largest total gain over the marked ads of one half, and score it on the other half. The
   gains of the two halves add up to the screen's gain.
4. The SE is clustered by building over all 189,647 held-out ads. I demean the per-ad gains
   (zeros included) over all of them, sum by building and take
   se = sqrt(G / (G - 1) × sum(t²)). For each part of the split I do the same with that
   part's gains and zeros elsewhere.

I split the gain by the ads only the new flag marks, only the old one marks, and both mark.
I also split the ads the new flag marks by their unit's training rows: all of them marked by
the new flag, some of them, or none.

The emulation moves only the held-out ads' locations. A refit would also re-estimate each
unit's and each building's level from their training rows, and those rows change flags too.
Where a unit's or building's training rows carry the same flags as its held-out ad, its level
in a refit would take back part of the change, so the emulation overstates the shift a refit
would make. That matters most for the 54 ads only the old flag marks. Their two buildings ask
close to L1's median, presumably because those buildings' levels make up for the old
coefficient, and the emulation raises their location by 0.083. So I also report the gain with
those ads left as L1 has them. The decision on a fit (part C) uses the full emulation's gain.

`f1_screen.py` also counts the rows and held-out ads each flag marks, with the units and
buildings they cover. A unit is L1's unit key: the building and the unit id, or the listing
when the unit id is missing.

For the mixed units I take each ad the new flag marks and ask whether its unit has an ad the
new flag leaves unmarked, among the unit's training rows for a held-out ad and among all the
unit's other rows for a training row. I give the share of such ads, the same share with an
unmarked ad that has a known description, and the share whose building has an unmarked ad.

To see what the mixed units look like, `f2_pairs.py` draws 10 held-out ads the new flag
marks whose unit has an unmarked training ad with a known description, and pairs each with
that unit's latest such ad. A Sonnet reader takes the 20 ads in pairs, with each ad's ask and
date, and classes each pair: both ads offer the apartment under a program, one under a program
and one at market rent, the two ads describe different apartments, or the text can't tell.

## Predictions, written before any of the above was computed

Each is for the emulation on L1's 189,647 held-out ads of the latest split.

1. δ comes out between -0.14 and -0.05 in each half (60%), and below 0 in both (90%). The
   ads both flags mark ask 0.020 under L1's median with L1's -0.083 in place, about 0.10
   under it without, and the ads only the new flag marks ask 0.107 under it. The heavy tail of
   L1's noise counts the far asks less than a mean does, which pulls δ toward 0.
2. The ads only the new flag marks gain +15 to +90 (60%), more than 0 (85%).
3. The ads both flags mark gain -10 to +15 (65%). Their net shift is δ + 0.083, close to 0.
4. The ads only the old flag marks lose: -90 to -25 (60%), less than 0 (90%). The emulation
   raises their location by 0.083 against a gap of +0.006, and with L1's noise near nu = 1.7
   and a scale near 0.04 that costs about 1 elpd an ad.
5. In all, the gain comes to -50 to +60 (60%), with an SE of 25 to 55 (60%). The two
   buildings of the old-only ads put most of the SE in two clusters. The gain over its SE
   exceeds 2 (15%), so I expect to record a miss and stop after part B.
6. With the old-only ads left as L1 has them, the gain comes to +10 to +100 (60%) and exceeds
   2 SE (55%).
7. Of the gain on the ads the new flag marks, more than half comes from those whose units
   have no training row the new flag marks (55%).
8. Counts. Training rows: 1,496 under the old flag and 2,464 under the new, from the counts
   above (95%, as a check). Each held-out ad is a different unit, so the held-out ads cover
   207 and 275 units. The training rows cover 850 to 1,300 units under the old flag and 1,400
   to 2,100 under the new (60% each), in 120 to 350 and 250 to 600 buildings (60% each). The
   held-out ads cover 103 to 105 buildings under the old flag (80%) and 135 to 168 under the
   new (65%).
9. Mixed units: 40% to 75% of the held-out ads the new flag marks have an unmarked training ad
   in their unit (60%), and 25% to 60% of the training rows it marks have an unmarked ad in
   theirs (60%). By building the shares are 85% to 99% for held-out ads (70%) and 80% to 98%
   for training rows (65%), since most program units are in buildings with market units.
10. Of the 10 pairs read, at least 5 are both under a program, with the unmarked ad's text
    silent on the program or phrasing it outside the pattern (55%), and at most 3 switch between
    a program and market rent (65%).
