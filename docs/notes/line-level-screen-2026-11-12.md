# A level for each line, screened on L1's held-out ads (2026-11-12)

`docs/notes/deals-pricier-lines-2026-11-12.md` proposed a lasting level for each line of a
building, between the building's level and the unit's. I wanted to know whether such a
level would help L1's held-out predictions before writing it as a model term, so I
screened it on L1's saved draws. This note makes no fit and spends nothing on Modal. The
scripts and their outputs are in `docs/notes/line-level-screen-2026-11-12/`.

## What I ran

L1 is the pool `drift-building-phase-b0-latest-9a7830fb-l1`, scored on the 189,647
held-out ads of the latest split. For each held-out ad I took the residuals (final ask
less L1's median, in log rent) of the held-out ads of other units in the same group, and
averaged them. I shrank the average by n / (n + k), where n counts those ads, then moved
the ad's predictive location by the result and scored L1's exact predictive again. That
score uses L1's draws of every location, unit scale, sigma, phase factor and nu
(`drift_score._density` with its Student-t mixture). I picked k from 1, 3, 10, 30 and 100
on one half of the buildings, split by a hash of the building, and scored the other half
with it, then swapped the halves. The SE is clustered by building.

I compared three groups:

- building
- building and bedrooms
- line: building, bedrooms and full baths

The screen reads other held-out ads' asks, so it is not a leak-free estimate of the term.
It reads them in two ways:

- `line.py` takes every other unit's held-out ad in the group, from any date.
- `line_time.py` takes only those listed on an earlier day than the ad itself. A fitted
  term would see ads from before the ad, so this version comes closer to what a term
  could learn. Even so, these earlier ads are later than any training ad.

## Results

All held-out ads with at least one other unit's ad in the group:

| group | ads read | n | k | elpd gain | SE | median error | 80% coverage |
|---|---|---:|---:|---:|---:|---:|---:|
| none (L1) | | 189,647 | | | | 0.04068 | 0.797 |
| building | any date | 176,345 | 30 | +510.7 | 68.1 | 0.04056 | 0.798 |
| building, bedrooms | any date | 161,321 | 10 | +1,687.6 | 111.6 | 0.04028 | 0.801 |
| line | any date | 157,856 | 10 | +1,959.8 | 112.1 | 0.04023 | 0.802 |
| building | earlier only | 153,201 | 100 | +172.3 | 27.1 | 0.04061 | 0.798 |
| building, bedrooms | earlier only | 131,525 | 30 | +705.8 | 49.3 | 0.04045 | 0.799 |
| line | earlier only | 127,886 | 10 | +750.0 | 83.1 | 0.04051 | 0.799 |

The median error and coverage are over all 189,647 ads, with no shift for ads outside the
group. Both fold halves picked the same k in every row.

Most of the gain sits below the building. The shift by building alone recovers a fifth to
a quarter of what the line recovers. L1's building walk already carries a building's
moves over time, so this residual share is mostly what the walk misses, plus what ads of
the same period share. Bedrooms take the bulk of the rest, and full baths add a little
more: +272 elpd with ads of any date, +44 earlier only. With earlier ads only, the gain
falls to about 40% of the any-date figure. The rest of the any-date gain comes from ads of
the same weeks moving together. A term fit on the training ads could not know about those
moves, so I would not count that part as evidence for a line level.

The Deals subgroup is the held-out ads whose L1 median lies more than 0.15 above the
building's other same-count asks (17,366 ads, chosen by `deals-check/sub.py` as in the
Deals note). In that subgroup:

| group | ads read | elpd gain | SE | median signed error | median error | 80% coverage |
|---|---|---:|---:|---:|---:|---:|
| none (L1) | | | | -0.0246 | 0.05340 | 0.703 |
| building | earlier only | +36.9 | 9.8 | -0.0243 | 0.05312 | 0.703 |
| building, bedrooms | earlier only | +141.5 | 18.5 | -0.0242 | 0.05311 | 0.705 |
| line | earlier only | +220.9 | 31.3 | -0.0235 | 0.05295 | 0.706 |
| line | any date | +424.5 | 38.6 | -0.0226 | 0.05229 | 0.710 |

In the subgroup the line shift adds elpd, but it moves the median's shortfall by only
0.001 to 0.002 and coverage by under 0.01. Even with the ads of any date the shortfall
stays at -0.023. Other units' residuals in the same line, then, don't share the
subgroup's error. A line level of this kind would help the subgroup about as much as it
helps any other ad, and would not close the gap the Deals readers found. The Deals note
raised selection as one cause, and this screen leaves it as the likelier one: the
subgroup is picked for a median far above the building's other asks, so an ad noisy in
their direction lands under the median.

## What this says about a line term

The screen supports a level below the building. With earlier ads only, a line level is
worth +750 elpd (SE 83), and building and bedrooms alone +706 (SE 49), both well past the
2 SE bar. For a term fit on training ads I would expect less than the screen shows, for
two reasons:

- A held-out ad's earlier ads sit closer in time than any training ad. The line's level
  in the training ads is older than that.
- L1 already gives each unit a lasting level. Where a line holds only one unit, a line
  level adds nothing to the unit's own.

The term was tried on the older model family as `lines` and tied (PSIS-LOO +22.5, lot SE
10.3; `docs/research-record.md`, rows 118 and 125). L1's unit level and building walk
should take up even more of it, which argues for a smaller gain than the screen, not a
larger one.

I have not written the term as code. The drift model's building paths, drawn given the
unit levels, left every chain creeping at R-hat 1.6 until the building term was collapsed
(`frontier/src/rentfrontier/drift.py`, module docstring). A line nests a building's units
more tightly, so a line term drawn the same way, as `drift`'s uncollapsed local terms are,
would very likely mix worse. The design I would try puts each unit's lasting level under
its line's: u_j ~ Normal(l_line(j), unit_sd), l ~ Normal(0, line_sd), with the line levels
integrated out alongside the units in the building's collapsed step. That changes
`drift.py`, whose hash L1 and the served b9 depend on, so it belongs in a new module
copied from the parts it changes, and it is more than a sprint's free work.

## Predictions for a line term on L1 (before any launch)

1. The fit passes the gate (45%).
2. elpd on the shared held-out ads gains over L1 by more than 2 SE (60%), and by 150 to
   600 (55%).
3. In the Deals subgroup, the median signed error stays within 0.004 of L1's -0.0246
   (70%).
4. 80% coverage on all ads moves by less than 0.005 (70%).
