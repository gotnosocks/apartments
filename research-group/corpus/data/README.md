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
