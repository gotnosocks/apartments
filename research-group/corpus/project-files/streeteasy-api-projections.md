# StreetEasy collection through the API: requests and cost per area

Prepared Oct 15 2026, 00:40 ET. Prices use $1.14 per 1,000 Oxylabs requests.

## How the new collection works

The crawler asks StreetEasy's public listing API (api-v6) three things, all through the Oxylabs proxy:

1. It lists every rental ad ever listed in an area with the search query. A request returns up to 4,000 ad ids, and the crawler splits an area by price and bedrooms whenever its count passes the 1,000-ad window of a single search.
2. It reads the full record of each ad, including its address, unit, building and complete price history, in batches sized to about 6 MB per request. A batch holds about 500 recent ads or about 125 of the oldest, since older ads carry longer histories. When the API times out, the crawler halves the batch and asks again.
3. It reads each building's details, such as units, year built, location and amenities, 100 or more buildings a request.

Each unit's newest ad carries the unit's whole rental history, so the crawler gets unit memberships without fetching unit pages.

## The NoMad check

I rebuilt NoMad from the API alone and compared it with the page crawl from Oct 8.

| | Page crawl | API |
|---|---:|---:|
| Requests | 13,504 | about 90, including retries I can now avoid |
| Cost | about $15.40 | about $0.10 |
| Ads with ids from 1,210,000 tied to a unit | 12,475 | 14,076 |
| Buildings | 213 | 218 |

Of the crawl's 12,475 ad-to-unit links, 12,357 match the API once unit spellings are normalized. Another 109 differ because the API ties the ad to two spellings of one unit, like "2" and "2nd-floor". The collection policy already drops those as conflicts. That leaves 9 links the API missed. The API also tied 1,610 ads to units the crawl never linked them to. The crawl never queued 1,534 of those ads at all.

## Per-area projections

The estimate is about 4 requests per 1,000 ads ever listed: 1 for listing ids, about 3 for full records, and a small share for buildings. "Page-crawl cost" uses the old crawl's average of 0.7 requests per ad, for comparison.

### Manhattan below 59th St, not yet collected

| Area | Ads ever listed | Active now | API requests | API cost | Page-crawl cost |
|---|---:|---:|---:|---:|---:|
| Financial District and Fulton/Seaport | 74,905 | 307 | 302 | $0.34 | $60 |
| Lower East Side and Two Bridges | 55,483 | 125 | 224 | $0.26 | $44 |
| Tribeca | 27,266 | 93 | 112 | $0.13 | $22 |
| Soho and Hudson Square | 24,764 | 71 | 102 | $0.12 | $20 |
| Battery Park City | 21,349 | 79 | 88 | $0.10 | $17 |
| Nolita | 15,935 | 31 | 66 | $0.08 | $13 |
| Little Italy | 7,684 | 18 | 33 | $0.04 | $6 |
| Chinatown | 6,741 | 11 | 29 | $0.03 | $5 |
| Noho | 6,299 | 12 | 28 | $0.03 | $5 |
| Civic Center | 77 | 0 | 3 | $0.00 | $0 |
| Midtown | 37,221 | 161 | 151 | $0.17 | $30 |
| Midtown South | 24,872 | 103 | 102 | $0.12 | $20 |
| Murray Hill | 55,343 | 236 | 224 | $0.26 | $44 |
| Kips Bay | 60,648 | 158 | 245 | $0.28 | $48 |
| Turtle Bay and Beekman | 44,215 | 144 | 179 | $0.20 | $35 |
| Sutton Place | 27,653 | 88 | 113 | $0.13 | $22 |
| Central Park South | 4,797 | 37 | 22 | $0.03 | $4 |
| **Total** | **495,252** | **1,674** | **2,023** | **$2.31** | **$395** |

### Brooklyn west and north of Prospect Park

