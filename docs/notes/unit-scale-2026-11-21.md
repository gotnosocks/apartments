# Unit scales by bedroom count and size, sized on stored predictions (no fit)

`docs/TODO.md` holds two unit scales for the base refit. U4 multiplies the sd of a unit's
lasting level by a factor for 2 bedrooms and one for 3 or more; U1 multiplies the sd of the
level and of its drift by `exp(gamma * max(0, log(sqft / 1000)))`. Their predictions
(`docs/notes/outlier-sprint-2026-11-11.md`, items 11 and 8) came from j9's backtest and the
latest split of an earlier design. The outlier sprint wrote that "no free check stands
behind the elpd range". Since then l2bt's design gained a Student-t unit level, which may
take part of what the scales were meant for. This note sizes both on l2bt's stored
held-out predictions, beside the year marks, gap bins and flag-change counts.

A unit scale acts most on units the fit has no ask of, since a unit with earlier asks has
its level pulled to them. So the marks below read the size of each scale on held-out ads of
units with no earlier ad in the dataset (new units), with a mark for new units on its own in
the reference so a bedroom or size mark gets no credit for newness itself.

No fit is run and no money is spent. The script and logs go in `unit-scale-2026-11-21/`.

## Method

`u1_scale.py` takes the scoring and marks of
`docs/notes/source-width-2026-11-21/s1_source.py`:
each held-out predictive of l2bt a Student-t on its median with the scale from its
quartiles, the scale multiplied by exp(a · x) and the centre moved by b · x, with an
intercept, a and b fitted on one half of the buildings and scored on the other, and
building-clustered SE. The degrees of freedom are picked on the ads of each reading.

A new unit is one whose held-out ad has no earlier ad of the same unit in the dataset, so
it has no ad in training. The size is `sqft` of the unit-features snapshot l2bt's dataset
was built from (`20261021-16cea7c`): the ad's stated size, else the median stated size of
the unit's other ads, else of its line; it reads no ask. `L` is `max(0, log(sqft / 1000))`
where a size is known and 0 where none is. Marks:

- `new`: a new unit (in the reference of every reading below);
- U4: `new, 2 bd` and `new, 3+ bd`;
- U4 on all units: `2 bd` and `3+ bd` for every ad, beside the two above;
- U1: `L` and `new × L`, beside U4's marks.

Readings, each from 2022 on (the base, gap bins, counts and year marks of 2022, 2023, 2025
and 2026, as a current Deals ad would feel them) and on all years (the base and all year
marks):

1. the reference with `new`, and the `new` mark's own gain over the reference without it;
2. U4's two marks over the reference;
3. the marks for every ad beside U4's;
4. U1's two marks over U4;
5. 80% coverage before and after, by bedroom count, for new units and others.

## Predictions, written before the script was run

1. From 2022 on, U4's marks gain +30 to +200 over the reference, positive on both halves,
   with the new-unit scale 1.05 to 1.25 for 2 bedrooms and 1.10 to 1.40 for 3 or more.
2. From 2022 on, 80% coverage of new units with 2 or more bedrooms is under 0.78 before
   U4's marks and within 0.02 of 0.80 after.
3. The bedroom marks for every ad add under 30 beyond U4's, from 2022 on.
4. From 2022 on, U1's marks over U4 gain +20 to +150, with a scale slope on `L` of 0.2 to
   0.6 (the scale at 2,000 sq ft 1.15 to 1.5 times that at 1,000).
5. On all years, U4's marks gain +100 to +400.

## Amendment, written before any reading

The script's first lines found no new unit among l2bt's 189,647 held-out ads: the latest
split holds out the latest ad of re-listed units only (`docs/leak-free-scoring.md`). The run
was stopped there, so no mark was fitted. Predictions 1, 2, 3 and 5 cannot be read on the
latest split, and the check is split in two:

- **A, the latest split (l2bt, units with earlier ads).** The bedroom marks for every ad
  (`2 bd`, `3+ bd`) and U1's `L`, each over the reference, from 2022 on and on all years.
