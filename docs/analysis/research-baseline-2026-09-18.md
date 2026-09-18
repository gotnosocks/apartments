# September 18 research pipeline verification

This run verifies the new capture/overlay/analytics/model boundary. It does not
establish NYC-wide price effects or forecasting accuracy.

## Collection smoke test

The newly configured local `.env` loaded successfully. A one-document Oxylabs
backfill for Sierra Chelsea returned HTTP 200 and archived one successful
observation, with redacted provider metadata and 122 pending discovered pages.
The isolated archive is `data/probes/intent-20260918`. No additional crawl is
running and the authoritative archive was not modified by this test.

## Frozen-data descriptive pilot

Source: `/data1/apartments/archive/snapshots/chelsea-20260908/apartments.duckdb`.
Knowledge cutoff: `2026-09-18T15:00:00Z`. Ledger:
`config/corrections.jsonl`, empty at this cutoff.

Analytical output: `data/exports/research-baseline-20260918`.
Pricing output: `data/model/research-baseline-20260918`.
Both contain hashed completion manifests. Repeating both commands with the same
inputs produced identical manifests and verified existing artifacts.

| Stage | Records |
| --- | ---: |
| Retained attribute intervals | 2,951 |
| ACTIVE contemporary asking-price observations | 444 |
| Quarantined/excluded price observations | 2,507 |
| Explicit dated correction assertions | 0 |
| Explicit furnished observations excluded from model | 22 |
| Explicit concession observations excluded from model | 44 |
| Repeated eligible unit/month captures removed | 155 |
| Modeled source units | 223 |
| Building labels | 115 |

The model converged in 1,371 coordinate-descent iterations at ridge strength 1.
It is explicitly descriptive (`holdout_fraction=0`): collection dates cover only
September 7–8. Time trend and seasonality are frozen, and no holdout accuracy is
claimed. Training MAE is approximately $564/month and training median absolute
percentage error is 5.39%; these are fitted-sample diagnostics, not evidence of
predictive performance.

Bedrooms and bathrooms are observed for all 223 modeled rows; area for 99.
Physical floors and south-facing windows are unknown for all 223. Elevator is
positively reported for 181 and unknown for 42, with no observed explicit
negative comparison group. This sample therefore cannot support the requested
floor, exposure or independently identified elevator premiums. Coefficients and
counterfactual warnings preserve that distinction.

The source IDs in this pilot are advertised source-page identities. They are
not independently verified physical apartments. The existing larger granular
dataset requires verified membership artifacts and an explicit adapter before
being presented as this pipeline's canonical-unit input. The current analytical
builder materializes its selected observations in memory; a streaming or
partitioned adapter is needed before scaling it to the complete NYC archive.

## Validation

Final repository regression result: **394 passed, 2 skipped**, in 20.55 seconds.
`git diff --check` passed. The offline suite ran outside the filesystem sandbox
because its asyncio executor shutdown hangs inside that sandbox.

Tests cover knowledge cutoffs, the studio-to-one-bedroom historical assertion,
correction conflicts, original-evidence retention, deterministic reruns, integrity
checks, train-only encoding, temporal holdouts, frozen unsupported time effects,
floor/elevator interaction contrasts, unknown amenities, and signed-dollar Pareto
comparisons. The full regression run and the live Oxylabs smoke test are separate:
the regression suite uses offline fixtures.
