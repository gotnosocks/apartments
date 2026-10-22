# Apartments project: full handoff (2026-10-15 ~02:00 UTC)

Written for a fresh Claude Code session (most likely on thelio at `/home/ben/code/apartments`) that needs to pick up the whole project without asking Ben anything already settled. It was assembled from the project instructions, the project chat (read in full), the active threads, the repo at master `7c4665e` (`CLAUDE.md`, `docs/handoff/*.md`, `docs/model/modal.md`, `docs/thelio-jobs.md`) and the shared project files. Where something is inferred and not checked, it says so.

**Things move fast.** Several fits and PRs were in flight when this was written. Before acting, check live state yourself (step 0 below).

---

## 0. First things to do

1. `cd /home/ben/code/apartments && git fetch && git log origin/master --oneline -20` to see what merged since `7c4665e`.
2. `/data1/apartments/serve/master/ops/job status`, `python3 ops/modal/cap.py` (Modal balance and recent launches), `systemctl --user list-units 'modal-*' 'modalq-*'`, and `gh pr list`.
3. Read `CLAUDE.md` (repo) and `~/.claude/CLAUDE.md` (Ben's global file on thelio, which holds his **plain-language style guide**, and possibly standing approvals; not checked).
4. Read the handoff note for the workstream you are taking: `docs/handoff/<modeling|data-improvements|data-collection|website|next-modeling-action|repo-state-cleanup>.md`. Each starts with its newest entry.
5. Find out whether the Midtown West fit (section 3) has run, passed and been served, because almost everything else waits on it.

---

## 1. Goal

Build a scientific model of how NYC asking rents are composed from an apartment's qualities, plus a website to monitor research progress, see tested and selected models, and browse observed listings with model estimates.

- Prefer **explanatory** features (quiet street, subway line, schools, park) over descriptive location effects. Don't lean on neighbourhood terms as a crutch.
- Good theories are elegant, parsimonious and interpretable, express uncertainty about each factor and about the final ask, and generalise.
- Keep a **scientific record** of every theory tested and its result (ledger, predictions written before fits, misses recorded as misses).
- **The model's price target is each listing's latest ask** (current ask for a live listing, final ask for an ended one). Ben's ideal is a latent ask per apartment that every ad observes; that design is a **backlog research suggestion only**, not scheduled work (`/mnt/project-files/modeling/latent-ask-design-2026-10-14.md`).

---

## 2. Standing rules (settled; don't re-ask)

These are in the project instructions. Repo copies are in `CLAUDE.md`, `docs/model/modal.md`, `docs/thelio-jobs.md` and the handoff notes.

**Fits and spend**
- Each rule, feature or model-term test runs on **Modal as its own full fit**, one at a time. No thelio exploration pairs and no bundling. A fit is served if it passes the gate and wins.
- **Budget:** $10/day accrues in a rate limiter. The balance is capped at one day's accrual. Launch only when the balance covers the estimate. Overruns carry forward as a negative balance. Don't ask Ben between fits; wait for credit. Tool: `ops/modal/cap.py`, ledger `/data1/apartments/modal/ledger.jsonl`.
- **Per-fit cap: about 1 hour of wall time, with no dollar cap** (Ben confirmed 2026-10-14 18:42Z; `PER_FIT_SECONDS=3600`, `PER_FIT_USD=None`, #773). Don't launch a fit estimated over an hour. Redesign it or record it as blocked by the cap. Areatime and the 4-hour AR(1) plan are blocked for this reason.
- **Never retry a failed fit on a new seed.** A convergence failure means a real problem. Investigate in order: 1) data, 2) model structure, 3) sampler settings.
- **Data before fit.** Fix the data before patching around it in the model. Data corrections toward a known ground truth proceed independently of model updates. **Don't refit for negligible data changes** (under 0.25% of rows, `NEGLIGIBLE_SHARE`, #740).
- **Convergence gate (strict, Ben's pick 2026-10-14 21:10Z, #788):** split R-hat ≤ 1.01 and bulk ESS > 400 on **every** building effect, not a random 32.
- **Free checks:** read-only analysis on thelio against the served fit and existing data (variance shares, residual breakdowns, screens) needs no approval.

**Evaluation framework (use it whenever fit results are discussed).** The source is §3 and the §10 preamble of `/mnt/project-files/research-review-fable/review-2026-10-08.md`, as adopted in §8 of `/mnt/project-files/modeling/research-review-2026-10-08.md`:
- paired PSIS-LOO on shared rows, with a bar of about 2 combined SE (the board now uses the larger of the iid SE and the lot-clustered SE; ties use building-clustered errors);
- building-level features scored by explained share against a permutation null, with grouped building holdouts;
- rent-derived terms must also win the latest time split;
- new-unit coverage from a time-split refit against nominal 0.79/0.95;
- descriptive share published on every run;
- predictions written before fitting, misses recorded as misses;
- predictive medians and intervals, never means;
- fits on different price targets are never compared (#733).

**Data corrections**
- **Corrections need independent evidence.** Ad text alone can't change a coded field such as bedroom count. Valid backing is another ad for the same unit with different copy, a floor plan, a stated size, or matching units in the same line. Price alone is never backing. Reposted broker copy isn't another ad.
- **Floor plans:** you may fetch and store a listing's floor plan image when its analysis calls for it, and use it as evidence. Plans live in `/data1/apartments/archive/floor-plans/<listing id>/`, and the scripts are in `/data1/apartments/tmp/suspect/fp`. Only a plan on the listing's own page counts. Building unit-page plans may show another period's layout.
- **Bulk ad reading** (screens, flag review, label checks) uses **Sonnet or Haiku subagents** for the per-ad work, not the main model.
- Brooklyn ads that StreetEasy files under a Manhattan building with the same number and street are held out as `brooklyn_misjoin` (quarantine-v17+). Evidence and candidate Brooklyn addresses are in `config/reviews/brooklyn-misjoins-20261014.jsonl`, for a remap once Brooklyn is collected. Every new dataset must run `frontier/scripts/brooklyn_screen.py`; a test enforces it.

**Serving, PRs, site**
- Threads may change the served model with no approval when a fit wins under the repo's selection rules (autoselect, the convergence checks, and the leak-free latest-split comparison for features that read other listings' prices) and the change goes through a reviewed PR. Publish with the normal publish step (dataset switch, commit, push, merge, publish) and post afterwards. **But see section 4 on the open Oct 13 hold.**
- **PR merging:** a thread may merge its own PR once a separate reviewer subagent approves it. Use squash-merge with an annotated `archive/pr-N` tag and `gh pr merge N --squash --match-head-commit`. Reviewers for site and docs PRs run on Sonnet; PRs touching models, selection, data rules or ops code use the default model. Run `ops/fmt` (ruff) before every commit.
- **Always working:** never end a turn with nothing pending. Keep the next fit queued. Before going quiet, start `/data1/apartments/serve/master/ops/team/wait-next --gpu --pr N` in the background with `--max` under 30. Never wait silently on another thread; watch its PR or job, and message it when you unblock it.
- Update `docs/handoff/<thread>.md` at each milestone.

**How Ben wants to be talked to** (from the retrospective and his Oct 14 feedback)
- **Plain language.** "Every message about modeling makes my eyes cross." No R-hat, ESS, version numbers or rule names unless he asks. Lead with what changed and what it means. His style guide is in `~/.claude/CLAUDE.md` on thelio.
- **Never ask him to type a permission phrase** ("go", "launch the X", "OK: …"). This was the single biggest frustration (about 45 times). If his standing rules allow a step, do it and report. If the harness truly blocks something, say so once, plainly.
- Answer where he asked. Don't send him to another thread.
- Take the recommended option yourself when it is within budget, reversible and doesn't change direction. Tell him afterwards. Bring him only real decisions, one at a time, with a recommendation.
- Check claims before sending. A wrong instruction to him is worse than a slower answer. Strike through and correct anything wrong.

---

## 3. What is served, running and queued right now

**Served model (as of the last checks, 2026-10-14 22:45–23:18Z).** The served model is the NB8 C fit on the old **first-ask** target:
`m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope-nb8-nostuy-v1-rows-5c1e5c7e-a100-4500k9cb1-nb8-ul15r1s4q12ad3`.
It covers eight neighbourhoods: Chelsea, West Village, Greenwich Village, East Village, Flatiron, Gramercy Park, NoMad and Stuyvesant Town/PCV.
- The live site is the Oct 10 20:09Z build (`/data1/apartments/site/builds/20261010T200723992516Z-37822512`), served by `apartments-site.service` at `http://thelio.tail3983e0.ts.net:8600` (tailnet only; also :8500).
- `docs/handoff/modeling.md` line 6ff calls the served C "split C f469edaa on quarantine-v13". That conflicts with the Website and cleanup checks. The split C used a `tune-` rule, and a tune rule can't be served. Verify with the leaderboard and autoselect output before relying on either.
- No latest-ask C has passed the gate and been served yet. That was the whole of Oct 14's work.

**Running or queued (state at 01:58Z on Oct 15)**
1. **NB9 (Midtown West) C fit.** Queued by the new Modeling session on master after the bedroom fix (#806, and #807 is merged too). It was due to start **about 02:33Z** once the Modal balance ($1.71 at the time) covered the $2.03 estimate. Data set `nb9-nostuy-v1` (Midtown West split into Hell's Kitchen and Hudson Yards, about 297k rows), with the elevator and pets text fills (#778, #794). One-hour cap, strict all-building gate.
   - Ben's authority for it: "Launch the NB9 C" (22:35Z), plus the "Run after merge" card tap (01:42:58Z). It's authorized; don't ask again.
   - **Deadline:** 468 captured current Midtown West ads (`/data1/apartments/tmp/mw-current-20261014/details/snapshot/`) start leaving the 7-day "available now" window on **Oct 20**. The site can only show them once an NB9 fit is served (Ben chose "wait for the fit", not unpriced display). Leave room for one fix-and-rerun.
   - If it fails the gate, follow data → structure → sampler. A free fallback exists: a local subset test of a per-building bedroom slope only where a building has 3+ rows in at least two bedroom groups, covering 106 E 10th, 159 2nd Ave, 870 Broadway, 222 E 17th and 4 Perry. Leave `unit_nu` alone.
2. **Fixed-rho AR(1) fit.** It runs right after a passing C, on that C's exact rule list. Its predictions are written for the NB9 rules (#808). Ben approved it ("Run it", Oct 14 18:39Z). It replaces C's building walk with a stationary AR(1) deviation, rho fixed at 0.89, at about 40 minutes and $1.70–2. It's owned by the **Next modeling action** thread. The first fit (unconverged) showed PSIS-LOO +395 vs C and new-building year gap +1.5 pp vs +5.2. **If it wins, take it to Ben before serving** (that was the agreed plan in that thread).
3. **Data improvements:** writing `bedrooms-ad-v6` (13 fixes) and `quarantine-v23` (56 holds) from a widened check: 719 studios priced above their building's 1BR/2BR rows, read by Sonnet, plus 10 floor plans. It was running tests at 01:59Z. It's probably under the negligible-change bar, so no refit, but check.

**Fit history worth knowing (Oct 13–14)**
- The latest-ask C refit failed the gate at The West Coast, which is one tax lot with two structures. The fix is a wing rule (`west-coast-wings-v1`, `nb8-nostuy-wings-v1`, #779).
- The wing C then failed narrowly at 110 W 26th St. Its five cheap asks turned out to be room or bait ads and are held out (#792).
- The v17 wing C (49 min, $2.14) failed the strict gate at 106 E 10th St (R-hat 1.030) and 222 E 17th (ESS 117), and the bedroom slope reached 1.08. The cause was in the data: about 970 rows coded studio but priced like 3–4 bedrooms, including placeholder "apt" ads. The fix is #806 (bedrooms-ad-v4: 22 corrections with independent backing; quarantine-v22: 146 placeholder studios held out), then #807 (bedrooms-ad-v5: 4 more from floor plans).
- **Lines** (subway line groups within an 8-minute walk) on the split C: PSIS-LOO +22.5 (lot SE 10.3), a tie, so it's unserved. Its new-building lpd is +63 (lot SE 14). It's recorded as held.
- Summary and calibration now run on thelio after a Modal fit (#761, #763). This fixed the 20-minute summary timeouts that wasted about $1 a fit from Oct 12 to 14.
- The new-building error has stayed at about **12%** through every model change since C. The Oct 12 review's stopping rule: if new model terms don't move that number, shift effort to better data on size and apartment quality (for example the photo screen).

---

## 4. Open decisions (only these need Ben)

1. **Ben's Oct 13 serving hold.** At 03:16Z on 2026-10-13, Ben told Modeling to run or enqueue nothing but his three tasks, and the hold on **autoselect, serving and publishing** was recorded (`docs/handoff/modeling.md:95`). Running fits has clearly been superseded by his later approvals. Whether a passing NB9 C may go live is **asked and unanswered**: the new Modeling thread asked him at 01:48Z ("may I serve it?") and will serve nothing until he says yes. Context:
   - The project instructions (Ben, reaffirmed 10-10) say a winning fit is served without asking.
   - His Oct 14 messages point toward serving: "I want it to work with the midtown west data included". He also answered the West Coast card ("add the rule, refit C, and serve it if it wins" was the recommended option) "in the thread"; which option he picked there is not checked.
   - The coordinator's view is that it should be served. The cautious reading still waits for his yes.
   - If you take over Modeling, check that thread for his answer. Recommend yes because of the Oct 20 window.
2. **Next Brooklyn crawl** (Data collection, asked 22:40Z, unanswered). Options: Clinton Hill (about 76k requests, about $85, recommended as the cheapest first test), Greenpoint (about 140k, $160), Williamsburg (about 240k, $270). The remaining Oxylabs credit is unknown. Paid scraping needs Ben's go. Crawl via the no-JS GraphQL path (#705, #708, #710); Ben said not to resume the Brooklyn scrape until he says so.
3. **Daily refresh of current listings** (proposed Oct 10, about 2–3k requests a day, roughly $2–4 a day; unanswered). Without it, Chelsea, West Village and Greenwich Village "available now" captures are stale (Oct 4–6), and the Oct 10 captures age out around Oct 17.
4. Anything a future fit wins that reads other listings' prices still needs the leak-free latest-split check; that's not a Ben decision.

Settled on Oct 14 (don't re-ask):
- the West Coast wing rule;
- the fixed-rho AR(1) (run it);
- Midtown West built and fitted;
- wait for the fit rather than show unpriced listings;
- elevator and pets fills as data corrections (done);
- cap = 1 hour, no dollar cap;
- strict gate;
- no seed retries;
- latest ask as the target;
- floor plans allowed;
- Sonnet/Haiku for bulk reads.

---

## 5. Workstreams

Every workstream became **a single Claude session on thelio that Ben talks to directly**, started from its project thread (Oct 14 22:39Z for Data collection, Website, Repo state cleanup and Next modeling action; Oct 15 01:45Z for Modeling and Data improvements). The old cloud-plus-bridge threads are closed. Thread titles in the project: Modeling, Data improvements, Data collection, Website, Repo state cleanup, Next modeling action.

| Workstream | State | Next step |
|---|---|---|
| **Modeling** (`docs/handoff/modeling.md`) | NB9 C queued, starting about 02:33Z. Owns the Modal queues `modalq-c*`, `modalq-nb9` and the scripts in `/data1/apartments/tmp/bridge`. | Report the gate result, time and cost. If it passes and Ben says yes, serve and publish. If it fails, data → structure → sampler. Then hand the rule list to Next modeling action for the AR(1). |
| **Next modeling action** (AR(1)) (`docs/handoff/next-modeling-action.md`) | NB9 predictions merged (#808). Waiting on a passing NB9 C. | Run the fixed-rho AR(1) on the same rules if it fits under 55 minutes. Score it (paired PSIS-LOO by building and by lot, new-building lpd, median miss, 80/95 coverage, year gap, descriptive share). Write up hit or miss per prediction. Take it to Ben before serving. |
| **Data improvements** (`docs/handoff/data-improvements.md`) | bedrooms-ad-v6 and quarantine-v23 in tests. Rule versions so far: latest-ask-v4, quarantine-v22/23, unit-labels-v17/18, unit-reviews-v2, bedrooms-ad-v5/6, elevator-from-ad-v1, pets-from-ad-v1, west-coast-wings-v1. Check the handoff for the next free version numbers before creating one. | Review and merge v6/v23, tell Modeling, and decide whether it clears the refit bar (probably not). Fill files must be rebuilt (`python -m rentfrontier.adfills elevator\|pets`) for any new dataset. |
| **Data collection** (`docs/handoff/data-collection.md`) | Midtown West crawl and dataset are finished. No crawl is running. Midtown West and Downtown Brooklyn crawl databases were deleted (snapshot kept). | Waiting on Ben for Brooklyn area and the daily refresh. Before proposing paid collection, estimate its value to the model against its cost. Never raise the rate above Ben's setting (64/min since Oct 9). Crawl code runs only through a new frozen runtime directory. |
| **Website** (`docs/handoff/website.md`) | Site unchanged since the Oct 10 build. #776 (Hell's Kitchen and Hudson Yards words, `nb9` in story) is ready and unmerged. | Once an NB9 fit is served: merge #776, check the Midtown West capture is still inside the window, place it under `archive/current-listings`, rebuild (about 5 GB, only when the GPU is idle), and verify the selectors, map, /best, available now and counts ("all ten neighbourhoods"). Feature hold: new ideas go to `docs/playtests/backlog.md`. The About page stays anonymous. |
| **Repo state cleanup** (`docs/handoff/repo-state-cleanup.md`) | All Oct 14 decisions done (record: `docs/model/unadopted-work-2026-10-14.md`). Leftover worktree and venvs deleted (10 GB freed; /data1 had 231 GB free). | Refresh the research dashboard once a latest-ask C is served: the CSVs in `/mnt/project-files/dashboard/` and the artifact https://claude.ai/artifact/WLw3xxZHyTXruJWiDLknzg. Both have been stale since Oct 10. Check the served model yourself; a message from Modeling may not arrive. |

Closed threads with results worth knowing:
- **110 W 26th St data check:** added a standing ad-fit screen to every data build (#793, #802) and quarantine-v19/20/21 (161 rows: short stays, rooms, wrong addresses).
- **Brooklyn ads on Manhattan buildings:** see `/mnt/project-files/data-collection/brooklyn-ads-on-manhattan-buildings-2026-10-14.md`.
- **Project retrospective:** `/mnt/project-files/retrospective/retrospective-2026-10-14.md`.
- **Next high-leverage model actions:** `/mnt/project-files/modeling/next-actions-2026-10-13.md`.

**Retired or held (don't retest without new reason):**
- Retired: lister, retail, noise, trees, crime, hpd, bigbed, amenlevel, nofloorslope, lognoise, predicted size, and the final-ask-only target.
- Closed as null: renov and stab.
- Held: lines (a tie) and areatime (over the cap until redesigned).
- Elevator and pets are now data corrections, not feature tests.
- Long list of null explanatory features: `dashboard/tests.csv` and `docs/model/feature-tests.md`. Most building-level features came back flat because the building term absorbs them. The newer explained-share scoring is the right way to judge them.

---

## 6. Machines, paths, budgets

- **thelio** (Ben's Linux box): Ryzen 5 3600X (6 cores), 15 GB RAM, RTX 2060 Super 8 GB. Repo checkout `/home/ben/code/apartments`, a copy that follows master at `/data1/apartments/serve/master`, and data under `/data1/apartments/` (crawls, archive, frontier runs, modal logs and ledger, site builds, tmp worktrees).
- Jobs go through `ops/job gpu|light` (`docs/thelio-jobs.md`). Long jobs run in `systemd-run --user` units. Full-data C fits get OOM-killed on thelio at about 6.9 GB inside the GPU slice, so time full-data changes on Modal.
- **Modal:** $10/day limiter, 1-hour per-fit cap (section 2). A C-sized fit is about 40–50 minutes and $1.70–2.75. NB9 fits are estimated at 50–60 minutes, close to the cap.
- **Oxylabs** (StreetEasy scraping): limited budget, remaining credit unknown. Paid requests need Ben's go-ahead. Rate cap 64/min.
- **GitHub:** `gotnosocks/apartments` (public).
- **Shared project folder** `/mnt/project-files/`: visible to cloud threads, **not** to thelio sessions directly. Floor-plan, dashboard and retrospective files mentioned above live there.
- **Ben's devices:** macbookair and thelio. Remote Control is set up for thelio at `/home/ben/code/apartments`.

---

## 7. Known process problems

- **Permission phrases.** The old setup (cloud thread relaying to a thelio bridge session) made thelio refuse relayed or card approvals for paid runs, so Ben was repeatedly asked to type exact phrases. As of 01:45Z on Oct 15, every workstream is a single thelio session to fix this. #734 added allow rules for the fit wrapper, the queue runner and the queue file. If a step is still blocked, don't hand Ben a phrase to type. Say plainly what is blocked and why, once. Ben has also been told to write standing approvals in his own words in `~/.claude/CLAUDE.md` on thelio; whether he did is not checked.
- **Approval cards on every new Remote Control session.** These appear even though the folder is pre-approved in the project. Ben is unhappy with this. It's a product issue (reported via support), and nothing in the repo fixes it.
- **Usage limits.** Limits hit on six days. Most recently around 23:30Z on Oct 14, every session stopped for about 80 minutes, and some thelio sessions went offline until poked. After any wake, re-check state yourself and restart `wait-next`. Keep context small: compaction is set near 200k, read logs with tail and grep, and ask subagents for conclusions.
- **Status requests.** Ben asked "status?" about 23 times. A scheduled digest was suggested and has not been set up. Keep the thread status lines current.
- **Stale or unlanded work.** "Done" work has sometimes never landed: the latest-ask switch was built as a tune variant, and paid wins lived only in briefs. When you finish something, make sure it's on master, in the ledger, and (if it wins) served.
- **Thread sprawl and duplicate threads.** Check whether something is already working on a task before starting another.
