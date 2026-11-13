# S12: the omitted causes behind S11's wrong signs (2026-11-13)

An amenity added to an apartment should essentially never lower its rent, so a negative
term in L1 means the model is missing a cause that travels with the code. S11
(`docs/notes/causal-screens-2026-11-13.md`) found two patterns:

- A. Negative own terms, five of them with a positive sum with the unit mean: among a
  unit's own ads, the one stating the code asks less, while a unit with the code asks more
  than one without. Hardwood's sum is negative too, so it comes up under B as well.
  Wood fireplace -0.98%, patio -0.33%, fireplace -0.31%, water views -0.27%, private outdoor
  space -0.14%, hardwood floors -0.12%.
- B. Negative sums: a unit with the code asks less than one without. Roof rights -2.04%,
  hardwood floors -0.66%, decorative fireplace -0.62%, city views -0.42%, balcony -0.33%,
  park views -0.27%, and the building's live-in super -0.53% on its own term.

In this note I look for the cause behind each, and for a fit candidate if one comes out. I
wrote each section's predictions before computing anything in it. Everything here runs on
thelio against L1's saved fit and the stored data, and nothing launches on Modal. The scripts
are in `docs/notes/amenity-signs-2026-11-13/`.

## Summary

All figures are percent of the ask. Part A's shares are against the fixed-effect estimate
for each unit (E3), which comes out negative for four of the six codes, and part B's against
the held-out regression with no added term. L1's terms in the tables are its posterior
medians, which differ from S11's figures above by up to 0.01.

| Code | Pattern | L1's term | Cause I found | Share it explains |
|---|---|---|---|---|
| Hardwood floors | A, own | -0.12 | Each later ad of a unit asks about 0.75% less against the market, and the code accrues over a unit's ads. I haven't run it inside L1 | All: E3's -1.14 becomes +0.18 to +0.25 |
| Wood fireplace | A, own | -0.98 | Within units the term is inside its noise, -0.50 ± 0.43 | The same drift takes 32% to 60% |
| Patio | A, own | -0.33 | None | The drift takes 11% to 13%, and -0.54 ± 0.12 is left in the first differences with every control |
| Fireplace | A, own | -0.31 | No estimate from the ads comes out negative. My hypothesis, untested, puts the sign on L1's design beside its other codes | Not tested |
| Water views | A, own | -0.27 | Within units the term is inside its noise, -0.14 ± 0.22 | Not separable from zero |
| Private outdoor space | A, own | -0.14 | As for fireplace | Not tested |
| Roof rights | B, sum | -2.03 | None. The code marks a shared roof deck or nothing in 21 of the 22 ads I had read | 31% within a building and lister |
| Hardwood floors | B, sum | -0.65 | None | 25% to 30% with the lister |
| Decorative fireplace | B, sum | -0.63 | On the held-out ads the sum is inside its noise, -0.22 ± 0.31 | Not separable from zero |
| City views | B, sum | -0.42 | Which buildings' ads state the code and which listers tick it | 99% within a building and lister |
| Balcony | B, sum | -0.34 | Which buildings' ads state the code | All within a building |
| Park views | B, sum | -0.27 | The held-out ads give +0.04 ± 0.19, and +0.76 ± 0.23 within buildings | All |
| Live-in super | B, own | -0.53 | None. Every control but the renovation words makes it more negative | None |

I found no fit candidate worth a place in the queue. A count of each unit's earlier ads should
put hardwood's own term right, but L1's held-out predictions already follow that drift, and
I expect -30 to +30 elpd against L1. A lister level loses 233 elpd on the held-out ads. The
photo pilot, the only direct test left for the negatives I couldn't name, waits for Ben.
`Fit candidates and cost` at the end gives the figures.

## Part A: the within-unit negatives

### Method

`a_within.py` takes each pair of consecutive training ads of a unit in L1's dataset with the
same bedrooms and full baths, and regresses the change in log ask from the earlier ad to the
later one on the change in each of the six codes. The market's move between the two ads goes
into a fixed effect for each quarter, entered as +1 at the later ad's quarter and -1 at the
earlier ad's, as a repeat-sales index does. I cluster the SEs by building.

