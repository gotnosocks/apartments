# Chelsea apartment data

Local StreetEasy capture and NYC rental-analysis pipeline.

## Setup

```bash
uv sync --extra dev
uv run apartments init
uv run apartments fetch-nyc
```

See [`browser-extension/README.md`](browser-extension/README.md) to install the
manually initiated browser capture extension.

## Storage

- `data/captures/`: immutable rendered HTML, structured JSON and page assets
- `data/apartments.duckdb`: queryable building, listing, history, capture and asset tables
- `data/exports/`: optional analytical exports

Capture files and the active database are excluded from Git.

## Ingest captures

```bash
uv run apartments import-captures data
uv run apartments reparse-history data
uv run apartments infer-furnishing-periods
uv run apartments summary
```

The import is idempotent. Raw captures remain the source of truth and can be
reparsed later as the parser improves.

## Interactive analysis

```bash
uv sync --extra app
uv run streamlit run app.py
```

Open the local URL printed by Streamlit. The main rental explorer includes
all-unit history, monthly trends, latest-rent and square-footage comparisons,
unit detail, and data-quality views. The Bayesian analysis is a dedicated page
in Streamlit's sidebar navigation and includes observed-versus-fitted, temporal
residual, and outlier-table diagnostics. Units `7` and `8` are excluded.

## Bayesian model

The PyMC model combines The Sierra Chelsea and neighboring Stonehenge Gardens
from May 2019 onward, aggregates to one median asking rent per building-unit-week,
and estimates a shared latent weekly local trend with 95% credible intervals plus
a time-constant adjusted building offset. Every unit with any confirmed Blueground furnished period
is excluded entirely, including its earlier conventional-rental history; the model
therefore has no furnished covariate. Cumulative indicators estimate the first-bedroom and
incremental second-bedroom premiums. Floor effects cumulatively sum adjacent-level
changes under a shared shrinkage prior. Marketed and physical floor numbers are
stored separately: because Sierra has no marketed floor 13, marketed floors 14 and
15 map to physical floors 13 and 14. The same building configuration classifies
Sierra A–J as garden-facing, K as both-facing, and L onward as street-facing
(called skyline in Sierra marketing). Stonehenge facing remains neutral pending
a verified courtyard/14th Street stack map. These rules come from `config/building_overrides.json`
during capture ingestion rather than model-specific SQL. The model also controls
for square footage, missing square footage, and unit random effects.
Sampling uses Nutpie's NUTS
backend with four chains.

```bash
uv sync --extra app --extra model
uv run python models/rent_model.py --frequency weekly
```

Outputs are written to `data/model/` and displayed on the dedicated Streamlit
**Bayesian Model** page.
