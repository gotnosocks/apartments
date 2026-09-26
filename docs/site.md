# Listings site

http://thelio.tail3983e0.ts.net:8600 (tailnet only).

The site shows the scraped listings with the selected model's rent estimates. Every estimate is
**leave-own-row-out**: it uses the building, the features, the market that month and the unit's
other listings, never the listing's own ask. The gap between ask and estimate is therefore a fair
signal of over- or under-pricing ([what an estimate is](model/listing-estimates.md)).

## Pages

- **Start page:** coverage figures, the listings available now (lowest ask against estimate first),
  and the market reference rent over time.
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
  - Listings with an unstable leave-own-row-out correction (Pareto k > 0.7) are marked \* and
    explained.
- **Unit:** asks and estimates of each of its listings over time.
- **Buildings** (`/buildings`, searchable and sortable) and **building** pages:
  - level against an average building and yearly trend, with 95% intervals;
  - the median ask against estimate;
  - MapPLUTO facts;
  - ask against estimate over time for every listing;
  - its units and listings.
- **About the estimates** (`/model`): what an estimate is and is not, calibration by estimate type,
  the fit's provenance, convergence gate and PSIS-LOO score, the parts of an estimate, and every
  feature coefficient.
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
   - the building registry and MapPLUTO extracts the run used (sha256).

   It refuses a failing gate. It writes `/data1/apartments/site/builds/<stamp>/site.sqlite` and
   `build.json`, swaps the `current` symlink atomically, and keeps the newest three builds. It takes
   about 8 s with a 1.1 GB peak, and the database is about 130 MB.
3. **Serve.** The app opens `current/site.sqlite` read-only (immutable) on each request, so a publish
   needs no restart.

Publishing on thelio takes the shared heavy-job lock like other heavy jobs:

```sh
cd /data1/apartments/serve/site
flock /data1/apartments/tmp/heavy.lock systemd-run --user --scope -p MemoryMax=2G \
  --setenv=TMPDIR=/data1/apartments/tmp/site-serve \
  /data1/apartments/venvs/serve-site/bin/python -m apartments.site build
```

To roll back data, point `current` at an earlier build: `ln -sfn builds/<stamp> current.new &&
mv -T current.new current` in `/data1/apartments/site`.

## Service

- **Unit:** `ops/systemd/apartments-site.service`, installed to `~/.config/systemd/user/`.
  - Waitress (8 threads) on `100.80.84.126:8600` and `127.0.0.1:8600`, MemoryMax 512M.
  - It accepts only the Host names localhost, `thelio`, `thelio.tail3983e0.ts.net` and the tailnet
    IP. Any other Host gets a 400.
  - It retries until the Tailscale address is up after a boot.
- **Code** runs from the serving worktree `/data1/apartments/serve/site`, with the venv
  `/data1/apartments/venvs/serve-site` (base dependencies only). Only the deploy script moves it:

  ```sh
  ops/site-deploy.sh            # origin/master
  ops/site-deploy.sh <commit>   # a specific commit
  ```

  It checks out the commit, runs `uv sync --locked` and restarts the unit. If `/healthz` does not
  answer within 30 s, it rolls back to the previous commit.
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
- **Tests:** `tests/site/`. A small bundle, dataset and registry go through the real builder, then
  every route is checked: filters, sorting, CSV, escaping of source text, headers, Host checks,
  gzip, ETag, 404 and 503, and a publish being picked up without a restart.
