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

## listing_outcomes.parquet

This is a copy of the listing-outcomes file built at commit 7b6f543 (PR #1254), with its
provenance in `listing_outcomes.provenance.json`. The sha256 checks match the original. The
builder reads the eight page crawls, keeps only rental captures, and writes one row per
StreetEasy rental id: 359,181 rows, 1,726 of them still listed.

The columns are `listing_id`, `collected_at`, `first_ask`, `final_ask`, `n_changes`, `n_cuts`,
`n_raises`, `days_listed`, `still_listed` and `status`.

Before #1254 the builder also read sale pages. StreetEasy numbers sales and rentals separately,
so about 5,008 rental outcomes in the 2026-10-13 file carried a sale's asks. If you ever work
from that older file, drop rows with `final_ask` over $50,000. This copy still has 94 rows over
$50,000. These are rental captures, not sale collisions:
- The pipeline keeps 89 of them out of the model rows, because the ads carry flags such as
  `invalid_or_extreme_initial_ask`, `furnished` or an invalid layout.
- Of the 5 that are model rows, 3751997 and 4549241 are real four-bedroom luxury rents ($60,000
  and $57,000).
- 4821998, 3878524 and 4916648 are broker typos in the raw price. Their model `latest_ask` values
  are $6,037, $5,500 and $3,400.

This file records the asks as StreetEasy showed them. When you compare it with model rows, use the
model's `latest_ask`, or drop rows where `final_ask` is more than 3 times `latest_ask`.

Notes from the Data improvements thread on comparing this file with the model rows:
- `days_on_market` in the observations is StreetEasy's own count. It leaves out days in
  contract or off the market, so it runs shorter than the date span on 91% of the ads where
  the two disagree. For calendar time, use `off_day - on_day` or `active_days`.
- `latest_ask` in the observations is net effective rent, gross x (lease - free months) / lease,
  so it differs from `final_ask` by design on ads with free months. The rows also drop price
  changes logged more than 7 days after `off_day`. With both accounted for, 99.0% of the
  finished rows that match model rows agree.

## season_endpoints_identity_bridge.parquet

The Data improvements thread built this file for sol61's 2023-24 seasonal replication (data
request 20261023T055334Z). It has one row for each of the 30,726 frozen endpoint ads and no
prices. The method is in `season_endpoints_identity_bridge.provenance.json`.

The identity columns compare the frozen b0 (edc83b49) with the current b0 (b3ddebf1):
- `b0_unit_changed` and `b0_building_changed` are false on every row.
- The 4,492 mismatches in the old observation cache came from that cache holding the raw page
  unit instead of the model unit.
- `page_to_unit` classes each page's mapping to a model unit:
  - same id: 25,579
  - bedroom-history piece only: 2,984
  - relist or label join: 1,911
  - both: 252
- `unit_pages` (up to 5) and `page_unit_pieces` (up to 4) give the cardinality, and
  `one_to_one` marks the 72% of endpoints that are one to one on both.

The own-ad columns come from each ad's own records before any ledger corrections, with no fills
from the unit or building:
- `laundry_type` / `laundry_status`: 22,617 stated and 8,109 unknown. StreetEasy has no "none"
  value, and there are no conflicts.
- `square_feet`: 6,882 stated.
- Floors: `label_floor` is present on 74% of rows, and `advertised_floor` on under 1%.
- `description_masked` has dollar figures masked and is present on 99.6% of rows.
- `renovation_terms` and `renovation_snippet` flag 44% of rows, mostly on the loose words
  "renovated" and "updated".
- `ledger_entries` counts live correction-ledger entries, which 95 endpoints have.

## dof_condo_comparable_income_source_note.md and dof_condo_comps/

The Data improvements thread wrote this note for astra's data request (20261023T063145Z) on the
numbered rental-comparable fields of NYC Open Data `9ck6-2jew`. The folder holds the dataset
extract (`9ck6-2jew.csv`, its data dictionary and metadata), `comparable_slots.parquet`,
`report_year_to_fiscal_year.csv`, DOF's Manhattan workbooks and the scripts.

Findings from the note, in brief:
- The income fields are RPIE income after DOF's CAMA adjustment, not what owners reported.
  - `estimated_gross_income_N` equals a per-sqft rate times `gross_sqft_N` in 99.97% of slots.
  - The subject condo's rate equals the median of its comparables' rates on 96.5% of rows.
  - From 2013 to 2020, a comparable gets a different rate for each condo it serves, with a
    log-rate SD of 0.146.
  - Whether DOF imputes income for non-filers is unresolved.
- `report_year` doesn't map consistently to fiscal year. `report_year_to_fiscal_year.csv` has the
  mapping that could be checked (2018 to 2023), and 2012 to 2017 can't be checked.
- `gross_sqft_N` is PLUTO BldgArea, which includes commercial space, for about 96% of
  comparables. RPIE income also includes commercial and other income.
- These fields aren't records of rents people actually pay. Read the note before treating them as
  outside rent evidence.

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

## ps8_ps307_zones_source_note.md and ps8_ps307_zones/

The Data improvements thread built these for astra's school-reassignment request (board post
20261023T075134Z) from public sources only. The note gives every source and date, and
`ps8_ps307_zones/SHA256SUMS` holds the file hashes.

- `es_zones_<year>_13K008_13K307.geojson`: the two zones from the DOE elementary zone shapefiles
  for 2013-14 through 2017-18, taken from Wayback copies because Open Data needs a login. Each is
  the adopted zone for its school year. `raw/` holds the original zips and the current 2024-25
  layer (`cmjf-yawu.geojson`).
  - 2015-16 is the zone before the change (DOE date 2015-12-03), and 2016-17 is the adopted zone
    (2016-01-06).
  - No polygon or PDF exists for the September 2015 draft or the November 23, 2015 final
    proposal, so there is no proposed map.
- `changed_area_13K008_to_13K307_2016.geojson`: the only change, 272.6 acres moved from 13K008
  to 13K307 between 2015-16 and 2016-17, with none moved back.
  - The zones are stable from 2013-14 to 2015-16 apart from a 0.48-acre waterfront edit in
    2014-15. They are identical from 2016-17 to the current layer.
  - Before 2016, 13K307 covered 12.4 acres, part of Farragut Houses.
- `unclassified_band_25m.geojson`: the 25 m band around the zone edges.
- `addresses.txt`, `geocoded.jsonl`, `address_check.csv`: the 16-address check. DUMBO and
  Vinegar Hill moved from 8 to 307, and Brooklyn Heights stayed in 8. No checked address falls
  within 25 m of an edge.
  - Concord Village (175 and 195 Adams St) stays in 13K008 in every DOE layer, which contradicts
    the Brooklyn Heights Association. The thread recommends the DOE layer, and how the draft
    treated it is unresolved.
- `scripts/`: extraction, comparison, classification and band code.

Dates: the draft came out in early September 2015, the final proposal on November 23, 2015, and
CEC13 voted 6-3 on January 5, 2016. The zones took effect for 2016-17, starting with the
kindergarten round that closed January 15, 2016.

The admission rules come only from press and civic reports:
- Current students were unaffected.
- Younger siblings of P.S. 8 students kept priority, for an unresolved length of time.
- P.S. 307's low-income set-aside share is unresolved. Only the Brooklyn Heights Association
  gives 50%, and Chalkbeat says "a portion".