The baseline, M0, also takes the changes in the ad columns L1 carries beside the codes:
features unstated, the FEED and OWNER source, log photos and a floor plan. So M0's coefficient
on a code's change stands in for L1's own term. Then I add controls one family at a time,
and all of them at once:

1. the channel: the pair's (earlier source, later source) as one of nine cells, in place of
   the source changes;
2. the lister: whether the lister's name changed between the two ads, where both carry one
   (`recs.parquet`'s `lister`, StreetEasy's source group label);
3. the earlier ad's ending, as S3 read it from the status history (deal, no longer
   available, delisted, paused, other or unknown);
4. the later ad's own price path: its count of cuts and raises and its days on the market,
   and the same for the earlier ad;
5. the form: a fixed effect for each (year, source) of each ad, entered as +1 for the later
   ad's and -1 for the earlier ad's, since the StreetEasy form and the codes' rates change
   over the years.

For each code I report M0's coefficient, the full model's, and the share of M0's negative
the full model removes, 1 - full / M0, with each family's share alone beside it. I also count
how often a code's switch on coincides with each control, and I run M0 on the pairs where
both ads state features, where a switch on cannot come from an ad that leaves the lists out.

A channel or lister switch after a failed rental would be a cause the phase and ending terms
of L2 hold only in part. If one carries the negatives, I check whether a lister-switch column
dated from earlier ads alone (the lister of the ad itself against its unit's previous ad,
both known when the ad opens) moves L1's held-out gap enough to be a fit of its own.

### Predictions (written before computing)

1. M0's coefficient on the switch is negative for at least 4 of the 6 codes (65%), and
   within a factor of 2 of L1's own term for at least 3 of them (55%).
2. On the pairs where both ads state features, the negatives shrink, and at least 2 of the 6
   lose their sign or their 90% interval below zero (55%). An ad that leaves the lists out
   and one that fills them in differ in more than the codes.
3. A code's switch on coincides with a change of source or lister in 25% to 55% of the
   switches (60%), against under 20% of the pairs without a switch (70%).
4. The price path removes the largest share of the six families: an ad with cuts was on the
   market longer, gets edited more and so states more codes, and its last ask is lower. It
   removes 25% to 60% of the mean negative over the six codes (50%).
5. The channel and the lister together remove a further 10% to 40% (50%).
6. The earlier ad's ending moves each coefficient by under 20% of M0's (60%): S3's endings
   move the next ask by about 1%, and only some of the switches follow them.
7. The form's (year, source) effects move each coefficient by under 20% (65%).
8. With every control, at least half of each negative goes away for 4 of the 6 codes (45%).
   Wood fireplace keeps a 90% interval below zero (55%), since a wood fireplace that comes
   and goes between ads of a unit more likely marks two apartments under one unit key than
   an edit.
9. A lister switch after a delisting or a pause asks 1% to 3% less than the same ending
   without a switch (45%). If it holds on L1's held-out gap, the column would be a fit worth
   50 to 200 elpd (40%).

### Follow-up: L1's own terms against the pairs

I wrote this section after the first run of `a_within.py` and before computing anything in
it. M0's coefficients come out positive for wood fireplace, fireplace, private outdoor space
and hardwood floors, so L1's own terms do not come back from the pairs of a unit's ads. L1
measures its own term differently from a first difference: it puts the ad's code beside the
code's mean over the ad itself and its unit's training ads priced earlier
(`building_zones_kitchen_sink.past_means`), and it holds the unit's level as a random effect
with a process over time. So `a2_device.py` asks which of these differences turns the sign.
On L1's training ads of units with a `unit_id`, with the market's move taken out by M0's
quarter effects, it runs:

1. E1, M0 on every consecutive pair of a unit's ads, with indicators for a change of bedrooms
   and of full baths in place of dropping those pairs;
2. E2, long differences: each ad against the first ad of its unit with the same bedrooms and
   full baths;
3. E3, a fixed effect for each unit with the ad's code alone, over all of a unit's ads;
4. E4, the same with the past mean beside the code, as L1 builds it;
5. E5, a fixed effect for each building in place of the unit's, with the code, the past mean
   and the bedroom and bath counts, which leaves the unit's level to the past mean as L1's
   random effect mostly does.

