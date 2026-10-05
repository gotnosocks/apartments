# Website playtests

Persona playtesters drive the website's improvements. Each round, every persona in
`personas/` gets the same `brief.md`, clicks through the live site in a real browser and writes
a report. The website thread then writes a `synthesis.md` beside the reports, ranking findings by
how many personas hit them and how badly, and turns the top items into one bundled PR with one
review per round (Ben 2026-10-05, to save tokens). Split out only a fix that has to ship before
the rest is ready.

- **At most 3 personas a round** (Ben 2026-10-05). Rotate through `personas/` from round to round,
  and include `best-1bed` whenever the round's changes touch listings, summaries or ratings.
  `ops/playtest.sh` refuses more than 3. Feature work Ben asks for directly keeps its own PRs.

- **Model:** playtesters run on Sonnet 5.5 (`claude-sonnet-5-5`, Ben 2026-10-05). The website
  thread's main session runs on Sonnet too (Ben 2026-10-05). Reviewers follow CLAUDE.md: Sonnet for
  site and docs PRs.
- **Run a round:** `ops/playtest.sh 2026-10-06-r6 renter mobile best-1bed`. Each persona runs as
  a systemd `--user` unit, `playtest-<round>-<persona>`. Its report goes to
  `/data1/apartments/tmp/playtests/<round>/<persona>/report.md`, with screenshots alongside. Wait
  for the units with `ops/team/wait-next --unit 'playtest-*'`.
- **Browser:** the venv at `/data1/apartments/venvs/playtest` runs Playwright on the system
  Chrome. Browser steps run as `ops/job light`.
- **Personas:** `persona:`, `viewport:` and `goals:` fields; add fresh ones each round.
  `best-1bed` (Ben 2026-10-05) looks for the best apartment for its wishes, not the furthest
  below its estimate.
