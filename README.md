# NYC rents: a pricing model for finding good deals

This repo holds a descriptive model of asking rents for New York City apartments and the
tools around it. The model says what an apartment usually asks, given everything known about
the unit, its building, its location and the date, and how sure it is. An ad that asks well
below that range is a candidate deal.

Ben owns the project and Claude threads do the work. On 2026-11-10 the aim changed from
explaining rents to finding deals with honest uncertainty, and the model below replaced the
earlier lines.

## Where things stand

**The served model is `drift-building-bedtext-layout-range`**: `drift-building` (below) plus
ten columns read from each ad's text and coded counts, a flag for text that names fewer
bedrooms than coded and marks for an ad coding more or fewer rooms than the apartment's
earlier ads. Deals has read it since 2026-11-18. It is fitted on Modal in one container for
about $2, with 13 scales held at the values of a base fit that passed the gate. Its market fit
of 2026-11-20 (`...-6cd1f12b-range-m3`) and its backtest (`...-d9028c57-range-j`) both pass
the gate. It has no held-out latest-split fit, so the table below scores its parent. On the
backtest's 9,346 final asks it scores an elpd of 10,042 against 9,979 for `drift-building`.

`drift-building` has a Student-t prior on building levels (`--level-dof 4`) and was fitted on
2026-11-10. It gives each apartment a level that drifts and each building a path of its own,
and it passes the convergence gate on all three of its fits (held-out split, that day's
market, a backtest a year back). `drift`, the same model without the building's path, was the
first model in the project with a term for the individual apartment to pass the gate on the
full data, and was served for the first hours of that day (4:42 AM to 9:19 AM ET).

Scores on the same 189,647 held-out ads (a 10% draw, each the newest ad of an apartment):

| Model | Held-out elpd | Typical miss of the middle estimate | 80% range holds | Gate |
|---|---|---|---|---|
| Fit 8 (no memory of the apartment) | 148,234 | 6.9% | 79.8% | passed |
| Kitchen sink (2026-10-24, every column on hand) | 156,105 | 6.6% | 80.1% | passed |
| Fit 4 (a fixed level per apartment) | 177,137 | 5.8% | 78.9% | missed |
| `drift` (a level per apartment that drifts) | 195,320 | 5.2% | 79.9% | passed |
| **`drift-building`** (plus a path per building; Student-t building levels) | **230,989** | **4.1%** | **80.7%** | **passed** |
| `l2bt` (`drift-building-phase-unitkn-level-bedtext`, latest-split frontier, unserved) | **237,654** | **4.0%** | **80.1%** | **passed** |

- **The Deals page** (`/deals` on the site) ranks the 6,502 ads on the market on 2026-11-20
  by how low each ask is for its apartment. It was published from the market fit with its
  backtest on 2026-11-21 at 1:20 AM ET (with exact CDF quantiles and fit-own previous asks).
  1,675 ads (25.8%) carry a caution and are left out of the list unless asked for. A caution
  marks a plain reason for a low ask that the model does not know: the text says
  income-restricted, an office, owners only, a lease takeover, or a short lease under a year;
  the apartment's ads disagree on its bedrooms; the ad codes more rooms than the apartment's
  previous ad; the page price is a net rent with no coded free months (from price or security
  deposit); the building has raised an ad after opening it low; the building's level is high
  on five or fewer ads; the ad is off the market (`frontier/src/rentfrontier/cautions.py`).
  Read against their own text on 2026-11-10 at 9:25 AM ET, 36 of the first 40 ads then shown
  were ordinary apartments with no plain reason for the low ask (2 had one: a lease
  takeover, which carries a caution since, and a text that names one more bedroom than
  the record; 2 could not be told). Before the cautions, under `drift`, it was 10 of 22.
- **The backtest.** Fitted on what was known on 2025-11-10 and scored on the first asks of
  the 9,346 ads open that day: ads in the lowest tenth of the score left the market in a
  median of 26 days and 17% had their ask cut; ads in the highest tenth took 72 days and
  62% were cut. (`drift-building` gave 26 and 71 days, 18% and 61%; `drift` 28 and 61 days,
  18% and 60%.)
- **Calibration.** On the held-out split the 50, 80, 90 and 95% ranges of `drift-building`
  held 52.5, 80.7, 90.1 and 95.2% of the asks. On the backtest's final asks the served
  model's held 51.7, 79.2, 89.4 and 94.6%.