Predictions:

1. E1 moves each code's coefficient from M0's by under 0.2 points (60%).
2. E3 gives each code the same sign as M0 for at least 5 of the 6 (60%).
3. E4 or E5 gives a negative own term for at least 4 of the 6 (40%), which would place the
   negatives in the past-mean device rather than in the ads.
4. E2 comes out at least 0.3 points below M0 for hardwood floors and water views (35%), since
   those codes switch on far more often than off, and a unit's ask may drift down against
   the market over its ads.

I added these two after the first run of `a2_device.py`, before computing them. E3 makes
hardwood floors -1.14% and wood fireplace -0.50% where the first differences make them
positive, and a first difference and a fixed effect differ like this when each unit's ask
drifts against the market over its ads while the code accrues. So the script also runs E3
split by the unit's number of ads, and E6, which is E3 with a linear trend in time for each
unit:

5. In E3, hardwood's coefficient is more negative for units with 5 or more ads than for
   units with 2 (60%), and for units with 2 it comes within 0.3 points of E1's (80%, close to
   true by construction).
6. In E6, hardwood's and wood fireplace's coefficients come within 0.5 points of M0's (45%).
   That would name each unit's own drift against the market over its ads as the cause the
   codes stand in for.

E6 gave hardwood +0.13%, close to M0's. A trend for each unit holds two things at once: a
drift common to all units (an apartment ages while the market index follows the city's mix)
and a drift peculiar to each unit (a renovation in one, wear in another). These would make
different fit candidates, so before computing them I added two more estimates:

- E7, E3 with a single slope in years since the unit's first ad, common to every unit;
- E8, E7 with the ad's number among its unit's ads beside the years.

7. E7 puts hardwood within 0.5 points of M0's (35%), and its common slope is negative, from
   -0.3% to -1.5% a year (50%).
8. If E7 misses, E8 does no better (60%), and the drift peculiar to each unit carries the
   codes.

E8 put the drift on the ad's number: each later ad of a unit asks about 0.75% less against
the market, and the years since the unit's first ad carry almost nothing beside it. L1 has
no term for this. Its phases act only on the noise scale, and its unit process holds each
unit's level near its training ads and reverts toward zero over 6.5 years. So before a fit
candidate goes in the queue I check the drift on L1's held-out ads. `e_relist.py` counts, for
each ad of a unit with a `unit_id`, the unit's ads priced before it, which reads dates alone
and no prices. On the held-out ads it reads the mean gap by that count's cell (0, 1, 2, 3,
4 to 5, 6 to 9, 10 or more, and no unit), the gap's slope on the count, and the elpd of a
crossfitted shift by cell, scored on L1's draws as S3 scored the phases. Predictions,
written before computing:

9. L1's held-out gap falls with the count, by 0.15 to 0.6 points per earlier ad over the
   ads with 1 to 10 earlier ads (50%). A held-out ad should carry about half the per-ad
   drift across its unit's training ads, since the unit process centres on their mean.
10. The shift by count cell gains 100 to 600 elpd over a constant shift (45%), and keeps at
    least half of that over a shift by L1's phase (55%), which stands in for L2's phase
    levels.

### Results: first differences

`a_within.py` found 751,210 pairs of consecutive training ads in 315,157 units. Figures are
percent, with one SE clustered by building.

| Code | L1's own term | M0 | Both ads state features | Every control |
|---|---|---|---|---|
| Wood fireplace | -0.98 | +0.22 ± 0.39 | +0.31 ± 0.40 | +0.40 ± 0.37 |
| Patio | -0.33 | -0.71 ± 0.12 | -0.69 ± 0.13 | -0.54 ± 0.12 |
| Fireplace | -0.31 | +0.29 ± 0.10 | +0.30 ± 0.12 | +0.29 ± 0.09 |
| Water views | -0.27 | -0.08 ± 0.17 | +0.06 ± 0.19 | +0.01 ± 0.17 |
| Private outdoor space | -0.14 | +0.62 ± 0.08 | +0.70 ± 0.09 | +0.63 ± 0.07 |
| Hardwood floors | -0.12 | +0.18 ± 0.08 | +0.32 ± 0.11 | +0.17 ± 0.07 |

