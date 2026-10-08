# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## State (2026-10-08 16:50 UTC)

- **New served fit** (refit on quarantine-v10 and ad-v3, #533): build 20261008T160955228743Z-6e89346d,
  run …ul11r1s4q10ad3. All page checks were clean, with no fixes needed: the /research/model refit notice hides
  itself; story numbers follow the data (new-apartment miss 9.4% on 517 asks); the worked example is now
  2G West Village; the design chapter shows 33 models after the 12:13 ET research-data rebuild.
  Checker script: `$S/verify.py` in the scratchpad (not in the repo); it is easy to redo with curl and site.sqlite.
- #536: "served model" defined at first use; the build-up band links to `#ranges`.
- Ben paused model runs at 16:07Z (per Modeling).

## State (2026-10-08 16:00 UTC)

- Playtest story7 (`/data1/apartments/tmp/playtests/2026-10-08-story7/`) acted on, all deployed:
  #527 wrapped theory labels keep a space between lines (copied text read "morefeatures");
  #528 the build-up says the opening's typical ask is the all-years held-out median and current
  asks run higher; #529 the accuracy chapter ends with "What this means for one estimate".
  The rest is under "Story round 7" in docs/playtests/backlog.md.

## State (2026-10-08 15:10 UTC)

- Story6 follow-ups merged and deployed: #522 the 12D example says a miss over twice the
  typical one can still sit inside the 95% range (about 1 ask in 20 lands outside); #524 a
  "Two kinds of range" box (`#ranges`) after the contents list separates intervals (how sure
  of a number, 90%/95%) from ranges (where an ask lands, 80% likely range, 95% in the example).
- Playtest story7 (story-reader) started to check them: `/data1/apartments/tmp/playtests/2026-10-08-story7/`.

## State (2026-10-08 13:45 UTC)

- **Playtest story6** (story-reader): the lay reader still gave up at Theories on trial. #520
  adds a skip hint at its top (italic, links to Cleaning, or Open questions without it), says the stretched axis in plain
  words, and flags the never-seen-apartment figure as rough under 1,000 asks (now 521).
  The rest went to the backlog under "Story round 6".
- Next on-story candidates: the 12D build-up (the "One apartment" example) (the built-year term, and why +12.4% is still
  inside the 95% range); the interval levels (80/90/95%) are still confusing.

## State (2026-10-08 13:35 UTC)

- **Theories chapter for lay readers:** #515 "The biggest wins" line and "(model term: …)"
  labels; #518 the score in plain words ("margin for luck" = standard error), PSIS-LOO and
  ΔELPD in a "The technical names" fold-out.
- **#516** a contents list of the story's chapters; **#517** the layers chart's axis says the
  share is "of the spread in asks between listings, not of the rent" (story5 misread it).
- **Playtest story6** (story-reader) started to check the theories rewrite:
  `/data1/apartments/tmp/playtests/2026-10-08-story6/`.

## State (2026-10-08 12:30 UTC)

- **Playtest story4** (`/data1/apartments/tmp/playtests/2026-10-08-story4/`, story-reader,
  economist, journalist) acted on: #509 the trust answer in the opening, "ask" defined, figure
  delays about halved; #510 theory labels wrap to four lines, none cut; #511 neighbourhood
  effects read "vs Chelsea"; #513 "spread" and the interval levels defined where first used.
  Off-story points in `docs/playtests/backlog.md` "Story round 4" (#512), unbuilt.
- **Next:** the theories chapter is still the hardest for a lay reader (36 rows, square-root
  axis); Student-t and Fourier remain only as parentheticals in its table. Then a story5 round.

## State (2026-10-08 11:30 UTC)

- **Playtest round 3 (story3) acted on:** #503 plain words in the switches and theories tables
  (`story.change_words`, "(why)" / "(no clear gain)" on blocked theories); #505 the example's
  miss in context and the served-model count; #506 the theories' score in plain words. The
  economist's off-story points are in `docs/playtests/backlog.md` ("Story round 3"), unbuilt
  under the feature hold (coordinator relay, 10:33Z).
- **#507 (live):** /research/model explains a `keep` when the served fit is on earlier data rules
  (quarantine-v6 vs current v10): "Waiting for a refit on the current data rules". Modeling has
  the current-rules refit queued, pending Ben's OK to stop the old queue; once it lands the notice
  goes away by itself.
- **Waiting on Modeling:** single-item effects result.json paths (low priority).
- **Next:** a fresh story playtest to confirm the round-3 fixes, then the remaining jargon.

## State (2026-10-08 08:40 UTC)

- **#495, #499 (live):** plain words for the layers and the first design era; the theories
  chart's labels wrap onto two lines (`story.label_lines`).
- **#500 (live):** story figures stay whole until they near view (`.whole`), a figure on screen at
  load plays at once, print shows every figure whole.
- **Waiting on Modeling:** single-item effects (`rentfrontier.effects` result.json paths) to add
  to "Inside two grouped tests", labelled as test fits unless served. Low priority, over days.
- **Next:** remaining jargon in the ledger and milestone tables, then a fresh story playtest.

## State (2026-10-08 07:50 UTC)

- **#487 (live):** the two repricing ideas now read "how the unit's previous listing was
  repriced" and "the same repricing idea, retested once Greenwich Village joined" (Ben asked what
  "the richer coded-features model" meant; both bases had the coded features).
- **#491 (live):** "Inside two grouped tests" on /research/story breaks out nb3-attrs-v1 (15 ad
  attributes) and nb3-nearby-v1 (6 walk-to places): share of listings, median walk, and a raw
  within-bedroom ask difference labelled as raw. Data: docs/model/group-items.json from
  `python -m rentfrontier.groupitems RUN --out ...` (run under `ops/job light -m 6G` with
  PYTHONPATH=frontier/src and the serve-frontier venv; tests run in the data-line venv). The
  section hides when the file names another run (regenerate it after each switch) or once the
  served model has any item's term (`text:<flag>`, `log m to <place>`): then show the served
  per-item effects instead. The served nb5 model has no such terms. Ben dropped the grouped
  per-item fits and put 21 single-feature fits on the backlog instead (#490). Modeling will
  send effects result.json paths (`rentfrontier.effects`, #488) as they land; show them labelled as test fits unless served.
  Never show the nb3 GV exploration numbers as served.

## State (2026-10-08 05:50 UTC)

- **Five neighbourhoods are served** (#468, nb5 run; build 20261008T044224922212Z-d3ede825,
  135,521 listings). Checked live: all five names on /, /estimate, /research, /research/story and
  /best; listings Chelsea 52,408, West Village 34,129, Greenwich Village 18,469, Gramercy Park
  18,333, Flatiron 12,182; no Park Slope. The story reads the nb5 variance (features 73%,
  building 9%) and the regenerated cleaning.json. #470: the summary fallback names any of the
  four non-reference areas from the inputs (`summary.NEIGHBOURHOOD_INPUTS`).
- **#477 (live):** the cleaning chapter names one joined unit (most spellings) and one clean
  split (bedrooms and ask both rising piece to piece; `<unit_id>~N` pieces), from
  `story.unit_examples`, cached per build in `web.story_checks()`. The story-reader playtest
  list is done.
- **Next:** an animated playback of the theories figure, then a fresh story playtest round.

## State (2026-10-08 04:20 UTC)

- **Story playtest follow-ups live:** #463 starts each figure's playback when it is well on screen
  (the "empty figures" were screenshots taken mid-animation; truncated labels already carry
  `<title>` tooltips). #465 adds a rent-jump example to "Are the remaining rent jumps real?":
  jumps by years between listings (`story.rent_jumps`, consecutive asks of a unit on one price
  basis, > 40% either way) and the middle-sized jump as a linked unit. `web.story_checks()` caches
  `accuracy` and `rent_jumps` per build (the page dropped from ~0.9 s to ~0.2 s).
- **Still waiting:** the five-neighbourhood fit is not served yet (build.json run is still the
  nb3 rows run). When it is, check the names, map, filters and story counts.
- **Next story item:** a real joined or split unit in the cleaning chapter (needs examples
  from `rentfrontier.cleaning`, which is Modeling's to regenerate).

## State (2026-10-08 03:30 UTC)

- **Five neighbourhoods (Ben, 2026-10-08 02:53Z):** Flatiron and Gramercy Park are to be two
  separate areas, five in total. Data is rebuilding the FGP dataset so `neighbourhood` itself is
  "Flatiron" or "Gramercy Park" per building (from the StreetEasy pageTitle in the crawl's
  `building_observations.raw_building_json`: 480 Gramercy Park, 327 Flatiron, 1 Park Slope). The
  site, rent map and summaries read names from that column, so no site change is needed. Check
  the live pages when that fit is served.
- **Story-reader playtest** (persona `story-reader`, round 2026-10-08-story) drove #459 (held-out
  row reconciliation, location-retest count, plain spread / standard error, glossary links;
  `summary.py` no longer guesses Chelsea) and #461 ("How close does it get?": median miss and
  likely-range coverage on the held-out asks, `story.accuracy`). Both live.
- **Next from that report:** see the 04:20 state above.

## State (2026-10-08 03:00 UTC)

- **The story's planned chapters are all live:** #450 "Cleaning the record" (reads
  docs/model/cleaning.json from `rentfrontier.cleaning`; Modeling regenerates it with each switch
  PR, alongside the variance) and #456 "Open questions" (location retests from the ledger's Retest
  column, rent jumps left after cleaning, ideas set aside despite a gain).
