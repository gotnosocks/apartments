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

Open the local URL printed by Streamlit. The app includes all-unit history,
monthly building trends, a Bayesian building index, latest-rent and square-footage
comparisons, unit detail, and data-quality views. Units `7` and `8` are excluded.

## Bayesian model

The primary PyMC model uses observations from May 2019 onward, aggregates to one
median asking rent per unit-week, and estimates a latent weekly building trend
with 95% credible intervals. A separate monthly model is retained as a sensitivity
test. Historical furnished eras begin at the first explicit
`Listed by The Blueground` event; uncertain management-to-Blueground transition
windows are omitted. The model includes controls for bedrooms, square footage,
missing square footage, and unit random effects.

```bash
uv sync --extra app --extra model
uv run python models/rent_model.py --frequency weekly
uv run python models/rent_model.py --frequency monthly
```

Outputs are written to `data/model/` and displayed in the Streamlit **Bayesian
model** tab. The furnishing timeline is evidence-based but does not prove the
underlying landlord/tenant relationship or exact furniture-installation date.