The first differences don't give back L1's own terms. Four of the six come out positive, and
only patio is clearly negative. The controls move each coefficient a little. The form's
(year, source) effects move the most, taking hardwood from +0.18 to +0.12 and wood fireplace
from +0.22 to +0.31, and the price path takes patio from -0.71 to -0.62.

A code switches on in the same pair as a change of source or lister in 58% to 71% of its
switches, against 34% of the pairs with no switch. The later ad has a price cut in 29% to
46% of the switches, against 33%, and the earlier ad ended in a delisting or a pause in 8%
to 17%, against 14%. Hardwood floors switches on 140,773 times and off 28,349 times. A new
lister asks 0.46% ± 0.05 more than the unit's previous ad, and after a delisting or a pause
that premium is 0.18 ± 0.10 points smaller. So a lister switch after a failed rental doesn't
carry the negatives, and a lister-switch column would not make a fit of its own.

Scores:

1. Missed. M0 is negative for 2 of the 6 codes, patio and water views.
2. Missed. On the pairs where both ads state features only water views loses its sign, and
   patio stays at -0.69.
3. Missed on both halves: 58% to 71% of the switches, against 34% of the pairs without one.
4. Missed. M0's mean over the six codes is positive, +0.09, so there is no mean negative to
   remove. Of the two negatives, the price path removes 12% of patio's and 48% of water
   views', and the form moves hardwood and wood fireplace more than the path.
5. Missed. The channel and the lister each move every coefficient by under 0.03 points,
   under 6% of patio's and water views' negatives.
6. Hit. The ending moves each coefficient by under 17% of M0's.
7. Missed. The form moves hardwood by 35%, wood fireplace by 40% and water views by 32%.
8. Missed on both halves. M0 has only 2 negatives, so at most 2 codes could lose half, and
   only water views does. Wood fireplace comes out +0.40 ± 0.37.
9. Missed. After a delisting or a pause, an ad with a new lister asks about 0.28% more than
   one with the same lister: a new lister adds 0.46% ± 0.05 after any ending, and 0.18% ±
   0.10 less of it after those two.

### Results: L1's device

`a2_device.py` read 1,706,824 training ads of 935,396 units. E4 and E5 give the code's own
term, beside the past mean.

| Code | M0 | E1 | E2 | E3 | E4 | E5 | E6 | E7 | E8 |
|---|---|---|---|---|---|---|---|---|---|
| Wood fireplace | +0.22 | +0.37 | -0.49 | -0.50 ± 0.43 | -0.15 | +0.56 | +0.60 | -0.20 | -0.34 |
| Patio | -0.71 | -0.73 | -0.61 | -0.80 ± 0.18 | -1.39 | -1.83 | -0.71 | -0.69 | -0.71 |
| Fireplace | +0.29 | +0.35 | +0.29 | +0.48 ± 0.12 | +0.34 | +0.32 | +0.17 | +0.30 | +0.30 |
| Water views | -0.08 | -0.06 | -0.44 | -0.14 ± 0.22 | +0.63 | +1.98 | +0.44 | -0.12 | -0.26 |
| Private outdoor space | +0.62 | +0.82 | +0.44 | +0.90 ± 0.11 | +1.02 | +1.48 | +0.69 | +0.77 | +0.83 |
| Hardwood floors | +0.18 | +0.20 | -0.28 | -1.14 ± 0.08 | -0.73 | -2.51 | +0.13 | +0.18 | +0.25 |

E7's common slope is -0.40% ± 0.02 a year. In E8 the ad's number takes -0.75% ± 0.03 an ad,
and the years fall to -0.07% ± 0.02. E3 split by the unit's count of ads gives hardwood
-0.19 ± 0.11 for units with 2 ads, -1.07 ± 0.09 for 3 or 4, and -1.49 ± 0.11 for 5 or more.

So a fixed effect for each unit turns hardwood negative where the first differences leave it
positive, the negative grows with the unit's ads, and a slope common to every unit removes
it. Each later ad of a unit asks about 0.75% less than the market index, and a code that
accrues over a unit's ads, as hardwood does, takes up that drift in any estimate that
compares an ad with its unit's mean. L1 compares each ad with its unit's level and with the
past mean of the code, so I expect its own term takes up the drift too, though I haven't run
the common slope inside L1. I haven't tested why later ads ask less. An apartment ages
between renovations, and the index follows the city's mix of ads, so either could do it.

