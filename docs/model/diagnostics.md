# The diagnostics folder

`rentfrontier.drift_diagnostics` writes the folder behind the site's diagnostics pages. It
takes the held-out ads of two drift fits, the same ads as the Estimates table
(`rentfrontier.drift_estimates`), and puts beside each ad how far its ask is from the model,
how much the fit knew about its unit and building, the apartment's previous ad, a list of
detector codes, and about sixty attributes of the ad, the unit and the building. The pages
use it to look for patterns in the misses: a missing model term, a term with the wrong
form, or bad data.

## Publishing

Run from `frontier/`, inside a memory scope, with the venv of the fits:

```sh
PYTHONPATH=src JAX_PLATFORMS=cpu systemd-run --user --scope -q -p MemoryMax=6G \
  /data1/apartments/venvs/bridge-frontier/bin/python -m rentfrontier.drift_diagnostics publish \
  drift-building-b0-latest-67d14e17-b9 --market drift-building-b0-market-67d14e17-n9 \
  --ads /data1/apartments/pipeline/datasets/ads-14f9e88d75290a0f.parquet \
  --registry /data1/apartments/external/registry/20261110-f1fc080-extend/registry.parquet \
  --features /data1/apartments/external --out /data1/apartments/site/diagnostics
```

The run of 2026-11-10 took 110 seconds and peaked at 3.6 GB.

`publish` goes through these steps:

1. It checks the runs as `drift_estimates` does. The first run must be on the latest
   split, the second on the market split of a market dataset, both fits of the same model,
   both past the convergence gate. It stops with a message otherwise, before writing.
2. It builds the Estimates rows of each run with `drift_estimates.table`, then adds `gap`,
   `miss`, `pit`, `z`, `building_ads`, `basis` and the `prev_*` columns from the run's scores and
   its dataset rows.
3. It combines the two runs as Estimates does. An ad held out by both fits takes the
   market fit's row.
4. It reads `--ads` for the unit label and the ad's own facts, then joins the attributes
   in `FEATURES`, and works out the detector codes.
5. It builds the buildings table from the latest run's dataset rows, and the history
   table from those rows plus the rows the market run's dataset adds.
6. It writes `ads.parquet`, `buildings.parquet` and `history.parquet`, each under a
   temporary name first, and then `meta.json` with the sha256 of each table.

Options:

- `--ads` defaults to the ads file recorded in the market dataset's manifest. Both runs
  read the same file, since the newest build holds every held-out ad of both.
- `--features` is the root of the snapshot folders. For each source family `publish`
  takes the newest folder: the latest by the date at the start of its name, and among
  folders of the same date the one modified last.
- `--source NAME=PATH` reads a given table for a source in place of its newest snapshot.
  `NAME` is a key of `SOURCES` in the module (`codes`, `attrs`, `pluto` and so on).
- `--registry` gives addresses, coordinates and the lot (`bbl`) of each building. Lot-level
  attributes need the `bbl` column.

## ads.parquet

One row per held-out ad, sorted by day and listing, in the same order as
`estimates.parquet`. `listing_id`, `source`, `building`, `address`, `unit_id`,
`neighbourhood`, `day`, `status`, the bedrooms and baths, `ask`, `model_median`, the
`model_lo95` to `model_hi95` bounds, `unit_ads`, `latitude` and `longitude` are the
Estimates columns unchanged. The rest:

| Column | Reading |
|---|---|
| `unit` | The unit label from the ad's page, as on the Deals page. |
| `gap` | log(ask) minus the log of the model's median, before the median is rounded. 0.05 reads as an ask about 5% over the model. |
| `miss` | `gap` over the model's spread s on the log scale, with s = (log `model_hi80` - log `model_lo80`) / 2.5631 from the unrounded bounds. 2.5631 is the width of a normal distribution's central 80% in standard deviations. `miss` keeps growing with the gap, so it orders the largest misses, where `z` stops near 3.5. |
| `pit` | The share of the predictive distribution under the ask, unrounded. |
| `z` | The normal score of `pit`, clipped to plus or minus 6. `pit` is a share of a finite number of draws, so the largest absolute `z` in the table is 3.56. |
| `building_ads` | The fit's training ads in the ad's building. |
| `basis` | `unit` when `unit_ads` is above 0, else `building` when `building_ads` is 5 or more, else `area`. |
| `prev_ask`, `prev_day`, `prev_bedrooms` | The apartment's ad before this one, by day, among the run's dataset rows. Empty for an apartment's first ad. |
| `square_feet`, `months_free`, `first_ask`, `days_on_market` | From the ads file. |
| `floor` | The floor read from the unit's label (`label_floor`), or else the floor stated in the ad (`advertised_floor`). |
| `flags` | A list of detector codes, described below. |
| attribute columns | One per entry of `meta.json["features"]` outside the columns above. |

