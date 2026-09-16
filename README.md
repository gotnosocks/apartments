# Chelsea apartments

One Python project for the StreetEasy scraper, durable raw archive, local archive browser,
rental explorer, and pricing model. Git and colocated Jujutsu track this repository.

Latest results: [September 8 Chelsea analysis](docs/analysis/chelsea-2026-09-08.md).
Updated coverage: [September 8 cloud preparation](docs/analysis/chelsea-2026-09-08-cloud-preparation.md).

[Point-in-time retention](docs/data/point-in-time.md) documents collection clocks,
append-only apartment attributes, and the evidence available at a historical cutoff.
[Human correction overlays](docs/data/corrections.md) preserve source values alongside
audited edits, effective dates, and reproducible correction versions.

## Setup

Python 3.12 or newer is required by the current model dependencies.

```sh
cd ~/code/apartments
uv sync --extra dev --extra app --extra model
```

Optional direct Firefox transport: add `--extra browser`. Oxylabs credentials belong
in the ignored, owner-only project `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`.
The existing local credentials have been moved here; do not put them in Git.

## Collect and browse

The browser reads a local archive. Cloud browsing and automatic browser checkpoints
are not enabled; download a cloud snapshot manually when needed.

```sh
uv run streeteasy-archive status
uv run streeteasy-archive serve --port 8765
uv run streeteasy-archive resume --transport oxylabs --max-requests 100
```

The default raw archive is `data/archive`. Its SQLite queue, compressed response
bodies, crawl scope, and cooldowns moved together from the former standalone
repository. The archive browser at http://localhost:8765 reads this live archive.
The saved Chelsea profile retains its concurrency and rate settings. Scraping
resumes its durable queue; it does not restart from zero. An exhausted scoped
queue means discovered pages were handled, not proof of complete historical coverage.
Use `streeteasy-archive --help` for bounded backfill and update options.

Backfills now open **View unavailable units** and follow its rental/sale detail
links, in addition to the current units and their price-history links. This uses
Oxylabs browser instructions for inventory pages; ordinary detail pages continue
to use server HTML. `update` defaults to current-only discovery; pass
`--include-unavailable` to include historical inventory, or
`--no-include-unavailable` to explicitly disable it. `resume` remembers the mode
and scope. Full price history already present on a fetched detail page is always
retained, even in current-only mode.

```sh
# Repair/extend a building backfill without resetting completed pages:
uv run streeteasy-archive backfill --building https://streeteasy.com/building/the-sierra-chelsea --transport oxylabs
# Resume that saved building and mode, optionally with a request budget:
uv run streeteasy-archive resume --max-requests 100
# Use the historical discovery for Chelsea instead:
uv run streeteasy-archive backfill --neighborhood chelsea --transport oxylabs
# Once the prior crawl is complete, start a lean new observation pass:
uv run streeteasy-archive update --neighborhood chelsea --transport oxylabs
```

Expanded inventories have separate archive keys such as
`?archive_view=unavailable-rentals`. This is an internal capture identifier, not a
StreetEasy query parameter: the transport visits the base building URL and opens
the requested panel. Raw expanded HTML, table rows, source totals, fetch time,
and provider instructions are retained. A missing panel or incomplete row count
creates a resumable coverage error instead of silently reporting success.

The September 8 repair test captured all 393 unavailable rental inventory rows
for Sierra Chelsea, followed four detail pages, and imported four additional
units (12K, 3B, 4C, PHD). The database grew from four to eight Sierra units;
the remaining detail/history queue still requires a backfill run. Inventory rows
are listing episodes, not necessarily distinct physical units. The earlier
Chelsea model is therefore based on incomplete building coverage and should be
refit after the expanded backfill is imported.

## Import and analyze

For this laptop, use the [Modal processing workflow](docs/data/modal-processing.md)
for bulk import, coverage audits, preparation, and fitting. The commands below
remain available for small local imports and browsing.

```sh
uv run apartments import-archive
uv run apartments summary
uv run streamlit run app.py --server.port 8501
```

The importer reads the raw archive locally and writes `data/apartments.duckdb`.
It imports full embedded rental history, including rows hidden behind Show more,
and preserves raw event objects and links to original response bodies. Sale data
stays in the raw archive and is excluded from rental analysis. Each capture and
its import marker commit atomically; failures remain retryable. Subsequent passes
skip both imported captures and already classified non-rental pages.

The rental explorer discovers its buildings from the database. Its Bayesian Model
page reads generated model artifacts. Original manual browser capture imports
remain available through `apartments import-captures`.

## Storage and provenance

- `src/streeteasy_archive/`: scraper and archive browser, installed by this project.
- `src/apartments/`: normalization and analysis ingestion.
- `data/archive/`: authoritative SQLite catalog and content-addressed compressed bodies.
- `data/apartments.duckdb`: derived rental records, snapshots, and historical events.
- `data/model/`: reproducible model inputs, posterior draws, diagnostics, and summaries.
- `models/rent_model.py`: pricing model; use `--help` for fit settings.
- `docs/archive/`: historical scraper design/validation notes; paths and access observations there reflect earlier revisions.

All data and credentials are excluded from version control. Back up the complete
archive with its writer stopped. Reprocessing archived HTML needs no StreetEasy
requests. Apartment attributes use the newest listing episode rather than whichever
historical page happened to be scraped last. Historical renovations/layout changes
can still make constant unit attributes an imperfect description of old listings.

## Development

```sh
uv run --extra dev pytest -q
jj status
git log --graph --oneline
```

The consolidation/model experiment is on `feature/chelsea-analysis`; the preceding
version is preserved at `archive/pre-chelsea-model-20260908`. The scraper history is
part of this repository's commit graph. There is no nested scraper project to install.

## Chelsea pricing model

```sh
uv run --extra model python models/rent_model.py --validate-from 2026-01-01 \
  --validation-draws 2000 --validation-tune 1500
```

The default fits all available history as monthly unit-level median prices. It
replaces the five-building model with pooled effects for every eligible building
and unit, a shared time trend, categorical floors including unknown floors, and
bedroom/bathroom/size controls. Unsupported first-digit floor guesses are treated
as unknown. Units with explicit furnished or Blueground evidence anywhere in the
archive are excluded entirely. Missing floor and size values do not remove units.
The likelihood is Student-t on log asking rent. The index is rebased to January
2022 when the modeled span includes that month.

`--validate-from` also fits a separate model withholding prices from that date,
then compares it with a last-observed-unit-rent baseline. This is a retrospective
price test: apartment characteristics and size scaling use the captured data, so
it is not a fully time-causal backtest. Each run saves training data, posterior
draws, convergence diagnostics, coverage, and output tables in `data/model/monthly`.
The model page in the analysis app reads these outputs. Sparse early years and
selective public listing histories limit interpretations as a Chelsea market index.