Fireplace and private outdoor space come out positive in every estimate from the ads, E4 and
E5 included. I expect their negatives in L1 come from its design beside its other codes, but
I haven't tested that. The overlapping codes (wood and decorative fireplaces beside
fireplace; patio, balcony and terrace beside private outdoor space) would be the first thing
to check.

Scores:

1. Missed narrowly. E1 moves private outdoor space by 0.20 points and the rest by under 0.15.
2. Missed. E3 keeps M0's sign for 4 of the 6, and wood fireplace and hardwood turn negative.
3. Missed. E4 is negative for 3 (wood fireplace, patio, hardwood) and E5 for 2.
4. Hit. E2 is 0.46 points below M0 for hardwood and 0.36 for water views.
5. The first half hit (-1.49 for 5 or more ads against -0.19 for 2) and the second missed:
   -0.19 for units with 2 ads against E1's +0.20.
6. Hit. E6 gives hardwood +0.13 and wood fireplace +0.60, each within 0.5 of M0's.
7. Hit. E7 gives hardwood +0.18, and the slope is -0.40% a year.
8. Doesn't apply, since E7 hit. E8 puts the drift on the ad's number rather than the years.

### Results: the held-out check

Every one of L1's 189,647 held-out ads has at least one earlier ad of its unit.
`e_relist.py` gives:

| Earlier ads | Held-out ads | Mean gap | 80% coverage |
|---|---|---|---|
| 1 | 77,037 | -0.22 ± 0.04 | 0.788 |
| 2 | 44,568 | -0.55 ± 0.04 | 0.794 |
| 3 | 28,219 | -0.66 ± 0.05 | 0.797 |
| 4 to 5 | 27,598 | -0.58 ± 0.04 | 0.813 |
| 6 to 9 | 11,392 | -0.64 ± 0.06 | 0.830 |
| 10 or more | 833 | -0.36 ± 0.22 | 0.820 |

Over the ads with 1 to 10 earlier ads the gap falls 0.08 ± 0.01 points an earlier ad, and
the same within each phase. A constant shift gains 582 ± 37 elpd, as in S3, and the shift by
count cell 555 ± 41, so the count loses 28 ± 14 against the constant. By phase the shift
gains 863 ± 49, and by phase and count 836 ± 51, 27 ± 17 less.

9. Missed. The gap falls 0.08 points an earlier ad.
10. Missed. The count loses 28 ± 14 elpd against the constant shift.

So L1's predictions already follow the drift. A held-out ad's level comes mostly from its
unit's latest training ads, and the gap moves little with the count. The drift changes how
L1 splits a unit's asks between its codes and its level and leaves the held-out predictions
nearly as they are. Coverage rises from 0.79 to 0.83 with the count, so L1's intervals are a
little wide for units with many ads.

## Part B: the between-unit negatives

### Method

`b_between.py` works on L1's 189,647 held-out ads. For each code I add the code's own
contribution back into L1's gap,

    r_i = (y_i - median_i) + b_own x_i + b_umean m_i,

with x_i the ad's own value, m_i its unit mean as L1's design builds it, and b their
posterior medians. Regressing r on x and m with no other term gives back about L1's terms,
since L1 holds everything else. Then I add candidate causes and read how far the sum of the
two coefficients moves toward zero:

1. the building's era by zone, the six eras of S11 by Manhattan and the rest (L1 has the eras
   alone);
2. PLUTO's building class with both of its characters (L1 has only C, D and S);
3. the description's renovation wording: renovated, gut renovation, new or updated kitchen or
   bath, and the old-detail words (original, prewar or vintage details, moldings);
4. the count of other premium codes the ad states (dishwasher, washer and dryer, central air,
   doorman, elevator, gym, any private outdoor space, a view other than the city, any
   fireplace), and the code's interaction with that count, for hardwood floors and city
   views: "advertising what you have".

Live-in super is a building column with no unit mean, so its r takes its own term alone.

