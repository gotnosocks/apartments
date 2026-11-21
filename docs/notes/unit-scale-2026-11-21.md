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
