# App sprint, 2026-11-10

Ben asked for the site to be rebuilt around two uses of the served model (2026-11-10):

1. a renter looks for apartments asking less than the model expects;
2. the modeler reads the model's misses to find data errors and regularities the model has
   no term for, and carries them into the data rules and the next fit.

An ask far below the model's range is a deal, a data error or a fact the model lacks (size,
floor, condition). The top of the Deals list of 2026-11-10 shows all three kinds mixed together:
its first row is a 3-bedroom asking $7,250 against a model middle of $26,848. The sprint
therefore builds the two uses on the same rows, and lets a tag written while reading one ad
serve both.

## Sections after the sprint

- **Deals** (`/`, `/deals`, `/listings/<id>`): the ads on the market, ordered by a cautious
  saving, each row carrying the facts the model lacks and the evidence behind its range.
- **Workbench** (`/workbench/...`): the held-out misses as a triage queue, the misses tabulated
  against every attribute the model does not use, the building levels against building
  attributes, and a building's full ad history.
- **Tags**: a reader marks an ad as a real deal, a data error of a given kind or an unmodeled
  reason. The site appends the tag to a ledger file. Deals hides ads tagged as not a deal, and
  the ledger is the labeled set for data rules and for judging the next model.

The pages built on the October 19 fit (Best for you, the old building and unit pages, Left out,
the Research section) come out once their replacements are live.

## Increments

Each is its own reviewed PR.

1. `rentfrontier.drift_diagnostics publish` writes the `diagnostics/` folder described below.
2. Workbench pages read that folder.
3. Deals and the listing page are rebuilt, reading `deals/` and `diagnostics/`.
4. Tags: the ledger, the buttons on listing, Deals and triage rows, the export.
5. Navigation: Deals as the home page, the October 19 pages removed.
6. A playtest round with renter and modeler personas, and its fixes.

## The `diagnostics/` folder

`python -m rentfrontier.drift_diagnostics publish LATEST_RUN --market MARKET_RUN --ads ADS
--registry REGISTRY --features DIR --out <site root>/diagnostics` writes three parquet files and
then `meta.json`, which carries each file's sha256 so that the site can refuse a mixed folder,
as `estimates/` does. `docs/model/diagnostics.md` describes the publisher and gives the counts
of the first publish.

`--ads` is a single ads file for both runs, the newest build, because the build behind the
latest dataset lacks over half of the market ads. `--features` is the root of the snapshot
folders, and `--source NAME=PATH` reads a given table in place of a family's newest snapshot.

### `ads.parquet`

One row per held-out ad, the same ads as `estimates/estimates.parquet`.

Core columns, always present:

| column | meaning |
| --- | --- |
| `listing_id`, `source`, `building`, `address`, `unit_id`, `unit`, `neighbourhood`, `day`, `status` | as in `estimates.parquet`; `unit` is the label read from the ad's page |
| `bedrooms`, `full_baths`, `half_baths`, `ask`, `model_median`, `model_lo95` ... `model_hi95` | as in `estimates.parquet` |
| `gap` | log(ask / model median) |
| `miss` | `gap` / s, with s = (log `model_hi80` - log `model_lo80`) / 2.5631, the predictive spread on the log scale read from the 80% range |
| `pit` | share of the predictive distribution under the ask, unrounded |
| `z` | the normal score of `pit`, clipped to plus or minus 6; `pit` comes from a finite number of draws, so `z` stops near 3.5 and `miss` orders the largest misses |
| `unit_ads` | the unit's ads in the fit's training rows |
| `building_ads` | the building's ads in the fit's training rows |
| `basis` | `unit` when `unit_ads` > 0, `building` when `building_ads` >= 5, else `area` |
| `prev_ask`, `prev_day`, `prev_bedrooms` | the apartment's previous ad in the dataset, when it has one |
| `square_feet`, `floor`, `months_free`, `first_ask`, `days_on_market` | from the pipeline's ads file; `floor` is the floor read from the unit's label, or else the floor stated in the ad |
| `latitude`, `longitude` | from the registry |
| `flags` | list of detector codes, see below |

An apartment, for `prev_*`, `beds_conflict`, `beds_jump` and `ask_jump`, is the building plus
the `unit_id` with a trailing `~1`, `~2` removed. The dataset cuts a unit into those pieces
where its bedroom count changes, so the model's own key would hide such changes. `unit_ads` and
`basis` keep the model's key.

Feature columns: every further column is an attribute of the ad, the unit or the building, and
`meta.json["features"]` lists each one as `{"name", "label", "kind", "level", "in_model",
"after", "source", "known_share"}`, with `kind` one of `number`, `category`, `flag` and `level`
one of `ad`, `unit`, `building`. `in_model` is true when the fit has a term for the attribute:
44 of the 61 listed on 2026-11-10 do, and a trend of the misses along one of them points at the
form of the term. `after` is true for an attribute known only once the ad has run (days on the
market, price cuts). The core columns `square_feet`, `floor`, `months_free`, `days_on_market`
are listed there too. The Workbench pages enumerate features from this list and hard-code none.

Detector codes in `flags`:

- `beds_conflict`: the unit's ads carry more than one bedroom count;
- `beds_jump`: this ad's bedroom count differs from the unit's previous ad;
- `ask_jump`: the ask is over twice or under half the unit's previous ask;
- `ppsf`: the ask per square foot is outside a plausible range;
- `extreme`: |`miss`| > 4 (0.6% of the ads on 2026-11-10);
- `building_side`: the building has at least 5 held-out ads, and at least 80% of them sit on
  the same side of the model's 80% range.

### `buildings.parquet`

One row per building in the latest fit: `building`, `address`, `latitude`, `longitude`,
`neighbourhood`, `zone`, `level` and `level_sd` (posterior mean and standard deviation of the
building's level, on the log scale, relative to its zone's surface at the building's
location), `train_ads`, `heldout_ads`, `heldout_gap` (mean `gap`), `heldout_miss` (mean `miss`),
`heldout_z` (mean `z`), and the building-level feature columns. `zone`, `level` and `level_sd`
are left out, with the reason in `meta.json["level_missing"]`, when the publisher can't rebuild
the fit's order of buildings.

### `history.parquet`

One row per ad in the latest dataset, plus the market dataset's ads the latest dataset lacks,
sorted by `building`, `unit_id`, `day`: `listing_id`, `building`, `unit_id`, `unit`, `day`,
`ask`, `bedrooms`, `full_baths`, `heldout`, `market`. An ad held out by the market fit takes the
market dataset's row. `heldout` is true when the fit behind the row held the ad out, and
`market` when the ad was on the market on the scoring day. Every ad of `ads.parquet` is in the
table. The listing page and the building page read a building's rows from it.

### `meta.json`

`model`, `runs`, `datasets`, `gate`, `scoring_day`, `published`, `features`, `skipped` (the
attributes left out and why), `sources` (each table read, with its sha256), `model_terms` (the
fit's terms in plain words), `level`, `level_missing`, `ppsf` (the bounds of the `ppsf`
detector), `coverage`, `counts`, and `sha256` for the three files.

## Statistical reading of the tables

The latest split holds out the newest ad of each unit with two or more ads, so the fit already
knows each such unit's level from its earlier ads. An attribute fixed for a unit (size, floor)
therefore shows up in those residuals only through change over time. Its plain effect shows in
two places: the market ads of units with no earlier ads (`basis` other than `unit`), and the
building levels against building attributes. The Workbench pages keep these readings apart.
