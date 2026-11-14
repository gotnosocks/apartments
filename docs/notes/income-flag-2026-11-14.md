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

## Results (2026-11-14)

I ran `f1_screen.py`, then `f2_pairs.py` and `f3_scale.py`, each under a 3 GB scope. Their
outputs are in `/data1/apartments/tmp/income-flag-2026-11-14/`. Since S15b the `-textflags`
copy holds `income_restricted_v2` with a negation guard, so a rerun of the three scripts
finds 265 marked held-out ads and 2,433 marked training rows where the numbers below have 275
and 2,464.

### The emulation

Each half of the buildings took the δ that did best on the other half's marked ads: -0.06 for
half 0 and -0.07 for half 1. Over all marked ads together the best δ is -0.06. Half 0's 205
marked ads lose 50.3 and half 1's 124 lose 13.8.

L1's coefficient for the old flag has a mean of -0.0834 over its 272 kept draws, with an sd of
0.0036 and a 90% interval from -0.0888 to -0.0775.

| Ads marked by | Ads | Buildings | Gain | SE | SE within the part |
|---|---:|---:|---:|---:|---:|
| either flag | 329 | 155 | -64.1 | 60.7 | 50.9 |
| both | 153 | 103 | -6.1 | 5.3 | 5.4 |
| old only | 54 | 2 | -55.9 | 59.0 | 8.2 |
| new only | 122 | 67 | -2.1 | 13.5 | 13.4 |
| the new flag (both and new only) | 275 | 153 | -8.2 | 14.3 | 14.1 |

The screen's gain is -64.1 ± 60.7, so gain/SE comes to -1.06. I record the screen as a miss
and stop after part B: I wrote no module, registration or predictions for part C.

Nearly all of the loss comes from a single building. 53 of the 54 old-only ads are in
505 W 37th St and lose 58.9 between them, while the other, in 143 Ludlow St, gains 3.0. In
505 W 37th St the old flag matches a fee schedule, where a monthly per-person fee is
"optional for income restricted units". It marks 108 of the building's 1,500 rows, all of them
from 2025 (48) or 2026 (60), and every row the building has from 2026. The new flag marks none
of them. For that building the old coefficient amounts to a drop of 0.083 on its recent ads,
which L1 places well (mean gap +0.006), and the emulation takes the drop away. A
refit without the old flag would let the building's path take the drop back, so I expect a fit
to lose far less on these ads than the emulation does. Since the part rests on one cluster, its
SE over all held-out ads (59.0) comes out about as large as its loss.

The ads the new flag marks gain -8.2 ± 14.3, and those are the ones a refit would keep:

- The ads both flags mark lose 6.1 ± 5.3. In sample they do best at δ = -0.09, gaining 0.4,
  so L1's -0.083 already suits them.
- The ads only the new flag marks lose 2.1 ± 13.5. In sample their best δ is -0.03, for a gain
  of 11.3. Their mean gap is -0.107, while their median gap is -0.039, and the quantiles run
  -0.33 (10%), -0.13 (25%), -0.039 (50%), +0.005 (75%) and +0.065 (90%). With 13% of them
  more than 0.3 under L1's median and most of the rest near it, a shift large enough to help the
  far ads costs more on the near ones under L1's heavy-tailed noise.

By the unit's training rows, for the ads the new flag marks:

| Unit's training rows the new flag marks | Ads | Buildings | Gain | SE | Mean gap |
|---|---:|---:|---:|---:|---:|
| all | 112 | 62 | -13.9 | 9.3 | -0.039 |
| some | 41 | 30 | +4.6 | 4.0 | -0.029 |
| none | 122 | 92 | +1.1 | 10.9 | -0.087 |

Every held-out ad's unit has training rows. Of the 112 ads whose unit's training rows all
carry the new flag, the old flag marks 60 as well. On those 60, L1's coefficient for the old
flag already carries the program's rent, and swapping it for δ loses 4.1. The other 52 have a
median gap of -0.024, so L1 places most of them well without the old flag's coefficient, and a
shift on top of that overshoots: they lose 9.9.
Where none of them do, the gaps are larger and too scattered for a common shift: the 49 new-only
ads in such units have a mean gap of -0.181 and gain 1.8 ± 10.5.

### Counts

| Ads marked by | Training rows | Units | Buildings | Held-out ads | Units | Buildings |
|---|---:|---:|---:|---:|---:|---:|
| old flag | 1,496 | 1,359 | 338 | 207 | 207 | 105 |
| new flag | 2,464 | 2,151 | 507 | 275 | 275 | 153 |
| both | 1,415 | 1,287 | 330 | 153 | 153 | 103 |
| old only | 81 | 72 | 8 | 54 | 54 | 2 |
| new only | 1,049 | 919 | 261 | 122 | 122 | 67 |

