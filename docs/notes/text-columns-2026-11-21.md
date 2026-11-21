# Text columns for coded fields left empty, sized on stored predictions (no fit)

`docs/TODO.md` lists five text columns, each a fit of its own: private outdoor space where
the coded field is false, penthouse, dishwasher where the coded field is false, furnished
and full floor. Their figures (+0.0154, +0.0058, +0.0064, +0.0071 and +0.0124) were gaps
against the model of the outlier sprint (`docs/notes/outlier-sprint-2026-11-11.md`). Since
then the model has gained the unit levels and terms of l2bt, and the joint size of the
queued base-refit terms is known (`docs/notes/joint-terms-2026-11-21.md`). This note sizes
the five marks on l2bt's stored held-out predictions, beside those queued terms, to decide
which belong in the base refit and whether any moves the low tail enough for a fit of its
own.

No fit is run and no money is spent. The script and log go in `text-columns-2026-11-21/`.

## Method

`j2_text.py` takes the method of `j1_joint.py` unchanged: the 129,861 held-out ads of l2bt
from 2022 on, each predictive a Student-t on its median with the scale from its quartiles,
the scale multiplied by exp(a · x) and the centre moved by b · x, a and b fitted on one half
of the buildings and scored on the other. The base is j1's eight kept terms (j1's ten less
the four-bedroom level and the share-0 flag). Each text mark is added with a scale and a
shift. The gain reported is the cross-fitted gain over the base, with building-clustered SE.

The marks come from the description of each listing's latest record, with the patterns of
the outlier sprint's quality scan (`tmp/outlier-sprint/qual/flags.parquet`, the patterns of
`features.DESCRIPTION_FLAGS` plus that scan's own). The coded fields come from the listing
codes l2bt read (`external/listing-codes/20261023-ks`). No mark reads the ask.

- outdoor, uncoded: the text names private outdoor space and `feat:PRIVATE_OUTDOOR_SPACE`
  is false
- dishwasher, uncoded: the text names a dishwasher and `feat:DISHWASHER` is false
- furnished: the text says furnished (the coded field is set on no held-out record)
- penthouse: penthouse, PH or top floor in the text
- full floor: full floor, floor-through or entire floor in the text

## Predictions, written before the script was run

1. Shifts: outdoor uncoded +0.006 to +0.015, dishwasher uncoded +0.002 to +0.006,
   furnished +0.003 to +0.009, penthouse +0.002 to +0.008, full floor +0.004 to +0.012.
   The unit levels of l2bt absorb part of each lasting premium, so each lands at or below
   the outlier sprint's figure.
2. Scales: penthouse and full floor above 1 (1.03 to 1.12), as the sprint found their
   spread wider; the other three within 0.97 to 1.04.
3. Gain over the base: each mark under 30 elpd, the five together under 80.
4. The low tail: fewer than 2% of the base's low-tail ads leave it when the five are added.
   No mark is a fit of its own; at most two go to the base refit's list.

## Results

The base (j1's eight kept terms) gains +1,807 (SE 79) over the stored predictives, against
j1's +1,833 with all ten. The marks over the base, cross-fitted, with building-clustered SE:

| mark | share of ads | gain over the base | by half (A, B) | scale (fit on A / B) | shift (fit on A / B) |
|---|---|---|---|---|---|
| outdoor, uncoded | 2.7% | +15.5 (9.9) | +2.6, +12.9 | 1.010 / 1.041 | +0.0046 / +0.0070 |
| dishwasher, uncoded | 3.0% | +3.4 (4.5) | +4.2, −0.8 | 1.033 / 1.025 | +0.0045 / +0.0015 |
| furnished, uncoded | 4.6% | +7.7 (7.0) | +0.6, +7.2 | 1.032 / 1.065 | +0.0005 / +0.0016 |
| penthouse | 4.2% | +7.8 (5.1) | +4.2, +3.7 | 1.023 / 1.041 | −0.0037 / −0.0024 |
| full floor | 2.4% | +0.7 (2.1) | −0.0, +0.7 | 0.975 / 0.972 | −0.0000 / +0.0016 |
| all five | | +32.7 (13.5) | +11.1, +21.6 | | |

None of the five is worth 2 SE alone. The five together are worth 33, about 2.4 SE, near the
size of j1's two smallest kept terms (22 and 23). Coded furnished is set on none of the held-
out ads, so the furnished mark is the whole text flag.

- l2bt's unit levels carry what the outlier sprint measured. Furnished and full floor keep
  almost no shift, and dishwasher keeps about +0.003.
- Outdoor space with the box unchecked keeps the most, about +0.006, about two fifths of
  the sprint's +0.0154. Its gain comes mostly from half B.
- The penthouse wording leaves a small negative shift: ads that say penthouse or top floor
  ask a little less than the model's floor terms give them.

## The low tail

Of 6,792 base low-tail ads (below the 5% point, each ad under the other half's fit), 72 leave
the low tail with all five marks added and 72 join it, about 1%. Among marked ads, the share
below 5% moves from 6.2% to 5.5% for penthouse and from 5.4% to 4.9% for furnished. The other
three stay near 5%.

## Predictions scored

1. Shifts: mostly wrong. Two of the ten half values are in range: outdoor, uncoded on half B
   (+0.0070) and dishwasher, uncoded on half A (+0.0045). Outdoor on half A is just under
   range (+0.0046 against +0.006 to +0.015), dishwasher on half B, furnished and full floor
   fall below range, and penthouse has the wrong sign.
2. Scales: half right. Five of the ten half values are in range: outdoor on half A (1.010;
   1.041 on half B is just over 1.04), dishwasher on both halves, furnished on half A (1.065
   on half B) and penthouse on half B (1.041; 1.023 on half A is just under 1.03). Full floor
   is wrong on both (0.97, below 1).
3. Gains: right. Each is under 30 and the five together are under 80.
4. Low tail: right. 72 of 6,792 leave (1.1%), and no mark is a fit of its own. The prediction
   allowed at most two for the base refit, and two are kept as optional below.

## What follows

No text column is a fit of its own. Overall 72 low-tail ads leave and 72 join (about 1% each).
For the base refit's list I keep as optional the marks whose gain beside the base exceeds 1.5
SE, a cutoff chosen after the run that sits just under the two it keeps (1.57 and 1.53 SE):
outdoor space with the box unchecked (+15.5, SE 9.9, a shift near +0.006, a gain unsteady by
half at +2.6 and +12.9) and penthouse (+7.8, SE 5.1, steady by half at +4.2 and +3.7, a shift
near −0.003 and a scale near 1.03). Penthouse also moves the most marked ads out of the low
tail (339 to 297). Furnished (1.1 SE), dishwasher (0.8 SE) and full floor (0.3 SE) leave the
queue.
