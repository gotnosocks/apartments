# Robust pricing and apartment candidate scoring

`score-apartments` connects the validated robust model to the preference frontier.
Market predictions and personal dollar preferences remain separate: changing a
model coefficient cannot change the preference surplus or Pareto membership.
The bundled example preferences are illustrative, not estimates of the user's
willingness to pay.

## Build a current point model

`models.fit_robust_service` refits the fixed specification on a verified historical
dataset, linking the completed monthly validation. It requires a knowledge cutoff
that has passed, at least 24 months and 100 rows, and observations covering the
month immediately before the requested pricing month. Source, code, runtime,
settings and membership hashes are recorded before fitting. The optimizer must
converge before publication.

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  uv run --locked --extra model python -m models.fit_robust_service \
  --dataset data/exports/chelsea-serving-history-20260918-asof1600 \
  --validation data/model/chelsea-monthly-validation-20260918 \
  --output data/model/chelsea-serving-20260918-v3 \
  --prediction-month 2026-09
```

The portable runtime uses Python's standard library. It replays the saved bedroom
increments, size imputation, trend, seasonality, building/unit effects, centered
amenity values, missingness terms and interactions. Publication checks parity
against the scientific NumPy/SciPy implementation for every selected training
identity/attribute combination at the pricing month. Serving does not fit a model
or need the optional Bayesian/model dependencies. New runtime or feature code
requires a new verified export; incompatible code cannot silently replay a bundle.

The completed September fit uses 53,218 historical unit-months through August
2026. This is a refit on previously analyzed data, not a fresh validation result.
The training target is each advertisement's **initial gross asking rent**. A search
candidate's current gross ask can differ after price changes; the residual is
not a guaranteed discount to a realized lease or current market-clearing price.

For audit or retrospective analysis, `models.export_robust_pricing` can export
a particular fit from the completed monthly experiment. Old exported fits are
subject to the same serving-age checks.

## Build capture-time candidate records

```sh
uv run --locked python -m apartments.cli build-candidates \
  /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  data/exports/chelsea-serving-history-20260918-asof1600 \
  data/exports/chelsea-candidates-20260918-asof1600 \
  --as-of 2026-09-18T16:00:00Z \
  --description-recovery data/exports/chelsea-description-recovery-20260918
```

This uses canonical source membership, independently verified source-shard hashes
and row counts, and description recoveries bound to exact capture/body hashes.
Attributes come from that capture; prices come from its current `pricing.price`,
never a historical price event. Corrections use the same source selectors and
ledger, applied at the collection instant. Original source hashes, extraction
evidence and applied corrections remain in the candidate records. Identity,
collection, parser, recovery and correction knowledge clocks are checked.

Active and inactive advertisements remain in the snapshot. The selector first
resolves the latest known capture **within each advertisement**. An inactive
latest capture cannot fall back to an older active capture of that advertisement.
An old inactive advertisement cannot hide a separate active advertisement merely
because the crawler fetched the old page later. Compatible active advertisements
for one canonical unit merge their evidence; conflicting active advertisements
are excluded before the budget filter. Unknown optional attributes are not filled
from another advertisement.

## Score an explicit snapshot

For updated source evidence, use the [bounded Oxylabs refresh](../data/candidate-refresh.md)
and score its fresh `snapshot/candidates.jsonl`. The completed
[September 18 refresh example](../analysis/chelsea-candidate-refresh-2026-09-18.md)
records seven selected units; the command below retains the earlier archived-data
example for reproducibility.

```sh
uv run --locked python -m apartments.cli score-apartments \
  data/exports/chelsea-candidates-20260918-asof1600/candidates.jsonl \
  config/example-search-preferences.json \
  data/model/chelsea-serving-20260918-v3/model \
  data/model/chelsea-search-example-20260918 \
  --as-of 2026-09-18T17:02:16.194421Z --max-age-days 7 --budget 6000
```

Choose an `--as-of` at or after the model's recorded `published_at` and the
candidate evidence cutoff. The timestamp above is the recorded cutoff of the
completed example. A supplied date alone does not turn saved captures into live
availability.

Candidate JSONL requires canonical `unit_id` and `building_id`,
`source_listing_id`, `collected_at`, a capture reference, `listing_status`,
`price_basis: "gross_advertised_rent"`, rent and attributes. `known_at` or
`known_as_of`, when supplied, restricts the knowledge cutoff. A generic
`observed_at` field is deliberately insufficient because historical datasets use
it as a price-event alias. Directly supplied files are treated as declared source
snapshots; use `build-candidates` for verified archive provenance.

The selector rejects stale, unknown-status, conflicting, invalid-price, known
furnished, known short-term and known concession rows. Unknown rental flags remain
unknown, so source omissions are still possible. It applies budget before ranking.
Missing valued attributes exclude a candidate by default; `--unknown-policy zero`
is an explicit alternative with the same signed-dollar semantics as the existing
ranking API.

The market score is separate. A model whose training knowledge or publication
time is after the requested cutoff cannot score. A model more than one pricing
month beyond its last training month cannot silently quote current rent. Invalid
layouts retain preference results but get an unsupported market-score status.
A known canonical unit paired with a different building is rejected for market
scoring; the saved training identity map prevents combining unrelated group effects.
The artifact records training advertisement IDs. If a currently active advertisement
itself contributed an earlier initial ask to training, the result flags that overlap:
its residual is partly fitted to its own asking history. It must not be presented
as independent evidence of a bargain. Neither this flag nor market predictions
changes preference ranking.

## Explanation and uncertainty

`RobustPricingModel.predict` returns components that sum exactly to log predicted
rent, familiarity, model horizon and support warnings. Centered component values
are not standalone amenity premiums. `marginal_contributions` re-encodes before
and after records, recomputing floor/elevator interactions. Changes involving
unknown attributes are labeled as reporting-pattern contrasts. These conditional
associations do not estimate causal effects or a renter's personal preferences.

No prediction band is promoted by this initial serving path. Unfamiliar buildings
return `unsupported_new_building`; familiar properties return
`not_calibrated_for_serving`, with a null interval. This preserves the observed
failure of pooled new-building bands rather than presenting a nominal 95% label
as reliable uncertainty. Validating transferable calibration remains open work.

Outputs are checksummed bundles containing the exact candidate input, preferences,
rankings, exclusions, selection counts, code hashes and model provenance. Identical
reruns verify and reuse them. Each ranked row says source-reported active at capture
and explicitly states that current availability is not verified. A renter-facing
interface and a prospective current-data evaluation are still outstanding.