An apartment, for `prev_*` and the two bedroom detectors, is the building plus the
`unit_id` with a trailing `~1`, `~2` removed. The dataset cuts a unit into those pieces
where its bedroom count changes, so the pieces are read together here to catch such
changes. `unit_ads` and `basis` keep the model's own key, with the pieces apart, since the
fit gives each piece its own level.

### Detector codes

| Code | Condition |
|---|---|
| `beds_conflict` | The apartment's ads in the run's dataset carry more than one bedroom count. |
| `beds_jump` | The bedroom count differs from the apartment's previous ad. |
| `ask_jump` | The ask is over twice the previous ask or under half of it. |
| `ppsf` | The ask per square foot is outside the range for the bedrooms. |
| `extreme` | The absolute value of `miss` is above 4. |
| `building_side` | The building has 5 or more held-out ads, 80% or more of them are under the model's 80% range (`pit` below 0.1), or 80% or more are over it (`pit` above 0.9), and this ad is among them. |

The `ppsf` ranges are in dollars per square foot a year (12 asks over the area):

| Bedrooms | Low | High |
|---|---|---|
| 0 | 30 | 150 |
| 1 | 25 | 140 |
| 2 | 22 | 155 |
| 3 or more | 20 | 170 |

They sit near the 0.5% and 99.5% points of the held-out ads with an area on 2026-11-10
(studios 32 to 143, one bedroom 27 to 137, two 23 to 152, three 20 to 167). The constants
are `PPSF` in the module, and `meta.json["ppsf"]` repeats them.

Counts on 2026-11-10, among 195,423 ads: `beds_conflict` 36,077, `beds_jump` 9,737,
`extreme` 1,237 (0.6%), `ask_jump` 930, `ppsf` 380, `building_side` 31. The absolute `miss`
has median 0.61 and 99th percentile 3.55, and its largest value is 21.

## Attributes

`FEATURES` in the module lists the attributes as data: the output name, a plain label,
the kind (`number`, `category`, `flag`), the level (`ad`, `unit`, `building`), the source
and the source's column. `SOURCES` gives each source's snapshot family, file and key
(`listing_id`, `building` or `bbl`). To add an attribute, add a line to `FEATURES`, and a
line to `SOURCES` if the table is new.

Each entry of `meta.json["features"]` carries, besides `name`, `label`, `kind` and `level`:

- `in_model`: the fit has a term for the attribute. Most of the listed attributes do. A
  trend of the misses along such an attribute points at the form of the term. Along an
  attribute with `in_model` false (distance to the subway, parks and water, noise
  complaints, the elevated lines, street width, heating type, brokerage, kind of lister,
  historic district) a trend points at a missing term.
- `after`: the attribute is known only once the ad has run (`days_on_market`, `n_cuts`,
  `n_raises`, `days_listed`). It describes how the market answered the ask, so it can
  explain a miss and can't price a new ad.
- `source` and `known_share`: the source's name and the share of the ads with a value.

`publish` leaves an attribute out, with the reason under `meta.json["skipped"]`, when its
source has no table, when the table lacks the column, when under 1% of the ads have a
value, or when a flag is true for under 1% of the ads. On 2026-11-10 that dropped `loft`
(true for 0.85%) and `furnished` (0.00%).

`meta.json["sources"]` records each table read: path, sha256, size and modification time.

Building-level attributes come from tables keyed by building or by lot, and they are in
`buildings.parquet` too. An amenity read from an ad's own text (`ad_pool`, `ad_parking`)
has level `ad`, since two ads of a building can disagree.

