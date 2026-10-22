# Is the previous-price feature appropriate?

Independent read of `nb3-prevprice-v2`, the feature set served since 2026-10-07 06Z (PR #392). Based on the repo at f8563e8 (`features.prevprice_v1`, `model.py`, `cohort.py`, `docs/leak-free-scoring.md`). I had no access to fit outputs on thelio; what I would check there is listed at the end.

## What the feature actually is

It is not "the previous rent as a covariate". Each row gets two numbers from the unit's **previous advertisement** (its latest earlier row of a different ad):

1. `previous_listing_price_change`: log(last ask / first ask) of that previous ad, counting only changes dated before this listing, clipped to ±30%. A cut says the previous ad asked more than the unit let for.
2. `log_previous_listing_repricings`: log(1 + number of price changes), centred.

Both are 0 for a unit's first listing. The level of the previous rent cancels in the ratio, so the feature carries no information about *how much* the unit rents for, only about whether the landlord's last ask was corrected, and by how much.

Fitted on the leak-free latest split (10,497 most recent listings of re-listed units, predicted from earlier data only): +84.2 ± 17.5 held-out ELPD. Earlier exploration showed the price-change term carries most of it: v1 (both terms) +68.5, count only +24.2, difference +44.2 ± 13.1.

## Why the trend and unit effects cannot absorb it

The served model is

    log ask = features + market trend[month] + season + bedroom-group curves
              + building level + building half-year walk + unit level + noise

Every term is a property of the apartment, the building or the market at a date. The only unit-specific term is a **constant** unit level.

The target is each ad's **initial ask** only (`cohort.PRICE_BASIS = historical_initial_own_advertisement_ask`). The ad's later cuts and its final ask never enter the likelihood. So the information "this unit was listed at 5,000, cut to 4,600, then rented" is simply not in the data the model sees. The unit level learns from the 5,000, not the 4,600. When the landlord lists again at 4,700, the model over-predicts by the uncorrected overshoot, and prevprice fixes exactly that: a landlord's next initial ask is anchored on where the last ad ended, not where it started.

Neither the market trend nor the bedroom curves can carry this. It is per-unit, per-episode, and sign-varying across units in the same month. The static unit level cannot either, because it is one number across the unit's whole history (2.4 rows per unit on average), and the overshoot is specific to one episode.

So Ben's intuition that "the other components should capture this" is right about the *kind* of information, but wrong about the *current* components: none of them observes final asks, and none of them is unit-level and time-varying. The feature is doing a real job.

## Where the "hack" concern is justified

1. **It patches a data-and-likelihood gap with a covariate.** The principled fix is to let the model see the final ask: add each ad's last price as a second observation (same unit, later date, flagged "repriced ask"), or model initial ask and final ask jointly. Then the unit level, the building walk and the trend learn from the corrected price directly, and prevprice should lose most of its gain. If it does not, the remaining gain is a genuine anchoring effect on landlord behaviour, which is then a defensible feature in its own right. If it does, the covariate was a shortcut around the data design and the joint model is the cleaner answer.

2. **It is a transient state, not an attribute.** For `/estimate` and the rent map the question is "what will this unit list for", and a lister's anchoring is legitimately part of that. For `/best` the question is "is this ask a good deal against fair rent", and there the feature should be **neutral or excluded**: a unit whose previous ad was cut by 10% is not worth less, its landlord has just learned the market. Including the term in the fair-rent comparison makes a corrected ask look fair rather than cheap. The pro/con tagging should treat it like commute: informational, not in the appeal score.

3. **Time skew of the latest split.** The held-out rows are the most recent listings, where the trend has the least data after it. If the market has moved recently, previous ads got cut and prevprice partly carries the market move the trend has not yet learned. Part of the +84 may therefore be trend extrapolation error, which Ben's concern does name. The split cannot separate the two; the check below can.

4. **Half the gain is a count.** The repricing count is a landlord-behaviour proxy (patient landlords list high and cut often). That is fine as an ask predictor but is again not an apartment attribute.

## Verdict

Keep it served for `/estimate` and the map. It is leak-free as built, it encodes real information the model otherwise never sees, and the gain is 4.8 SE on a held-out, forward-in-time test. But it is a stand-in for a missing part of the likelihood rather than a feature of the apartment, so:

- Tag both prevprice terms **neutral** for `/best` now (they are not pros or cons of the apartment), and do not show them as pills.
- Queue the principled replacement test: a design that **adds final asks as observations** (one extra row per repriced ad, flagged, same unit) with and without prevprice, scored on the latest split. The result settles whether the feature is a hack. My expectation: the price-change term shrinks a lot, the count term survives.
- A cheaper second test: `unit_drift` (per-unit linear drift, already in `ModelConfig`) or a unit-level AR term with and without prevprice. This asks whether a time-varying unit component absorbs it. I expect only partly, because the overshoot is an episode effect, not a drift.

## What I would check on thelio (fit outputs I could not read)

1. The posterior of `previous_listing_price_change` in the served run. Near +1 means "next initial ask = last ad's final price" (pure anchoring); well below 1 means partial correction. Either is informative; a coefficient near 1 is the strongest sign the final ask belongs in the likelihood instead.
2. The latest-split gain split by gap since the previous listing (under 6 months vs over 12). Gain concentrated in quick relists means anchoring, which is unit-level. Gain spread evenly across gaps, and concentrated in the last few months of the data, means the feature is carrying the market move the trend has not learned (Ben's concern).
3. The gain split by sign of the previous change (cut vs raise vs none). A raise-side gain of similar size to the cut side is anchoring; cut-only gain suggests it mostly marks over-askers.
4. Whether `/best` currently includes the prevprice contribution in the fair rent it ranks against (`explain`/`kit` term tagging).

## Addendum (Ben's reply, 2026-10-07 14:11Z)

Ben's objection: the correction has no time dependence. A 1% cut three years ago and a 1% cut yesterday enter the model identically. Checked: `prevprice_v1` applies one coefficient to the raw clipped ratio; the base set's "months since last listing" is a separate additive term, and there is no interaction or decay. The objection stands. The feature also ignores how much the market moved between the two ads.

Effect size: +84.2 over 10,497 held-out rows is 0.008 nats per listing, roughly a 1% narrower predictive spread. It passed because the latest split has power at 2 SE, not because the effect is large. The selection rule has no effect-size or semantic-validity floor.

Revised recommendation:
1. Unserve it; the coded-v2 serving fit (`…-nb3-coded-v2-rows-9371a18-…`) is gate-passing and on disk. Modeling owns the switch; Ben's word there.
2. Any retest must be time-aware: change × decay(gap) or gap bins, scored on the latest split against coded-v2 and against the undecayed version.
3. The principled design: final asks as flagged observations plus a time-varying unit deviation (random walk or AR on the unit effect), so a recent correction moves the unit's current level and an old one barely does. That is a model change, not a feature.

## Ben's decision (2026-10-07 14:15Z) and wording for Modeling

Ben: unserve prevprice; record that it was removed manually for semantic invalidity; update the elegance check so similar constructions are marked down. He also rejects a per-unit monthly random walk on practicality (parameter count and memory), even though it would pass on elegance.

Suggested wording.

**Selection record (config/main-analysis.json selection_reason, and the served-model history):** "Withdrawn by Ben on 2026-10-07, not by score. nb3-prevprice-v2 had won the latest split by +84.2 ± 17.5 (0.008 nats per held-out row). Its price-change term applies one coefficient to the previous advertisement's log(last ask / first ask) with no dependence on how long ago that advertisement was or how far the market has moved since, so a 1% cut three years ago and a 1% cut yesterday are the same evidence. A future version must make the correction decay with the gap since the previous advertisement. Served model reverts to nb3-coded-v2 (run …-nb3-coded-v2-rows-9371a18-…, summary 838e50f)."

**Refusal in autoselect/latestselect:** a withdrawn-sets registry (every set built on `prevprice_v1`: nb-prevprice-v1, nb-prevprice-v2, nb3-prevprice-v1, nb3-prevprice-v2, any prevtext set) with the reason "withdrawn 2026-10-07: semantically invalid, correction has no time dependence", so the midnight Modal fits and the v8 latestselect step cannot re-serve it.

**Elegance brief, new criterion (bump BRIEF_VERSION):** "Semantic validity. Every term must mean what it claims at every row. A term built from past information must carry that information's age or distance: a signal observed three years ago and one observed yesterday are not the same evidence and may not share one coefficient. Mark down a design whose term treats them as the same. Example of a failure: a covariate equal to the previous advertisement's price correction, with no decay in the time since that advertisement. Example of a pass: the same correction multiplied by a decay in the gap, or carried by a unit-level state that moves over time."
