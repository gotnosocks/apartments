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
interval.

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
and the lowest coverage.

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
subgroup's median error within 0.002 of c3ab's, and its coverage within 0.01. So neither
L1 nor U2 addresses these ads, and the fits already queued should not be expected to close
the gap. The subgroup needs a term of its own.

## A term that would: a level for each line

The subgroup's median follows the building's pricier lines because the model's building
level is shared by every unit of the building, and what one line asks pulls the rest. A
single change, a lasting level for each line (building, bedrooms and full baths), with
its own prior scale, gives the building's cheaper lines their own offset. Each line's
level is a random effect with a Normal(0, line_sd) prior, summed into the median like the
unit's level. The model reads only the line's key (building, bedrooms, full baths), which
the ad itself carries, and the line's training asks as targets, as it reads every training
ask. A line with more training ads gets a better estimated level, and one with none falls
back to the building. A within-building rank effect (a line's position in the building by
size or baths) would give the same offset to lines it has never seen, from the ad's
fields alone.

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
