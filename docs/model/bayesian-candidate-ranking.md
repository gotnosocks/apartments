# Current-listing preferences with PyMC diagnostics

`rank-current-apartments` connects an accepted PyMC fit to the
preference frontier. Since 2026-09-26 the repository selection is a frontier summary, which this
command refuses, so pass a PyMC selection with `--selection` (see
[current analysis](current-analysis.md)). It considers only current-capture observations already in
that fit, matching the scrape → transform → fit → analyze workflow. It never
substitutes the older robust model or predicts newly scraped units without a
refit.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache MPLCONFIGDIR=/tmp/apartments-mpl \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run --frozen --no-sync python -m apartments.cli rank-current-apartments \
  config/example-search-preferences.json data/model/my-current-ranking \
  --selection /data1/apartments/tmp/<you>/pymc-selection.json \
  --as-of 2026-09-19T09:26:27Z --budget 6000
```

The example assigns $600/month per bedroom, $100 for an elevator and $150 for
in-unit laundry. These numbers are illustrative, not inferred coefficients or
the user's stated preferences. Supply a JSON object with your own values. The
[preference contract](pricing.md#preference-and-frontier-contract) defines
supported attributes, category indicators and signed aversions. Budget is an
optional hard monthly-ask limit; capture age defaults to seven days.

Monthly surplus equals supplied preference benefits minus asking rent. Pareto
membership compares asking rent and each signed benefit, ignoring zero-valued
attributes. The frontier depends on those inputs, including attribute knownness,
and is independent of fitted prices, residuals and posterior interval widths.
An apartment can have a positive fitted residual and still be personally
preferred. A negative residual is not automatically a bargain.

## Data and uncertainty

Candidates must have source-reported ACTIVE status, supported gross asking-rent
basis, valid capture/knowledge clocks, sufficiently recent capture, and canonical
unit/advertisement identity. Conflicting active advertisements, stale captures
and known furnished/short-term/concession flags retain the existing candidate
exclusion rules. The cutoff controls source eligibility only: the selected fit
is the latest accepted posterior, so this command is retrospective analysis,
not a historical model backtest. Captured ACTIVE status does not guarantee that
an apartment remains available.

Each ranked unit is tied back to its exact fitted observation. The analysis
reconstructs its latent price from all retained joint posterior draws, checks
agreement with the saved residual product, and runs fresh derived diagnostics.
The separate market comparison contains the posterior median and 95% interval
for latent conditional median asking rent, plus its signed fitted residual.
It is neither a transaction estimate nor a posterior prediction interval.
The candidate's asking price contributed to the fit.

If the new derived diagnostics fail, market intervals and residuals are withheld
under `diagnostic_only`; the personal preference calculation can remain usable.
Source-review notes are verified against the selected source, posterior and
description archive. Known bedroom/bathroom conflicts mask that attribute only
for preference computation, retain the untouched source record and original
value in a withholding audit, and mark market interpretation
`source_review_required`. Unscoped interpretation-limiting notes exclude the
candidate until their scope is understood.
If compatible advertisements merge, a limiting source review on another merged
advertisement also excludes the unit; choosing one advertisement cannot hide
that conflict.

Missing or conflicted valued attributes exclude an apartment from the frontier
by default, while retaining its row and unknown keys. `--unknown-policy zero`
is an explicit alternative. It can favor missing attributes when the preference
is negative, so results preserve the unknown list. No coefficient or posterior
distribution fills a missing physical attribute.

## Saved results

The checksummed output contains `rankings.jsonl`, `excluded.jsonl`, `summary.json`,
the supplied preferences, exact selected-model record and implementation files.
Selection, source, fit, preference and source-review bindings are preserved.
The command verifies model/data bindings, reconstructs the saved design, and
refuses incomplete or unaccepted fits. It does not scrape, fit, change source
observations or select a new main model. Identical inputs and unchanged code
reuse the same output; changed inputs require a new output directory.

`score-apartments` retains the older robust-scoring interface for explicit legacy
work. `rank-apartments` ranks an independently supplied candidate snapshot. The
new command is the main path when using the selected PyMC analysis.

## Chelsea integration run, September 19

The actual selected-posterior run is saved as
`data/model/chelsea-main-bayesian-preference-ranking-20260919`, using the example
above. All 172 current observations entered selection; 95 exceeded the $6,000
budget. Of the 77 remaining units, 52 had known valued attributes and five were
Pareto efficient. One source-conflicted unit had its affected preference
attribute and market interpretation withheld. No other candidate failed the
fresh contribution diagnostics. Every comparison used all 24,000 joint draws.
These results demonstrate the workflow with illustrative preferences, not a
personal recommendation. Output checksums and withholding/frontier invariants
were verified on the published bundle.

Validation: 61 focused tests cover ranking, candidate selection, pricing and main-fit CLI routing,
including model-independent frontier membership, diagnostic/source withholding,
cutoff eligibility, exact fitted-observation identity, and the default
floor-increment specification.
The integration bundle predates the additional merged-advertisement review
guard. It merged zero advertisements, so that guard does not alter these results;
its conflict behavior is covered by a focused regression test.
