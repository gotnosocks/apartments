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
