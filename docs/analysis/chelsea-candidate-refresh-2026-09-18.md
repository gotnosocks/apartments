# Chelsea candidate refresh, September 18, 2026

A bounded Oxylabs pass refreshed **23 previously eligible ACTIVE advertisements**
between approximately 17:20 and 17:22 UTC. All 23 requests returned HTTP 200 and
passed advertisement and canonical unit identity checks. Provider metadata records
**23 API submissions**, below the frozen ceiling of 69; there were no retries,
parse failures or identity quarantines.

The project's `.env` credentials loaded successfully without being printed or
copied into the run artifacts. All collection went through Oxylabs. A one-target
preflight completed before the remaining batch, and completed-run replay verified
the same snapshot without submitting another request.

## What changed

| Fresh source status | Advertisements |
| --- | ---: |
| ACTIVE | 13 |
| RENTED | 5 |
| NO_LONGER_AVAILABLE | 4 |
| IN_CONTRACT | 1 |

Ten previously ACTIVE advertisements now report a status excluded from candidate
selection. One remaining ACTIVE advertisement, `5154603`, reduced its gross ask
from **$7,950 to $7,500**. These are observed source changes between the older and
new captures; their exact effective times are not inferred from the collection
timestamps. Both captures remain available.

The plan started from the verified September 18 16:00 UTC candidate snapshot,
whose recent ACTIVE captures dated from September 12. Its no-budget selection
contains 23 eligible advertisements. An additional two furnished advertisements
and one with a known concession were excluded. Another 271 stale advertisements
were outside this refresh scope. No new-listing discovery was performed, so the
result is not a census of available Chelsea rentals.

## Effect on the illustrative search

The same demonstration preferences assign $600 per bedroom, $100 for an elevator,
and $150 for in-unit laundry. These are not the user's preferences. The model is
unchanged: the verified September robust fit trained through August 2026.

At the recorded scoring cutoff `2026-09-18T17:23:00Z`, with a one-day capture-age
limit and $6,000 budget, the new captures yield:

| Outcome | Count |
| --- | ---: |
| Input fresh captures | 23 |
| Inactive source statuses excluded | 10 |
| ACTIVE but over budget | 6 |
| Selected canonical units | **7** |
| Enough known attributes for the example preferences | **4** |
| Pareto-efficient units under those preferences | **3** |
| Separate market point comparisons | **7** |

The earlier example selected 14 units, with 10 preference-eligible and three on
the frontier. Two of those earlier frontier units now report RENTED or
NO_LONGER_AVAILABLE. The fresh example's three frontier units are:

| Source unit | Gross monthly ask | Bedrooms | Elevator | Laundry |
| --- | ---: | ---: | --- | --- |
| 270 West 25 Street, 1A | $4,550 | 1 | Yes | In building |
| 250 West 15 Street, F | $3,995 | 0 | Yes | In building |
| Ruby Chelsea, N16K | $5,110 | 0 | Yes | In unit |

Frontier membership follows only the stated preference dimensions and prices.
It does not rank unvalued location, layout or other differences, and does not use
the model prediction as the renter's willingness to pay. Source-reported ACTIVE
status at capture is not a guarantee of future availability.

Six selected units were seen in model training; one is a new unit in a known
building. None of these seven advertisements overlaps the training advertisement
IDs, although prior advertisements for the same unit may contribute to its unit
effect. These are conditional research-model comparisons, not independently
validated valuations. No calibrated prediction intervals are served.

## Reproduction and evidence

- Refresh run: `data/probes/chelsea-candidate-refresh-20260918`.
- Plan SHA-256:
  `7c2385c6c3686e7840e33860c6635c862c56765d68677a1cfb19f4d86c031add`.
- Fresh candidate SHA-256:
  `a20c42d2ff674517bc3961d9afef0e5ae5240833bd681b1ceef55be291b874c3`.
- Ranking bundle: `data/model/chelsea-refreshed-search-20260918`.

The [refresh guide](../data/candidate-refresh.md) documents collection, bounded
retries, crash recovery, frozen corrections, response retention and failure rules.
The [scoring guide](../model/robust-candidate-scoring.md) documents the independent
preference and market calculations. To reproduce this ranking:

```sh
uv run --locked python -m apartments.cli score-apartments \
  data/probes/chelsea-candidate-refresh-20260918/snapshot/candidates.jsonl \
  config/example-search-preferences.json \
  data/model/chelsea-serving-20260918-v3/model \
  data/model/chelsea-refreshed-search-20260918 \
  --as-of 2026-09-18T17:23:00Z --max-age-days 1 --budget 6000
```

The exact command replayed successfully against the completed bundle. The full
regression suite passed **531 tests, with two skipped**. New cases cover partial
preflight/resume, zero-request completed replay, rebuilding a missing interpretation
from archived bytes, request metadata redaction, changed source status/price,
wrong-unit and HTTP failures, interrupted uncertain submissions, persistent blocked
response pauses and effective-dated corrections on new captures.

Current discovery coverage, renter-specific preferences, calibrated uncertainty
for unfamiliar buildings, and prospective model evaluation remain separate work.
