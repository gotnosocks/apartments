# Manual review of high unit-level deviations

**Date:** 2026-09-21  
**Fit:** `chelsea-bayesian-expanded-spline-floor-disk-20260919`  
**Queue:** `data/model/review-queue/chelsea-bayesian-expanded-spline-floor-disk-20260919-26b5dd019416-v1`  
**Review scope:** one observation per unit, first 60 units ranked by absolute unit-level deviation

This is a direct archive review, not an LLM result. It used the selected queue,
full archived descriptions, raw listing observations, own-advertisement price
events, canonical-unit memberships, building observations and building-level
comparables. No source values were changed and no live request was made.

## Executive findings

The top tail is not a homogeneous set of mispriced conventional apartments.
It contains several recurring data/product classes:

1. **Price-entry or price-event anomalies.** Examples include $46,917 for a
   2018 two-bedroom, $13,000 immediately falling to $3,000, $999/$1,597/$1,610
   same-day studio asks in one building, and a $9,100 → $500 history.
2. **Commercial or nonstandard products.** Retail, restaurant, professional
   loft, gallery and full-floor loft offers are being compared with ordinary
   apartments.
3. **Income-restricted and shared-housing products.** Port 10 income-restricted
   apartments, SROs, roommate offers and shared-bath studios are not the same
   product as unrestricted whole-apartment rentals.
4. **Location/identity conflicts.** Several descriptions explicitly name a
   different address or neighborhood from the canonical building identity.
5. **Omitted premium/layout features.** Penthouse, duplex, private terrace,
   full-floor, keyed/private elevator and large loft attributes repeatedly
   explain large positive deviations. These should become evidence-backed
   feature candidates, not automatic price corrections.

The correct immediate response is **source/product-scope review and feature
measurement**, not replacing prices with model-friendlier values.

## The top case: 21 Chelsea #1206

