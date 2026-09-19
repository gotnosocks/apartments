# Bounded detail collection from reviewed rental discovery

`apartments.discovery_detail_refresh` connects the reviewed search queue to the
existing Oxylabs capture engine. It verifies both the queue and the underlying
page-report manifest, reconstructs every in-scope card occurrence, and rejects
changed evidence, identity conflicts, missing advertisements or silent truncation.
Furnished and concession offers are collected; product eligibility belongs after
collection. No building, search or other URLs are added while the plan runs.

The collector requests `/rental/<observed advertisement ID>`, an existing supported
StreetEasy route that identifies the advertisement independently of listing
turnover on a unit landing page. It preserves every observed search link and its
source evidence. The detail response must match the advertisement ID and every
known unit/building identity. If the search only supplies an advertisement URL,
the physical-unit identity remains unknown until the detail page's canonical
unit link is verified. A conflicting response is a failure, not an inferred alias.

This matters for the September 18 queue: its 213 entries include **204 unit URLs
and nine advertisement routes**, despite the old review field being named
`canonical_unit_url`. The initial review's count of 213 distinct canonicalized
links was not a verified count of physical units. The new plan treats those nine
unit identities as unresolved. Existing analytical unit identities were not
changed by this clarification.

## Prepare, preflight, and resume

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m apartments.discovery_detail_refresh \
  --review data/model/chelsea-current-discovery-pass-review-20260918 \
  --discovery-report data/probes/chelsea-rental-discovery-live-20260918/reports/6db4e5a16e7236d42c46f11c4dc3c783de469e00243c30ca5baa9a8319b7efe0 \
  --output data/probes/chelsea-discovery-details-20260918 \
  --max-targets 213 --plan-only
```

Remove `--plan-only` and add `--max-new-requests 1` for a single-target preflight.
Remove that preflight limit to continue the same frozen plan. `--max-targets`
bounds the complete target inventory (maximum 500), never truncates it. The
Oxylabs handler permits at most three provider submissions per target, so this
213-target plan has a hard ceiling of 639 submissions including the preflight.
This is a request ceiling, not a quoted cost. Rendering is off and submissions
are sequential, at no more than one per second. The project `.env` supplies
credentials; secrets are excluded from archived metadata and source control.

The existing capture engine now exposes `execute_prepared`, allowing the old
candidate-refresh selector and the new discovery selector to share durable
request intents, raw-response archiving, source challenges/authentication pauses,
body-hash verification, result checkpoints and interruption behavior. Uncertain
interrupted requests are not automatically repeated. A saved raw response can be
reinterpreted without another paid request. Completed checkpoints are reused.
Any plan/code change prevents resuming in the old directory.

All successfully parsed statuses are retained, including RENTED and inactive
outcomes. A failure does not restore an older ACTIVE claim. Search-card
attributes are not represented as a previous full apartment record; initial
detail captures have empty change tables and an explicit `change_basis`.
Candidates carry `discovery_provenance` as well as capture/interpretation clocks
and the normal raw-response provenance. Source attributes remain uncorrected in
this collection step; subsequent versioned transformations apply review overlays.

The outputs use the existing bounded refreshed-candidate snapshot contract.
They do not automatically replace a fitted cohort or selected model. Review
identity, status, price terms, duplicate active advertisements and source scope,
then transform and fit before analysis. Missing search results are not evidence
of inactivity, and this finite queue is not a Chelsea census.

Validation: **92 tests pass** across old/new refresh, candidate snapshot,
discovery orchestration and search parsing. The new tests exercise advertisement
versus unit identity, changed source evidence, no product filtering at collection,
preflight/resume/replay, inactive statuses, wrong unit/building/advertisement
responses, durable blocked-response pauses and uncertain-request preservation.

## September 18 live plan

Plan SHA-256: `733fa30f351c14db0cb74a46cfebfa68416d29f3be6a1526e180bf2ac2790e75`.
The one-target preflight completed successfully at 00:33 UTC on September 19
(September 18 locally): advertisement 4547048 resolved to Chadwin House #6D,
ACTIVE, $6,555 gross asking rent, matching the discovered identity and price.
The complete plan finished at 00:45:56 UTC: **213 provider submissions, all HTTP
200, with no retries**. Of these, 204 passed canonical-unit projection: 201 ACTIVE,
one DELISTED, one NO_LONGER_AVAILABLE and one RENTED. The nine advertisement-only
canonical links remain unresolved; all raw responses are retained. A completed
replay with network calls disabled reused the checkpoints without requests.

The verified completion review selects **168 units** under the existing
seven-day, unfurnished, no-concession eligibility policy. It excludes 22 for
concessions, 11 for furnishings and three for inactive status. Of the selected
units, 137 occur in the reference cohort; all selected buildings occur there.
These are candidate-selection results, not a newly transformed or fitted cohort.
The four earlier current advertisements absent from this discovery pass are not
declared inactive. The running Bayesian fit remains frozen to its earlier source.

Completion evidence is in
`data/model/chelsea-discovery-detail-completion-review-20260918`; the publisher
verifies raw bodies, result/plan bindings, snapshot rows and the read-only
transport ledger. The [identity review](../analysis/chelsea-discovery-detail-identities-2026-09-18.md)
records the nine unresolved responses without merging units.