Then I read ads. I draw about 100 held-out ads that state one of these codes and that L1
over-predicts by more than its 80% interval (gap below the 10% bound), and 50 controls that
state the same codes with gaps inside the 50% interval, matched on the code, zone and
bedrooms. Sonnet subagents read each ad's description blind to its group and fill a fixed
checklist: finishes dated or unstated, renovation stated, a walk-up floor, light, layout or
size words, the block, and a free line naming what the apartment seems to lack for its
price. I compare the checklist's rates between the groups.

If finish quality comes out as the likeliest omitted cause, I run a photo pilot. I fetch the
photos of about 60 of the read ads through OxyLabs, and Sonnet subagents with vision rate the
kitchen and the bath each on a fixed four-point scale (1 dated or worn, 2 plain and older,
3 updated, 4 new or high end). Then I check whether the rating explains the gap and the sign.

### Predictions (written before computing)

1. With no added term, the regression gives back each sum within 30% (70%).
2. Era by zone removes over half of roof rights' -2.04% (55%) and under a third of each of
   the other codes' negatives (60%).
3. The full building class removes over half of live-in super's -0.53% (50%). The super
   marks mid-century elevator rentals, and the class's second character separates them.
4. The old-detail words come with hardwood floors and decorative fireplaces at least twice
   as often as with other ads (70%), and the renovation wording removes 20% to 60% of
   hardwood's and decorative fireplace's negative sums (45%).
5. Hardwood's and city views' terms are more negative by at least 0.3 points in ads stating
   at most one other premium code than in ads stating three or more (60%).
6. Together the added terms remove at least half of the negative sum for 3 of the 6 unit
   codes (45%).
7. In the read ads, dated or unstated finishes are the checklist item that differs most
   between the over-predicted ads and the controls (45%), ahead of a walk-up floor (25%) and
   size or layout (20%).
8. If the photo pilot runs, the mean of the kitchen and bath ratings correlates with the gap
   at 0.15 to 0.35 (50%), and a point of rating goes with 2% to 6% of the ask (50%).

I added a field to the readers' checklist when I wrote it, after the regressions and before
any reading came back: whether the text supports the code as the apartment's own feature
(private), as the building's (shared), only in part (a juliet balcony, a peek view, a
decorative mantel), or not at all. Seven codes went to the readers, live-in super among them,
at 15 over-predicted ads and 7 controls each, 154 ads in all. The added prediction:

9. The code is shared, partial or unmentioned in the text more often among the over-predicted
   ads than among the controls, by at least 10 points over all codes (45%), and by at least
   20 points for roof rights and balcony (35%).

None of the candidate causes above moved the sums, and the reading separated nothing. Part A
found that the codes come and go with the lister and the form, so before computing it I
added a last check. `f_lister.py` reruns the regression of r with a fixed effect for each
lister (StreetEasy's source group label on the ad's last record), for each building, and for
each building and lister together, by demeaning within each group:

10. The lister's fixed effect removes at least a third of the negative sums of roof rights,
    hardwood floors and city views (40%), since listers fill in the codes and carry different
    parts of the market.
11. The building's moves each sum by under 30% (50%), since L1 already holds the building's
    level.
12. The building and lister cell removes at least half of those three sums (35%).

The lister moved several sums, so I asked whether a lister term would predict L1's held-out
asks better, before computing it. `g_lister_gain.py` shifts each held-out ad by its lister's
mean gap over the other half of the buildings, shrunk as S3 did, and scores the shift on
L1's draws:

13. The shift by lister gains 100 to 800 elpd over a constant shift (40%).

### Results: the regressions

`b_between.py` gives the sum of each code's two coefficients, in percent with one SE
clustered by building. Live-in super has its own term alone.

