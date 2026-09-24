# Residual review queue (unit-level deviation)

`apartments build-review-queue` publishes a small, immutable bundle from the
explicitly selected PyMC fit (`config/main-analysis.json`) and a standalone
HTML page for browsing the largest mispricing signals with links to the
StreetEasy advertisement and canonical unit page. It is report-only: it reads
`fit/residuals.jsonl`, `fit/group-effects.jsonl` and the dataset's
`observations.jsonl` (all hash-verified against their bundle manifests), never
opens the posterior draws, and does not fit, scrape or change the selection.

```sh
uv run --locked --extra model python -m apartments build-review-queue
uv run --locked --extra model python -m apartments serve-review-queue --port 8767
```

The bundle location is derived from the selection:
`data/model/review-queue/<experiment>-<fit manifest hash>-<queue version>`.
An unchanged selection verifies and reuses the bundle; a new selection or a
changed queue implementation publishes to a new directory automatically. The
server resolves that directory from `config/main-analysis.json` on every
request, so after `build-review-queue` (or a new selection plus a rebuild) the
page updates with no restart. Until a bundle exists for the current selection
it answers 503 with the build instruction. On thelio,
`deploy/thelio/apartments-review-queue.service` serves the page at
http://thelio.tail3983e0.ts.net:8767/ alongside the review workbench; pass a
directory argument instead to pin one bundle.

## When to rebuild

The queue is **not** rebuilt automatically. Run `build-review-queue`:

- after `python -m apartments.main_analysis --experiment … --dataset …` publishes
  a new selection (the selection command prints this reminder);
- after the review-queue implementation version changes (the bundle name ends
  with the queue version, so an old bundle is simply no longer located).

Nothing else invalidates it: the bundle is bound to the selected fit's manifest
hashes, and fits are immutable. The page at port 8767 reports "no review queue
bundle is published for the selected fit" until the rebuild finishes.

## Ranking

The queue is ranked on absolute **unit-level deviation**:

```
unit_deviation_log = residual_log + unit_effect_median
```

i.e. the log gap between the advertised ask and the fitted median with the
apartment-specific unit effect removed, while building, feature, trend and
season contributions are retained. `fitted_rent_without_unit`,
`unit_deviation_dollars` and `unit_deviation_percent` are the same quantity on
the rent scale, using the posterior-median unit effect (an approximation of the
median without that effect, not a full posterior recomputation).

Why not the residual alone: the selected fits carry a per-unit random effect
and about 47% of fitted units have a single observation. For those units the
split between unit effect and residual is set by the prior variance ratio, not
by data. In the selected fit (`sigma` 0.066, `sigma_unit` 0.086) the residual
is a median 39% of the deviation for single-observation units. Ranking on the
residual therefore under-flags rarely listed apartments and hides omitted
features that the unit effect absorbs; penthouse and top-floor units with unit
effects of +0.4 to +0.5 and near-zero residuals are the clearest example in the
current queue. The extreme tail is unchanged (the Student-t likelihood already
places gross source errors in the residual), but only about 61% of the top
1,000 rows coincide between the two rankings.

Each row keeps both views: `residual_*` and `residual_rank` alongside
`unit_deviation_*` and `rank`, plus `unit_effect_log` (with its 95% interval),
`building_effect_log` and `unit_observations`.

## Contents

| Artifact | Meaning |
| --- | --- |
| `queue.jsonl` | Every fitted observation with source identity, links, layout fields, price basis, fitted values, both rankings, existing source-review kind and a description snippet |
| `summary.json` | Cohort counts, medians, singleton share, top-N overlap between rankings, warnings |
| `queue.html` | Self-contained page embedding the top `--page-limit` rows by deviation, the top by residual and every saved current capture; sort by any column, filter by scope, direction, minimum deviation, year, bedrooms and text, one row per unit |
| `complete.json` | Bindings: selection, fit and source manifest hashes, residual/group-effect/observation hashes |

Links are emitted only for `https://streeteasy.com/...` URLs derived from the
source listing ID and canonical unit URL. Description snippets come from the
selected fit's archived description bundle (latest capture per observation)
and are hash-verified; they are not re-fetched.

## Interpretation

A large deviation is a review signal for source errors, omitted features,
identity conflicts or price-basis problems (commercial offers, net-effective
asks, income-restricted or short-term products). It is an in-sample quantity
from a fit that includes the apartment's own evidence and is not a bargain
score or a prediction interval. Existing source-review notes are shown in the
`Review` column when the selection binds them; a blank cell does not certify
source accuracy.