Over all rows the old flag marks 1,703 rows in 1,497 units and 356 buildings, and the new flag
2,739 rows in 2,273 units and 532 buildings.

### Mixed units

Of the 275 held-out ads the new flag marks, 59.3% have a training ad in their unit that the
flag leaves unmarked (58.9% counting only ads with a known description), and 96.4% have one in
their building. Of the 2,464 training rows it marks, 26.4% have an unmarked row in their unit
(26.2% with a known description), 43.1% have any other row there, and 91.0% have an unmarked
row in their building.

`f2_pairs.py` drew 10 of the held-out ads with an unmarked training ad of known description in
their unit, and a Sonnet reader took each pair without being told which ad the flag marks. The
later ad in each pair is the flagged one.

| Pair | Building | Earlier ad | Later ad | Reader's verdict |
|---:|---|---|---|---|
| 1 | 482 Franklin Ave | $1,997 (2016), silent | $2,090 (2021), program | program and silent |
| 2 | 807 Jefferson Ave | $2,199 (2019), silent | $2,000 (2021), program | program and silent |
| 3 | 797 Sterling Pl | $3,400 (2018), silent | $2,666 (2019), program | different apartments |
| 4 | 136 W 109th St | $1,950 (2020), silent | $3,671 (2024), program | program and silent |
| 5 | 100 Himrod St | $2,150 (2018), market | $2,124 (2025), program | switch |
| 6 | 495 St Johns Pl | $3,350 (2023), silent | $2,289 (2024), program | different apartments |
| 7 | 20 Jefferson St | $2,399 (2017), market | $2,387 (2019), program | switch |
| 8 | 207 E 105th St | $1,700 (2019), silent | $2,250 (2026), market | neither under a program |
| 9 | The Stanwix | $2,204 (2022), silent | $2,407 (2026), program | program and silent |
| 10 | 876 Bergen St | $2,115 (2019), market | $2,415 (2022), program | switch |

From the reader's notes:

- In pairs 1, 2, 4 and 9 the unmarked ad carries the building's usual description with no
  income terms. In pairs 1 and 2 the program ad repeats the earlier text and adds the income
  table, so both ads probably offer the unit under the program, and only the later one says so.
- In pairs 5, 7 and 10 the earlier ad reads as a market rental. Pair 5 quotes a net effective
  rent, pair 10 offers free months, and pair 7 takes 3 to 6 month leases, which the reader
  counted as the weakest cue. In pair 10 the program ad asks $2,415, the gross rent the earlier
  ad gave before its concession.
- In pairs 3 and 6 the unit key joins different apartments: a 3 bedroom and a 2 bedroom, and a
  duplex and a studio.
- In pair 8 the flagged ad describes a stabilized studio with no income restrictions. Both
  flags match that sentence, so `income_restricted_v2` needs a guard against the negation before
  a fit reads it.

### A wider spread for the new flag's ads (not in the predictions)

After the emulation I checked L1's coverage. Its 80% intervals cover 0.571 of the 275 held-out
ads the new flag marks (0.562 for both flags, 0.582 for new only), against 0.753 for 275
held-out ads neither flag marks, drawn at random with the seed 20261114. `f3_scale.py` then
multiplies L1's noise scale and unit sd for the marked ads by m, picks m on one half of the
buildings and scores it on the other, as S14 did.

Both halves picked m = 2.0, and the marked ads gain 63.5 ± 16.0 (3.96 SE, 15.9 within the
part). The ads both flags mark gain 33.1 ± 10.2, and those only the new flag marks gain
30.4 ± 10.6. Over all marked ads the total peaks at m = 2.0 (63.5) and 2.5 (63.4). The null
picks 1.1 and 1.2 and gains 1.4 ± 2.0.

I wrote no predictions for this search and chose its grid after the main result, so I treat it
as a lead for a later screen. A refit would widen the marked training rows' noise too, and their
units' levels would move with it. The change I would test next gives the rows the new flag
marks a factor on the noise scale, as D1 does for duplexes
(`docs/notes/duplex-factor-2026-11-13.md`), once the flag has the guard from pair 8. D1's k
multiplies the noise scale alone, while the m here multiplies the unit sd as well. That change
needs its own predictions before any fit.

### The predictions, scored

1. Hit. δ is -0.06 and -0.07, inside -0.14 to -0.05 and below 0 in both halves.
2. Miss. The new-only ads lose 2.1, outside +15 to +90 and below 0.
3. Hit. The ads both flags mark lose 6.1.
4. Hit. The old-only ads lose 55.9.
5. Miss. The total of -64.1 falls below -50 to +60, and its SE of 60.7 lies above 25 to 55.
   The gain did not exceed 2 SE, which I gave 15%.