| Code | L1's sum | No added term | Era by zone | Class | Words | Premium count | All |
|---|---|---|---|---|---|---|---|
| Roof rights | -2.03 | -2.59 ± 0.14 | -2.34 | -2.53 | -2.47 | -2.84 | -2.59 |
| Hardwood floors | -0.65 | -1.06 ± 0.06 | -0.96 | -0.97 | -1.07 | -1.13 | -1.13 |
| Decorative fireplace | -0.63 | -0.22 ± 0.31 | -0.19 | -0.07 | -0.39 | -0.20 | -0.50 |
| City views | -0.42 | -0.57 ± 0.08 | -0.55 | -0.57 | -0.54 | -0.78 | -0.75 |
| Balcony | -0.34 | -0.23 ± 0.08 | -0.18 | -0.27 | -0.14 | -0.48 | -0.33 |
| Park views | -0.27 | +0.04 ± 0.19 | +0.16 | +0.04 | +0.12 | -0.20 | -0.06 |
| Live-in super | -0.53 | -0.26 ± 0.05 | -0.36 | -0.37 | -0.24 | -0.40 | -0.42 |

On the held-out ads the sums come out larger than L1's for roof rights, hardwood and city
views, and inside their noise for decorative fireplace and park views. No added term moves a
sum toward zero by more than 0.25 points, and the count of other premium codes makes every
sum but decorative fireplace's more negative.

The old-detail words come in 21% of the decorative fireplace ads against 6% of the others,
and in 7.4% of the hardwood ads against 4.7%. The ads stating roof rights say "renovated"
less often than the others, 21% against 33%, and so do the ads stating a balcony, 21%
against 34%. Split by the count of other premium
codes, hardwood's sum is -1.10 ± 0.15 in ads stating at most one and -1.15 ± 0.08 in ads
stating three or more, and city views' -0.52 ± 0.17 and -0.77 ± 0.10.

Scores:

1. Missed. Only roof rights comes within 30% of L1's sum, at -2.59 against -2.03.
2. Missed. Era by zone moves roof rights by 10%.
3. Missed. The class makes live-in super's term more negative, -0.37 against -0.26.
4. The first half hit for decorative fireplace (3.5 times as often) and missed for hardwood
   (1.6 times). The second missed: the words make both sums more negative.
5. Missed. Hardwood's sum is the same in both groups, and city views' is more negative in ads
   with three or more other premium codes.
6. Missed. With every added term, no negative sum shrinks by half. Roof rights stays at
   -2.59, and the other sums grow.

### Results: the reading

Sonnet subagents read 154 ads, 105 over-predicted and 49 controls; 2 had no text. Rates are
percent of each group's ads, with the SE of the difference.

| Item | Over-predicted | Controls | SE of the difference |
|---|---|---|---|
| Code is the apartment's own | 29.5 | 28.6 | 7.8 |
| Code shared, partial or unmentioned | 70.5 | 71.4 | 7.8 |
| Finishes dated | 0 | 0 | |
| Finishes unstated | 26.7 | 26.5 | 7.6 |
| Finishes new or updated | 73.3 | 73.5 | 7.6 |
| Renovation stated | 27.6 | 24.5 | 7.5 |
| Walk-up, third floor or higher | 4.8 | 4.1 | 3.5 |
| Bright or sunny | 53.3 | 53.1 | 8.6 |
| Size or layout issue | 9.5 | 10.2 | 5.2 |
| Location issue | 5.7 | 0 | 2.3 |
| Seasonal or special terms | 2.9 | 0 | 1.6 |

The readers found nothing missing in 64 of the 105 over-predicted ads and 30 of the 49
controls, 61% each. Among the rest, a converted bedroom came up in 5 over-predicted ads and 2
controls, and an ask net of a concession in 2 over-predicted ads and no control.

The text gives the codes little support in either group. Roof rights is a shared deck or goes
unmentioned in 14 of 15 over-predicted ads and all 7 controls. City views go unmentioned in
12 of 15 and 6 of 7, park views in 13 of 15 and 6 of 7, and live-in super in 13 of 15 and 7
of 7. Balcony is the apartment's own in 9 of 15 and 4 of 7, hardwood in 8 of 15 and 4 of 7,
and decorative fireplace in 10 of 15 and 5 of 7.

7. Missed. No reader found dated finishes, and unstated finishes come at the same rate in
   both groups. Only the location issues differ by more than 2 SE, in 6 of 105 ads.
8. Not scored, since the pilot didn't run.
9. Missed. The code is shared, partial or unmentioned in 70.5% of the over-predicted ads
   and 71.4% of the controls.

### Results: the lister

`f_lister.py` found 3,204 listers among the held-out ads; 0.12% have none.

