# Website thread handoff

What the next turn of the website thread needs. Updated at each milestone.

## Handover to the new Website thread (2026-10-14 22:45 UTC)

Ben is moving each workstream to a single thelio session he talks to directly. Start here, then
read the dated entries below for history.

### State

- Served fit: `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-nb8-nostuy-v1-rows-5c1e5c7e-a100-4500k9cb1-nb8-ul15r1s4q12ad3`,
  the NB8 fit across all eight neighbourhoods.
- Live build: `/data1/apartments/site/builds/20261010T200723992516Z-37822512`, built
  2026-10-10 20:09Z and served on :8600 and :8500 by `apartments-site.service`.
- The site shows Estimates (listings, buildings, the rent map, /best, available now, the estimate
  form) and Research (story, board, model, validation). The research data rebuilds every 10
  minutes from `/data1/apartments/dashboard/site/data.json`.
- Recent PRs, all merged:
  - #775 and #780: The West Coast wings. When a fit has `the-west-coast-west-wing`, the site
    names the pages "The West Coast (West Street wing)" and "The West Coast (Washington Street
    wing)". It sends a capture on the-west-coast or the 97 Horatio page to the West Street wing
    when its label is three digits, and to the-west-coast otherwise, following
    `west-coast-wings-v1`. The table is in `src/apartments/site/wings.py`.
  - #784: story words for `nb8-nostuy-wings-v1`.
  - #781 (Modeling): `anatomy.py` describes `walk_ar`, `walk_ar_rho` and `walk_rho_prior`.
    `tests/site` passes on master again.
  - #689, #690: new-unit coverage on the checks and in the story.

### Open work

- #776 holds the nb9 words: Hell's Kitchen and Hudson Yards in `summary.NEIGHBOURHOOD_INPUTS`,
  and `nb9` in `story.AREA_WORDS`. Merge it when Modeling serves an nb9 fit (Ben 18:40Z: wait
  for the fit, no unpriced display). Then:
  1. check whether the Midtown West capture
     (`/data1/apartments/tmp/mw-current-20261014/details/snapshot/`, 468 ads) is still inside
     the 7-day window, which it leaves on Oct 20;
  2. if Data collection has placed it under `archive/current-listings`, rebuild and verify both
     areas in the selectors, map, /best, available now and the counts ("all ten
     neighbourhoods"; count words go up to ten).
- The coverage and explained-share slots fill from the served entry's data. A slot without its
  key stays hidden or reads "not yet measured".
- The Chelsea, West Village and Greenwich Village current captures are stale (newest
  `20261004` and `20261006-greenwich-village`). They show as past until a recrawl. The daily
  crawl waits on Ben.
- The wing fit on `nb8-nostuy-wings-v1` is running on Modal. When autoselect serves it, check
  the two West Coast pages and that captures from the complex are priced.

### Standing rules

See the handover section at the top.
