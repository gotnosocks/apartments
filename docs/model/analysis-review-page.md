# Review Bayesian contributions, residuals and source evidence

The **Contributions and Residuals** page opens the PyMC posterior selected in
`config/main-analysis.json`. It verifies the model, analytical dataset, archived
source descriptions and any attached source-review notes. It does not scrape,
fit or edit source data.

From the repository root:

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync streamlit run app.py
```

Open **Contributions and Residuals** from the sidebar. The September 19 selection
uses `chelsea-bayesian-current-floor-disk-20260918` on
`chelsea-reviewed-current-analysis-20260918`: 52,863 observations, 22,189 units,
1,131 buildings and 172 current captures. Its descriptions come from
`chelsea-refreshed-bayesian-descriptions-20260918`; eight individual source reviews
come from `chelsea-current-residual-source-review-20260918`.

This is a saved sample, not live availability or complete Chelsea market coverage.
The default table shows up to 100 current observations; raise the row limit to
500 to show all 172. Search by advertisement ID or unit URL, filter by building,
or inspect the entire historical cohort. Residual percentages use fitted median
rent as the denominator. Current asking prices participated in fitting, so these
are in-sample residuals, not independent prediction errors or bargain scores.

## Source conflicts stay visible

The listing table names individual source reviews. The selected apartment shows
the review explanation alongside its estimates; count conflicts also receive a
warning in the feature-comparison tab. Blank review cells do not certify accuracy.
Review notes cannot attach to a different model or dataset: their fit, source,
residual values and exact literal captures must match. An invalid review stops the
page rather than silently disappearing. A selected review requires its matching
description archive.

For example, advertisement 5155021 has conflicting studio and one-bedroom claims.
The page preserves its recorded count and supports conditional scenarios while
warning that a closer fitted price cannot resolve the source contradiction.
[The current source review](../analysis/chelsea-current-fit-and-residual-review-2026-09-19.md)
explains the evidence and limitations. Later historical floor and laundry
corrections are published separately and have not yet been fitted.

## Contributions and joint feature scenarios

The apartment view shows asking rent, a posterior interval for its conditional
median rent, residuals and unit history. Posterior **mean log contributions** sum
to mean log rent. They are not additive dollar allocations or sums of posterior
medians. Building and unit effects can absorb omitted amenities and data problems.

Change one or more recorded attributes together. The model re-encodes bedroom,
bathroom, area, amenity and floor terms while holding date, building/unit offsets
and unspecified inputs fixed. It uses the retained joint posterior for intervals
and checks endpoint support and contrast diagnostics. Unsupported, reporting-only
or diagnostically unreliable scenarios do not receive physical-value intervals.

These are conditional associations, not causal renovation returns or personal
willingness to pay. Missing area uses bedroom-specific reference-area encoding;
a bedroom scenario with missing area is not a fixed-square-footage comparison.
The selected floor specification uses threshold increments. Sparse supported
levels, gaps and limited within-building overlap constrain interpretation;
listed labels do not establish physical height.

## Captured text and verification

The source tab displays literal archived descriptions, original body/record
hashes and collection/interpretation clocks. Historical description captures can
postdate prices; neither capture nor review timestamps establish when a physical
attribute changed. StreetEasy links may now show different content.

`apartments.bayesian_analysis.BayesianAnalysis` verifies the saved posterior and
reconstructs its design. `apartments.bayesian_source_review` binds source notes to
that fit, its unchanged input rows and literal capture archive. Selection and
Streamlit caches invalidate on changed bundle metadata; loading verifies content
hashes. Reload the saved analysis explicitly after selecting another fit.

The real-data AppTest in
`data/model/chelsea-current-main-page-validation-20260919` verifies all 172 current
rows, eight review notes, the studio/one-bedroom warning and the joint scenario
showing a $3,665 conditional median. It uses the actual posterior and source
archives without model/evidence mocks. Focused tests also cover stale reviews,
changed counts/prices/captures, missing evidence and failure without fallback.
Persist corrections through the versioned [correction workflow](../data/corrections.md).
