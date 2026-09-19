# Spatial candidates for the complete reviewed cohort

Verified building coordinates now cover **all 52,653 observations, 22,155 units
and 1,129 buildings** in the 210-exclusion source candidate, including all 172
current listings. This extends the earlier current-only location inventory.
No new scraping or geocoding was required, and no model has been refitted with
these candidates.

The extraction checks 71,641 historical listing captures against the exact
historical archive inventory. Every capture must match its own raw listing ID,
raw building ID, canonical unit URL, analytical building slug and retained source
membership. It also verifies the historical target against its original record.
The correct archive is `chelsea-granular-20260917-canonical-url-v1`; the similarly
named `canonical-units` transform has different hashes and was rejected.

The building evidence comprises **1,613 archived building-page captures** plus
the previous **172 verified current-listing captures**. Building pages are read
from the original compressed archive, decompressed and checked against the
snapshot's body hash. Their Flight records are decoded, including spatial and
address references. The extractor preserves both the original field path and
reference target path. Missing/cyclic references and conflicting coordinate
channels remain explicit failures; text records beginning with `$` stay literal
text. The old building pages use referenced fields that the current-only reader
did not need to resolve, so reusing that reader without this step was insufficient.

All 1,785 location captures agree within their matched buildings. The resulting
artifact contains raw latitude/longitude and offsets in degrees from the equally
weighted building center **40.7442066811, −73.9996485633**. That center is a
cohort summary, not a geographic NYC centroid, and the offsets are not distances
in meters. The recorded interpretation clock is **2026-09-19T08:30:50Z**.
Location interpretation is retrospective: it does not establish a building's
footprint at every historical advertisement date.

## Street features and model support

Simple literal-address parsing yields **25 street labels**. It removes a leading
house number and normalizes case/whitespace. It does not resolve aliases or
certify street names against an official registry. In particular, `6th avenue`
and `avenue of the americas` remain separate labels in this artifact.

Two labels have only one building each: `avenue of the americas` (695 Avenue of
the Americas) and `chelsea square` (4 Chelsea Square). Each has 13 observations;
those repeated observations do not supply independent buildings for estimating
a street association. Literal building addresses do not identify a particular
apartment's window exposure or street-facing view.

The two coordinate columns plus 25 street indicators have rank 27 on the building
table. Their additional rank after building indicators is **zero**: every
observation's spatial row is exactly its building's row. The artifact checks this
identity without constructing a large dense incidence matrix. An intercept plus
all 25 unmodified street indicators would also be redundant; a fitted design
would need an explicit contrast/reference representation.

This does not automatically rule out spatial modeling. It means the separation
between location and the remaining building effect depends on hierarchical
structure and priors. Given the project's focus on known buildings and feature
contributions, adding location solely to improve unseen-building predictions is
not the objective. The next useful test is whether the existing building-effect
posterior has spatial patterns that motivate a location term or structured
building prior, followed by a controlled PyMC fit and a sensitivity analysis of
amenity contributions and residuals. A coordinate coefficient should not be
presented as an independently identified location premium.

## Reproduction and checks

Artifact: `data/model/chelsea-cohort-spatial-candidates-20260919`. It contains all
capture evidence, per-building candidates, historical listing bindings, exact
source-file hashes, a coverage/rank report and frozen extraction code. Original
source files, input manifests and implementations are checked again before
publication. The source dataset and selected main model remain unchanged.

**26 tests pass** across current/cohort spatial extraction. They include actual
Flight decoding from a generated HTML page, historical listing/building joins,
raw-body and snapshot-URL failures, exported-coordinate disagreement, typed
capture identity, reference cycles, coordinate-versus-street conflict handling,
equal-building centering, and identical full-pipeline replay. These checks
establish extraction behavior; they do not establish spatial model performance.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  uv run --frozen --no-sync python -m models.cohort_spatial_features \
  --dataset data/model/chelsea-reviewed-price-basis-complete-analysis-20260919 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --bodies /data1/apartments/archive/bodies \
  --current-spatial data/model/chelsea-current-spatial-candidates-20260918 \
  --interpreted-at 2026-09-19T08:30:50Z \
  --output data/model/chelsea-cohort-spatial-candidates-20260919
```