6. Miss. With the old-only ads left as L1 has them, the gain is -8.2 ± 14.3.
7. Miss. The new flag's ads gain nothing to split. Those in units with no marked training row
   gain 1.1, and those in units whose training rows are all marked lose 13.9.
8. Mostly hit. The training rows (1,496 and 2,464), the held-out units (207 and 275) and all
   four building counts fall inside. The training units miss: 1,359 under the old flag against
   850 to 1,300, and 2,151 under the new against 1,400 to 2,100. I expected more repeated rows
   per unit.
9. Hit on all four shares: 59.3%, 26.4%, 96.4% and 91.0%.
10. Half right. The reader put 4 pairs under a program with the other ad silent, one short of
    5, and 3 as switches, within the limit of 3.

### Conclusion

S15 is a miss at -64.1 ± 60.7 (gain/SE -1.06), and part C did not run. Most of the loss comes
from 505 W 37th St, where the old flag marks a fee schedule on the building's recent ads.
Without that building, the ads the new flag marks still gain nothing from a shift
(-8.2 ± 14.3). L1's -0.083 suits the ads both flags mark, and the ads only the new flag marks
scatter too widely for a common shift to help. I would follow up on that scatter: m = 2.0 on
their noise scale and unit sd gains 63.5 ± 16.0, in a search I chose after the main result.

## S15b: AMI tier against L1's scatter on income-restricted ads (2026-11-14)

After S15's miss I searched for a wider spread on the ads `income_restricted_v2` marks and
found m = 2.0 on L1's noise scale and unit sd, for +63.5 ± 16.0. Both that hypothesis and the
one in this section came from a search after S15's miss. A program sets a unit's rent from its
income tier, so a 40% AMI unit and a 130% AMI unit in the same building can ask very different
rents. If the scatter comes from tiers, a level by tier should do as well as the wider spread.

### The screen