- **Next:** check the site when the first Flatiron + Gramercy Park fit is served (map guides,
  basemap, neighbourhood names, the cleaning chapter's "earlier served fit" note until cleaning.json
  is regenerated). Then polish the story: an animated playback of the theories, and a playtest of
  /research/story with a persona subagent.

## State (2026-10-08 02:10 UTC)

- **Story chapters 2 and 3 are live** (#445 theories on trial, from the feature-test ledger;
  #446 how the design evolved, from the `selection` milestones: eras, a term-span strip, the
  prevprice spell). story.py holds the parsers; tests/site/test_story.py pins them.
- **Next chapter: data-quality before/after views**, then open questions, then an animated
  playback of the theories.
- **#448 merged and deployed: site ready for Flatiron + Gramercy Park.** The rentmap guides read
  E/W streets, word and named avenues (Park Av S, Lexington, Irving Pl). Neighbourhood names come
  from the rows (`summary.hood_name` adds "the" for the West/East Village only). Data stamps the
  single name "Flatiron + Gramercy Park"; no sub-area split. Data refetches the basemap on the nb4
  registry in its registry PR. Check the map once the first FGP fit is served.

## State (2026-10-07 21:45 UTC)

- **Storytelling is now the standing work** (Ben, 2026-10-08 ~01:12Z via the coordinator; it lifts the
  feature hold for this). Whenever no redeploy or fix is pending, improve `/research/story`: a long-form,
  blog-style narrative. Every number is read from data, every figure has a text alternative and a table,
  and it stays inside the CSP (server SVG, CSS animation).
