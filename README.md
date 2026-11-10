# NYC rents: a pricing model for finding good deals

This repo holds a descriptive model of asking rents for New York City apartments and the
tools around it. The model says what an apartment usually asks, given everything known about
the unit, its building, its location and the date, and how sure it is. An ad that asks well
below that range is a candidate deal.

Ben owns the project and Claude threads do the work. On 2026-11-10 the aim changed from
explaining rents to finding deals with honest uncertainty, and the model below replaced the
earlier lines.

## Where things stand

RESULTS-PLACEHOLDER

## The model in one page

Each ad's log asking rent is the sum of

| Term | What it holds | Where |
|---|---|---|
| Columns | Bedrooms, baths, size, floor curves, amenities, building attributes, ad text codes: about 250 coefficients | `building_zones_kitchen_sink.py` |
| Citywide time | A weekly random walk plus season | `building_zones_gibbs.py` |
| Location | A smooth surface per zone (Manhattan, outer boroughs) at 1 km | `building_zones.py` |
| Building | A level for each of 68,000 buildings around its zone's surface | `building_zones.py` |
| Unit | A lasting level for each apartment plus a drift that fades over a few years | `drift.py` |
| Local drift | A short-lived level per building by month, and per neighbourhood by quarter | `drift.py`, `drift_building.py`, `drift_local.py` |
| Noise | Student-t, with a scale per bedroom group | `b0.py` |

The unit term is what makes the model useful for deals. An apartment that asked 8% over its
building's norm two years ago probably still asks more, but less surely than if the ad ran
last month. The model weighs each earlier ad of the unit by how long ago it ran, and the
predictive range for an apartment with recent history is about half as wide as for one the
model has never seen.

The sampler is a blocked Gibbs sweep in JAX on a GPU. [docs/model/drift.md](docs/model/drift.md)
gives the equations, the sampler and the checks, and the module docstrings give the details.

## From an ad to a deal score

1. `ops/streeteasy-collect` and the pipeline (`pipeline/`) turn scraped pages into one row
   per ad, with the data rules applied.
2. `ops/market-dataset HASH` builds two datasets from a pipeline build: the market dataset
   (every ad, with the ads on the market now marked) and a backtest (the same as of one year
   earlier).
3. `ops/modal-fit` fits a model on a Modal GPU. The fit predicts every ad outside its
   training rows at each kept draw.
4. `python -m rentfrontier.drift_score RUN` turns those into predictive densities, intervals
   and, for each ad, the share of the model's distribution below its ask.
5. `python -m rentfrontier.drift_deals deals RUN --ads ADS --out DIR` writes the deals table,
   lowest share first. `... validate` checks the score against what happened to the ads of
   the backtest: time on the market and price cuts.

## How a change earns its place

- **Predictions first.** Each fit has predictions written before it runs, and a results note
  that scores them (`docs/notes/`).
- **One change per fit**, compared on the same held-out ads.
- **Held-out score.** The latest split holds out the newest ad of 189,647 apartments. A model
  is scored by its log predictive density there (elpd), the error of its median, and the
  coverage of its intervals.
- **Convergence gate.** Split R-hat at most 1.01 and bulk ESS over 400 on every scalar and
  coefficient. A fit that misses the gate is not rerun on a new seed: the data, then the
  model, then the sampler get looked at, in that order.
- **No leaks.** A row's rent reaches the fit only as its target. Every aggregate a row uses
  is built from earlier ads only ([docs/leak-free-scoring.md](docs/leak-free-scoring.md)).

[docs/research-record.md](docs/research-record.md) lists every model and experiment the
project has tried, with its numbers and what became of it.

## Map of the repo

| Path | What is there |
|---|---|
| `frontier/src/rentfrontier/` | The models, samplers, scoring and splits. Start with `drift.py`. |
| `frontier/tests/` | Their tests. Each sampler step is checked against dense algebra. |
| `pipeline/` | The data pipeline: steps, data rules, audits, materialized tables. |
| `src/apartments/` | The scraper, the archive and the listings site. |
| `ops/` | Scripts: jobs on thelio (`ops/job`), fits on Modal (`ops/modal-fit`), data builds, deploys. |
| `config/` | Data-rule inputs: corrections, reviews, quarantines, and the served model's selection. |
| `docs/` | [docs/README.md](docs/README.md) maps it. Notes are dated; handoffs say where each thread stopped. |
| `models/`, `analysis/`, `tests/` | The first generation of models (2026-09, Chelsea) and their tests. Kept because saved fits hash these files. |

## Working here

```sh
cd frontier && uv sync --extra dev          # the modelling package and its tests
.venv/bin/python -m pytest tests/test_drift.py -q
ops/fmt && ops/lint --changed               # before every commit
```

- Heavy work runs on thelio through `ops/job` ([docs/thelio-jobs.md](docs/thelio-jobs.md)) or
  on Modal through `ops/modal-fit` ([docs/model/modal.md](docs/model/modal.md)).
- Changes merge through reviewed pull requests. [CLAUDE.md](CLAUDE.md) holds the rules for
  Claude threads, and [docs/coding-standards.md](docs/coding-standards.md) the code style.
- The README this one replaced, with the scraper's setup and the Chelsea pilot's history, is
  [docs/archive/readme-2026-09.md](docs/archive/readme-2026-09.md).
