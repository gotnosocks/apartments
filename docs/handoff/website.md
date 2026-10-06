# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## State (2026-10-06 17:30 UTC)

- **Ben's /best asks, all merged and deployed:** #337 StreetEasy links at the top of listing pages
  (`#streeteasy`) and on /best rows (plus a `streeteasy` CSV column); #338 Street View links on
  listing, building and /best pages; #339 every plus shown; #340 Street View stands in the
  building's own street facing it (`site/streetview.py`: address to basemap street, nearest
  centreline point, affine grid-to-lat/lon fit, heading back to the building), after a lot-point
  pano opened inside a restaurant; #343 /best on phones: rows become cards below 640px, 44px tap
  targets, no sideways scroll at 320px (`.columns` uses `min(22rem, 100%)`).
- **Ben's /best feedback** is logged at the top of `docs/playtests/backlog.md` (#341). The
  site-side pills for "fronts a big street" and transit wait on Data improvements' fields.
- **Hand-set facing (#342, Data improvements):** `config/corrections/exposure-manual.csv` rows reach
  the site after `rentfrontier.exposure` and a site build; build 20261006T170007853712Z shows
  16 Barrow 1B "set by hand". Rebuild: in `/data1/apartments/serve/site`, `ops/job light -m 3G --
  /data1/apartments/venvs/serve-site/bin/python -m apartments.site build`.
- **Phone checks:** Chrome at `/usr/bin/google-chrome` with the playtest venv's Playwright
  (`executable_path=`); script at `/data1/apartments/tmp/mobile-best/shot.py`.

## State (2026-10-06 15:45 UTC)

- **Best for you (/best, #331, #332)**: an exception to the hold (Ben, 15:13 UTC). It ranks current
  listings by a preference sheet read at runtime from `/data1/apartments/preferences/<profile>.json`
  (`ben-v1`). The sheet stays out of the repo: Ben's OK at 15:25 UTC was to push without it.
  Score = Σ sign × |posterior-mean β| × input, plus the sheet's latent weights on the building's
  level and trend; it is a recombination of the model's terms, not new scores. Modeling's check
  matches to 5 digits. Default sort is fit at a good price (score − log(ask/estimate)); "best for
  the money" (score − log ask) ranks cheapest first unless filtered. Code: `site/best.py`. No
  intervals yet (Modeling: add only if Ben asks).

## State (2026-10-06 12:00 UTC)

- **Three-neighbourhood model served (#318, Modeling).** Run
  `m7-…-yearnoise-nb3-coded-v2-rows-9371a18-…-nb3-v5f1u5-gv1005`, build
  20261006T110910914042Z-39eb773f (104,967 listings). Post-publish checks passed: map,
  `/estimate`, Greenwich Village listing pages, counts, calibration by year (every year 93–95% /
  77–79%). The two refits of the earlier design failed the effects gate; this one passed.
- **Growth note back on the rent map (#321)** with Modeling's figures for this run (r7gv); it is
  keyed to the run id, so after the next switch ask Modeling for new figures again.
- **Anatomy describes `area_time` (#322)**: fixed the site test broken by #311. The count shows
  unknown until a record gives `sizes["areas"]`.
- **Playtests:** rounds 9 and 10 (best-1bed) logged (#316, #319). #313: a playtester step may
  wait 10 minutes; a full fit (`ops/job gpu -x`) holds every light slot, so start rounds between
  full fits (check with `timeout 15 ops/job light -m 1G -- true`).
- **Exposure evidence (#315):** Data improvements' per-unit evidence table and wording are in
  backlog item 11, to build when the hold lifts.
- Earlier today: #304 (playtester model `claude-sonnet-5-5`), #308 (`wait-next --max` 25),
  #310 (board re-baselined on the Greenwich Village data; fits on the 1 October data and older now unscored: `prior_scores` keeps one baseline, Modeling's code).

## State (2026-10-05 20:30 UTC)

- **Website features on hold (Ben, 18:22 UTC).** Playtest only with `best-1bed`, one persona a
  round, and log findings in `docs/playtests/backlog.md` (#299; round 8 in #302). No feature or
  playtest-fix PRs; fixes for things broken or wrong on the live site still ship. Ben's standing
  approval (19:23 UTC): apply his changes the coordinator relays without asking again, except
  spending money or deleting data.
- **Greenwich Village ready (#300).** The site follows the data for a third neighbourhood. The
  map's growth decomposition shows only while run `m7-…-nb-v5f1u3-d1005` is served; ask Modeling
  for new figures after the three-neighbourhood refit (03:00 ET 2026-10-06). After it lands,
  check the map, `/estimate` and a Greenwich Village listing page.
- **Bigger map (#298)** and the playtester model id `claude-sonnet-5` (#301) merged.

- **Round 7 done (#291).** Since then: calibration by year on About and "why the map grows less
  than the median ask" on the rent map (#293, Modeling's numbers), a "Start here" card on Home
  (#294), a walk-up / elevator choice on the rent map (#296, tax class C / D), and the map sized to
  the window's height rather than the space below its top (this PR; about 500 px wide on a
  1366×900 screen instead of 175). Live build 20261005T180141796618Z-c11c9123.
  Open from the round 7 synthesis: a dollar baseline for the estimate breakdown; photos, a map and
  street quietness for best-1bed; counts for the not-stated filters.

- **Exposure live (#290).** Data improvements' labels (`/data1/apartments/exposure/labels.parquet`)
  go into a build's `exposure` table: a Faces fact on listing pages, short words in listing
  tables and a Faces filter (`/listings?faces=rear`). 12,875 units labelled (8,195 own, 4,680 from
  their line) in build 20261005T172157196192Z-c11c9123. Code deploys don't rebuild the database:
  a labels change shows after the next site build. "Looks onto" and the summary are unchanged until
  agreed with Data improvements.
- **Estimate form: line facing and previous listing groups (#289).**

- **Ratings live (#285).** Card on listing pages, `/ratings`, `/ratings.csv`, `/ratings.json`;
  stored in `/data1/apartments/ratings/ratings.sqlite` (made on the first save). Design in
  `docs/ratings.md`. Round 6 (#284) merged and deployed.
- **Earlier-data charts on Chart.js.** Exploration fits trained before the board moved to the
  current data (100 at 17:00 UTC) sit in the "Scored on the earlier data" chart, now zoomable
  (prefixes `fp`, `ep`) with a best-so-far line (display only, `web.best_so_far`). Only 2
  exploration fits are scored on the current data, so the main exploration chart is sparse until
  Modeling rescores or refits.

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
- **Since then (all merged and deployed):** #273 separate full and exploration frontier charts;
  #275 listing pages say what the model makes of the listing (`summary.py`); #277 exploration fits
  on the earlier data drawn apart; #279 a note when ask and estimate move opposite ways by more
  than 5% each (`opposite_moves`); #280 small hover cards that wrap; #282 the frontier charts drawn
  with Chart.js 4.5.1 plus the zoom plugin, vendored flat in `static/` (`VENDOR.md`), built by
  `static/fitchart.js` from a `script.chart-spec` JSON block, with the SVG as the no-JS fallback.
  The earlier-data, history and elegance charts are still SVG.
- **Playtest rule (Ben 2026-10-05):** at most 3 personas a round, one bundled PR and one review
  per round, `best-1bed` in any round that touches listings, summaries or ratings
  (`docs/playtests/README.md`, enforced by `ops/playtest.sh`).
- **Playtest round 6** (best-1bed, `/data1/apartments/tmp/playtests/2026-10-05-r6/synthesis.md`):
  one bundled PR adds Laundry, Doorman and Outdoor filters, "Elevator: Yes or not stated", a
  features line in listing tables, and Looks onto, Outdoor space and the floor read from the
  unit number on listing pages.
- **Walk-up wording (Modeling):** the walk-up floor effect lost; never imply one. Where walk-ups
  are explained, say it was tested, didn't improve predictions, and isn't applied beyond the
  existing floor terms.
- **Kit step for Modeling.** After the summary bundle and rent map, and before
  `apartments.site build`:
  `cd /data1/apartments/serve/master/frontier && JAX_PLATFORMS=cpu /data1/apartments/serve/master/ops/job light -m 8G -- uv run --frozen --extra gpu python -m rentfrontier.kit <run> --summary <bundle>`.
  A build without the kit shows "not available for this build".
- **Validation page** shows the served design's unit split, marked indicative when the fit failed
  the gate (#232).

## Next

1. After each round, add findings to the top of `docs/playtests/backlog.md` (docs-only PR).
2. After the next served-model switch, check that `/estimate` still works. `autoselect-publish.sh`
   builds the kit.
3. Optional: cache the parsed kit per database (about 12 ms per request).

## Standing rules

Merge and deploy site PRs after subagent review. About-page attribution stays anonymous.
fields-review-v2 is held by Ben's choice.
