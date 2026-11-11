# Rents site

http://thelio.tail3983e0.ts.net:8600 (tailnet only; also on port 8500).

The site shows the served drift model ([model/drift.md](model/drift.md)) in four sections with
shared navigation and style: **Deals**, **Estimates**, **Workbench** and **Tags**. Each section
reads a folder under the site root, written by a publish step of the model.

Each estimate comes from a fit that never saw the ask it is compared with: the newest ad of each
apartment is held out of the fit on the latest split, and the ads on the market out of the fit on
the market split ([leak-free scoring](leak-free-scoring.md)).

## Pages

### Deals

- **Deals** (`/`, and `/deals` for the same page): the ads on the market on the scoring day,
  ranked by how low each ask sits in the served model's predictive range for that apartment
  (`apartments.site.deals`). The page reads the `deals/` folder that
  `python -m rentfrontier.drift_deals publish` last wrote (`deals.json`, `meta.json`,
  `validation.json`), so it shows the last complete publish. Ads with a caution
  (`rentfrontier.cautions`) are left out unless asked for. Publish only from a fit that passed
  the gate, with its backtest. A link that changes the order starts again at the first page.

### Estimates

`python -m rentfrontier.drift_estimates publish LATEST_RUN --market MARKET_RUN --registry
REGISTRY --out <root>/estimates` writes `estimates.parquet`, one row per ad a fit held out, and
then `meta.json` (the model, the two runs and their convergence gates, the latest fit's held-out
scores, the counts, and the table's sha256). A row's `source` is `latest`, a past ad that is the
newest ad of its apartment, whose final ask the fit on the latest split never saw, or `market`,
an ad on the market on the scoring day, held out by the fit on the market split. An apartment's
earlier ads have no estimate: the fits learned from their asks. Both runs must be fits of one
model that passed the gate.

`apartments.site.estimates` reads only that folder. It refuses a table whose sha256 is not the
one in `meta.json` (the pages answer 503 until the next publish), hashes a table once per file
version, and queries it with DuckDB: one connection per process, one thread, 256 MB.

- **Overview** (`/estimates`): what the estimates are, the model and its two runs with their
  gates, held-out accuracy (the median error as a percent of the ask, `exp(x) - 1` of the
  log-scale median absolute error, and how often the 50/80/90/95% ranges held the asks against
  what they are meant to), the counts, and links to the list, the CSV and Deals.
- **All held-out ads** (`/listings`): the estimates, 50 a page, filtered by address or building,
  neighbourhood (grouped by borough when there are several), bedrooms, ask range, years and
  which ads (`status`: all, `current` for the ads on the market, `past` for the latest fit's),
  and ordered newest first, by the ask against the model (`sort=low` or `high`, by
  `below_share`) or by the ask. Each row has the ask, the model's middle estimate, its 80%
  range, where the ask sits ("lower than 95%" of the asks the model would expect) and links to
  the estimate's page and to StreetEasy. With a filter, a line sums up the matches: count,
  median ask, median of the model's medians, and the share of the past ads inside the 80% and
  95% ranges.
- **CSV** (`/listings.csv`, the same query string): every column of the table, streamed in
  chunks of 5,000 rows.
- **Estimate** (`/listings/<listing id or audit id>`): the ask against the model's middle
  estimate and its 50/80/95% ranges (drawn as nested bands), where the ask sits in words, how
  many of the apartment's earlier ads the model learned from (none makes it a new apartment to
  the model, with a wider range), the fit and run that made it, and links to StreetEasy and
  Street View. When `diagnostics/` is published, the page adds the ad's facts, its flags and the
  building's ads, and the building's name links to its Workbench page when the Workbench has
  the building. An ad with no held-out estimate answers 404.
- **Hoboken and Jersey City** (`/new-jersey`, `/new-jersey.csv`): observed asks with no model,
  read from the `observed` table of `current/site.sqlite`. Without that file the page is empty.
- **How it works** (`/about`): the model in a few paragraphs, with its terms, gates, coverage and
  counts from `diagnostics/meta.json`, then how to read a held-out estimate, the range bar on
  Deals, the cautious saving, a miss on the Workbench, and tags. Without `diagnostics/` the page
  leaves the figures out and says so.
- Without an `estimates/` folder the overview, the list and the estimate pages answer 503 "No
  estimates have been published yet."

When a publish covers neighbourhoods in more than one borough, the filters group their choices by
borough (`boroughs.BOROUGHS` maps the scrape's StreetEasy names). Each group opens with a
whole-borough choice ("All of Brooklyn"), and `nb=Brooklyn` filters to the borough's
neighbourhoods.

### Workbench

`python -m rentfrontier.drift_diagnostics publish` writes `diagnostics/` (`ads.parquet`,
`buildings.parquet`, `history.parquet`, `meta.json`). `apartments.site.workbench` checks the
tables' sha256 against `meta.json` and queries them with DuckDB.

- **Overview** (`/workbench`): calibration of the held-out ranges, the attributes with the
  largest misses, and the detector flags.
- **Signals** (`/workbench/signals`, `/workbench/signals/<feature>`): the held-out miss by each
  attribute's levels.
- **Triage** (`/workbench/triage`, `/workbench/triage.csv`): the held-out ads ordered by miss.
- **Buildings** (`/workbench/buildings`, `/workbench/buildings/<building>`): each building's
  level and its held-out ads.

### Tags

- **Tags** (`/tags`, `/tags.jsonl`, `/tags.csv`): the ledger of readings of ads
  (`apartments.site.tags`): a confirmed deal, a data error, or something the model has no term
  for. A form on the listing page posts to `/tags`, and `append` adds a JSON line to
  `tags/tags.jsonl` under a file lock. When the file ends partway through a line, `append`
  writes a newline first, so each record stays on a line of its own.

### Service pages

- `/healthz` (JSON: status, model, scoring day, and the counts of deals and estimates; 503 when
  neither table is published) and `/robots.txt` (disallow all).

## Data flow

1. **Estimates.** The Estimates pages read `<root>/estimates/`, which
   `python -m rentfrontier.drift_estimates publish` writes from a passing pair of drift fits
   (above). The rest of this section is the path that makes `site.sqlite`, whose `observed`
   table the Hoboken and Jersey City page reads:
   `python -m rentfrontier.summary <run>` (frontier package; see
   [listing estimates](model/listing-estimates.md)) writes a summary bundle under
   `/data1/apartments/frontier/summaries/`. Only runs that pass the convergence gate are accepted.
2. **Publish.** After an autoselect switch is merged and deployed, `ops/autoselect-publish.sh`
   runs the three publish steps for the served run: the rent map (`rentfrontier.rentmap`), the
   estimate kit (`rentfrontier.kit`, which the build checks and prices captures with) and the
   site build below. Each step keeps an
   output that already exists for the run and commit.
   `python -m apartments.site build` publishes the summary that `config/main-analysis.json`
   selects (checked against the selection's sha256); `--summary <bundle>` publishes another one. It writes one SQLite snapshot and
   checks every input against the bundle's provenance:
   - the bundle's files (sha256);
   - the analytical dataset it was made from (observations.jsonl sha256);
   - the building registry and MapPLUTO extracts the run used (sha256);
   - the bundle's copies of the run's row-dropping rules (`data-rule-<rule>.jsonl`): a dataset row
     missing from the bundle must be one of their rows, and it goes into the quarantined table.

   It refuses a run that fails the gate unless the selection records a decision to serve it anyway
   (`gate_override`: who decided, when, and why). It writes
   `/data1/apartments/site/builds/<stamp>/site.sqlite` and `build.json`, swaps the `current` symlink
   atomically, and keeps the newest three builds, or only the new one when its database is over
   4 GB. It takes
   about 8 s with a 1.1 GB peak for Chelsea alone, and about 18 s with a 1.9 GB peak for Chelsea and
   West Village (86,568 listings), with a database of about 130 MB and 400 MB respectively. The
   eight neighbourhoods (214,931 listings) take 1:42 with a peak of about 5.0 GB.

   The build streams the bundle's rows so a fit of every borough fits in memory. It reads them
   from `rows.parquet` in chunks of about 40,000 rows (`CHUNK_ROWS`), each a run of whole
   buildings, with buildings that share a unit kept together, and in the bundle's order within a
   chunk, which breaks ties in time as the bundle does. It indexes `observations.jsonl` by byte
   offset and reads a row back only when asked. The kit checks read the stored listings as a
   stream, and pricing the pipeline's current ads reads only the ads' own buildings and units,
   with the relisting centre worked out once from every listing. It works out the research
   story's held-out accuracy, rent jumps, unit examples and border medians into meta
   (`story_checks`). The fit of
   297,273 listings takes 4:36 with a peak of 3.8 GB (7.5 GB before streaming). The all-scraped
   fit (1,755,430 listings in Manhattan and Brooklyn, 2026-10-17) takes 48:39 with a peak of
   5.2 GB and writes a 10.3 GB `site.sqlite`, 7.2 GB of it the `listings` table and 2.1 GB the
   kit's building draws. DuckDB sorts the chunks on one thread, since with more it failed to pin
   blocks under its 1 GB limit. `estimate_build.load_kit` holds the kit's draws in flat float
   arrays: as Python lists, the kit's 67,735 buildings with 250 draws each pushed the build past
   8 GB.

   With `SITE_DETAIL_ON_REQUEST=1`, which `ops/autoselect-publish.sh` sets unless the caller sets
   it to another value, the build leaves the fitted listings' dollar parts out of the `listings`
   table (`contributions` stays null; 3.2 GB of the 10.3 GB all-scraped `site.sqlite` of Oct 17
   by a column scan) and copies them from `rows.parquet` into
   `detail.parquet` beside `site.sqlite` (`apartments.site.detail`). The copy is sorted by
   `audit_id` in row groups of 8,192, with each row's parts in a single list column, and
   `meta.stats.detail` records its rows and bytes. `detail.lookup` reads
   a listing's parts from it through one DuckDB connection per process (one thread, 128 MB),
   cached by the bundle's sha and the audit id. Ads priced from the kit keep their parts in the
   table. On the eight-neighbourhood build the file holds 135 MB in place of 547 MB of JSON, and
   the parts it gives back for Ben's opened listings and 2,000 random ones match the stored ones
   to the cent; on the all-scraped bundle (1.75M rows) the copy takes 30 s on one thread with
   1.2 GB resident and writes 779 MB, and a lookup takes 12 to 35 ms.

   A bundle summarized with `--range-atoms` (`FRONTIER_RANGE_ATOMS=1`, #1065) carries 64 range
   atoms and a noise group per row in place of the likely ask ranges, plus `noise.json`. For
   such a bundle the build copies the atoms into `ranges.parquet` (sorted by `audit_id`, rows
   with atoms only) and `noise.json` beside `site.sqlite`, and `meta.stats.ranges` records the
   rows and bytes. `apartments.site.ranges` works out a listing's 95% and 80% ranges
   from its atoms when the table holds none, cached by the bundle's
   sha and the audit id; rows from a summary chunk that fell back to the exact solve keep their
   ranges in the table. The kit's scoring check reads its reference ranges the same way, for the
   few hundred rows it scores. A listing with no atoms or no noise table for its group has no
   range.

   With `SITE_KIT_ON_REQUEST=1`, which `ops/autoselect-publish.sh` also sets unless the caller sets
   it to another value, the build leaves the `kit_buildings` table empty and copies the
   kit's `buildings.parquet` into `kit_buildings.parquet` beside `site.sqlite`
   (`estimate_build.write_kit_file`), in row groups of 2,048 buildings with each building's
   feature slopes in a single list, and `meta.stats.estimate_form.kit_file` records its rows,
   bytes and whether it came out sorted. `estimate_build.building` reads a building's draws from
   it through DuckDB. On the all-scraped kit the file holds 421 MB in place of 2.08 GB of JSON,
   the copy takes 12 s with 0.3 GB resident, and a lookup takes about 55 ms.
3. **Serve.** The app reads `deals/`, `estimates/` and `diagnostics/` by their files' versions,
   so a publish needs no restart. A request for the Hoboken and Jersey City page opens
   `current/site.sqlite` read-only (immutable).
4. **Research data.** `rentfrontier.dashboard` (frontier environment, run from
   `/data1/apartments/serve/master` by `ops/research-data-build.sh`) writes the board's
   `data.json`: entries, as-of snapshots, milestones and the data-quality card. Each entry carries
   the judge agents' pairwise `elegance` judgements of its design (`rentfrontier.elegance`: a list
   of `{vs, verdict, reason}`, verdict "more elegant", "equal" or "less elegant"; empty when none),
   `psis.p_loo`, its `model` (the design's ModelConfig as the run recorded it) and `sizes` (the rows
   fit's rows, features, months, buildings and units), `why_not_served`, autoselect's plain reason the fit cannot be served (null when it
   can), and its `tier` (`rentfrontier` fit tiers: `{name: "exploration" | "full", draws, warmup,
   chains, subset}`; none means full). Exploration fits are research points (on the frontier only when they pass
   the gate) and are never served; a fit with a `subset` has no PSIS-LOO score on the full data and shows in tables only. The
   top-level `exploration` holds the goal, dataset, baseline, a legend of `tiers` and `notes`.
   The top-level `autoselect` is autoselect's decision
   on the current board against the served run: keep or switch, the reason, the eligible fits and
   every fit checked; an error note replaces it if a pairing fails. The build writes
   `/data1/apartments/dashboard/site/data.json`. When the publish comes from the repository's
   selection, the build also stores the selection's reason (`selected_by`, `selection_reason`, `gate_override`).

`apartments-dashboard-build.path` starts the build when a fit's run record, LOO score or variance
shares land (a new directory in `/data1/apartments/frontier/runs`, `loo`, `variance` or `rescores`), and
`apartments-dashboard-build.timer` every 10 minutes as a fallback. The script waits a minute for a
burst of files to settle, then builds only if a finished record or master changed since the last
build (a fingerprint in `/data1/apartments/dashboard/.last-build`), and builds again if more landed
meanwhile. The build reads run records, per-row LOO scores and the current dataset, without draws, and runs as a light job (see
[thelio-jobs.md](thelio-jobs.md)), on the light CPUs at idle CPU and I/O priority (about 4 minutes of one core and 1.6 GB, under a 2.5 GB cap with no swap; a skip takes a second). Each build is a
new directory with the `site` symlink swapped atomically, so a reader gets a complete file.

Publishing on thelio is a light job ([thelio-jobs.md](thelio-jobs.md)):

```sh
cd /data1/apartments/serve/site
TMPDIR=/data1/apartments/tmp/site-serve /data1/apartments/serve/master/ops/job light -m 3G -- \
  /data1/apartments/venvs/serve-site/bin/python -m apartments.site build
```

To roll back data, point `current` at an earlier build: `ln -sfn builds/<stamp> current.new &&
mv -T current.new current` in `/data1/apartments/site`.

## Service

- **Unit:** `ops/systemd/apartments-site.service`, installed to `~/.config/systemd/user/`.
  - Waitress (8 threads) on `100.80.84.126:8600` and `127.0.0.1:8600`, MemoryMax 3G.
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
  TMPDIR=/data1/apartments/tmp/site-serve /data1/apartments/serve/master/ops/job light -m 3G -- \
    /data1/apartments/venvs/serve-site/bin/python -m apartments.site build
  cp ops/systemd/apartments-site.service ~/.config/systemd/user/
  systemctl --user daemon-reload && systemctl --user enable --now apartments-site
  curl -fsS http://127.0.0.1:8600/healthz
  ```
- **Logs:** one access line per request (client, method, path, status, milliseconds) in the journal:
  `journalctl --user -u apartments-site -f`.
- **Stop:** `systemctl --user disable --now apartments-site`.

## Production properties

- **Read-only, apart from the tags ledger.** The database is opened with `mode=ro&immutable=1`,
  SQL is parameterized, and sort columns come from fixed lists. Invalid filter values are ignored rather than turned into errors.
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
- **Tests:** `tests/site/`. Fixtures write small `deals/`, `estimates/` and `diagnostics/`
  folders, and a small bundle, dataset and registry go through the real builder. The tests then
  check the routes: filters, sorting, CSV, escaping of source text, headers, Host checks, gzip,
  ETag, 404 and 503, a publish being picked up without a restart, and every `url_for` name in
  the templates against the app's views.