- **B, the backtest of the served Deals design** (`drift-building-bedtext-layout-range-b0-
  market-d9028c57-range-j`: final asks of the 9,346 ads open on 2025-11-10). Its stored
  predictive is scored by `drift_score.score_run` (exact), and the same Student-t reading is
  taken from its quartiles, with the degrees of freedom picked on its elpd. A new unit is one
  with no row in the run's training rows (as `drift_deals.deals` marks it). The reference is
  an intercept and `new`; then U4's marks, the bedroom marks for every ad beside them, and
  U1's two marks beside U4's. The halves are buildings split by the parity of a CRC32 of the
  building id. This is the served design, which differs from l2bt (no lease phase, no
  Student-t unit level), and the ads are few, so its SEs are wide.

Predictions for the amended check:

6. B: U4's marks gain +10 to +80 over the reference, positive on both halves, with the
   new-unit scale 1.10 to 1.40 for 2 bedrooms and 1.20 to 1.60 for 3 or more.
7. B: 80% coverage of new units with 2 or more bedrooms is under 0.76 before U4's marks
   and between 0.77 and 0.82 after.
8. B: the `new` mark's own scale is over 1.05, and U1's marks gain under 20 beside U4's.
9. A: from 2022 on, the bedroom marks for every ad gain under 40.
10. A: from 2022 on, U1's `L` gains +20 to +150 with a scale slope of 0.2 to 0.6; on all
    years +50 to +300. This replaces prediction 4, whose U4 marks are all zero there.

## Results

Predictions 1, 2 and 5 could not be read: the latest split has no new unit. Predictions 3
and 4 read on part A, where U4's marks and `new × L` are all zero, so they are scored below
beside 9 and 10, which replaced them. Both parts ran in full (`u1_scale.log`,
`u2_backtest.log`).

### B, the backtest of the served design