**Advertisement:** [2477915](https://streeteasy.com/rental/2477915)  
**Unit page:** [21 Chelsea #1206](https://streeteasy.com/building/21-chelsea/1206)  
**Model row:** August 2018; ask **$46,917**; fitted rent excluding the unit
effect **$7,152**; deviation **+556.0%**; 0 days on market.

### Square footage conclusion

The archived evidence does **not** support calling 985 square feet invalid:

- The structured listing record reports **985 sqft**.
- The two archived captures of the same advertisement both report 985 sqft
  (snapshot IDs 6497 and 10594); the value is not a one-capture parser glitch.
- The 21 Chelsea building has 75 archived rental advertisements with two-bedroom
  records. Among 67 with known square footage, the range is **756–1,050 sqft**,
  median 808 sqft. 985 is high but inside the observed building range.
- The raw listing body for snapshot 6497 also contains `livingAreaSize: 985`.

The square-footage field should remain **unmodified** pending independent
floor-plan or source evidence. It may still be wrong in reality, but this
archive does not establish that.

### What is anomalous

The price is the stronger issue:

- `pricing.price` is 46,917.
- The only own-ad price change is also 46,917.
- The ad has both ACTIVE and NO_LONGER_AVAILABLE events on 2018-08-02 and
  `daysOnMarket: 0`; there is no later rented price.
- The description is generic building marketing copy and does not explain a
  $46,917 monthly ask, a furnished product, a concession or a special package.

**Decision:** high-priority **price-entry/source anomaly**; do not correct the
price to $7,152 or any other inferred value. Verify the original listing
representation or an external historical source if this row matters. Keep the
985 sqft value as observed.

## Highest-priority cases

| Rank | Advertisement | Evidence-based interpretation | Recommended treatment |
|---:|---|---|---|
| 1 | [2477915](https://streeteasy.com/rental/2477915) | $46,917, zero-day listing; 985 sqft is corroborated and plausible within the building | Price/source review; do not alter sqft or invent a price |
| 2 | [652674](https://streeteasy.com/rental/652674) | Structured 0BR/3BA/14-room record plus “Full Floor, Move-in Ready”; likely full-floor nonstandard product or bad layout encoding | Scope/layout review; do not treat as ordinary studio |
| 3 | [4953355](https://streeteasy.com/rental/4953355) | Canonical building is 500 W 21st, but source address is 502 W 21st and description says third-floor walkup; building is an 8-story condo | Identity/location conflict; quarantine until resolved |
| 4 | [4979243](https://streeteasy.com/rental/4979243) | $999 studio, 415 sqft, zero-day listing, no explanatory description; same-day 225 W23 records have similarly unusual asks | Price/source review; compare the full building batch |
| 5 | [4761346](https://streeteasy.com/rental/4761346) | Explicit income brackets and minimum/maximum household income | Separate income-restricted product or quarantine from unrestricted fit |
| 6 | [937046](https://streeteasy.com/rental/937046) | Restaurant/retail offer at 102 8th Avenue with liquor license, kitchen and outdoor seating, mapped to 267 W15 | Quarantine as commercial and location-conflict |
| 7 | [4758015](https://streeteasy.com/rental/4758015) | Explicit income-restricted Port 10 studio | Separate/quarantine product scope |
| 8 | [1260588](https://streeteasy.com/rental/1260588) | “Professional Loft Space available for business use,” 2,000 sqft and two bathrooms | Quarantine as commercial/nonresidential |
| 9 | [4023400](https://streeteasy.com/rental/4023400) | Initial $13,000, then $3,000 at contract/rent; model intentionally uses the initial ask | Preserve events; flag initial-price anomaly and compare final-ask sensitivity |
| 10 | [761202](https://streeteasy.com/rental/761202) | SPAC1, no description, $5,300 → $6,000; space/product scope is unclear | Human review; do not infer a correction |
| 11 | [2221592](https://streeteasy.com/rental/2221592) | Explicit SRO and shared bathroom | Quarantine or model as separate shared-housing product |
| 12 | [609730](https://streeteasy.com/rental/609730) | 4,000 sqft full-floor artist loft, key-locked elevator; structured studio | Nonstandard loft/layout review; likely feature/scope issue |
| 13 | [3813894](https://streeteasy.com/rental/3813894) | Description is only “z”; no usable source explanation | Insufficient evidence; inspect original body/parser result |
| 14 | [610152](https://streeteasy.com/rental/610152) | Private-floor penthouse with two terraces | Add penthouse/private-outdoor evidence; do not quarantine as a bad price |
| 15 | [2993341](https://streeteasy.com/rental/2993341) | Description names 145th/Malcolm X Boulevard, inconsistent with 133 W14 | Location/copy conflict; quarantine pending identity review |
| 16 | [878514](https://streeteasy.com/rental/878514) | Explicitly furnished; price path 11,500 → 10,500 → 15,500 | Furnished/product-scope quarantine; preserve price events |
| 17 | [661080](https://streeteasy.com/rental/661080) | Duplex penthouse, two planted terraces, keyed elevator and 1,100 sqft outdoor space | Add omitted-feature evidence; retain only if product scope is intended |
| 19 | [3924616](https://streeteasy.com/rental/3924616) | Structured 3BR/3BA at $4,500, but sparse description only says “townhouse charm” | Layout/price basis review; do not replace counts or price |
| 20 | [3591788](https://streeteasy.com/rental/3591788) | Suites at Orchard Townhouse, furnished/live-work, 2–12 month stays and hotel/restaurant services | Short-term/furnished/service-product quarantine |
| 24 | [2299495](https://streeteasy.com/rental/2299495) | Penthouse comprises top two floors, 2,025 sqft, private roof terrace and keyed elevators | Add omitted penthouse/outdoor/duplex features |
| 25 | [4415651](https://streeteasy.com/rental/4415651) | Street-level white-box commercial unit with freezers, mezzanine, basement and terrace | Quarantine as commercial |
| 30 | [2833618](https://streeteasy.com/rental/2833618) | Description refers to McGolrick Park, inconsistent with 160 W24 / Chelsea | Location/copy conflict; quarantine |
| 33 | [1547768](https://streeteasy.com/rental/1547768) | 317 10th Avenue GL1 explicitly says “store front Gallery” | Quarantine as commercial |
| 37 | [2818381](https://streeteasy.com/rental/2818381) | Structured studio/1BA but description says gut-renovated 3BR/2BA with balcony | Strong layout extraction conflict; quarantine/correct only with source support |
| 43 | [1316454](https://streeteasy.com/rental/1316454) | Explicit roommate offer for one bedroom in a 3BR apartment | Quarantine as shared housing |
| 47 | [3684817](https://streeteasy.com/rental/3684817) | $9,100 → $8,800 → $500 within four days | Price-event anomaly; preserve raw history and exclude/sensitivity-test the initial row |
| 57 | [2835944](https://streeteasy.com/rental/2835944) | Explicit private studio with shared bathrooms | Quarantine as shared housing |
| 59 | [3131335](https://streeteasy.com/rental/3131335) | Structured address 545 W23, canonical building 555 W23, description says Riverdale | Identity/location conflict; quarantine |

## Repeated modeling implications

### 1. Add product-scope masks before adding features

A substantial fraction of the positive tail is explained by penthouses,
full-floor lofts, duplexes, private outdoor space, commercial offers or furnished
service products. A unit random effect currently absorbs some of these features,
which is why the unit-level queue surfaces them. Add source-backed evidence
fields first:

- `commercial_or_nonresidential`
- `income_restricted`
- `shared_bath_or_room`
- `furnished_or_short_term`
- `full_floor_or_loft`
- `penthouse_or_duplex`
- `private_outdoor_access`
- `private_or_keyed_elevator`

Keep the raw text and capture scope. These should initially support review and
matched sensitivity fits, not automatic corrections.

### 2. Treat exact price histories as first-class evidence

Rows 9 and 47 demonstrate why using only the initial ask can create extreme
signals. The raw source preserves the subsequent events. Do not overwrite the
initial ask; add a separate final/current ask and price-path projection, then
compare initial-ask and final-ask fits.

### 3. Location conflicts should be a hard review gate

Rows 3, 15, 30 and 59 have direct address/neighborhood contradictions. These are
not amenity omissions. They should be quarantined before feature or residual
interpretation, with the source URL and canonical identity retained.

### 4. Do not infer corrections from model fit

For the top case, the model indicates that $46,917 is implausible, but it does
not identify the correct replacement price. Likewise, a large negative deviation
does not establish that a listing should be raised to the fitted price. The
review result should be a source-bound scope decision, a confirmed field
correction, or an unresolved case.

## Recommended next implementation

Create one reviewed source projection for the high-confidence cases above:

1. quarantine commercial/nonresidential, shared-bath/roommate and explicit
   income-restricted products;
2. quarantine direct location/identity conflicts;
3. flag, but do not automatically remove, price-event anomalies and
   penthouse/duplex/loft cases;
4. refit on the same retained rows and compare the unit-level deviation queue;
5. keep the top-60 manual decisions as a fixed development panel, then review a
   second untouched panel before promoting any new feature or exclusion policy.

The 985 sqft in 21 Chelsea #1206 should **not** be included in the first
correction projection. The price anomaly is the supported finding; the area is
not.
