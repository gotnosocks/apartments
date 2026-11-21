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
