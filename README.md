# NYC apartment search and pricing

Collect, correct, and analyze NYC rental listings to explain asking rents and
compare apartments against an individual's willingness to pay for amenities.
Chelsea is the existing pilot. The [project intent](docs/project-intent.md)
defines the data contracts, temporal semantics, model scope, and research gates.

The main model is **hierarchical Bayesian PyMC**, using compiled sampling and
the saved joint posterior. The workflow is **scrape → transform → fit → analyze**,
emphasizing feature contributions and fitted residuals. The [current-analysis workflow](docs/model/current-analysis.md)
includes fresh observations in the fit. The [complete model-version report](docs/model/main-model-evolution.md)
records every major model generation, its equations, source revisions, model
changes and promotion rationale over time. A standalone [HTML version](docs/model/main-model-evolution.html)
is also included for browser reading. Research progress (the Pareto frontier
of held-out ΔELPD × fit time, and how it moved over time) is on the
[research dashboard](docs/dashboard.md) at http://thelio.tail3983e0.ts.net:8500,
rebuilt every 10 minutes from the run records.
The [current-listing ranking command](docs/model/bayesian-candidate-ranking.md)
connects that selected PyMC fit to personal preference frontiers, with separate
posterior price diagnostics and explicit unknown/source-conflict handling.
New main fits default to listed-floor threshold increments; `--linear-floor`
is available for explicit legacy research or replay.
The [first residual audit](docs/analysis/chelsea-residual-review-2026-09-18.md)
found concrete price-entry, commercial-scope and possible omitted-feature issues
to guide the next iteration.
The [Bayesian feature research](docs/model/bayesian-feature-research.md) examines joint
coefficient uncertainty and separate bathroom increments, supported by source
audits of [extreme group effects](docs/analysis/chelsea-group-effects-2026-09-18.md)
and [bathroom composition and access](docs/analysis/chelsea-bathroom-evidence-2026-09-18.md).
The [identification audit](docs/analysis/chelsea-bayesian-identification-2026-09-18.md)
documents sparse contrasts and dependence on group pooling. Focused reviews of
[floor plans](docs/analysis/chelsea-floorplan-visual-review-2026-09-18.md) and
[lease/product wording](docs/analysis/chelsea-lease-product-scope-2026-09-18.md)
separate new evidence from proposed model features.
The [parameter audit](docs/analysis/chelsea-bayesian-parameter-audit-2026-09-18.md)
challenges every representation and prepares listed-floor threshold increments;
only 364 retained observations currently have known listed floors.
The [first converged Bayesian results](docs/analysis/chelsea-bayesian-bathrooms-2026-09-18.md)
report credible intervals and the remaining source-quality and residual-scale issues.
The [prior-sensitivity comparison](docs/analysis/chelsea-bayesian-prior-sensitivity-2026-09-18.md)
finds stable common bathroom increments but a strongly prior-dependent second-half-bath term.
The [residual-scale follow-up](docs/analysis/chelsea-bayesian-residual-scale-2026-09-18.md)
records the failed noise experiment and the computational checks for its retry.
The [category comparisons](docs/analysis/chelsea-bayesian-category-sensitivity-2026-09-18.md)
translate joint draws into laundry, doorman, HVAC and pet-rule associations;
an unexpected doorman result prompted a [source overlap review](docs/analysis/chelsea-doorman-overlap-2026-09-18.md).
The [first cohort revision](docs/analysis/chelsea-reviewed-cohort-2026-09-18.md)
applies source-evidenced quarantines and compares residuals and feature contrasts
after refitting on the retained cohort.
The [interior-evidence iteration](docs/analysis/chelsea-interior-evidence-2026-09-18.md)
audits recurring ceiling/layout wording and records the latest reviewed fit.
The [matched interior experiment](docs/analysis/chelsea-interior-model-2026-09-18.md)
tests those claims against reporting controls and traces changed residuals to
private outdoor space and other omitted features.
The [outdoor comparison](docs/analysis/chelsea-outdoor-model-2026-09-18.md)
tests structured versus text-corroborated amenity claims across 18 matched fits.
Changed residuals expose both ambiguous source labels and missed access wording;
outdoor premiums remain sensitive to the evidence policy.
The [access-scope follow-up](docs/analysis/chelsea-outdoor-scope-2026-09-18.md)
separates source claims and tests them on previously unreviewed units. Independent
review still finds scope and access errors, so those claims remain review evidence.

