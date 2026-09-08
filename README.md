# Chelsea apartments

One Python project for the StreetEasy scraper, durable raw archive, local archive browser,
rental explorer, and pricing model. Git and colocated Jujutsu track this repository.

## Setup

```sh
cd ~/code/apartments
uv sync --extra dev --extra app --extra model
```

Optional direct Firefox transport: add `--extra browser`. Oxylabs credentials belong
in the ignored, owner-only project `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`.
The existing local credentials have been moved here; do not put them in Git.

## Collect and browse

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

## Import and analyze

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
