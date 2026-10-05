# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## State (2026-10-05 14:10 UTC)

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
  - #259 plain labels for the breakdown terms, and plain accuracy words on the home page
  - #260 the estimate is a market ask, not a renewal or legal rent
  - #261 /estimate says first-listing ranges run narrow (single-listing coverage of the 80% and 95%
    ranges; listing pages already said so)
  - #262 the listings count spells out the default Status and Elevator filters, with links that
    narrow them
  - #263 building suggestions as you type (`/buildings.json` plus a datalist in site.js). On
    /estimate a pick sets the building id, unless two buildings share the name
  - #266 current listing pages say when this ad went on StreetEasy (`site/ad_dates.py`: the
    page's own `onMarketAt`, only when its listing id is the row's; a return after a rented or
    off-market break comes from that listing id's own events). Per ad, never per unit (Ben). The
    `ad_dates` table needs a site build to fill; build 20261005T140617320837Z dates 235 of 235.
- **Playtest round 5** (journalist, renter, renewer, mobile, `/data1/apartments/tmp/playtests/2026-10-05-r5/`,
  `synthesis.md` lists the planned PRs): #267 the default-filter links read as actions.
- **Kit step for Modeling.** After the summary bundle and rent map, and before
  `apartments.site build`:
  `cd /data1/apartments/serve/master/frontier && JAX_PLATFORMS=cpu /data1/apartments/serve/master/ops/job light -m 8G -- uv run --frozen --extra gpu python -m rentfrontier.kit <run> --summary <bundle>`.
  A build without the kit shows "not available for this build".
- **Validation page** shows the served design's unit split, marked indicative when the fit failed
  the gate (#232).

## Next

1. Round 5 PRs in `synthesis.md` order: building Units table capped at 13 rows (branch
   site-building-units-all started), "Building level" glossary entry and class codes, rent map
   fit to area, estimate form's two steps, breakdown on phones, unit chart legend, journalist items.
   Optional: warn when a building link lands on a much pricier building.
2. After the next served-model switch, check that `/estimate` still works. `autoselect-publish.sh`
   builds the kit.
3. Optional: cache the parsed kit per database (about 12 ms per request).

## Standing rules

Merge and deploy site PRs after subagent review. About-page attribution stays anonymous.
fields-review-v2 is held by Ben's choice.