1. In `rentfrontier.b0textflags` I add a guard against a negation just before a match ("no
   income restrictions", "no income caps") to `income_restricted_v2`, and on the rows it marks
   I read from the description:
   - `ami_pct_text`, the AMI percentage the ad ties to its unit: the only one it states, or,
     when it states several, the one it ties to the unit or its price;
   - `ami_tiers_text`, how many different AMI percentages it states;
   - `income_min_text` and `income_max_text`, the household income band it states.

   All of them go into a single rebuild of the `-textflags` copy of L1's dataset.
2. A Sonnet reader checks the extracted tier on about 60 ads.
3. On L1's held-out ads of the latest split that the guarded flag marks, I put each ad in a
   bin by its tier. I fixed the bins before looking: 50 or less, 51 to 80, 81 to 100, 101 to
   130, above 130, several tiers with none tied to the unit, and none stated. Each bin gets
   a level added to L1's location in every draw, on a grid from -1.00 to +0.30. As S15 picked
   δ and m, each half of the buildings takes each bin's level from the other half's ads in
   that bin, and a bin with no ads in the other half gets 0. I score the gain against L1 as
   is, with SEs clustered by building over all held-out ads, by bin and in total.
4. On the same ads I rerun S15's spread search (m on the noise scale and unit sd), and then
   the spread search again with the tier levels in place.
5. I compare the mean squared gap from L1's median on these ads before and after the tier
   levels.

If the tier level does as well as the spread factor or better, I write a module with a level by
tier. Otherwise I write the spread factor's module.

### Predictions, written before any tier was extracted

L1's unit level already holds the rent of a unit whose training rows are at one tier, and in
S15 the ads whose unit's training rows all carry the flag asked only 0.039 under L1's median.
So I expect the tier to explain a part of the scatter, mostly on ads whose units have no
marked training row.

1. Of the held-out ads the guarded flag marks, 15% to 40% get an `ami_pct_text` (60%), and
   the same range holds for its training rows (60%). 20% to 50% state at least one percentage
   (60%), and 25% to 55% state an income band with a minimum or a maximum (60%).
2. Among held-out ads with a tier, the bin from 101 to 130 holds the most (55%), and the bin
   of 50 or less holds at most 10% of them (70%).
3. The reader finds the extracted tier right on at least 90% of the ads it checks (70%).
4. The tier level gains +3 to +30 (60%), clears 2 SE (30%), and gains at least as much as the
   spread factor on the same ads (10%).
5. On the guarded ads the spread search picks m = 2.0 or 2.5 in both halves (70%) and gains
   +45 to +75 (70%).
6. With the tier levels in place the spread search still picks m of 1.7 or more in both halves
   (75%), and the two together gain less than 15 over the spread factor alone (70%).
7. The tier levels narrow the mean squared gap of these ads by 3% to 20% (60%).
8. If at least 5 held-out ads state a tier of 80 or less and 5 state one above 130, the first
   group's mean gap is at least 0.2 below the second's (65%).

### Results (2026-11-14)

The guard and the four columns are in `rentfrontier.b0textflags`, and the rebuilt copy is
described in `docs/notes/text-flags-2026-11-13.md` (A negation guard and the program's terms).
The guard unmarks 10 held-out ads, so the guarded flag marks 265 held-out ads in 143
buildings, and L1's 80% interval covers 0.562 of them. `g1_counts.py` counts the tiers,
`g2_tier.py` runs steps 3 to 5, and `g3_noise.py` runs the spread search with m on the noise
alone. Their outputs are in `/data1/apartments/tmp/income-flag-2026-11-14/`.

Only 27 of the 265 ads state a tier, and all of them state a single one:

| bin | ads | half 0 | half 1 | mean gap | 80% coverage | levels picked (half 0, half 1) | gain |
|---|---|---|---|---|---|---|---|
| 50 or less | 0 | 0 | 0 | | | | |
| 51 to 80 | 0 | 0 | 0 | | | | |
| 81 to 100 | 4 | 1 | 3 | +0.001 | 0.75 | -0.02, +0.10 | -3.8 ± 2.4 |
| 101 to 130 | 17 | 9 | 8 | -0.053 | 0.71 | -0.02, -0.04 | +0.1 ± 1.6 |
| above 130 | 6 | 6 | 0 | +0.009 | 0.67 | 0, 0 | 0 |
| several, none tied | 0 | 0 | 0 | | | | |
| none stated | 238 | 131 | 107 | -0.067 | 0.55 | -0.02, -0.02 | +9.1 ± 5.9 |

The six ads above 130 are all in half 0, so each half scores them with a level of 0. The
tier levels gain +5.3 ± 6.8 in all, and the bin with no tier carries all of it: it is a
level for the flag's ads without a tier, and a fit reading v2 would have that level through
v2's coefficient. L1 has a coefficient for the old flag only. The bins with a tier together
gain -3.7.

On the same 265 ads the spread search picks m = 2.5 in both halves and gains +65.4 ± 20.2,
against +63.5 ± 16.0 on S15's 275 ads. The tier levels gain 60.0 ± 19.2 less than the spread.
With the tier levels in place the spread search picks m = 2.0 in both halves, and the two
together gain +70.7 ± 17.8, +5.3 ± 4.6 over the spread alone. The tier levels narrow the mean
squared gap from L1's median from 0.0459 to 0.0440, by 4.2%.

With m on L1's noise scale alone and the unit's sd as drawn, as D1's factor would act, the
search picks m = 3.5 in both halves and gains +62.4 ± 16.6, 96% of the spread's gain on
both. Every one of the 265 ads has a training row of its unit, and over L1's draws the unit
part's variance averages 0.0018 against 0.0005 for the noise's squared scale, so m on the
noise alone has to be larger to widen the predictive as much.

### The predictions, scored

1. Miss on every part. 10.2% of the held-out ads and 10.0% of the training rows get an
   `ami_pct_text`, 10.2% and 10.7% state a percentage, and 60.4% and 56.0% state an income
   band, just above the range.
2. Hit on both parts. 17 of the 27 held-out ads with a tier are in the bin from 101 to 130,
   and none are at 50 or less.
3. Hit. The reader found the tier right on all 68 ads it checked.
4. Partial. The total of +5.3 is in the range, but all of it comes from the bin with no tier
   (+9.1), and the bins with a tier lose 3.7 together. The total does not clear 2 SE (0.8 SE)
   and gains far less than the spread, as I expected at 30% and 10%.
5. Hit on both parts: m = 2.5 in both halves, +65.4.
6. Hit on both parts: m = 2.0 in both halves with the tier levels in place, and +5.3 over the
   spread alone.
7. Hit: the squared gap narrows by 4.2%.
8. Doesn't apply, since no held-out ad states a tier of 80 or less.

### Conclusion

The tier explains little of the scatter on these ads. Only 27 of the 265 state one, and L1
already places those well: their bins have 80% coverage from 0.67 to 0.75 and mean gaps from
-0.053 to +0.009. Most of the scatter is in the 238 ads with no tier, with coverage of 0.55
and a mean gap of -0.067. The wider spread does much better, so I wrote the spread factor's
module as D1's is built, with the factor on the noise of marked rows: I1, in
`docs/notes/income-noise-2026-11-14.md`. Both hypotheses came from a search after S15's miss, on the same held-out ads, so the
spread's +65.4 ± 20.2 and the noise's +62.4 ± 16.6 overstate what a fit would gain.
