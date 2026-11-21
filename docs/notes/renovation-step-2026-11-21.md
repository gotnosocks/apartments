# A renovation step dated from the unit's own ads, sized on stored predictions (no fit)

`docs/TODO.md` lists a renovation step: a column that turns on at the first ad of a unit
whose text says renovated or gut renovated after an earlier ad of the unit lacked the words,
and stays on for the unit's later ads. The outlier sprint found ads switching the words on
at +0.009 to +0.012 over the model, and ads dropping them at zero. The TODO predicted a
coefficient of +0.005 to +0.010 and an elpd gain under 40. This note sizes the step on
l2bt's stored held-out predictions, beside the queued base-refit terms, with the method of
`docs/notes/text-columns-2026-11-21.md`, to decide whether it belongs on the base refit's
list.

No fit is run and no money is spent. The script and log go in `renovation-step-2026-11-21/`.

## Method

`j3_renov.py` takes `j2_text.py` unchanged in its base and scoring: the 129,861 held-out ads
of l2bt from 2022 on, each predictive a Student-t on its median with the scale from its
quartiles, the scale multiplied by exp(a · x) and the centre moved by b · x, a and b fitted
on one half of the buildings and scored on the other, with building-clustered SE. The base
is j1's eight kept terms.

The words are the `renovated` and `gut` flags of the outlier sprint's quality scan
(`tmp/outlier-sprint/qual/flags.parquet`), read from the description of each listing's
latest record. A unit's ads are the rows of l2bt's dataset with its `unit_id`, training and
held-out alike, ordered by `price_at`. For a held-out ad only ads of the unit priced
strictly earlier count as earlier, and their text is all the mark reads; no mark reads an
ask.

- step: some ad of the unit up to and including this one has the words, and an ad of the
  unit priced before that one lacks them
- switch: this ad has the words and the unit's latest earlier ad lacks them (the step's
  first ad)
- worded, no bare ad before: this ad has the words and no earlier ad of the unit lacks
  them, for comparison only (a unit level carries a lasting premium)

Each is added alone beside the base with a scale and a shift. The step is the candidate;
the switch and the comparison mark only help read it.

## Predictions, written before the script was run

1. Shares among the held-out ads from 2022 on: the step 3% to 10%, the switch 1% to 4%.
2. Shift of the step on each half +0.005 to +0.010, as the TODO says; scale 0.97 to 1.05.
3. The switch's shift within 0.004 of the step's on each half: once renovated, a unit's
   later ads sit as far over its level as the first.
4. The comparison mark's shift within ±0.004 on each half: the unit level already carries
   a lasting premium.
5. Gain of the step over the base under 40 and positive on both halves; under 2 SE, so the
   step goes on the base refit's list as optional at most.
6. The low tail: fewer than 1% of the base's low-tail ads leave it with the step added.

## Second check, predictions written after the first runs

The first runs (`j3_first.log`, then `j3_renov.log` with controls added after it) gave the
switch +117 (SE 18), mostly by a wider scale, and wording for a dishwasher turning on +74
(SE 15) with the same scale near 1.10. Much of the switch's gain may belong to any rewritten
description. `j4_rewrite.py` counts, for each held-out ad, how many of the scan's 31 text
flags differ from the unit's latest earlier ad (every held-out ad of the split has one), and
adds three marks together: 1 flag changed, 2 changed, 3 or more changed. Predictions:

1. The scale rises with the count; 3 or more changed needs 1.10 to 1.25 on each half.
2. The three count marks together gain more than the switch alone (over 117).
3. Beside the count marks, the renovation switch keeps a shift of +0.004 to +0.008 on each
   half, a scale within 0.97 to 1.04 and a gain under 40.
