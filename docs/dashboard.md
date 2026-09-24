# Research-progress dashboard

http://thelio.tail3983e0.ts.net:8500 (tailnet only). It replaces the Streamlit app, the review
queue, the docs server and the canonical-unit review page, which were stopped on 2026-09-24.

## What it shows

- **Pareto frontier** of row-split held-out ΔELPD (vs the promoted PyMC model) against fit time,
  with the board's frontier staircase, ±1 paired SE, gate status (hollow = fails the gate or
  screen-grade) and the promoted reference.
- **As of** scrubber: every chart, headline number and table re-renders with the results that
  had landed by then; the board's own rules (`leaderboard.choose_best`, `leaderboard.on_frontier`)
  are replayed at each moment, so the frontier and best at any date are what the board would have
  said then.
- Unit split (secondary), best ΔELPD over time, fit time over time, cumulative compute by model
  line, all entries (sortable, with notes and annotations) and milestones (merged PRs and
  app-model selections from git history). Every chart has a table view.

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
    ~450 MB peak, MemoryMax 1G).
- Build by hand: `cd frontier && uv run python -m rentfrontier.dashboard --out <dir>`.
- Stop: `systemctl --user disable --now apartments-dashboard.service apartments-dashboard-build.timer`.