| Code | No added term | Lister | Building | Building and lister |
|---|---|---|---|---|
| Roof rights | -2.59 ± 0.14 | -2.25 ± 0.16 | -2.10 ± 0.23 | -1.78 ± 0.27 |
| Hardwood floors | -1.06 ± 0.06 | -0.74 ± 0.07 | -0.89 ± 0.09 | -0.79 ± 0.11 |
| Decorative fireplace | -0.22 ± 0.31 | -0.08 ± 0.31 | -0.32 ± 0.44 | -0.56 ± 0.48 |
| City views | -0.57 ± 0.08 | -0.28 ± 0.09 | -0.27 ± 0.11 | -0.01 ± 0.12 |
| Balcony | -0.23 ± 0.08 | -0.09 ± 0.08 | +0.14 ± 0.13 | +0.05 ± 0.14 |
| Park views | +0.04 ± 0.19 | +0.50 ± 0.20 | +0.76 ± 0.23 | +0.68 ± 0.25 |
| Live-in super | -0.26 ± 0.05 | -0.40 ± 0.05 | | |

10. Missed. The lister removes 30% of hardwood's sum, 51% of city views' and 13% of roof
    rights'.
11. Missed. The building moves roof rights by 19%, hardwood by 16%, city views by 53% and
    balcony past zero.
12. Missed. The building and lister cell removes 31% of roof rights' sum, 25% of hardwood's
    and 99% of city views'.

So city views and balcony are negative between units because of the buildings whose ads
state them and the listers who tick them. L1 holds each building's level, pooled toward its
block, and the codes' unit means then take up what the pooling leaves of the building's
level. Within a building, the views and the balcony are worth zero or more. Park views' sum
on the held-out ads is already inside its noise, so L1's -0.27 doesn't come back there. Roof
rights keeps -1.78 within a building and lister, hardwood -0.79, and live-in super grows
more negative with the lister, so I haven't named a cause for those three.

The lister gain:

| Shift | elpd over no shift |
|---|---|
| Constant | 582 ± 37 |
| By phase | 863 ± 49 |
| By lister | 349 ± 39 |
| By phase and lister | 378 ± 38 |

13. Missed. The shift by lister loses 233 ± 41 elpd against the constant shift, and 486 ± 48
    by phase. A lister's mean gap on one half of the buildings doesn't carry to the other
    half, so a lister term would not predict better. The largest listers' mean gaps run from
    -1.30% to +0.60%.

## The photo pilot

I didn't run it. The brief made it conditional on finish quality looking like the omitted
cause, and it doesn't: no reader found dated finishes in the 154 ads, and unstated finishes
come at 26.7% of the over-predicted ads and 26.5% of the controls. The photos would still be
the most direct test for roof rights, hardwood and live-in super, the three negatives I
couldn't name, since a photo shows the kitchen and bath when the text says nothing. Photo
fetches need Ben's own word. The pilot would cost about 480 OxyLabs requests (60 ads at about
8 photos each) and about 0.4M Sonnet input tokens for the vision reads, with no Modal time.

## Fit candidates and cost

1. A count of each unit's earlier ads, read from the dates alone, as a term beside L1's phase.
   I expect it would move the drift out of hardwood's own term and the unit mean, so L1's
   codes would read as the worth of the feature. The held-out check gives -28 ± 14 elpd for
   the count over a constant shift, so I expect -30 to +30 against L1. Under the rule it doesn't merit a
   fit for elpd. If Ben wants the codes' terms to read right, it would cost one fit, about
   $11.50 on Modal. Against L2 it would do no better: over a shift by phase the count gives
   -27 ± 17 elpd, and L2's phase levels already take some of the drift.
2. A lister level. Rejected: -233 ± 41 elpd on the held-out ads.
3. An extraction of whether the text supports each code, at scale. Not recommended: the
   support doesn't separate the over-predicted ads from the controls. For the record, the
   reading ran about 3,000 input tokens an ad on Sonnet, so the 1.7 million training ads
   would come to about 5 billion tokens.

S12 adds nothing to the Modal queue. The negatives with no named cause are patio's own term,
roof rights, hardwood between units, and live-in super, and the photo pilot is the next test
for the last three.
