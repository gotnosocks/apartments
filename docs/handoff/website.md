# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## State (2026-10-05 17:30 UTC)

- **Estimate form live.** `/estimate` uses the prediction kit (#228, `rentfrontier.kit`) through
  the site build (#229). The kit for the served u3 run is at
  `/data1/apartments/frontier/kits/<run>-05eecfc`, and build 20261005T083600015380Z-f33640aa
  passes both checks (scoring within 0.24% on 93 rows, encoding at least 99.7%).
- **Oct 5 data publish** (build 20261005T114229499178Z-c11c9123, run …nb-v5f1u3-d1005) is
  live with the kit. `ops/autoselect-publish.sh` (#236) now runs the kit step itself.
- **Playtest round 3** (seven personas, `/data1/apartments/tmp/playtests/2026-10-05-r3/`): every
  persona reached its goals, and all five planned PRs are merged and deployed:
  - #238 building level vs typical rent wording and the estimate button
  - #239 home tiles as links, plus entries for the form and the rent map
  - #241 listing diagnostics folded away and glossed
  - #242 median estimate in the listings summary, and the building facts the form takes
  - #243 advertisement start and price change, and earlier bedroom counts on listing pages
  - #245 forms show "Working…" while loading; #246 "Available now" with few matches links the past
    listings; #247 the estimate form can set the elevator and doorman
- **Playtest round 4** (five personas, `/data1/apartments/tmp/playtests/2026-10-05-r4/`,
  `synthesis.md`): PRs merged and deployed:
  - #249 the "Why this model" box no longer says "the incumbent" for two different models
  - #250 "Your ask" says which side of the simulated asks it is on
  - #251 the skip link and #result take keyboard focus
  - #252 estimate building choices show built, floors, elevator and listings, and say when two
    share an address and tax lot (Ava High Line and 507 West Chelsea are separate towers, per
    Data improvements)
  - #253 rent map: a plainer area caveat, and why the trend differs from the median ask
  - #254 "the model is 95% sure the typical rent itself is …", and a Glossary link in the
    Estimates nav
  - #255 the breakdown says a feature's line is only its own part (Modeling: penthouse +12.2%;
    the rest sits in the unit and building lines)
  - #256 rent map choices are kept in the URL
- **Kit step for Modeling.** After the summary bundle and rent map, and before
  `apartments.site build`:
  `cd /data1/apartments/serve/master/frontier && JAX_PLATFORMS=cpu /data1/apartments/serve/master/ops/job light -m 8G -- uv run --frozen --extra gpu python -m rentfrontier.kit <run> --summary <bundle>`.
  A build without the kit shows "not available for this build".
- **Validation page** shows the served design's unit split, marked indicative when the fit failed
  the gate (#232).

## Next

1. Still open from round 4:
   - "On the market since" for current ads. Blocked on data: `listing_events` (StreetEasy price
     history) lives in a DuckDB nobody has located. The only copy is
     `/data1/apartments/archive/snapshots/chelsea-20260908`. I asked for
     `listing_started.parquet` (source_listing_id, listed_at, first_ask, days_on_market).
   - Jargon on lay pages: the model codename and PSIS-LOO on the home page, plus the breakdown
     labels "Building size and bath slopes" and "Price basis" (frontier TERM_LABELS).
   - The 92.8% under-coverage for single-listing units is only on the model page.
   - No autocomplete in building search.
   - Filter defaults (Status All, Elevator Any) are easy to miss.
   - The estimate is a market rate, not a stabilized renewal; say so where a tenant compares.
2. After the next served-model switch, check that `/estimate` still works. `autoselect-publish.sh`
   builds the kit.
3. Optional: cache the parsed kit per database (about 12 ms per request).

## Standing rules

Merge and deploy site PRs after subagent review. About-page attribution stays anonymous.
fields-review-v2 is held by Ben's choice.
