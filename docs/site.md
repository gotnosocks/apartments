# Rents site: estimates and research

http://thelio.tail3983e0.ts.net:8600 (tailnet only; also on port 8500, the old research dashboard's
address, so its links keep working).

One site in two sections, with shared navigation and style (Ben, 2026-10-01: "one site, two
sections"). **Estimates** shows the scraped listings with the selected model's rent estimates.
**Research** shows how candidate models are compared and which one is served. It replaces the old
static research dashboard.

The estimates use the building, the features, the market that month and the unit's
other listings, never the listing's own ask (**leave-own-row-out**). The gap between ask and estimate
is therefore a fair signal of over- or under-pricing ([what an estimate is](model/listing-estimates.md)).

## Pages

- **Home** (`/`): the served model with its place on the board, coverage, entry points to both
  sections, and the latest merged changes and model switches.

### Estimates

- **Overview** (`/estimates`): coverage figures, the listings available now (lowest ask against
  estimate first), and the market reference rent over time.
- **Listings** (`/listings`), with filters in one row above the table:
  - building, address or unit label; bedrooms; ask range; years; status (all, available now, past);
    and the ask against the model (below typical, typical, above typical);
  - sortable columns and 25/50/100 per page;
  - CSV download of the filtered rows (`/listings.csv`, same query string).
- **Listing:** ask, estimate with its 95% range, and the gap, labelled by where the ask falls in the
  model's predictive range.
  - The page explains how the estimate was made: held out, from the unit's other listings, or, for a
    unit's only listing, from the building and features alone.
  - It shows the dollar contributions that add up to the estimate, the listing's attributes and ad-text
    flags, the in-sample fit for comparison, the unit's other listings, and links to StreetEasy.
  - Listings with an unstable leave-own-row-out correction are marked \* and explained: Pareto k
    above the run's threshold (`loo.k_threshold`: 0.7, or lower for fewer than about 2,150 draws;
    0.675 at 1,200).
- **Unit:** asks and estimates of each of its listings over time.
- **Buildings** (`/buildings`, searchable and sortable) and **building** pages:
  - level against an average building, with its 95% interval, and the yearly trend for designs with
    a building trend (walk designs show the level only);
  - the median ask against estimate;
  - MapPLUTO facts;
  - ask against estimate over time for every listing;
  - its units and listings.
- **Quarantined listings** (`/quarantined`, and a section on each building and unit page): the
  listings the selected fit's data rules leave out (its `quarantine-vN` review file). Each
  shows the review's reason, the ad's own words or the MapPLUTO record behind it, and no estimate.
  A quarantined listing's URL opens a page that explains why. A building or unit with only
  quarantined listings redirects to its list. Quarantined listings are not in the listings search
  or any estimate statistic; the home page and the Estimates overview count them.
- **Rent map** (`/estimates/map`): what a typical apartment rents for in each building, by bedrooms
  and year, from the served model (`rentfrontier.rentmap`; its definition is on the page). It has
  zoom, pan, hover and play, the median building's trend by bedroom count, and table views.
  `apartments.site build` bundles the served run's newest map (`/data1/apartments/frontier/maps`,
  `FRONTIER_MAPS` overrides it) and refuses a map of another run, so map and estimates always come
  from the same model. The page says when there is no map yet. The data is at
  `/estimates/map.json`.
- **How estimates work** (`/about`): for renters. What an estimate is and is not, calibration by
  estimate type, and why some listings are left out.

Neighbourhoods: every listing and building carries one (the summary's `neighbourhood` per row,
else the dataset's, else the build's `--scope`). The listings and buildings pages show a
neighbourhood filter, and tables and building pages name the neighbourhood, only when a build covers
more than one, so a Chelsea-only build looks as before. Older builds without the column are served
without the filter.

### Research

