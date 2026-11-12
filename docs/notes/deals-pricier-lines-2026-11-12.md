# Deals ads that follow the building's pricier lines (2026-11-12)

Readers of the Deals page judged 15 of the default top 60 false because the building's
ads with the same bedroom count ask about what the deal asks, while the median follows
the building's pricier lines (`docs/handoff/project-owner.md`). The first held-out check
of that group is in `docs/notes/own-history-2026-11-12.md`, section "The building's
same-count ads", run on b9: where b9's median sits more than 0.15 above the mean of the
building's other same-count ads, the final ask lands 0.031 under the median and the 80%
interval covers 0.666. I asked whether L1 or U2 moves that, using L1's and c3ab's
held-out predictions. This note makes no fit and spends nothing on Modal.

## What I ran

I took the 189,647 held-out ads of the latest split, which L1 and c3ab share, and read
their `pred_scores.npz` (`pred` is the median in log rent, `q` holds the quantiles). For
each ad I averaged the log asks of the training ads in the same building with the same
bedroom count, from other units, in the 24 months up to the ad, each moved by a monthly
index, and moved the average back to the ad's month. 166,922 ads have such training ads.
The subgroup is the ads whose median lies more than 0.15 above that average. The script is
`/data1/apartments/tmp/sprint-20261112/deals-check/sub.py`.

The index is a quick rebuild (the mean within-unit deviation of the training asks by
month), not the one the own-history script recovered from its parquet, so the subgroup is
17,594 ads here against 9,796 there. The mean gap matches the earlier one (-0.028 against
-0.031) and coverage is higher (0.715 against 0.666), so the larger group is a milder
version of the same one.

## Results

Signed error is the final ask minus the median, in log rent. Coverage is for the 80%
interval. "Rest" is every ad outside the first group, so it includes the 7,679 ads of the
second.

| group | model | n | median signed error | mean signed error | coverage |
|---|---|---:|---:|---:|---:|
| median over the building's ads by > 0.15 | c3ab | 17,594 | -0.0256 | -0.0279 | 0.715 |
| | L1 | 17,594 | -0.0241 | -0.0262 | 0.703 |
| median under the building's ads by > 0.15 | c3ab | 7,679 | +0.0153 | +0.0262 | 0.663 |
| | L1 | 7,679 | +0.0140 | +0.0249 | 0.652 |
| rest | c3ab | 149,328 | -0.0027 | -0.0017 | 0.822 |
| | L1 | 149,328 | -0.0029 | -0.0018 | 0.812 |
| all | c3ab | 166,922 | -0.0044 | -0.0044 | 0.811 |
| | L1 | 166,922 | -0.0045 | -0.0043 | 0.801 |

Defining the subgroup by L1's median instead of c3ab's changes nothing past the third
decimal. L1 shifts the median error in the subgroup by 0.0015 toward zero and lowers its
coverage by 0.012, in step with the 0.010 it lowers coverage everywhere. The phase factors
widen intervals by lease phase and do not read the building's other lines, so they leave
the subgroup where c3ab put it: 0.025 under the median, covering 0.70 to 0.72, against
0.81 to 0.82 for the rest. The group under the building's ads has the mirror error (+0.015)
and the lowest coverage. Part of both errors is mechanical: I chose the groups by how far
the median sits from the building's other asks, and an ask noisy in the same direction as
the building's other asks lands on the far side of the median. The table does not show
how much of the error that selection makes.

By the number of training ads of the unit itself, the subgroup splits 6,864 with one, 4,483
with two and 6,247 with three or more. Their median signed errors are -0.0266, -0.0256 and
-0.0251, and their coverages 0.697, 0.715 and 0.735. Coverage rises slightly with the
unit's own history, and the pull toward the building's lines does not shrink.

## Would U2 move it

U2 gives each unit's lasting level its own mixing scale, so a unit whose training asks sit
far from the building's level is shrunk less toward it. That moves an ad's median only
through the unit's own training deviations, and only where those are large. In the
subgroup the shortfall is the same 0.025 for units with one, two and three or more
training ads. If shrinkage of the unit's own deviation drove it, the shortfall would
change with the number of training ads. The 39% of the subgroup with a single training ad
would gain from a heavier tail only where that ask lies well below the median, and the
earlier ask is already in the median through the unit's level. I expect U2 to leave the
subgroup's median error within 0.002 of c3ab's, and its coverage within 0.01. L1's part of
this rests on its held-out predictions. U2's part is an expectation from its structure,
since U2 has not been fitted. On that reading the fits already queued should not close the
gap, and the subgroup needs a term of its own.

## A term that would: a level for each line

By a line I mean the units of a building with the same bedroom and full-bath counts. The
served model, `drift-building`, gives each unit a lasting level and each building a
level and walk, and has no level between the two (`docs/model/drift.md`). The subgroup's
median follows the building's pricier lines because every unit of the building shares the
building level, so what one line asks pulls the rest. A lasting level for each line, with
a Normal(0, line_sd) prior summed into the median like the unit's level, would give the
building's cheaper lines their own offset. A line with more training ads gets a better
estimated level, and one with none falls back to the building.

A `lines` term was tried twice on the earlier model family, on 2026-10-10 and on split C on
2026-10-14 (`docs/research-record.md`, rows 118 and 125; `docs/model/unadopted-work-2026-10-14.md`).
It tied, with PSIS-LOO +22.5 (lot SE 10.3), and was left unserved. I have not checked
whether its line key matches this one. The retest would differ in two ways. It would sit
on the drift model, whose unit level and building walk already take up some of what the
old term found. And it would be scored on this subgroup, where the error is concentrated,
rather than on the whole set alone. Before writing the fit I would read the old term's
definition and keep the key if it matches.

Leak risk: the line level reads other listings' prices only as training targets, the way
the unit's level and the building walk already do, so it is leak-free under
`docs/leak-free-scoring.md`. A covariate built from the building's other asks (the average
I used above) would read other rows' prices as features and would need the leak rules
applied. For the held-out latest split, a line's training ads come from before the
held-out ad, so the level never sees the ad's own final ask.

## Predictions for such a fit (before any launch)

1. In the subgroup, the median signed error falls from -0.025 to between -0.015 and -0.005
   (60%).
2. Coverage in the subgroup rises from 0.715 to over 0.75 (55%).
3. The rest keep coverage within 0.01 of 0.822 (75%).
4. elpd on the shared held-out ads gains over c3 by more than 2 SE (60%).
