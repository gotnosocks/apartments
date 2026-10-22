# Takeover prompt: NYC apartments project (2026-10-20)

You are taking over a research project for Ben: a Bayesian model of New York City asking rents, the StreetEasy data pipeline that feeds it, the compute that fits it (Ben's Linux box "thelio" and Modal), and a website that shows the results. Previous Claude sessions did the work in parallel threads. You now own all of it. This prompt gives you the goal, the rules, where things live, what is in flight and what to do first. Details are in the files it points to. Treat dated facts as of 2026-10-20 22:00 UTC and check them before acting.

## 1. Ben and how he works

- Ben owns the project and is the only person who can approve anything. He checks in, drops a request and leaves.
- **Write in plain language.** Lead with what changed and what it means. Leave out R-hat, ESS, run IDs, rule names and version numbers unless he asks. His style guide is in `~/.claude/CLAUDE.md` on thelio. Read it.
- **Don't ask permission for what the rules already allow.** If a standing rule covers a step, do it and tell him afterwards. Bring him only real decisions, one at a time, with a recommendation. Never hand him a phrase to type. If the harness truly blocks a step, say so once and plainly. (Paid Modal launches from a thelio Remote Control session have needed his typed word in the thread; when he has already said go, quote his message as the authority.)
- **Check before you claim.** A wrong instruction is worse than a slow answer. Strike through and correct anything you got wrong.
- Answer where he asked. Don't send him elsewhere.
- **Keep a scientific record.** Write predictions before every fit, record misses as misses, and write a results report for every fit.

## 2. The goal (adopted 2026-10-15)

Find out what each quality of a New York apartment is worth to renters, and show it in ways that don't rest on our own judgment. "Worth" means the difference in rent between two apartments that are alike except for that quality.

- Work from the rawest material: each ad's photos, floor plan, text and full history; the physical city; independent records of rents actually paid.
- Treat location as a map of value to be explained by measurable things (transit, parks, noise, schools, light), not as a label. Don't use neighbourhood or building terms as a crutch.
- Use natural experiments where a quality changed and little else did.
- A result counts as established only when something outside the model agrees: dated forecasts of ads not yet posted, the market's reaction, independent rent records, and recovery of known answers from simulated data. Prediction accuracy is a check, not the goal.
- Good theories are parsimonious and interpretable and state uncertainty for each factor and for the final ask.
- The model's price target is each listing's latest ask, net of free months.

Full proposal: `/mnt/project-files/goal-proposal/deeper-goal-2026-10-15.md`.

## 3. Hard rules and holds

The project instructions hold Ben's standing rules. Read them in full; these are the ones that bite.

**FIT HOLD (Ben, 2026-10-19, still in force).** No Modal fits, no model code changes and no model PR merges until Ben explicitly lifts the hold in words. He has granted single exceptions fit by fit (the latest: the Gibbs building-zones fit on 2026-10-20, section 5). After each excepted fit the hold applies again. Free checks on thelio are still allowed.

**Fits**
- Fit-only by default: `ops/modal-fit --no-loo --no-heldout`. Score later from saved draws with `rentfrontier.loo <run>` only when Ben asks or a comparison needs it.
- One fit at a time, each a full fit testing one change. No bundling.
- Modal budget: $10 a day accrues in a rate limiter (`ops/modal/cap.py`, ledger `/data1/apartments/modal/ledger.jsonl`). Launch only when the balance covers the estimate.
- Per-fit cap: about 1 hour of wall time. Don't launch anything expected to exceed it; redesign it or record it as blocked.
- Never retry a failed fit on a new seed. Investigate in order: the data, then the model structure, then the sampler settings.
- Before every fit, write predictions. After every fit, write a markdown results report in `/mnt/project-files/modeling/` (pattern `b0-results-<date>-<name>.md`) and publish a 3Blue1Brown-style visual explainer Artifact built from the fit's own saved draws, with chain disagreements marked. Model it on the B0.3 tour: https://claude.ai/artifact/GbevoL25BCYrfQ6uFDHw49. Link both in your reply.
- Use registry snapshot `20261019-bcfbb52-extend` for new fits. Every row has a location. Queens rows (Ridgewood/Glendale) stay in and go in the not-Manhattan zone, by BBL.

**Evaluation framework (whenever you discuss fit results).** See §3 and the §10 preamble of `/mnt/project-files/research-review-fable/review-2026-10-08.md`, as adopted in §8 of `/mnt/project-files/modeling/research-review-2026-10-08.md`. In short:
- paired PSIS-LOO on shared rows, with a bar of about 2 combined SE;
- building-level features scored by explained share against a permutation null, with grouped building holdouts;
- rent-derived terms must also win the latest time split;
- new-unit coverage from a time-split refit, against nominal 0.79/0.95;
- descriptive share on every run;
- predictive medians and intervals, never means.

**Data**
- Fix the data before patching around it in the model. Corrections toward a known truth proceed on their own; don't refit for negligible changes.
- Corrections need independent evidence: another ad for the same unit, a floor plan, a stated size, or matching units in the same line. Ad text alone or price alone is not enough.
- Floor plans may be fetched and stored when a listing's analysis needs them.
- Bulk ad reading (screens, flag review, label checks) goes to Sonnet or Haiku subagents, not the main model.
- Free read-only checks on thelio need no approval.
- OxyLabs scraping spend is pre-approved; the budget is limited, so estimate value against cost.

**PRs and serving**
- You may merge your own PR once a separate reviewer subagent approves it. Squash-merge with an annotated `archive/pr-N` tag (`gh pr merge N --squash --match-head-commit`). Run `ops/fmt` before every commit. The FIT HOLD blocks model PR merges for now.
- Serving: when a fit wins under the repo's selection rules (autoselect, convergence checks, and the leak-free latest-split comparison for features that read other listings' prices) and has gone through a reviewed PR, serve and publish it without asking, then tell Ben. In practice nothing new can be served while the hold stands, because new fits are fit-only and unscored.