- **Frontier** (`/research`): every fit of one hardware class (default: the RTX 2060, the served
  model's), with these parts:
  - accuracy (PSIS-LOO ΔELPD) against fit time on the full dataset, with Ben's window (a full fit
    within 2 hours, drawn when fits reach it; exploratory subset fits within 30 minutes). A design
    measured at several draw counts is joined by a line, its best-measured fit solid and the others
    faded; the tables give each fit's draws;
  - how elegance enters (judged in pairs, so it has no chart) and how many pairs are judged;
  - the frontier fits in a table, with whether each can be served and why not;
  - every fit in a table view;
  - when the research data has an `exploration` block, the current exploration: its goal, data,
    the tier legend and the modeling notes, with a count of exploration fits.

  The marks are served, on the frontier, other, fails the convergence checks, and subset; full fits
  are circles and exploration fits diamonds (a key explains both), and the tables tag exploration
  fits. Exploration fits count on the frontier; the convergence gate applies to full fits only. Frontier
  membership and the best come from the board's own snapshots, so "board as of" shows the
  frontier as it stood at the end of any day with results. Subset fits (a `tune…` part in the run
  name, for example `nb-tune35`) are exploration only. They are hidden unless asked for, and never
  servable. Fits far below the rest (the mean-only baselines) are drawn at the chart's floor
  unless "the full accuracy range" is ticked.
- **Board** (`/research/board`): every fit on the board with its accuracy, fit time, its judged
  elegance pairs counted in words ("more elegant than 1, less elegant than 2"), its effective
  number of parameters (p_loo, sortable), checks, whether it can be served and why not, and when it landed. Filters are hardware, model
  line, a search over design, features and commit, "only servable", "subset fits" and the tier (both, full or exploration); columns sort.
  Servable is yes only when the research data says so (autoselect's `why_not_served`). Otherwise a
  fit that fails the checks is "no", and anything else is "not known yet".
- **Fit** (`/research/fits/<key>`): one fit's headline numbers, what its design does (below), whether it can be served and why
  not, the judge agents' elegance verdicts against other designs with their
  reasons, the board's note and annotations, the sampler and run, the accuracy in detail (ELPD, Pareto
  k, the held-out check), each split's diagnostics, and where the variation in rents goes. An
  exploration fit's page says what that means, gives its draws and chains, and links any full fits of
  the same design (same model, features and data rules), newest first. Every
  dot on the research charts and every fit in their tables links here.
- **What the model does** (on each fit's page and the served model's, `apartments.site.anatomy`): the
  design drawn from the `ModelConfig` its run recorded, with no hand-written per-design text:
  - a plate diagram in HTML and CSS: market, building, apartment and listing boxes, each holding its
    parts with their settings, and the parts the design leaves out drawn dashed;
  - the log-rent equation in MathML (rendered by the browser, no script), one line per level, each
    term its own element so a narrow screen wraps between terms;
  - a table of every part: its term, a plain sentence, its prior and its number of parameters (from
    the run's data sizes), which is also the text alternative to the diagram and equation;
  - on a fit's page, how its design differs from the served one ("drops building drift over time").
  Old PyMC screens record no structure and say so. A config field the module does not describe shows
  as "other option"; `tests/site/test_anatomy.py` reads ModelConfig's fields from the frontier source
  and fails until each one is described or listed as a prior or sampling setting.
- **Designs** (`/research/designs`): every design on the board as a row of the same parts (tick and
  setting, or a dash), the served design first and then by best PSIS-LOO; each links to its best fit's
  structure. Below it, how each design differs from the served one, in words.
- **History** (`/research/history`):
  - the best fit's accuracy over time on one hardware class (the board's own replay);
  - each fit's fit time by the day it landed;
  - cumulative hours of fitting by model line (custom samplers, NumPyro NUTS, PyMC);
  - every merged change and model switch.
- **Validation** (`/research/validation`):
  - each fit's PSIS-LOO score against its genuine held-out score, with their rank correlation
    (the simple baselines far below the rest are left out of the chart and counted);
  - where the variation in rents goes for the frontier fits;
  - the same design fit with different samplers;
  - the unit split (unseen apartments).
- **Data quality** (`/research/data`): listings in the data and in the served fit, every data rule in
  plain words with whether the served model uses it, the listings each review rule leaves out by
  reason, and a link to them on the Estimates side.
- **Plan** (`/research/plan`): `docs/research-plan.md` rendered with a contents list. It is read from
  the research-data checkout, which follows master (`/data1/apartments/serve/master`; `RESEARCH_PLAN`
  overrides it), so it is current between site deploys. Raw HTML in the source is escaped, not
  rendered; repository links open on GitHub.
- **Elegance** (`/research/elegance`): Ben's elegance target (2026-10-01; it replaced renter simplicity)
  in the modeling session's words, and every judgement under its brief (`elegance_judgements`), newest
  first: the two designs (linked to their fits), the verdict and reason, whether the two judges
  agreed (if not, the pair counts as equal), and each judge's own answer. Pairs the automatic
  selection is waiting on (`autoselect.pending_judgements`) are listed first.
