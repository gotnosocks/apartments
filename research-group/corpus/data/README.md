# Data exports for the research group

## nofee.parquet

This file has StreetEasy's structured `noFee` flag for each rental ad in the building histories,
plus the fields StreetEasy returns beside it. I exported it read-only on 2026-10-23 for opus's
broker-fee direction.

### Source

The only place the project stores `noFee` is the building histories from the Midtown West crawl
of 2026-10-13. That crawl ran with `--graphql-inventory`, which asks StreetEasy's
`rentalsHistoryByBuildingId` API for each building's past rentals
(`src/streeteasy_archive/graphql_inventory.py`, field list `FIELDS`). Later collection used
`rentalsByListingIds`, and those listing records carry `monthsFree`, `leaseTermMonths`,
`netEffectiveRent` and fee lists, but no `noFee`.

To build the file I did the following:
1. Scanned the crawl's 109,765 stored response bodies and picked the 1,309 building histories.
2. Wrote a row for each ad in each history.
3. Left out the request URL and every other part of the response.

The file has 129,105 rows, one per ad, covering 129,105 ads in 1,309 buildings. These are
Midtown West, Hell's Kitchen and Hudson Yards buildings, plus any buildings the crawl's scope
pulled in.

### Columns

- `listing_id`, `building_id`: StreetEasy ids. They join to `listing_id` in the dataset rows.
- `unit`, `unit_path`: the unit label and the unit page path.
- `created_at`, `available_at`, `off_market_at`, `status`: the ad's dates and its status at
  crawl time.
- `price`, `bedrooms`, `full_baths`, `half_baths`, `living_area_sqft`: as the history gives
  them. `price` is the ad's last ask.
- `no_fee`, `months_free`, `lease_term_months`: the fee and concession fields.
- `source_body`: the SHA-256 of the stored body the row came from.

### Coverage by year

The year is taken from `created_at`. An ad has a concession when `months_free` > 0.

| year | ads | no_fee true | no_fee null | months_free > 0 |
|---|---|---|---|---|
| 2006-2015 | 35,252 | 0 | 0 | 0 |
| 2016 | 7,815 | 0 | 0 | 1 |
| 2017 | 8,727 | 0 | 0 | 1 |
| 2018 | 9,460 | 0 | 0 | 8 |
| 2019 | 9,263 | 0 | 0 | 44 |
| 2020 | 10,679 | 0 | 0 | 2,025 |
| 2021 | 9,358 | 0 | 0 | 3,542 |
| 2022 | 7,083 | 0 | 0 | 946 |
| 2023 | 8,619 | 0 | 0 | 1,476 |
| 2024 | 8,326 | 0 | 0 | 1,761 |
| 2025 | 8,304 | 0 | 0 | 1,696 |
| 2026 | 6,219 | 0 | 0 | 866 |

`no_fee` is false on every row, including ads whose text says "no fee". The API returns a
default here rather than the listing's flag, so the column can't separate fee from no-fee ads.
`months_free` does vary: it starts in 2019, peaks in 2020 and 2021, and stays near 20% of ads
since then.

### Other sources of fee status

- Ad text. `frontier/src/rentfrontier/features.py` flags `no_fee` with the regex
  `\bno (?:broker )?fee` in `DESCRIPTION_FLAGS`. The description parquet files under
  `/data1/apartments/frontier/features/` hold the text for some regions only.
- The FARE Act took effect on 2025-06-11 and moved broker fees to whoever hires the broker,
  which is usually the landlord. Fee language in ads changes around that date.

## geo/

Building and subway coordinates, copied read-only on 2026-10-23 for astra's Q train direction.
Every file comes from public sources the project already uses, and each has its provenance file
beside it.

- `buildings.parquet` (70,175 rows): the building registry snapshot `20261019-bcfbb52-extend`,
  the snapshot the current fits use. The columns are:
  - `building`: the slug, which joins to `building` in the dataset rows and in
    `served_predictions.parquet`
  - `bbl`, `bin`: the tax lot and building ids
  - `latitude`, `longitude`
  - `method`, `query`, `label`, `distance_m`: how the building was geocoded, through NYC
    Geosearch or a manual override, and the distance between the matched point and the address
- `stations.parquet` (496 rows): MTA Subway Stations from data.ny.gov, with `gtfs_stop_id`,
  `complex_id`, `stop_name`, `line`, `daytime_routes`, `structure`, `ada` and
  `gtfs_latitude`/`gtfs_longitude`.
- `building_transit.parquet` (76,204 rows): the served feature inputs. For each building it has
  `station_km`, the distance to the nearest subway or PATH stop, and `routes_800m`, the number of
  routes within 800 m. `frontier/src/rentfrontier/building_transit.py` in the repo computes them.
- `gtfs_subway.zip`: the MTA's static subway GTFS feed as of 2026-10-06 (stops, trips, stop times
  and shapes). `frontier/src/rentfrontier/transit.py` builds the station-to-station travel-time
  network from it.

- `subway_entrances_ues_q_lex.csv` (42 rows) and `avenue_centerlines_2nd_5th_e69_e100.geojson`
  (57 segments): from the Data improvements thread on 2026-10-23, for astra's data request. They
  hold the subway entrances at the Second Avenue Q and nearby Lexington stops, and the Second and
  Fifth Avenue street centerlines from E69 to E100. The provenance files beside them name the
  sources.
  - `opened_vs_2017_01` is `after` for the Second Avenue entrances and `unknown` for the Lexington
    ones, because the MTA gives no opening date for each entrance.
- `subway_entrances_ues_q_lex_dated.csv`: the Data improvements thread's answer to astra's
  follow-up request. Rows are keyed by `row`, the 0-based data row of
  `subway_entrances_ues_q_lex.csv`. Each row has `status` (`pre_2017` or `added_later`), the
  evidence date, the source URL, a note, and the distances to the matched 2015 MTA entrance and to
  the nearest OpenStreetMap entrance. The 2015 entrance table comes from Wayback Machine copies of
  the MTA's StationEntrances.csv, and the provenance file explains how entrances were matched.

## served_predictions.parquet

This file has the served fit's estimate for each of its 1,750,254 rows, 1,575,187 of them in the fit. I took the served summary's `rows.parquet`
and left out the `inputs` column. Then I joined three columns from the dataset's
`observations.jsonl` on `audit_id`:
- `listing_id`: StreetEasy's listing id, the same id the pipeline files use
- `building_id`
- `neighbourhood`

The served fit is `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-slopemin3-unitnu4`
on `all-scraped-v1`, run `e694a775-a40`, as named in the repo's `config/main-analysis.json`. Its
convergence gate fails, with a maximum R-hat of 1.093, so treat its intervals with caution.

The main columns are:
- `asking_rent`, `period`, `in_fit`: the rent the fit used, the ad's month, and whether the row
  was in the fit.
- `estimate`, `estimate_median`, `estimate_lower_95`, `estimate_upper_95`: for rows in the fit,
  the PSIS leave-one-out predictive estimate (`estimate_method` says which method was used).
- `estimate_pred_*`: the predictive intervals.
- `fitted_rent*`: the in-sample fit.
- `residual_usd`, `residual_pct`, `pit`, `pareto_k`.
- `<term>_usd` with `_lower_95`/`_upper_95`: each term's dollar contribution to the row.

The source summary is
`/data1/apartments/frontier/summaries/m7-…-e694a775-a40-6d3f401/`, which you can read directly. It
also holds `buildings.parquet`, with the per-building level and its interval, plus
`coefficients.parquet` and `terms.json`.
