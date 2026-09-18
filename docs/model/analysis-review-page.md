# Review contributions, residuals and source evidence

The **Contributions and Residuals** page makes the current reviewed Chelsea model
inspectable without fitting, scraping or modifying data. It opens with the saved
current sample and can search the entire fitted cohort by advertisement ID or
unit URL. Positive residuals mean asking rent exceeds fitted rent; percentages
use fitted rent as the denominator.

From the repository root, run:

```sh
uv run --locked --extra app streamlit run pages/2_Contributions_and_Residuals.py
```

The page is also available in the sidebar when running the existing `app.py`.
Its default bundles are:

- Model: `data/model/chelsea-reviewed-analysis-20260918-v3/model`.
- Training dataset: `data/model/chelsea-reviewed-analysis-20260918-v3/dataset`.
- Residuals: `data/model/chelsea-interior-reviewed-residuals-20260918`.
- Archived descriptions: `data/model/chelsea-analysis-descriptions-20260918`.

The supplied model contains 52,712 observations, including 13 current captures
from September 18. That is a bounded saved sample, not live availability or
complete Chelsea market coverage. The sidebar accepts another compatible set of
bundles and provides an explicit reload button. Blank the description path to
review model diagnostics without a description archive.

## Follow an apartment's residual

Filter the saved current sample or all fitted observations, choose a building,
and search an advertisement or unit URL. Review order can prioritize absolute
residuals, asks above fitted rent or asks below it. The optional one-observation-
per-unit filter prevents repeat advertisements from filling the queue.

For the selected observation, the page shows asking rent, fitted rent, the
residual and the apartment's fitted history. Grouped log contributions include
layout, size, building/unit effects, calendar terms, amenities and missingness.
The reference component is shown separately so it does not flatten the other
bars; the full sum still reconstructs log fitted rent. Exact components remain
available for inspection.

These terms describe the saved parameterization. Building/unit effects may
absorb missing amenities, and a small residual does not establish complete
measurement. A large residual is a source-review signal, not a correction or a
bargain score. All displayed observations contributed to the fit.

## Compare explicit feature changes

Select one or more attributes and submit their joint changes. The portable model
re-encodes the apartment, including bedroom-dependent area normalization and
interactions. Identity, date, building/unit effects and unedited attributes stay
fixed. The comparison is a conditional asking-price association, not a feasible
renovation plan, causal return or personal willingness to pay.

For example, advertisement 5154892 has a $5,895 ask and a fitted rent of about
$6,422 in this model. Holding its other attributes fixed, changing recorded
building laundry to in-unit laundry raises fitted rent by about $321, or 5.00%.
The cohort has 285 buildings with known laundry variation. That support does
not by itself resolve confounding or convert the estimate into causal value;
the [earlier stability analysis](../analysis/chelsea-amenity-stability-2026-09-18.md)
is complementary evidence.

The interface withholds a feature-value estimate when a changed endpoint is
unknown, the feature has fewer than two known values, the destination lacks
categorical support, the numeric destination lies outside its observed range,
or the resulting bedroom/bathroom combination is absent from training. It shows
the reason and support counts instead. In particular, physical-floor data is
unobserved in the current fit; a zero encoded effect is not displayed as a zero
economic value.

Each comparison reports endpoint observation/unit counts, destination-building
counts, numeric ranges and within-building/unit variation. Those counts are
descriptive support, not independent sample sizes or confidence intervals.
Rare-category and group-identification warnings remain visible. The full feature
coverage table also exposes exposure families that contain only positive claims
and unknowns. Changing a feature does not edit the original observation.

## Inspect the actual captured text

The Source evidence tab shows the archived description for a selected capture,
its original body and parsed-record hashes, and collection and interpretation
clocks. Text is displayed literally, including any markup, rather than executing
source HTML. StreetEasy links are convenient references but may now show content
different from the saved capture.

The description archive is bound to this exact fitted dataset and preserves all
its source captures, including explicit records without usable text. Historical
description captures can postdate their associated price events. Neither capture
time nor description recovery time establishes when a physical feature changed.
Experimental outdoor classifications are not displayed as apartment facts.

The complete archive retains 71,922 captures: 71,386 have usable descriptions
and 536 explicitly lack text. Descriptions cover 52,297 observations, including
all 13 current rows; 415 historical observations have no usable description.
This inventory is independent of whether an advertisement mentions any particular
amenity. Its exact source-bound rebuild is:

```sh
.venv/bin/python -m models.analysis_description_archive \
  --dataset data/model/chelsea-reviewed-analysis-20260918-v3/dataset \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --recovery data/exports/chelsea-description-recovery-20260918 \
  --refresh data/probes/chelsea-candidate-refresh-20260918 \
  --output data/model/chelsea-analysis-descriptions-20260918
```

## Verification and implementation

`apartments.analysis_review.AnalysisWorkspace` verifies immutable bundle hashes,
model/dataset/residual binding, identity and target membership, residual arithmetic,
and selected-observation prediction parity. Description identity, capture membership,
text hashes and knowledge clocks are checked independently. A cache signature
includes every declared file's metadata, with full verification on reload.

Tests exercise joint re-encoding, normalized aliases, intentional unknown values,
unsupported physical-floor changes, unsupported layouts, numeric extrapolation,
source-text binding, tampering and residual mismatches. Streamlit AppTest exercises
the actual saved model, search, laundry comparisons, unsupported-value suppression,
no-op errors, archived descriptions and missing-bundle handling. No browser surface
was available for a rendered visual check.

The real-artifact check at
`data/model/chelsea-analysis-workspace-check-20260918-v2` retains all 13 current
details, eleven laundry contrasts, the feature-support table and code snapshots.
All current contribution sums reconstruct fitted rent within $0.000000000017;
all 13 unsupported physical-floor comparisons suppress feature-value estimates.
The complete description archive also passed exact replay.
The final full test suite passed **845 tests, with two skipped**.

The page is a read-only research view. Persisting review decisions still uses the
existing source-review and correction workflows described in
[current analysis](current-analysis.md) and [corrections](../data/corrections.md).
