# Research-progress dashboard

http://thelio.tail3983e0.ts.net:8500 (tailnet only).

## What it shows

- **Pareto frontier** of PSIS-LOO ΔELPD over the row split's training rows (vs the m0-base
  baseline) against the scored fit's time, with the board's frontier staircase, ±1 combined SE
  (paired SE and Monte Carlo error) and gate status (hollow = fails the gate or screen-grade). The
  metric and rules are in the [research plan](research-plan.md).
- **As of** scrubber: every chart, headline number and table re-renders with the results that
  had landed by then; the board's own rules (`leaderboard.choose_best`, `leaderboard.on_frontier`)
  are replayed at each moment, so the frontier and best at any date are what the board would have
  said then.
- Validation (PSIS-LOO against genuine held-out ΔELPD per entry, with their rank correlation),
  unit split (secondary), best PSIS-LOO ΔELPD over time, fit time over time, cumulative compute by
  model line, all entries (sortable, with Pareto-k reliability, notes and annotations) and
  milestones (merged PRs and app-model selections from git history). Every chart has a table view.
- A **hardware** multi-select: check any set of hardware classes (default: every thelio class,
  remembered per browser; quick picks "All thelio" and "All"). Each class keeps its own frontier
  and best, since a fit time only competes with fit times on the same hardware. With several
  classes checked, their entries share the charts. Shape marks the hardware (circle RTX 2060,
  square CPU, diamond Modal), and each class's frontier and best-over-time lines get their own
  dash.
  The entries table's **Timing** column shows how many cores other processes kept busy during the
  fit (recorded from commit 3c26c4a; clean below 0.5), because thelio fits run one at a time for
  clean timings.
- The ΔELPD axis zooms past the baseline by default (it sits far below every other entry and is
  drawn at the floor); "Full ΔELPD range" shows everything.

## Rent map (`map.html`)

A prototype of Ben's visualization goal (2026-09-29: "a visualization geo-spatial-temporal model of
rents stratified by number of bedrooms"), for the app's selected model.

- **What a value is.** What a typical apartment with that many bedrooms rents for in a building in
  a year (`rentfrontier.rentmap`):
  - bathrooms, size, views and ad-text features at Chelsea's average for the bedroom count;
  - floor and building amenities (elevator, doorman, pets, building facts) at the building's own
    average;
  - plus the building's level, its path over time and its own bedroom premium, and the market that
    year (trend averaged over the year's months, no season).

  The value is the posterior median of the typical asking rent, with a 90% interval.
- **Map.** One dot per building on Manhattan's street grid (rotated 29°, avenues up the page), with
  guide lines for the avenues and a few streets placed from the buildings' own addresses. Colour is
  one of five fixed rent bands per bedroom count (quintiles over all building-years), so a band
  means the same in every year. Years before a building's first listing in the fit are the model's
  extrapolation; they are hidden by default and hollow when shown.
- **Controls.** Bedrooms (studio, 1, 2, 3+), a year slider with play, hover for a building's value
  and interval, and a table view.
- **Chelsea average by bedrooms over time.** The typical rent averaged over buildings, per year and
  bedroom count, with the chosen count's 90% interval.
- **Data.** `python -m rentfrontier.rentmap <run>` (a heavy job: take the lock) writes
  `/data1/apartments/frontier/maps/<run>-<commit>/map.json`. The dashboard build copies the newest
  map of the run that `config/main-analysis.json` selects, and the page says so when there is none.

## How it is built and served

- `frontier/src/rentfrontier/dashboard.py` reads the leaderboard's records (frontier runs under
  `/data1/apartments/frontier/runs/`, PyMC screens, rescores, annotations) and git history, and
  writes `data.json` next to a copy of the static page in `dashboard/` (plain HTML, CSS and JS,
  no dependencies). Each build goes to `/data1/apartments/dashboard/builds/<stamp>/`; the `site`
  symlink is swapped atomically.
- Units in `ops/systemd/` (installed to `~/.config/systemd/user/`):
  - `apartments-dashboard.service`: `python3 -m http.server` on the tailscale IP, port 8500,
    MemoryMax 128M;
  - `apartments-dashboard-build.timer` → `apartments-dashboard-build.service`: every 10 minutes,
    follows `origin/master` in `/data1/apartments/serve/master` and rebuilds (about 20 s,
    ~450 MB peak, MemoryMax 1G). The build waits for `/data1/apartments/tmp/heavy.lock`, so it never
    runs during a timed fit. A fit can hold the lock for up to an hour, hence `TimeoutStartSec=2h`.
- Build by hand: `cd frontier && uv run python -m rentfrontier.dashboard --out <dir>`.
- Stop: `systemctl --user disable --now apartments-dashboard.service apartments-dashboard-build.timer`.