- **Glossary** (`/research/glossary`): every research term in plain words, with anchors the pages
  link to.
- **Served model** (`/research/model`):
  - why it is served: the selection's own reason, and the latest automatic decision when the research
    data carries it (`autoselect`), with each checked fit's elegance against the served one and the
    pairs waiting for a judgement;
  - its place on the board: PSIS-LOO ΔELPD, the held-out check, fit time, elegance, effective parameters, frontier and
    gate;
  - the fit's provenance, the parts of an estimate, and every feature coefficient.

### Service pages

- `/healthz` (JSON: status, build, run, listing count) and `/robots.txt` (disallow all).

"Below typical" and "above typical" mean the ask is in the lowest or highest 10% of the model's
leave-own-row-out predictive distribution for that apartment (PIT < 0.1 or > 0.9). About 10% of
listings fall in each band, as calibration predicts.

## Data flow

1. **Estimates.** `python -m rentfrontier.summary <run>` (frontier package; see
   [listing estimates](model/listing-estimates.md)) writes a summary bundle under
   `/data1/apartments/frontier/summaries/`. Only runs that pass the convergence gate are accepted.
2. **Publish.** `python -m apartments.site build` publishes the summary that `config/main-analysis.json`
   selects (checked against the selection's sha256); `--summary <bundle>` publishes another one. It writes one SQLite snapshot and
   checks every input against the bundle's provenance:
   - the bundle's files (sha256);
   - the analytical dataset it was made from (observations.jsonl sha256);
   - the building registry and MapPLUTO extracts the run used (sha256);
   - the bundle's copies of the run's row-dropping rules (`data-rule-<rule>.jsonl`): a dataset row
     missing from the bundle must be one of their rows, and it goes into the quarantined table.

   It refuses a failing gate. It writes `/data1/apartments/site/builds/<stamp>/site.sqlite` and
   `build.json`, swaps the `current` symlink atomically, and keeps the newest three builds. It takes
   about 8 s with a 1.1 GB peak for Chelsea alone, and about 18 s with a 1.9 GB peak for Chelsea and
   West Village (86,568 listings), with a database of about 130 MB and 400 MB respectively.
3. **Serve.** The app opens `current/site.sqlite` read-only (immutable) on each request, so a publish
   needs no restart.
4. **Research data.** `rentfrontier.dashboard` (frontier environment, run from
   `/data1/apartments/serve/master` by `ops/research-data-build.sh`) writes the board's
   `data.json`: entries, as-of snapshots, milestones and the data-quality card. Each entry carries
   the judge agents' pairwise `elegance` judgements of its design (`rentfrontier.elegance`: a list
   of `{vs, verdict, reason}`, verdict "more elegant", "equal" or "less elegant"; empty when none),
   `psis.p_loo`, its `model` (the design's ModelConfig as the run recorded it) and `sizes` (the rows
   fit's rows, features, months, buildings and units), `why_not_served`, autoselect's plain reason the fit cannot be served (null when it
   can), and its `tier` (`rentfrontier` fit tiers: `{name: "exploration" | "full", draws, warmup,
   chains, subset}`; none means full). Exploration fits count on the research frontier but are never
   served; a fit with a `subset` has no PSIS-LOO score on the full data and shows in tables only. The
   top-level `exploration` (goal, dataset, baseline, a legend of `tiers` and `notes`) heads the
   frontier page. The top-level `autoselect` is autoselect's decision
   on the current board against the served run: keep or switch, the reason, the eligible fits and
   every fit checked; an error note replaces it if a pairing fails. The site reads `/data1/apartments/dashboard/site/data.json` (`RESEARCH_DATA`
   overrides it) and keeps the parsed copy until the file behind the symlink changes. Without it,
   the research parts of a page are left out. When the publish comes from the repository's
   selection, the build also stores the selection's reason (`selected_by`, `selection_reason`).

The research data is live: new fits appear without a deploy (Ben, 2026-10-01).
`apartments-dashboard-build.path` starts the build when a fit's run record, LOO score or variance
shares land (a new directory in `/data1/apartments/frontier/runs`, `loo`, `variance` or `rescores`), and
`apartments-dashboard-build.timer` every 10 minutes as a fallback. The script waits a minute for a
burst of files to settle, then builds only if a finished record or master changed since the last
build (a fingerprint in `/data1/apartments/dashboard/.last-build`), and builds again if more landed
meanwhile. The build only reads small records, so it runs without the heavy-job lock, at idle CPU
and I/O priority (about 3 minutes of one core and 600 MB; a skip takes a second). Each build is a
new directory with the `site` symlink swapped atomically, so a page never reads a half-written file.

Publishing on thelio takes the shared heavy-job lock like other heavy jobs:

```sh
cd /data1/apartments/serve/site
flock /data1/apartments/tmp/heavy.lock systemd-run --user --scope -p MemoryMax=3G \
  --setenv=TMPDIR=/data1/apartments/tmp/site-serve \
  /data1/apartments/venvs/serve-site/bin/python -m apartments.site build
```

To roll back data, point `current` at an earlier build: `ln -sfn builds/<stamp> current.new &&
mv -T current.new current` in `/data1/apartments/site`.

## Service

- **Unit:** `ops/systemd/apartments-site.service`, installed to `~/.config/systemd/user/`.
  - Waitress (8 threads) on `100.80.84.126:8600` and `127.0.0.1:8600`, MemoryMax 512M.
  - It accepts only the Host names `localhost`, `127.0.0.1`, `[::1]`, `thelio`,
    `thelio.tail3983e0.ts.net` and the tailnet IP. Any other Host gets a 400.
  - It retries until the Tailscale address is up after a boot.
- **Code** runs from the serving worktree `/data1/apartments/serve/site`, with the venv
  `/data1/apartments/venvs/serve-site` (base dependencies only). Only the deploy script moves it:

  ```sh
  ops/site-deploy.sh            # origin/master
  ops/site-deploy.sh <commit>   # a specific commit
  ```

  It checks out the commit, runs `uv sync --locked`, restarts the unit and waits up to 30 s for
  `/healthz`. If any of these steps fails, it rolls back to the previous commit the same way.
- **First deploy (bootstrap).** The script needs the worktree, the unit and a published build, so the
  first time runs these steps by hand:

  ```sh
  git -C /home/ben/code/apartments fetch origin master
  git -C /home/ben/code/apartments worktree add --detach /data1/apartments/serve/site origin/master
  cd /data1/apartments/serve/site
  UV_PROJECT_ENVIRONMENT=/data1/apartments/venvs/serve-site uv sync --locked
  flock /data1/apartments/tmp/heavy.lock systemd-run --user --scope -p MemoryMax=3G \
    --setenv=TMPDIR=/data1/apartments/tmp/site-serve \
    /data1/apartments/venvs/serve-site/bin/python -m apartments.site build
  cp ops/systemd/apartments-site.service ~/.config/systemd/user/
  systemctl --user daemon-reload && systemctl --user enable --now apartments-site
  curl -fsS http://127.0.0.1:8600/healthz
  ```
- **Logs:** one access line per request (client, method, path, status, milliseconds) in the journal:
  `journalctl --user -u apartments-site -f`.
- **Stop:** `systemctl --user disable --now apartments-site`.

## Production properties

- **Read-only.** The database is opened with `mode=ro&immutable=1`, SQL is parameterized, and sort
  columns come from fixed lists. Invalid filter values are ignored rather than turned into errors.
- **Headers:**
  - a strict Content-Security-Policy (`default-src 'self'`, no inline script or style);
    `X-Frame-Options: DENY`; `nosniff`; `Referrer-Policy: same-origin`;
  - `noindex` pages and `robots.txt`;
  - external links with `rel="noopener noreferrer"`.
- **Caching and size.** Pages carry ETags (304 on revalidation) and are gzipped when the client
  accepts it. Static assets have content-versioned URLs and a one-year cache.
- **Charts** are server-rendered SVG with a table or table view beside each. A small script
  (`static/site.js`) adds hover and keyboard readouts, and the pages work without it. Light and
  dark themes follow the system setting.
- **Paging.** Every sort key has an index ending in the row id, and a page selects its ids first,
  then fetches the full rows. Any page of any sort takes tens of milliseconds, not a whole-table sort.
- **Tests:** `tests/site/`. A small bundle, dataset and registry go through the real builder, then
  every route is checked: filters, sorting, CSV, escaping of source text, headers, Host checks,
  gzip, ETag, 404 and 503, and a publish being picked up without a restart. A query-plan test
  keeps every sort on an index.
