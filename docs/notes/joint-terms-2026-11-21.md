# The queued base-refit terms fitted together on stored predictions (no fit)

`docs/TODO.md` queues about ten terms for the next refit of the base model. Each was sized
alone by calibration on stored predictions (`docs/notes/history-scan-2026-11-18.md`,
`docs/notes/duplex-scale-2026-11-18.md`, `docs/notes/large-unit-text-2026-11-21.md`). Their
classes overlap: a changed-count ad is often a two-bath ad, and a large unit is often in
the top tier. Single sizes therefore cannot be added. This note fits them all at once on the
same stored predictions, so the refit's decision rests on one joint size.

No fit was run and no money was spent. The script and log are in `joint-terms-2026-11-21/`.

## Method

`j1_joint.py` follows `calib2.py` of the history scan. Each held-out predictive of l2bt
(`drift-building-phase-unitkn-level-bedtext-b0-latest-c1ffaefd-l2bt`, latest split) is a
Student-t on its median with the scale from its quartiles; 7 degrees of freedom match the
stored elpd best. Every ad's scale is multiplied by exp(a · x) and its centre moved by b · x,
where x holds an intercept and the marks below. a and b are fitted on one half of the
buildings (the history scan's halves) and scored on the other, both ways. The intercept alone (one scale and one shift
for every ad) is the control, and the terms' gain is the full fit's gain over it.

The marks read coded fields, the floor snapshot or the text, never the ask:

- changed counts: the unit's earlier ads in training do not all carry this ad's bedroom and
  bath counts (`same` of the history scan's `baths.py`, false), plus the same mark at 2 baths
- 2 baths, and 3 or more baths
- 4 or more bedrooms
- top 3% of predicted rent within the year
- floor 1 on the snapshot the served floor curve reads (`unit-floor/20261021-d84914c0`)
- duplex wording (`b0duplex`)
- at 3 or more bedrooms, the building's share of other held-out ads naming finishes, and a
  flag for share 0, in buildings with 4 or more held-out ads

129,861 held-out ads from 2022 on. Their stored elpd totals about 166,700.

## Joint size

| fit | cross-fit gain (building-clustered SE) |
|---|---|
| intercept only | +502 (42) |
| all terms | +1,833 (79) |
| terms over the intercept | +1,331 (70); +593 on half A, +739 on half B |

The intercept picks a scale of 0.89 and a shift of −0.003 on both halves: on ads from 2022
on the model's predictive is about 11% too wide overall. That is the control result of the
history scan (0.9) and is a matter for the noise by year (Y1 in TODO). It is kept out of the
terms' gain.

## Each term beside the others

Picked on half B and scored on A, then the reverse:

| term | share of ads | scale | shift | gain lost when dropped |
|---|---|---|---|---|
| changed counts | 21.4% | 1.20 / 1.22 | +0.003 / +0.005 | 448 |
| changed, 2 baths (added) | 4.6% | 1.05 / 1.02 | −0.007 / −0.011 | 22 |
| 3 or more baths | 1.9% | 1.16 / 1.12 | −0.033 / −0.033 | 134 |
| 2 baths | 17.0% | 1.05 / 1.05 | −0.007 / −0.006 | 83 |
| 4 or more bedrooms | 3.1% | 0.95 / 0.98 | −0.006 / −0.006 | 8 |
| top 3% predicted | 3.0% | 1.15 / 1.23 | +0.007 / −0.002 | 40 |
| floor 1 | 7.5% | 1.06 / 1.07 | −0.007 / −0.009 | 81 |
| duplex | 5.2% | 1.09 / 1.06 | −0.002 / −0.004 | 23 |
| 3+ bed, finish share (per unit share) | 2.0% | 0.96 / 0.93 | +0.015 / +0.020 | 44 |
| 3+ bed, share 0 | 5.9% | 0.94 / 0.96 | −0.001 / −0.005 | 11 |

- The changed-count scale is a third of the whole gain and holds its single size (1.2).
- The three-bath level (−0.033) and the top tier's scale (1.15 to 1.23) keep their single
  sizes. The top tier's shift changes sign between the halves.
- The four-bedroom level shrinks from −0.015 alone to −0.006 and is worth 8. The three-bath,
  finish and share-0 terms take it. It can leave the refit.
- The finish share keeps its level, about +0.015 to +0.020 from share 0 to share 1. Its scale
  below 1 says those buildings' large units are also a little more predictable. The share-0
  flag adds 11 beside it and can leave the refit too.
- Floor 1 holds a level near −0.008 and a scale near 1.065, both kinds of term the TODO lists.

## The low tail

Each ad is placed in its adjusted predictive under the other half's fit. Of 6,911 ads below
the 5% point under the intercept-only fit, 993 leave the low tail under all terms and 873
join it. Within each marked class the share below 5% falls to about 5%: from 13.7% to 5.6%
for 3 or more baths, 10.7% to 5.5% for changed counts at 2 baths, 10.6% to 5.3% for the top
tier, 8.9% to 5.0% for duplex wording, and 8.0% to 5.3% on floor 1. About one in seven
low-tail ads changes, which is the part of the Deals list the refit would move.

## Limits

- These are adjustments on stored predictions. A refit moves the building levels and the
  bedroom step with the terms, so the building-trait terms (the finish share, three baths)
  may be partly absorbed by the levels or come out larger.
- The finish share counts every other held-out ad of the building, later ones included. The
  refit term takes it from earlier ads only, as TODO says, which makes it noisier.
- The elpd comes from the t approximation and the latest split's held-out ads, not from a
  backtest of the Deals model.

## What follows

The base-refit item in TODO gets the joint size: about +1,300 elpd on held-out ads from 2022
on, building-clustered SE 70, beside an overall scale near 0.89 that belongs to the noise
term. The four-bedroom level and the share-0 flag can be dropped, each worth about 10. The
refit stays Ben's decision (about $22). A note with its predictions goes on master before
the fit, and these sizes are its starting point.