The repository retains the StreetEasy scraper, durable raw archive, archive and
review browsers, and prior pricing experiments. New work connects immutable
captures and dated overlays to reproducible analytical inputs, interpretable
price contrasts, and preference frontiers. Git and colocated Jujutsu track the code.

Start with the [reproducible research pipeline](docs/data/research-pipeline.md)
for collection → corrections → dated analytics → model → preference ranking.
Its original baseline commands include `build-analytical`, `fit-pricing-legacy`,
and `rank-apartments`. Main `fit-pricing` now uses the verified Bayesian workflow
and requires a reviewed bathroom/source-composition projection.
For the full Chelsea history, `build-historical` uses the completed canonical
dataset with the [own-advertisement temporal contract](docs/data/historical-own-advertisement.md).
The older workflows below retain their original assumptions and data contracts.
The [September 18 baseline verification](docs/analysis/research-baseline-2026-09-18.md)
records the live Oxylabs check, deterministic rebuild, descriptive fit, and data gaps.
The [full-history Chelsea amenity pilot](docs/analysis/chelsea-amenities-2026-09-18.md)
adds audited historical reconstruction, earlier-year and unseen-building tests,
supported dollar contrasts, and offline description recovery.
The [recovery and validation follow-up](docs/analysis/chelsea-recovery-ablation-2026-09-18.md)
records full description recovery, extraction audits and matched missingness controls.
The [amenity stability report](docs/analysis/chelsea-amenity-stability-2026-09-18.md)
qualifies marginal estimates with model-setting sensitivity, building resampling
and numerical checks. The [feature-family comparison](docs/analysis/chelsea-feature-blocks-2026-09-18.md)
identifies the main sources of prediction improvement. The
[monthly validation results](docs/analysis/chelsea-monthly-validation-2026-09-18.md)
show the benefit of frequent updates and the failure of pooled prediction bands
for unfamiliar buildings.
The [model-to-search example](docs/analysis/chelsea-serving-example-2026-09-18.md)
connects the robust September model to capture freshness, advertisement identity,
and a preference frontier. See the [scoring guide](docs/model/robust-candidate-scoring.md)
for `build-candidates` and `score-apartments`.
The [Oxylabs refresh](docs/analysis/chelsea-candidate-refresh-2026-09-18.md)
rechecked 23 advertisements and rebuilt the example from fresh source captures;
the [refresh guide](docs/data/candidate-refresh.md) covers bounded collection and
resume behavior.