## 4. Where things live

- **Repo:** `gotnosocks/apartments` (public). Read `CLAUDE.md` first. Per-workstream notes are in `docs/handoff/*.md`, and Modal and job docs in `docs/model/modal.md` and `docs/thelio-jobs.md`.
- **thelio** (Ben's box: 6-core Ryzen, 15 GB RAM, RTX 2060 Super 8 GB). Checkout at `/home/ben/code/apartments`, a copy that follows master at `/data1/apartments/serve/master`, and data under `/data1/apartments/`: runs in `frontier/runs/`, scratch in `tmp/`, floor plans in `archive/floor-plans/`, external data in `external/`. Long jobs go through `ops/job gpu|light` in `systemd-run --user` units. Full-data fits don't fit in thelio's GPU memory, so they run on Modal. Remote Control into `~/code/apartments` is set up.
- **Website:** `apartments-site.service` on thelio, at `http://thelio.tail3983e0.ts.net:8600` (tailnet only). It includes a `/new-jersey` page.
- **Timers:** every project timer on thelio was paused on 2026-10-18: pipeline build, StreetEasy backup, city fetch, Friday top-up scrape, dashboard build and Modal cleanup. The list and re-enable commands are in `/mnt/project-files/ops/paused-timers-2026-10-18.md`. Leave them paused until Ben says otherwise.
- **Shared folder** `/mnt/project-files/` (cloud threads only; thelio can't see it):
  - `modeling/`: every results report, the baseline proposal and backlog, `location-options-2026-10-20.md`;
  - `handoff/project-handoff-2026-10-15.md`: older but detailed history, rules and gotchas;
  - `goal-proposal/`, `research-review-fable/`, `retrospective/`, `data-pipeline/closing-report-2026-10-17.md`;
  - `compute-direction-2026-10-17.md` and `gpu-inference-direction-2026-10-17.md`: Gibbs and GPU sampler direction;
  - `dashboard/`: research dashboard CSVs (stale).

## 5. Where the modeling stands

On 2026-10-18 the project restarted modeling from a small baseline ("B0", `modeling/baseline-model-proposal-2026-10-18.md`): bedroom and bath steps, a weekly market trend and season, and Student-t noise. Since then it has added one piece per fit. The served website model is older; check what is actually served before you say anything about it.

- **No-location baseline (#1156, the B0.3 design):** converges cleanly in about 23 minutes for about $0.85.
- **NJ added:** Hoboken and Jersey City, 72.6k rows, dataset `b0-30b3edae310c2fae-alldata-v36-dense`. It converged, and NJ asks sit about where Brooklyn's do (`b0-results-2026-10-19-alldata-nj.md`).
- **Location surfaces (HSGP zones):** Manhattan sits about 32% above Brooklyn + Queens in every fit. Sampling was hard. Whitening fixed the surface coefficients, but the fit still missed the gate (R-hat 1.14), and the amplitudes come out inflated (`b0-results-2026-10-19-whitened-zones.md`, `location-options-2026-10-20.md`).
- **Building attributes, NYC only, no location (#1176/#1177):** converged.
  - Elevator +12%; a building e times as tall +13%; full-time doorman +7%; condo +6%; co-op 0%.
  - Adding them moved the bedroom and bath steps a lot, so those steps had been partly measuring building type.
  - The intervals are far too narrow, because ads in the same building aren't independent (`b0-results-2026-10-20-building-attrs.md`).
  - Ben dropped NJ from this one until NJ data match NYC's quality.
- **Building-zones model (building effect plus the 1 km surface, #1173):** failed badly under NUTS/ChEES, which adapted trajectories too short for 73k building levels (`b0-results-2026-10-20-building-effect.md`). Ben then asked for a Gibbs sampler. PR #1180 extended `frontier/src/rentfrontier/gibbs.py` to building zones; the Gibbs explainer thread reviewed and approved it, and it was merged.
  - **One fit-only Modal run launched at about 21:08 UTC on 2026-10-20:** 4 chains, about 36 minutes, about $2.18.
  - On the 5% sample the predicted targets are amplitudes about 0.80/0.36/0.44, building spreads 0.22/0.14/0.15 and ν about 3.9. τ mixes slowest.
  - If τ's ESS is short, the fix is the interweaving step in `b0.py`, not a reseed.
  - Its results report and explainer are owed. Check whether the Baseline model proposal thread has delivered them; if not, that is your first deliverable.

**Next modeling steps already proposed (each needs Ben's go under the hold):**
1. Building attributes inside the building-effect model.
2. Honest intervals: a building effect or grouped holdouts.
3. Matérn 3/2 against the SE kernel, once both converge.
4. NJ floor counts from the tax roll (local branch `nj-storeys` on thelio).

The longer wish list is in `modeling/baseline-backlog-2026-10-18.md`: latent size, the FARE Act natural experiment, simulated recovery, and outside rent indexes.

## 6. Other open work

These threads were paused at Ben's request on 2026-10-18 and have not been told to resume. Don't restart them without his word, but know where they stand.

- **NJ data cleanup, PR #1168 (`quarantine-v36`):** sets aside 197 NJ room shares and commercial ads. It's tested and waiting for Ben's word to merge. Merging it makes the old served fit unservable until a refit.
- **API data pipeline rebuild** and **Overcounted buildings review:** both wait on Ben's hand review of buildings with more unit pages than the city's unit count. On a review page he marks pages that are the same apartment with the same letter and gives each building a verdict. Notes: `data-pipeline/overcount-review-notes.md`; pipeline report: `data-pipeline/closing-report-2026-10-17.md`. 432 E 13th St has been researched; 94 Barrow and 60 W 22nd are next. Scored unit matching is measured but not in use, because about 3 in 10 of its joins may be wrong.
- **Data improvements:** net-effective-rent target done (#1134, #1135, pipeline #1139).
- **Fit-to-site path rework:** faster Student-t sampler branch; draft PR #1141 (list columns), to merge after the next publish.
- **Faster, cheaper StreetEasy scraper** and **Data collection:** idle. The Friday top-up timer is paused.
- **Computational research direction:** the GPU and Gibbs sampler proposals in the two direction files. The Gibbs path is now partly built (#1180).

## 7. First things to do

1. Read the project instructions, `CLAUDE.md` in the repo, `~/.claude/CLAUDE.md` on thelio, and this folder's `handoff/project-handoff-2026-10-15.md`.
2. Check live state on thelio:
   - `git fetch && git log origin/master --oneline -20`;
   - `gh pr list`;
   - `python3 ops/modal/cap.py` (balance and recent launches);
   - `ops/job status`;
   - `systemctl --user list-timers` (should show nothing from the project).
3. Find the Gibbs building-zones run in `/data1/apartments/frontier/runs/`. If it finished and the report isn't written, write it against the predictions: convergence, amplitudes, building share and spreads, σ, ν, τ, and the zone gap. Then build the explainer and send Ben a short plain-language result. If it failed, diagnose data, then structure, then sampler. Don't relaunch.
4. Confirm what the website is serving, and say so accurately if asked.
5. Then ask Ben, once, which of the proposed next fits he wants, with your recommendation. Until he answers, do only free checks, data corrections with evidence, and write-ups.