- **How the building model came to pass.** Under a normal prior on building levels
  `drift-building` predicted much better than `drift` and every one of its fits missed
  the R-hat line. With chains twice as long (round seven) every quantity that had missed
  for chain length passed with room and one still missed on both fits: the spread of
  building levels in the outer boroughs (R-hat 1.013 and 1.020 against 1.01). The
  best-supported cause is about ten buildings. Most of them have listings coded with 0
  bedrooms at the rents of the building's 3-bedrooms (in the eight that were read, every
  such ad has a blank or placeholder text and the source's own count of 0). The sampler
  takes thousands of sweeps to decide whether such a building is dear or its ads are
  outliers, and under a normal prior each one moves the whole zone's spread, so the
  chains are probably still arriving when a fit ends. Ten buildings' levels explain 95
  to 98% of the differences between chains. The fix is in the data (of 1,596
  studio-coded ads whose text names two or more bedrooms, 25 of 40 read were whole
  apartments, so roughly 750 to 1,250; and 4,517 placeholder listings) and in the model:
  a Student-t prior on building levels (`Settings.level_dof`). Round eight ran it
  on one container with the seed that had failed: the leverage was gone, the container
  passed the gate, and its held-out score was 126 above the same container under the
  normal prior. Round nine ran the three full fits (nine containers, $33.02, on budget
  Ben added for it), with predictions written first: all three pass, with the outer
  spread's R-hat at 1.005 or under, and the held-out score is 128 above the normal
  prior's. The note of 2026-11-10 has the evidence.
- **What is next.** The choice of 4 degrees of freedom and the other open items are in
  `docs/TODO.md`. A base refit with free scales, about $22, waits on Ben's decision
  (`docs/handoff/project-owner.md`).

[docs/model/lineage.md](docs/model/lineage.md) gives the four-generation model evolution tree,
the Bayesian plate diagram, and the current production stack across all site sections.
[docs/model/drift-explainer.html](docs/model/drift-explainer.html) is a visual walk
through the model and these results. [docs/handoff/project-owner.md](docs/handoff/project-owner.md)
says where work stopped.

## The model in one page

Each ad's log asking rent is the sum of

| Term | What it holds | Where |
|---|---|---|
| Columns | Bedrooms, baths, size, floor curves, amenities, building attributes, ad text codes: about 250 coefficients | `building_zones_kitchen_sink.py` |
| Citywide time | A weekly random walk plus season | `building_zones_gibbs.py` |
| Location | A smooth surface per zone (Manhattan, outer boroughs) at 1 km | `building_zones.py` |
| Building | A level for each of 68,000 buildings around its zone's surface, with a Student-t prior (4 degrees of freedom) in the served fits | `building_zones.py`, `drift.py` |
| Unit | A lasting level for each apartment plus a drift that fades over a few years | `drift.py` |
| Building drift (`drift-building`) | A path per building that wanders and returns, one step a quarter | `drift.py`, `drift_building.py` |
| Bed and bath marks (served model) | Ten columns: text naming fewer bedrooms than coded, and the ad's bed and bath counts against the apartment's earlier ads | `drift_building_bedtext_layout_range.py` |
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
5. `python -m rentfrontier.drift_deals deals RUN --ads ADS --registry REGISTRY --out DIR`
   writes the deals table, lowest share first, with each ad's cautions
   (`rentfrontier.cautions`; `... texts RUN`
   writes the ads' own descriptions for the ones read from text). `... validate` checks the
   score against what happened to the ads of the backtest: time on the market and price cuts.
   `ops/deals-refresh` runs steps 2, 3 and 5 as `datasets`, `backtest-datasets`, `fit`,
   `backtest-fit` and `publish`, and `python -m rentfrontier.drift_kept_report RUN` reports
   kept-draw R-hat over 1.05 and far-thin buildings without changing the gate or the table.
6. `python -m rentfrontier.drift_estimates publish LATEST_RUN --market MARKET_RUN --out DIR`
   writes the Estimates table: every ad the two fits held out, with its ask beside the
   predictive median and intervals of a fit that never saw it.
7. `python -m rentfrontier.drift_today publish MARKET_RUN --registry REGISTRY --out DIR`
   writes the Price now table: every apartment the market fit knows, with the median and
   intervals of what it would ask if listed today, from the fit's saved draws
   ([docs/site.md](docs/site.md#price-now)).

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
| `frontier/src/rentfrontier/` | The models, samplers, scoring and splits. Start with [frontier/README.md](frontier/README.md) and `drift.py`. |
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