9,346 ads, 3,168 of them new units, 4,718 with a size in the unit-features snapshot
`20261110-ddd2fe8` (the backtest dataset's); the degrees of freedom picked on the
stored elpd are 7. Gains are cross-fitted, with building-clustered SE; scales are given as
fitted on half A, then on half B.

| reading | gain (SE) | by half | scales |
|---|---|---|---|
| `new` over an intercept | +10.4 (10.9) | −4.5, +14.9 | 1.031, 1.160 |
| U4 over the reference | +21.0 (10.5) | +6.1, +14.9 | 2 bd 1.203, 1.084; 3+ bd 1.308, 1.470 |
| bedroom marks for every ad, beside U4 | +14.5 (7.7) | | 2 bd 1.113, 1.094; 3+ bd 1.155, 1.083 |
| U1 over U4 | +46.2 (12.1) | +26.8, +19.4 | `L` 1.693, 1.433; `new × L` 0.890, 0.911 |

U4's gain is +11.6 on new 0-1-bedroom ads, which carry no U4 mark: beside U4's marks the `new`
mark narrows them (coverage 0.839 to 0.806). New 3-or-more-bedroom ads add +7.4 and new
2-bedroom ads +1.9. `new × L` also shifts the centre up by 0.056 and 0.099 per unit of `L`.
The size slope of the scale is 0.36 to 0.53 for units with earlier asks and 0.27 to 0.41 for
new units.

80% coverage by group ("own" is the stored predictive's 10% and 90% quantiles, "t" the
Student-t reading with an intercept only, "ref" with the intercept and `new`):

| group | own | t | ref | U4 | U4 + U1 | ads |
|---|---|---|---|---|---|---|
| new, 0-1 bd | 0.796 | 0.809 | 0.839 | 0.806 | 0.805 | 1,665 |
| new, 2 bd | 0.743 | 0.751 | 0.772 | 0.782 | 0.783 | 987 |
| new, 3+ bd | 0.672 | 0.686 | 0.711 | 0.810 | 0.804 | 516 |
| repeat, 0-1 bd | 0.822 | 0.827 | 0.811 | 0.811 | 0.802 | 3,695 |
| repeat, 2 bd | 0.795 | 0.798 | 0.786 | 0.786 | 0.789 | 1,745 |
| repeat, 3+ bd | 0.780 | 0.789 | 0.778 | 0.778 | 0.809 | 738 |

New units with 2 or more bedrooms cover 0.751 with the reference and 0.792 with U4's marks.

### A, the latest split (l2bt, units with earlier ads)

| reading | gain (SE) | by half | scales |
|---|---|---|---|
| bedroom marks, from 2022 (df 7) | +68.7 (17.4) | +35.2, +33.5 | 2 bd 0.970, 0.977; 3+ bd 0.901, 0.924 |
| `L`, from 2022 | +30.0 (9.9) | +14.2, +15.8 | 1.217, 1.169 |
| bedroom marks, all years (df 5) | +122.4 (21.0) | +61.7, +60.7 | 2 bd 0.972, 0.973; 3+ bd 0.887, 0.910 |
| `L`, all years | +27.0 (8.5) | +14.8, +12.3 | 1.161, 1.142 |

The bedroom marks narrow: most of their gain from 2022 on is on 3-or-more-bedroom ads with
no size over 1,000 sq ft known (+40.4 of +68.7), whose 80% interval covers 0.822 with the
reference and 0.802 with the marks. `L`'s slope is 0.16 to 0.20 from 2022 on and 0.13 to
0.15 on all years. Its gain is on the ads over 1,000 sq ft, yet 0-1-bedroom ads over that
size cover 0.690 from 2022 on and still 0.702 with `L`.

## Predictions scored

3. Wrong, read on A: the bedroom marks gain +68.7 from 2022 on, over 30.
4. Partly right, read on A: `L` gains +30.0 from 2022 on, inside +20 to +150, with a slope
   of 0.16 to 0.20, under 0.2 to 0.6.
6. Mostly right. U4 gains +21.0 and is positive on both halves (+6.1, +14.9); the 3+ bd
   scale is 1.31 and 1.47, inside 1.20 to 1.60; the 2 bd scale is 1.20 on one half and 1.08,
   under 1.10, on the other.
7. Right: 0.751 before, 0.792 after.
8. Wrong. The `new` scale is 1.16 on one half and 1.03, under 1.05, on the other; U1 gains
   +46.2 (SE 12.1) beside U4, over the 20 predicted.
9. Wrong. The bedroom marks gain +68.7 from 2022 on, and they narrow 3-or-more-bedroom ads
   by 8% to 10%.
10. Partly right. `L` gains +30.0 from 2022 on, inside +20 to +150, but +27.0 on all years,
    under +50, and its slope from 2022 on is 0.16 to 0.20, under 0.2 to 0.6.

## What follows

- **U4's 3-or-more-bedroom factor holds on the served design.** On the backtest, new
  3-or-more-bedroom units go from 0.711 to 0.810 coverage and new 2-bedroom units from
  0.772 to 0.782. Of the gain of +21 (SE 10.5), +7.4 is on new 3-or-more-bedroom ads and
  +1.9 on new 2-bedroom ads; the other +11.6 is the `new` mark narrowing new small units
  once U4 widens the large ones. The sprint note's +100 to +500 was for a fit's elpd on the
  latest split, so it does not compare with a 9,346-ad backtest. The factors read here,
  1.08 to 1.20 for 2 bedrooms and 1.31 to 1.47 for 3 or more, sit at or below the low end
  of the note's 1.2 to 1.6 and 1.4 to 2.0.
- **l2bt's re-listed large units are already wide.** Its 3-or-more-bedroom ads of units
  with earlier asks cover 0.822 from 2022 on, and a mark narrows them. Whether its
  Student-t unit level already widens new large units, as U4 would, cannot be read on the
  latest split, which holds out no new unit. A backtest of l2bt's design (one fit with the
  ads open on 2025-11-10 held out) would read it; that spends money and goes to Ben.
- **U1 is modest.** Its size slope is 0.13 to 0.20 on l2bt and 0.27 to 0.53 on the served
  backtest, against the sprint note's `gamma` of 0.3 to 0.6, and its gain is +27 to +46,
  against +150 to +500. It leaves 0-1-bedroom ads over 1,000 sq ft at 0.70 coverage: a size
  slope shared by every bedroom count does not cover them, and a stated size at odds with the
  bedroom count is the first thing to read there.
- The predictions of U1 and U4 in `docs/TODO.md` are revised down to these readings. Both
  stay on the base refit's list; neither is a reason to spend before Ben decides the refit.