Some sources stop before the market fit's ads: `top_floor` and `penthouse` cover 98% of
all ads and 44% of the market fit's, `broker_group` 98% and 41%, the lister and outcome
columns 17% and 6%.

## buildings.parquet

One row per building of the latest fit, 67,972 on 2026-11-10: `building`, `address`,
`latitude`, `longitude`, `neighbourhood` (the most common among the building's ads),
`zone`, `level`, `level_sd`, `train_ads`, `heldout_ads`, `heldout_gap`, `heldout_miss` and
`heldout_z` (means over the building's rows of `ads.parquet`), then the building-level attributes.

`level` and `level_sd` are the mean and standard deviation, over the kept draws, of the
fit's `bld`. The fit gives a building a level, constant over time, and gives its zone
(Manhattan, the other boroughs) a smooth surface over the map. `bld` is the building's
level minus the surface at the building's point, on the log scale. It is what the fit
assigns to the building itself after the location, the terms for the building's
attributes, each unit's own level and the building's quarterly path. A level of 0.10 reads
as rents about 10% over what the location and the attributes give. Its prior is a
Student-t with 4 degrees of freedom and the zone's spread.

The draws carry no building names, so `levels` rebuilds the fit's numbering: zone by zone,
and inside a zone in the order the buildings first appear in the dataset's rows, using
the registries named in the run's `result.json`. It uses the numbering only if each zone
gets the count of buildings the run recorded and the total equals the width of `bld`.
Otherwise the level columns are left out and `meta.json["level_missing"]` gives the reason. On
2026-11-10 the counts agreed (21,990 and 45,982), and among buildings with 20 or more
training ads the level correlates 0.68 (Manhattan) and 0.43 (other boroughs) with the
building's mean log ask relative to its neighbourhood, bedrooms and year. Shifting the
numbering by one building drops that to 0.08 and 0.04.

## history.parquet

One row per ad, 1,900,447 on 2026-11-10, sorted by building, unit and day: `listing_id`,
`building`, `unit_id`, `unit`, `day`, `ask`, `bedrooms`, `full_baths`, `heldout`, `market`.
A page reads a unit's or a building's past from it.

`publish` starts from the latest run's dataset rows (1,896,471), with `heldout` true for
the ads the latest fit held out. From the market run's dataset it then takes the rows of
the ads the market fit held out, and the rows of the ads absent from the latest dataset.
An ad held out by the market fit gets the market dataset's row, with the ask and day its
estimate was made for, `heldout` true and `market` true. `market` therefore marks the ads
on the market on the scoring day (6,774). Every ad of `ads.parquet` is in the table once,
with `heldout` true and the same ask.

## meta.json

`model`, `runs`, `datasets`, `gate`, `scoring_day` and `published` as in the Estimates
meta, then `features`, `skipped`, `sources`, `level` (a sentence on its meaning, or null),
`level_missing`, `model_terms`, `ppsf`, `coverage`, `counts` (ads by source, buildings, history rows, ads
by basis, ads by detector code) and `sha256` by table name. `publish` writes it last. A
reader compares the hashes with the tables and refuses a folder where they differ.

`model_terms` lists the terms of the latest fit in plain words, 54 on 2026-11-10.
`model_terms` in the module reads the coefficient names saved in the run's `posterior.npz`
through the patterns in `TERMS` (bedrooms, baths, season, size, floor, the building and ad
attributes, each unit's average of the ad-level attributes), then adds the parts in `PARTS`
whose draws the run kept (the city's level over time, the surface of each zone, the level and
quarterly path of each building, the level and drift of each unit). A coefficient name with
no pattern is listed as it is, so a new term shows up untranslated until `TERMS` gets a line.

`coverage` is the share of the latest fit's rows of `ads.parquet` inside the central 50%,
80% and 95% of the predictive distribution, computed from `pit`: 0.5253, 0.8081 and 0.9524
on 2026-11-10. The Estimates meta gives 0.5247, 0.8074 and 0.9520 over all 189,647 ads
held out by the latest fit. The table here has 188,649 of them, since the other 998 take
the market fit's row.