| Area | Ads ever listed | Active now | API requests | API cost | Page-crawl cost |
|---|---:|---:|---:|---:|---:|
| Park Slope | 60,417 | 142 | 244 | $0.28 | $48 |
| Prospect Heights | 19,135 | 43 | 79 | $0.09 | $15 |
| Gowanus | 12,466 | 180 | 52 | $0.06 | $10 |
| Carroll Gardens | 15,805 | 34 | 66 | $0.08 | $13 |
| Cobble Hill | 10,315 | 16 | 44 | $0.05 | $8 |
| Boerum Hill | 14,511 | 42 | 61 | $0.07 | $12 |
| Brooklyn Heights | 22,883 | 55 | 94 | $0.11 | $18 |
| DUMBO and Vinegar Hill | 14,757 | 77 | 62 | $0.07 | $12 |
| Downtown Brooklyn | 36,506 | 284 | 149 | $0.17 | $29 |
| Fort Greene | 23,843 | 93 | 98 | $0.11 | $19 |
| Clinton Hill | 29,911 | 86 | 122 | $0.14 | $24 |
| Red Hook | 3,218 | 7 | 15 | $0.02 | $3 |
| Columbia St Waterfront | 3,505 | 5 | 17 | $0.02 | $3 |
| **Total** | **267,272** | **1,064** | **1,103** | **$1.26** | **$213** |

### North Brooklyn and Crown Heights (optional)

| Area | Ads ever listed | Active now | API requests | API cost | Page-crawl cost |
|---|---:|---:|---:|---:|---:|
| Greenpoint | 49,652 | 223 | 201 | $0.23 | $40 |
| Williamsburg and East Williamsburg | 177,775 | 333 | 714 | $0.81 | $142 |
| Bushwick | 151,171 | 317 | 607 | $0.69 | $121 |
| Bedford-Stuyvesant | 167,005 | 418 | 671 | $0.76 | $133 |
| Crown Heights | 112,508 | 293 | 453 | $0.52 | $90 |
| **Total** | **658,111** | **1,584** | **2,646** | **$3.02** | **$525** |

### Areas already collected, read again to fill gaps

| Area | Ads ever listed | Active now | API requests | API cost | Page-crawl cost |
|---|---:|---:|---:|---:|---:|
| Chelsea and West Chelsea | 79,584 | 247 | 321 | $0.37 | $64 |
| West Village | 63,347 | 148 | 256 | $0.29 | $51 |
| Greenwich Village | 43,584 | 90 | 177 | $0.20 | $35 |
| Flatiron and NoMad | 42,165 | 127 | 171 | $0.19 | $34 |
| Gramercy Park | 33,103 | 66 | 135 | $0.15 | $26 |
| East Village | 116,890 | 201 | 470 | $0.54 | $93 |
| Stuy Town | 10,112 | 34 | 43 | $0.05 | $8 |
| Midtown West | 133,941 | 501 | 538 | $0.61 | $107 |
| **Total** | **522,726** | **1,414** | **2,111** | **$2.41** | **$417** |
All four groups together come to about 7,900 requests, about $9. The same coverage by page crawl would cost about $1,550.

## Daily top-up

Once an area is collected, a daily run keeps it current:

- about 10 requests to list the active ads in every area,
- about 12 requests to read the roughly 5,700 active ads in full,
- 1 or 2 requests to read the ads that dropped off since the day before, which records their last price and status,
- 1 request for any new buildings.

That comes to about 25 requests a day, roughly $0.03 a day or $1 a month, for all the areas above. It replaces the separate daily refresh of current ads proposed earlier at 2,000 to 3,000 requests a day.

## Limits

- The API answers with GATEWAY_TIMEOUT when a response would pass about 10 MB, so batch sizes follow the expected bytes and halve on a timeout.
- The search window stops at 1,000 results, so the crawler splits large areas by price and bedrooms. That costs about one extra request per 1,250 ads.
- Ads that the API ties to two spellings of one unit stay excluded under the current policy, about 1% of NoMad's ads.
- The API gives no unit for 1,038 of NoMad's 15,114 recent ads, about 7%. The policy needs a unit, so those ads stay out, as they do now.