The primary project and archive now live on **thelio**, with the archive under
`/data1/apartments/archive`. See the [hosting and migration runbook](docs/operations/thelio.md)
for the verified cutover record and access to the review and archive browsers.
Migration completed on September 16 at 21:19 EDT; Modal retains a frozen backup.
Direct Tailscale access: [research dashboard](http://thelio.tail3983e0.ts.net:8500/) ·
[raw archive](http://thelio.tail3983e0.ts.net:8765/).

Earlier baseline: [September 17 minimal canonical-unit model](docs/analysis/chelsea-minimal-2026-09-17.md).
Earlier results: [September 8 Chelsea analysis](docs/analysis/chelsea-2026-09-08.md).
Updated coverage: [September 8 cloud preparation](docs/analysis/chelsea-2026-09-08-cloud-preparation.md).

[Point-in-time retention](docs/data/point-in-time.md) documents collection clocks,
append-only apartment attributes, and the evidence available at a historical cutoff.
[Human correction overlays](docs/data/corrections.md) preserve source values alongside
audited edits, effective dates, and reproducible correction versions.

## Setup

Use [uv](https://docs.astral.sh/uv/getting-started/installation/) to manage Python
and project dependencies. `.python-version` selects Python 3.12; `uv.lock` records
the dependency versions. Run commands from the repository root.

```sh
cd ~/code/apartments
uv sync --locked --extra dev --extra model
```

Run Python and project tools through `uv run --locked`; uv manages the environment
and installs the project, so activation and `PYTHONPATH` overrides are unnecessary.
Select extras explicitly when running optional tools: `--extra model` for modeling
and Parquet processing, `--extra modal` for Modal,
and `--extra migration` for archive transfers. Include every extra you need when
running `uv sync`, which removes packages outside the selected dependency set.
For dependency changes, use `uv add` (with `--optional EXTRA` when appropriate)
and commit both `pyproject.toml` and `uv.lock`. Use `uv lock` after manual dependency
edits; routine `--locked` commands fail if the lockfile needs updating.

All listing scraping uses Oxylabs. Credentials belong in the process environment
or ignored, owner-only project `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`.
See `.env.example`; never put actual credentials in Git. The optional browser
package remains for legacy fixtures and debugging.

## Collect and browse

The browser reads a local archive. Cloud browsing and automatic browser checkpoints
are not enabled; download a cloud snapshot manually when needed.

```sh
uv run --locked streeteasy-archive status
uv run --locked streeteasy-archive serve --port 8765
uv run --locked streeteasy-archive resume --transport oxylabs --max-requests 100
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
uv run --locked streeteasy-archive backfill --building https://streeteasy.com/building/the-sierra-chelsea --transport oxylabs
# Resume that saved building and mode, optionally with a request budget:
uv run --locked streeteasy-archive resume --max-requests 100
# Use the historical discovery for Chelsea instead:
uv run --locked streeteasy-archive backfill --neighborhood chelsea --transport oxylabs
# Once the prior crawl is complete, start a lean new observation pass:
uv run --locked streeteasy-archive update --neighborhood chelsea --transport oxylabs
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

Run archive processing on thelio against `/data1/apartments/archive`, keeping
intensive work off the laptop. The [Modal processing workflow](docs/data/modal-processing.md)
is retained for reference; its old volume is now a frozen backup and does not
receive new thelio reviews or updates. Future cloud runs need an explicit upload
of their current inputs.

```sh
uv run --locked apartments import-archive
uv run --locked apartments summary
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
uv run --locked --extra dev --extra model --extra migration python -m pytest -q
jj status
git log --graph --oneline
```

The consolidation/model experiment is on `feature/chelsea-analysis`; the preceding
version is preserved at `archive/pre-chelsea-model-20260908`. The scraper history is
part of this repository's commit graph. There is no nested scraper project to install.

### Code style

Format all Python files with [ruff](https://docs.astral.sh/ruff/formatter/)
using its default settings. Format the files you create or change before committing:

```sh
uvx ruff format path/to/changed_file.py
uvx ruff format --check path/to/changed_file.py
```

Do not run `ruff format` over whole directories. Fit protocols record the SHA-256
of their implementation files, so reformatting a file hashed by a running or
selected fit aborts that fit or breaks verification of its saved results. Leave
those files unchanged; reformat them only after the fits that hash them are retired.

## Chelsea pricing model

```sh
uv run --locked --extra model python models/rent_model.py --validate-from 2026-01-01 \
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

### Granular data for the next model

The [granular cloud dataset](docs/data/granular-dataset.md) keeps individual fetches,
page versions, observed attributes, and every source history occurrence. Listing
episodes are links, not aggregation units. Temporal alignment, physical-unit
resolution, corrections at a selected effective time, and aggregation are explicit
model-stage decisions. The legacy monthly fitter remains separate.

The [September 16 full-data quality report](docs/data/chelsea-granular-quality-2026-09-16.md)
records the generated tables, missingness, source disagreements, and integrity checks.

### Thelio hosting

See [Thelio setup and migration](docs/operations/thelio.md) for archive paths, resumable transfer, validation, services, and SSH access. The primary-data cutover passed verification on September 16 at 21:19 EDT.