- **#438 merged and deployed:** `/research/story`, "What a rent is made of" (src/apartments/site/story.py).
  - Layers diagram from the anatomy, grouped like `rentfrontier.variance`. It shows shares once the served
    entry has `variance`; Modeling runs the variance on every switch, starting with the 9b6c16d 4500 refit.
  - Forest plot of headline effects.
  - Animated waterfall of the median current listing's LMDI contributions.
- **Next chapters, in order:** theories tested (a timeline from docs/model/feature-tests.json); design
  evolution (milestones and served history); data-quality before/after views; open questions. Also an
  animated playback of the theories.
- Backlog item 14 (a current price for every unit seen) was added in #421; not started.

## State (2026-10-07 04:00 UTC)

- **Captures use the fit's unit levels (#385):** a captured current listing of a unit the fit has
  seen is scored with that unit's level from the kit's `units.parquet` (#380), and copies the same
  ad's earlier description (Modeling: keep it). The served kit `…gv1005-1c2790b` has the file;
  live build 20261007T033530415762Z: 44 of 44 GV captures use fitted levels. 1 University Pl 2J
  is $5,671 (fit $5,443; the gap is expected, says Modeling).
- **/best rule (Ben, 2026-10-07; #383, docs/site.md):** pills only for served-model terms;
  commute and ad-stated bed size are grey notes (#384). No pills for hand labels (2B "wall"
  outlook, #382, not shown; waits for Data improvements' footprint feature).
- **Flex note (#387):** "ad says it can be set up as a N+1-bed"; 2J stays coded as a 1-bed (Ben).

## State (2026-10-07 00:40 UTC)

- #377 (Ben's OK, 00:16Z) prices current-listings captures the served fit's dataset never read with the
  run's prediction kit (`site/captures.py`, `method = "kit"`), using the dataset's own current-row rules
  (`candidate_search.select_candidates` + layout/rent support). A dataset-dropped listing or a unit
  the dataset prices as current stays out. Live: 44 Greenwich Village listings from the Oct 6 capture on
  /best (best #7, Hilary Gardens 34A); Oct 4 Chelsea/WV unchanged. `build.json` stats `captured_current`
  says how many were priced and why the others were skipped.
- A data-only rebuild is `apartments.site build` from /data1/apartments/serve/site (step 3 of
  `ops/autoselect-publish.sh`); site-deploy alone keeps the old build.
- Open (non-blocking, reviewer): `first_listing_of_unit` stays set if a unit has an earlier listing
  but no relisting centre is recoverable; no test of `captures.encode` with an earlier listing.

## State (2026-10-06 21:50 UTC)

- #368 live: My ratings removed; no rating was ever stored. #369 live: a listing whose ad has
  no size shows the size the model carried from the unit's earlier ad (only when the model has
  a size input). Round 11 findings are in docs/playtests/backlog.md; none need action yet.
- Next: pills for lines and jobs once Modeling's nb3-lines-v1 and nb3-access-v1 are in a
  served build, then ask Ben once for weights. Features stay on hold otherwise.

## State (2026-10-06 21:15 UTC)

- #366: on /best the floor counts from the usual floor (the median, the 4th), so floors 1–3
  get a "low floor" minus. Ben keeps his sheet's floor weight at 1× (20:26 UTC). #367: every
  minus pill is shown. Ratings removed at Ben's request (21:02 UTC); backlog entry added.

## State (2026-10-06 19:30 UTC)

- **Informational notes on /best (grey, not pills; Ben 2026-10-07), read at runtime from `/data1/apartments/wishes/` (newest file by
  name; each table's path and mtime are in the ranking cache key; the ranking is unchanged):**
  #355 commute (`commute-*.csv`; a neutral grey note since #384, not a plus or minus)
  and #362 bed size (`bed-size-*.csv`: "King bed fits (ad)", a floor read from the ad's text).
  Each also has a `best.csv` column.
- **Waiting on Modeling:** per-line subway (`nb3-lines-v1`, "L within 8 min" and so on; 7, J/Z and
  G unpriced) and jobs access (`nb3-access-v1`, "log jobs within 30 min"). Once a served build
  has their coefficients, add labels and hover text (`subway-lines-*.csv`, `jobs-access-*.csv`),
  then ask Ben once for their weights in his sheet. Amenity isochrones come later (Data
  improvements).

## State (2026-10-06 17:30 UTC)

- **Ben's /best asks, all merged and deployed:** #337 StreetEasy links at the top of listing pages
  (`#streeteasy`) and on /best rows (plus a `streeteasy` CSV column); #338 Street View links on
  listing, building and /best pages; #339 every plus shown; #340 Street View stands in the
  building's own street facing it (`site/streetview.py`: address to basemap street, nearest
  centreline point, affine grid-to-lat/lon fit, heading back to the building), after a lot-point
  pano opened inside a restaurant; #343 /best on phones: rows become cards below 640px, 44px tap
  targets, no sideways scroll at 320px (`.columns` uses `min(22rem, 100%)`).
- **Ben's /best feedback** is logged at the top of `docs/playtests/backlog.md` (#341). The
  pills for "fronts a big street" and transit only once they are served-model terms.
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

- **Ratings (#285)** were removed on 2026-10-06 at Ben's request; see the backlog. Round 6
  (#284) merged and deployed.
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
