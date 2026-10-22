# Digest: "Team Lead" session (session_01MURubdSssXouG5HC2orbEi), Sep 25 to Oct 2 2026

This covers everything before event fd525511 (2026-10-02 20:19 UTC). Later events were covered elsewhere.
The times are given in ET (machine clock, EDT = UTC-4), with UTC in brackets where useful.
Ben's own messages are quoted. "TL" = this Team Lead session. Cross-session messages are relays from peer Claude sessions, not Ben.

**Shape of the transcript:** there is one exchange on Sep 25. After that the transcript is silent until Ben runs `/clear` on Oct 1 at 19:39 ET, and all later activity falls between Oct 1 19:39 ET and Oct 2 16:18 ET.
I found **no compaction summaries** ("continued from a previous conversation") anywhere in the transcript. The `/clear` means that whatever happened between Sep 25 and Oct 1 was not in this session's context. Most of that history came through peer status replies and memory files instead.

---

## Fri Sep 25

- **16:23 ET, Ben (desktop): "is the dashboard app running?"**
  - TL: yes, it is at http://thelio.tail3983e0.ts.net:8500 (HTTP 200).
  - Service: `apartments-dashboard.service` is a python `http.server` bound only to the tailnet IP 100.80.84.126, serving `/data1/apartments/dashboard/site`.
  - Rebuilds: `apartments-dashboard-build.timer` rebuilds every 10 minutes. The current rebuild was waiting on `/data1/apartments/tmp/heavy.lock`, which was held by a NUTS timed fit (`frontier-serial13`, `nuts-c7-dense-2060`, 60-minute timeout) with `pytest tests/test_nuts.py` queued behind it.
  - The memory note `research-dashboard` was read during this turn. It says that on 2026-09-24 Ben scrapped four served sites (Streamlit :8501, review queue :8767, docs server :8768, canonical-unit review :8766; PR #14) in favour of one research-progress dashboard (PRs #12 and #13).
  - That dashboard was built by `frontier/src/rentfrontier/dashboard.py`, with the timer following origin/master in `/data1/apartments/serve/master` and venv `/data1/apartments/venvs/serve-frontier`.
  - Work on the m8 summary reader (branch `app/summary-reader`) was put on hold.
- The transcript is silent until Oct 1.

## Thu Oct 1 (evening ET)

**Context from peer reports:** fifteen PRs merged on Oct 1 (#98–#109, #112):

| PR | Change |
|---|---|
| #98 | Chelsea + West Village combined cohort |
| #99 | Goal set to the Pareto frontier of PSIS-LOO × fit time × simplicity on the combined data; ties go to the simpler model |
| #100, #102, #104, #107, #109, #112 | Site rewrite "one site, two sections", PRs 1–6 of 7 (nav/home, research frontier, board, validation/glossary/plan, rent map in Estimates, neighbourhood filters) |
| #101 | Research data: complexity, why a fit can't be served, autoselect's decision |
| #103 | Tuning-subset rule `tune-b35-v1` (exploration only) |
| #105, #106 | Exact Gibbs speedups, −38% sampling time |
| #108 | Simplicity judged by two blind judge agents (9 pairs, all agreed) |

**19:39 ET.** Ben ran `/clear`, then: **"Confer with the other agents and give me an update on what's happened since I last checked in."**
TL found the peers with ListAgents and messaged them with SendMessage. All five replied:

- **Site session**, "Production website for listings and price estimates": the rewrite is at 6/7 PRs merged. PR 7/7 retires the static dashboard and makes the site also answer on :8500. Each PR is reviewed by a separate agent and squash-merged with an `archive/pr-N` tag.
- **Modeling session**, "NYC rent project modeling handoff":
  - #110 (Ben's new limits: full fits up to 2 h, subset fits under 30 min) and #111 are in review.
  - The faster refit of the served model took 1,168 s against 1,765 s and tied on PSIS-LOO.
  - Four full combined fits (bath-and-floor, floor slope, two slopes, t-units) were running one after another at 4,500 draws each. The first attempts ran out of GPU memory, so the reruns keep every 9th draw.
- **West Village scrape process**:
  - The crawl finished Sep 30 at 11:30 EDT with no block or credit errors.
  - Fetched: 14,803 units with unit pages and 25,061 listing pages. Another 14,374 were reused, and 8,458 pre-2014 ads were skipped by Ben's cutoff.
  - Snapshot `west-village-backfill-20260930` (55 GB, read-only).
  - Transform `west-village-granular-20260930-canonical-url-v1`: 15,169 units, 40,126 linked listings.
  - Unit-spelling alias table: 257 groups, 248 of them confirmed by listing history, opt-in. PRs #79, #80 and #85.
  - "Ben now allows authors to self-merge after review."
- **Sampler-review session**, bridge-cse-01t3icecktmzp9pgxgy3ufms-df: idle since Sep 25. It had found that the custom Gibbs sampler beats library NUTS because of its method: exact block draws, units integrated out, buildings eliminated by Cholesky. It recommended lifting the Gibbs deprecation with guardrails, and needed Ben's yes or no.
- **Bend session**, bend2-experiments-89: idle since Sep 28. Ben had dropped the SMC/quadtree plan. Bend v2.0.34 can't run on this machine (Node 26, no Bun, no C compiler, and Ben declined the official installer).

TL posed four decisions.

**20:02 ET, Ben: "1. Ship together 2. We can let the sampler review session stay idle. 3. Bend session can stay idle 4. I do want to use the west village alias table in the model runs."**
- Shipping together means one deploy carries site PR 7 and the faster-refit selection change. Production stays frozen until then.
- The alias table goes in as its own PR and fit, scored on the rows both versions keep. The West Village session briefed the modeling session on it and did not run a model itself.

**20:16 ET, Ben: "Do we have any successful fits on the combined data yet?"**
- Yes: **m7-nocurves-bathfloor** passed at 19:57 ET.
  - Max R-hat 1.0087, minimum ESS 584.
  - **PSIS-LOO 87,334.1 ± 308.8**, held-out +67.1 dELPD, 2,800 s.
- Caveat: 881 rows have Pareto k above 0.67, against 444 on the Chelsea-only fit.
- An earlier 3,000-draw attempt failed (ESS 373).

**20:24 ET, Ben: "Are we sure that using less data doesn't reduce the fit time effectively? It seems like our iteration speed is still slow."**
- Subset `tune-b35-v1` (35% of buildings, 26k rows): 994–1,272 s. Full combined data (78k rows): 2,800 s.
- Fit time is roughly 750 s fixed plus 20 s per thousand rows, and subset fits fail the convergence gate.
- TL suggested screening designs with fewer draws instead.

**20:29 ET.** Ben floated starting fresh from an "empty model" ("rent equals a constant"). TL proposed a ladder of designs.
**20:32 ET.** Ben said this replaces the modeling queue and tables design work, and asked TL to "tile this together and propose next steps".

**20:41 ET, Ben's directive (key standing instructions):**
- "Kill the current fit and queue"
- "just start a new autoresearch on the full data and try to get the best fit possible at a range of fit time limits, prefer simpler more elegant models"
- "investigate the shortest experiments that will give us good data. Iteration speed is important."
- "Don't run a prescribed ladder, try to make frontier models along the whole fit time x performance curve. Put a reasonable effort in a lower time limits before moving to longer time limits."
- "show the exploration data on the site"
- "Don't jump to full fits at every frontier model while I'm awake, I'm nosy and want to see you making progress on the research. Do full data frontier runs between 12am and 5 am PT." TL translated this to **03:00–08:00 ET**.
- "Who does what is good." Ben had separately prompted the West Village scrape session to start a **Greenwich Village** scrape (#113, "Add Greenwich Village as a crawl neighborhood", merged 20:15 ET).

**20:42 ET.** TL stopped four queued fits (floor slope was mid-run and lost; two slopes; t-units; bath-and-floor with the alias table). The GPU was left idle.

**20:49 ET, Ben: "The exploration points should count as frontier points for the site ... Later when we have a full fit, we can serve the model with the full fit for the other parts of the app, but the research pages with the frontier should still show the exploration points."**
- The rule became: exploration fits are frontier points, tagged by tier, and only full-data, gate-passing, full-tier fits are served.

**20:51 ET.** Modeling confirmed:
- #111 merged, #110 rebased, #115 (faster refit) open.
- The 4,500-draw bath-and-floor fit was the first gate-passing full-data fit.
- A calibration batch had started.

**20:56 ET.** Asked whether a change to the served model needs his OK, Ben answered **"No"**.
- TL confirmed that the Sep 30 rule holds: autoselect switches the served model by its rule, and switches still merge as PRs.
- TL fixed a stale memory note that had said Ben must approve selection changes.

**21:10 ET, Ben: "What's the eta on the new site?"** TL said #114 (the last site PR) and #115 were open, and estimated 1–2 h.

**21:13 ET, Ben: "I'd like to ship the site as soon as we have new research fits to show on the research page, so I can track results there live."**
- New deploy trigger: #114, #117 (fit tiers), the site's exploration PR, and at least one exploration fit.
- #115 no longer gates the deploy.

**21:25 ET.** First exploration fits on the full combined data: m0-base 64,985 in 147 s, m5-nocurves 84,383 in 243 s.

**21:26 ET, Ben: "Can we prompt the agents to do live updates that are not affected by a lock? It would be sweet to just get them right away."**
- TL asked the site session to move the research-data rebuild off `heavy.lock`, at nice 19 / ionice idle, triggered whenever a fit lands, with an atomic write.
- The rebuild had been put under the lock in #19, to protect fit timing.

**21:27–21:28 ET, Ben: "when can I see the new research page with the latest completed fits?" / "Yes, getting a preview of the research page would be great."**
- The site session started a preview at **:8602** (systemd-run unit `apartments-site-preview`, with its DB under `/data1/apartments/tmp/preview`).
- The site session first reported an ETA as if the preview were up. TL checked it itself, found it down, and asked for light builds to skip the lock.
- The preview was confirmed up at 21:37 ET.

**21:40 ET.**
- The preview showed 4 exploration fits, `/research/board?tier=exploration`, and diamonds on the History chart.
- Modeling had a pairing cache on branch `perf/board-cache` (later #120: board build 81 s to 31 s).

**21:45 ET, Ben: "I see the old 'simplicity' definition showing up centered around renter understanding. I think for my purposes I'm actually more interested in a modeling-oriented elegance, rather than fewer things to explain to a renter. Thoughts?"**
- TL proposed criteria for the judges:
  - one coherent generative story;
  - few mechanisms, used consistently;
  - no overlapping or competing terms (ties to Ben's rule that "a model that's hard to sample is misspecified");
  - few special cases;
  - natural forms over arbitrary ones;
  - economy of structural choices.
- Implementation details (samplers, reparameterizations, knot spacing) still don't count.
- p_loo (effective parameters) was offered as an objective companion.

**21:54 ET, Ben: "the 'one sentence explanation' term can go entirely. Go ahead with the proposed changes to an 'elegance' target."**
- Sent to the modeling and site sessions, and memory updated. On a tie, the more elegant model is served.

**21:59 ET.**
- Elegance went live on the preview (`/research/elegance`; `/research/simplicity` returns 404).
- p_loo is shown as "effective parameters".

**22:42 ET.** Elegance is PR #123: 12 pairs re-judged blind, all agreed, and m0-base was judged more elegant than the richer designs. Calibration on bath-and-floor:

| Run | Time | PSIS-LOO |
|---|---:|---:|
| Full: 4,500 draws | 2,800 s | 87,334.1 |
| Medium: 2×(300+1500) | 1,116 s | 87,323.9 (within MCSE) |
| Short: 2×(100+300) | about 6 min | overestimates by 18–102 |

## Fri Oct 2

**Overnight, from the 00:46 ET status (all merged):**

| PR | Change |
|---|---|
| #114 | Retire static dashboard |
| #115 | Faster refit selection |
| #116 | Plan: fresh autoresearch |
| #117 | Fit tiers |
| #118 | Judged simplicity |
| #119 | Board on the combined cohort |
| #120 | Board cache |
| #121, #122 | Lock-free live research build |
| #123 | Elegance axis |
| #124 | Exploration diamonds |
| #125 | Exploration tier = 2×(100+600) draws |
| #126 | A short fit never dominates a better-measured fit of the same design |
| **#127** | **Autoselect serves the first full combined fit: bath-and-floor, 4,500 draws, 87,334** |
| #128 | Elegance replaces simplicity; p_loo |
| #129 | Rent map labels |
| #130 | Area naming (merged 01:02 ET) |

Exploration gains (PSIS-LOO on the full data):
- building walk ≈ +13,600
- unit-consistency features +2,900 to +4,100
- bedroom slope ≈ +2,600
- per-building bath and floor slopes with t-units ≈ +3,000 more
- building facts and neighbourhood ≈ 0 beyond the building level

**00:48 ET. Deploy blocked.**
- The site session's harness refused the production deploy without Ben's go-ahead given in that session itself.
- TL refused to deploy from its own session, because that would bypass the block. The request waited for Ben in the site session.

**11:22 ET. Site LIVE in production.** Ben said "deploy" in the site session.
- Code: master a955e39, at **http://thelio.tail3983e0.ts.net:8600** and :8500.
- Build `20261002T152105817395Z-925f469c`, serving model `m7-nocurves-bathfloor-nb-facing-v1` with 86,568 listings.
- `apartments-dashboard.service` was removed, and `apartments-site` now serves both ports.
- `apartments-dashboard-build.path` watches runs/loo/variance/rescores.
- Old unit files are backed up in `/data1/apartments/tmp/deploy-units-backup`. `ops/site-deploy.sh` rolls back on a failed health check.
- The :8602 preview stays up. The production freeze is over, and memory was updated.

**11:46 ET. Overnight full fits** (combined data, inside the window):

| Fit | Time | Gate | PSIS-LOO |
|---|---:|---|---:|
| m0q + clean unit features | 415 s | pass | 67,885 |
| m1q + clean | 1,079 s | fail | 81,499 |
| m5 + clean | 1,326 s | pass | 84,123 |
| m5 + served features | 1,521 s | pass | 84,277 |
| t-units + clean | 1,391 s | fail (R-hat 1.011) | 85,703 |

- The served model is unchanged at 87,334.
- Exploration ranks designs to within about 30 points but scores 14–58 too high.
- Lead: two per-building slopes on clean features, 87,487 in exploration and judged more elegant.
- #132: 55 elegance pairs (52 agreed).
- #133: alias table as data rule `unit-labels-v2`, held until a full v2 fit exists.
- #131: dropped the `chelsea_median` alias.

**11:50 ET, Ben (iOS): "Tell me about the selected model. Use diagrams and equations."** TL gave a full write-up of m7-nocurves-bathfloor + nb-facing-v1 (see Durable facts).
The weak spots it named were the ad hoc slope set and the long list of one-off binary flags.

**12:33 ET.** New exploration lead: Student-t apartments with three per-building slopes on clean features.

| Design | Exploration PSIS-LOO |
|---|---:|
| Three slopes: size, 2nd bath, floor | 87,748 |
| Three slopes: size, 2nd bath, 3rd bath | 87,723 |
| Two slopes (1,500 draws) | 87,452 |

- Dropping Student-t apartments costs 1,575. Using listing attributes only costs 1,700.
- At this point the modeling session said clean features beat served features.

**14:05 ET, Ben: "Latest updates?"**
- Site redeployed at f8ed3cf with #134: fits of the same design at several draw counts are joined by a line.

| Exploration fit | PSIS-LOO |
|---|---:|
| Floor slope + served features | 87,952 (best) |
| m7, no slopes + served features | 87,886 |
| Floor slope + WV building facts | 87,783 |

- TL flagged that this contradicts the "clean features win" claim.
- Suspect rows (Pareto k above 0.64) rise to 1,480–1,590 in the richer designs, against 256 for the simplest.
- #135: 30 more elegance pairs.
- Tonight's queue: floor slope + alias table; floor slope + served features; two slopes + clean unit floor features; floor slope + clean unit floor features.
- Session cleanup: the Bend and sampler-review sessions are no longer running. Remaining are site, modeling and West Village/Greenwich Village.
- TL asked Ben to confirm the site session's claim of standing deploy approval.

**15:08 ET, Ben: "Yes confirmed"** (standing approval for site deploys).
- TL's memory write was refused by its permission check twice. TL suggested Ben add the note to `site-deploy-freeze.md` himself, or allow memory-directory writes.

**15:12–15:13 ET, Ben: "Please instruct the data improvements agent to start work on data improvements, starting with the suspect rows." He also said: "Apparently invalid rows may be quarantined to exclude them from the fit."**
- TL sent the brief to the new session bridge-cse-01tr3qzpmvxdtqxwfrhkzp1d-5d, guessing it was the right one. It confirmed it is the "data agent".
- The brief repeated the house rules (see Durable facts).

**15:14 ET, Ben: "No, what you wrote seems good."**

**15:18 ET. Data agent findings** on the 881 high-k rows in the served fit:
- They are mostly structural:
  - 72% are alone in their building's half-year walk knot;
  - 47% are in buildings with 5 or fewer rows;
  - 461 are their unit's only row;
  - the rate rises with bedrooms;
  - 669 have positive elpd, so they are influential rather than misfit.
- By neighbourhood: Chelsea 430 (0.91%), West Village 451 (1.47%).
- This went to modeling as a small-building pooling signal.
- Real errors found: about 20 split building IDs sharing a BIN, and West Village never screened (quarantine-v1 and v2 were Chelsea-only).

**15:45 ET. Data agent PRs:**
- **#137**, West Village ad text (34,087 of 34,118 rows) plus new feature set **nb-facing-v2**. 252 tests pass; ready to merge.
- **#138**, quarantine-v3 (DRAFT): 261 rows, v2's 188 plus 73 new:
  - 34 ads placed elsewhere (Brooklyn, Park Slope, UWS);
  - 21 short-stay offers;
  - 16 commercial spaces;
  - 1 room;
  - 1 contradicted ask.
  - The new rows average −3.13 PSIS-LOO per row, against +1.12 overall.
  - It waits for the batched 03:00–08:00 refit together with #133.
- **Dropped:** building-aliases-v1, because the shared BINs were mostly geocoder artefacts.
- **Kept as modeling signals:** net-effective asks and bedroom-count conflicts.

**16:18 ET, Ben:** "Do we have anything in the model for public transit access? The unit page lists transit info as well as schools, colleges, parks, and museums..." Everything from here on is covered elsewhere.

---

## Durable facts

### Repository
- **Local path** on Ben's machine `thelio`: `/home/ben/code/apartments`.
  - TL worked in worktree `/home/ben/code/apartments/.claude/worktrees/bridge-cse_01MURubdSssXouG5HC2orbEi`.
  - Other bridge sessions use `.claude/worktrees/bridge-cse_<id>`.
- **Default branch:** `master`.
- **Other branches seen:** `perf/board-cache` and `app/summary-reader` (on hold).
- **Packages:** `frontier/src/rentfrontier/` (run.py, dashboard.py, simplicity.py → elegance), `src/apartments/` (site, unit_spelling_aliases), `src/streeteasy_archive/` (cli, collection_policy, neighborhoods).
- **Other repo files:** `docs/research-plan.md`, `config/` (main-analysis.json, simplicity-judgements.jsonl, review overrides), `ops/site-deploy.sh`.
- **GitHub:** the owner/repo name never appears in the transcript. PRs are numbered #12–#138 and handled with `gh`.
- **Run tooling:** `uv run --locked`; GPU fits run with `uv run --extra gpu python -m rentfrontier.run --split rows --model <m> --features <f> ...`.
- **Data root:** `/data1/apartments`. It holds `serve/master`, `venvs/serve-frontier`, `frontier/runs/`, `tmp/heavy.lock`, `tmp/bridge/` (drive.sh, serialNN.sh queue scripts, exploreN.sh), `tmp/preview` and `dashboard/`.

### Data
- **StreetEasy archive scrape** (`streeteasy_archive` package). The "Oxylabs" proxy never appears in this window, so the provider is not confirmed here.
- **Neighbourhoods:**
  - Chelsea (the original).
  - West Village, crawled Sep 30.
  - Greenwich Village, added as a crawl neighbourhood in #113 on Oct 1, with the scrape started by Ben's prompt.
  - Ben set a pre-2014 cutoff for ads.
- **Combined Chelsea + WV cohort** (#98): 86,568 listings (about 78k used in fitting), 2,296 buildings.
- **WV artefacts:**
  - snapshot `west-village-backfill-20260930` (55 GB, sha256 3b209717…);
  - transform `west-village-granular-20260930-canonical-url-v1`;
  - unit-spelling alias table (257 groups, opt-in; as data rule `unit-labels-v2` in #133);
  - audit at `data/probes/west-village-20260930-final/audit.json`.
  - Square feet are stated on only 18% of WV rows.
- **Quarantine rules:** quarantine-v1 and v2 cover Chelsea only; quarantine-v3 is in draft (#138). The evidence for an exclusion must be the ad's own words or MapPLUTO, never the residual.
- **Public datasets** named in research-plan.md:
  - MapPLUTO for building facts;
  - transit feature set `unitdescplutotransit-v2` (74ff297, Sep 29), built from a snapshot of MTA subway entrances and station stops (GTFS), with Citi Bike and PATH listed. It gives the walk to the nearest station and the lines within 400/800 m, and covers the 2015 Hudson Yards 7 extension. In Chelsea the median walk to a station is 206 m.
  - Also listed as candidates: DOE schools, 311, crime, violations and permits.

### Model
- **Served model:** `m7-nocurves-bathfloor` with features `nb-facing-v1`, i.e. `m7-nocurves-bathfloor-nb-facing-v1` (#127). Fit on the RTX 2060 GPU with the custom Gibbs sampler in 2,800 s at 4,500 draws, thinned every 9th.
- **Structure:**
  - Response: Student-t likelihood on log rent.
  - Market: intercept, a quarterly random-walk trend, and a 12-month season.
  - Features: 97 named feature effects.
  - Per building: level b_k, a half-year random walk w_k(t), and slopes for bedroom, 2nd bath and floor.
  - Per unit: a Student-t effect u_j.
  - West Village is +8.1% against Chelsea.
- **Fitted scales:** σ≈0.034 (ν≈2.3), τ_b 0.162, τ_bath 0.182, τ_γ 0.099, τ_u 0.039, τ_w 0.034, τ_T 0.031.
- **Variance shares:** features 74.6%, market and time 9.7%, building 9.0%.
- **Scoring:**
  - PSIS-LOO (elpd); the served model has 87,334 ± 309.
  - Convergence gate: R-hat and minimum ESS (it passed with 1.0087 and 584).
  - Pareto k above about 0.64–0.67 marks rows where the estimate is unreliable (881 in the served fit).
  - p_loo is shown as "effective parameters".
  - Earlier dashboards used row-split ΔELPD.
- **Fit tiers:**
  - Exploration: 2×(100+600) draws, about 2–10 minutes; scores run 14–58 high but rank designs to within about 30.
  - Full: 4,500 draws.
  - Exploration fits count on the research frontier but are never served.
  - Autoselect serves only full-tier, full-data, gate-passing fits. A tie goes to the more elegant model.
  - Changes to the served model do **not** need Ben's OK (Sep 30 rule, reconfirmed Oct 1).
- **Limits (#110):** full fits up to 2 h, subset fits under 30 min.
- **Design names seen:** m0-base, m0q, m1q, m5(-nocurves), m7-nocurves-bathfloor, t-units, floor-slope, two/three slopes.
- **Feature sets seen:** nb-facing-v1 (served), nb-facing-v2 (#137, adds WV ad text), "clean unit features", listing attributes only, unitdescplutotransit-v2, WV building facts.
- **Elegance judges** (#108 → #123/#128): two blind judge agents compare pairs of designs. The criteria are a coherent generative story, few mechanisms used consistently, no overlapping terms, few special cases, natural forms, and economy. Renter-understanding and the one-sentence rule were dropped at Ben's request.
- **Sampler-review finding:** the custom Gibbs sampler beats NUTS because of exact block draws (units integrated out, buildings eliminated by Cholesky). NUTS/JAX code also exists (tests/test_nuts.py).

### Website
- **Stack:** Python. `apartments.site` (web.py with templates and a SQLite build) runs as the user systemd unit `apartments-site`.
- **Research data:** `data.json`, built by `rentfrontier.dashboard` and reloaded on mtime change. `apartments-dashboard-build.path` plus the timer rebuild it off-lock at idle priority.
- **Hosting:** Ben's machine `thelio`, Tailscale-only. Production is http://thelio.tail3983e0.ts.net:8600 (with :8500 as a legacy alias); the preview is :8602.
- **Sections:** Estimates (listings, buildings, rent map, neighbourhood filters) and Research (frontier, board with tier filter, per-fit pages, history, elegance, validation, glossary, plan, /research/model).
- **Production since Oct 2 11:22 ET:** a955e39, then f8ed3cf with #134.

### Sessions TL coordinates
TL talks to them with **SendMessage** over local UDS sockets (`/run/user/1000/cc-socks/<pid>.sock`), finds them with ListAgents, and receives `<cross-session-message>` relays. Peer approvals never count as Ben's.

| Session | Socket | Role |
|---|---|---|
| "NYC rent project modeling handoff" | sock 300276 | Modeling and autoresearch. Owns fits, the run queue, autoselect and elegance judging. |
| "Production website for listings and price estimates" | sock 1063850 | Site code and deploys. Has Ben's standing approval for deploys, which its own harness enforces. |
| "West Village scrape process" | sock 143455 | The crawler. Did the WV crawl and alias table, and is now on the Greenwich Village scrape. "Data Collection" is not named in this window; this is presumably the crawler role. |
| Data agent, bridge-cse-01tr3qzpmvxdtqxwfrhkzp1d-5d | sock 3099695 | Data improvements: suspect rows, quarantine and ad text. Started Oct 2 at about 15:12 ET. |
| Sampler-review (bridge-cse-01t3icecktmzp9pgxgy3ufms-df) and bend2-experiments-89 | — | Idle by Ben's choice, then no longer running as of Oct 2. |

The machine also runs `claude-rc.service`, the Remote Control bridge.

### House rules and conventions
- **PRs:**
  - One PR per change, and agents open a PR for each unit of work.
  - Another agent reviews and squash-merges on gates, with an `archive/pr-N` tag before the merge.
  - Authors may self-merge after review.
- **Data changes:** exclusions are written as rules, not hand-picked rows. Models are compared only on rows both versions keep.
- **Compute:**
  - Local compute only.
  - Heavy jobs take `/data1/apartments/tmp/heavy.lock`, and timed fits run one at a time.
  - Light builds (research data, previews) stay off the lock at nice 19 / ionice idle.
- **Night window:** full-data full fits run only from 03:00–08:00 ET (Ben: "12am and 5 am PT"). drive.sh refuses full-tier fits outside it.
- **Daytime:** short exploration fits only, so Ben can watch progress.
- **Modeling rule:** a model that is hard to sample is treated as misspecified.
- **Deploys:**
  - Production deploys need approval inside the site session, and a go-ahead relayed from TL doesn't count.
  - Ben confirmed standing approval for merged site PRs on Oct 2. TL could not save this to memory because its permission check refused the write.
- **Memory:** TL keeps memory notes such as `site-deploy-freeze.md`, `github-pr-workflow.md`, `research-dashboard`, `auto-research-loop` and `listings-site`.

### Ben's preferences
- He wants to watch research progress live, on the research pages and without redeploys ("I'm nosy").
- Iteration speed matters to him. He prefers simpler, more elegant models and frontier points across the whole fit-time range, starting at low time limits.
- His messages are short and often from iOS. He likes concise status updates with tables, and asked for diagrams and equations when he wanted to understand the model.
- He gives broad autonomy:
  - served-model switches by rule without his OK;
  - self-merging;
  - standing deploy approval;
  - "Who does what is good".
- TL checks peer claims itself, such as loading the preview URL before passing on a link.

## Open items / next steps (as of Oct 2, about 16:18 ET)

1. **Tonight's full fits (03:00–08:00 ET):** floor slope + alias table (#133 unit-labels-v2); floor slope + served features; two slopes + clean unit floor features; floor slope + clean unit floor features. Autoselect switches in the morning if a fit clearly wins, or ties and is more elegant.
2. **#133 and #138** merge only after a passing full fit that uses them. #138, quarantine-v3, is still a draft.
3. **#137** (WV ad text, nb-facing-v2) is ready to merge. A feature-set refit is needed to use it.
4. **Unresolved:** do clean unit features or served features win? Exploration results contradict each other.
5. **Rising high-k rows:** 1,480–1,590 in the richer designs. Small-building pooling has been handed to modeling as the lever.
6. **Greenwich Village scrape** is in progress in the WV crawler session.
7. **Ben's standing deploy approval** is not in TL's memory. Ben needs to add it to `site-deploy-freeze.md` or allow memory writes.
8. **Elegance** keeps getting judged as new designs appear (#132, #135).
9. **Transit question** (Ben, 16:18 ET): `unitdescplutotransit-v2` exists in research-plan.md (from Sep 29) but isn't in the served nb-facing-v1. Schools, parks and similar features are only candidates so far. This is handled in the later segment.
10. **Still waiting on Ben:** the sampler-review session's "lift the Gibbs deprecation?" question was never answered (the session was left idle). The Bend runtime question was also dropped.

---

## Oct 2, 16:18–18:19 ET (read directly by the catch-up thread)

- **Location features:** transit (#139) null on combined data (+0.0 ± 13.8 PSIS-LOO), closed unmerged. West Village ad text (nb-facing-v2, #137, merged) +136 ± 34. Open space (#140, nb-openspace-v1, dated High Line sections) being fitted. Schools deferred by Ben (zone maps public only for 2024–25). Ben: the data agent picks its own direction from now on.
- **#141 nb-text-v1:** 14 more ad-text flags, screened on Chelsea residuals; WV gain is the honest out-of-sample test (river_view, central_air leaned on WV).
- **New construction (DCP Housing DB):** null, no PR. Ad-text sqft/floor fill: not worth building.
- **Backlog ideas from Ben:** GP / spatial surface (nb-loc-v1: 71 RBF bumps 250 m apart, exploration tonight), space-time surface (after a spatial signal), line-specific transit (low priority; only 2/3 express hint), Fourier seasonality K=2 (queued after current three), noise scale per bedroom group (code done, 36 tests).
- **Other rental sites:** Zillow/Trulia skipped (same parent as StreetEasy). Metronest dropped. Ben's rule: public pages with no login/captcha may be fetched via Oxylabs Web Scraper API only if substantial uplift. Corcoran/Compass/ApartmentList ToS forbid scraping and their listings are already on StreetEasy (5–9% each), so no-go. Ben: "do not do the additional scrape at this time."
- **Oxylabs:** Web Scraper API (`source: universal`, realtime endpoint, `src/streeteasy_archive/oxylabs.py`), creds in `/home/ben/code/apartments/.env`. Recommendation: Micro $49/mo (~42.6k results) plus top-ups. GV crawl hit 429s from 01:25 UTC Oct 2 (likely quota); Ben sorted the account.
- **GV crawl:** resumed 17:39 ET; raised to 8/min with 2 workers at 18:09 via `data/probes/greenwich-village-20261001/run-8pm-2w.py` (`--concurrency 2 --api-rps 1/7.5`), pre-2014 cutoff. Fallback on 429s: run-8pm.py (1 worker) → run-4pm.py → stop and notify; 2-hourly monitor. Estimate 25–45k requests, finish ~Oct 4–6. 45k would exceed Micro.
- **Tonight's exploration queue:** nb-text-v1, per-bedroom noise, nb-loc-v1 (~12 min each). Full fits 03:00–08:00 ET incl. quarantine-v3 + unit-labels-v2. After the batch lands and #133 merges, the data agent readies #138.
- **Session names now:** "Data Collection" (crawler, formerly "West Village scrape process"), "NYC rent project modeling handoff", data agent "bridge-cse-01tr3qzpmvxdtqxwfrhkzp1d-5d", "Production website for listings and price estimates".
