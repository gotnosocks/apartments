# Modeling handoff: NYC apartments → "NYC Rent Model" project (2026-10-21)

You are taking over the modeling work of Ben's NYC apartments research project: a Bayesian model of New York City asking rents, fitted on Modal from data prepared on Ben's Linux box "thelio", with results shown on a website. Earlier Claude threads did the work. This document is self-contained. It replaces the takeover prompt of 2026-10-20 and adds everything since. Facts are as of 2026-10-21 23:30 UTC. Check live state before acting on any of them; PR states below come from the threads' own reports and were not re-checked against GitHub when this was written.

## 1. Ben and how he works

- Ben owns the project and is the only person who can approve anything. He drops a request and leaves, and reads replies later.
- **Plain language.** Lead with what changed and what it means. Leave out R-hat, ESS, run IDs and version numbers unless he asks. His style guide is `~/.claude/CLAUDE.md` on thelio; read it.
- **Don't ask permission for what the rules already allow.** Do it, then tell him. Bring him real decisions one at a time, with a recommendation.
- **Check before you claim.** If you got something wrong, strike it through and correct it.
- **Keep a scientific record.** Predictions before every fit, misses recorded as misses, a results report after every fit.
- He thinks hard about model design and often reshapes a proposal mid-stream (e.g. "Floor will interact with elevator", "Why not just do a GP?"). Take his design notes seriously, restate the design back in one short paragraph, and update the PR's predictions before the fit.
- He sometimes says "no free check, predict from the context" — then answer from existing fits without running anything.

## 2. The goal (adopted 2026-10-15)

Find out what each quality of a New York apartment is worth to renters, and show it in ways that don't rest on our own judgment. "Worth" is the difference in rent between two apartments alike except for that quality.

- Work from the rawest material: each ad's photos, floor plan, text and full history; the physical city; independent records of rents actually paid.
- Treat location as a map of value to be explained by measurable things (transit, parks, noise, schools, light), not as a label. Don't use neighbourhood, building or surface terms as a crutch.
- **Ben's sharpened reading (2026-10-21):** the aim is to move variance out of the descriptive terms (the map surface, the per-building levels and the error) into named features people pay for. A feature that shifts weight from building levels into a named amenity at no cost to held-out prediction is a success, not a wash. Shifting credit among correlated features (doorman, gym, elevator) is expected. Held-out prediction is a check that nothing got worse, not the bar.
- Use natural experiments where a quality changed and little else did.
- A result counts as established only when something outside the model agrees: dated forecasts of ads not yet posted, the market's reaction, independent rent records, recovery of known answers from simulated data.
- Good theories are parsimonious and interpretable and state uncertainty for each factor and for the final ask. Report predictive medians and intervals, never means.
- Price target: each listing's latest ask, net of free months.

Full proposal: `/mnt/project-files/goal-proposal/deeper-goal-2026-10-15.md` (in the apartments project's shared folder; copy anything you need, since the new project may not see that folder).

## 3. Standing rules (from the apartments project instructions)

**FIT HOLD (Ben, 2026-10-19, still formally in force).** No Modal fits, model code changes or model PR merges until Ben explicitly says go, in words. In practice he has been giving a go fit by fit (and design by design) all through 2026-10-21; each go covers the fit or change he named and nothing more. After each excepted fit the hold applies again. Free read-only checks on thelio are still allowed. Quote his message as the authority when a launch needs it.

**Fits**
- Fit-only by default: `ops/modal-fit --no-loo --no-heldout`. Score later from saved draws (`rentfrontier.loo <run>` or the held-out scoring used in recent reports) only when Ben asks or a comparison needs it. Recent reports have included latest-split held-out scores, and Ben has found them useful.
- One fit at a time, each testing one change, no bundling (Ben has sometimes bundled several features into one fit on his own say-so).
- Modal budget: $10/day accrues in a rate limiter (`ops/modal/cap.py`, ledger `/data1/apartments/modal/ledger.jsonl`). Launch only when the balance covers the estimate. Recent Gibbs fits cost $0.37 to $0.73 each.
- Per-fit cap: about 1 hour of wall time. Redesign or record as blocked if a fit would exceed it.
- Never retry a failed fit on a new seed. Investigate the data, then model structure, then sampler settings.
- After every fit: a markdown results report (recent pattern `building-zones-<name>-results-<date>.md`), a results-note PR in the repo, a data page Artifact, and a 3Blue1Brown-style step-through explainer Artifact built from the fit's own saved draws with chain disagreements marked (style: https://claude.ai/artifact/GbevoL25BCYrfQ6uFDHw49). Link both in the results reply.
- **Per-feature table in every report (Ben, 2026-10-21):** for every column show share of ads, premium, and contribution premium²·p(1−p), plus held-out scores for the ads that have the feature, so a rare feature with a large effect doesn't look unimportant.
- Registry snapshot `20261019-bcfbb52-extend`; every row has a location. Queens rows (Ridgewood/Glendale) stay in, in the not-Manhattan zone by BBL.
- New Jersey is out of the current building-zones line until NJ data match NYC's quality (no footprints, no condo data).

**Evaluation framework (whenever discussing fit results).** §3 and the §10 preamble of `research-review-fable/review-2026-10-08.md`, as adopted in §8 of `modeling/research-review-2026-10-08.md`: paired PSIS-LOO or held-out elpd on shared rows with a ~2 combined SE bar; building-level features scored by explained share against a permutation null with grouped building holdouts; rent-derived terms must also win the latest time split; new-unit coverage from a time-split refit against nominal 0.79/0.95; descriptive share on every run; predictions before fitting, misses recorded as misses; predictive medians and intervals.

**Data**
- Fix the data before patching around it in the model. Corrections toward a known truth proceed on their own; don't refit for negligible changes.
- Corrections need independent evidence (another ad for the same unit, a floor plan, a stated size, matching units in the same line). Ad text alone or price alone is not enough.
- Floor plans may be fetched and stored when a listing's analysis needs them.
- Bulk ad reading goes to Sonnet or Haiku subagents.
- OxyLabs scraping spend is pre-approved (limited budget).

**PRs and serving**
- A thread may merge its own PR after a separate reviewer subagent approves it: squash-merge with an annotated `archive/pr-N` tag (`gh pr merge N --squash --match-head-commit`). Run `ops/fmt` before every commit. Model PRs still need Ben's go under the hold.
- Serving: when a fit wins under the repo's selection rules (autoselect, convergence checks, leak-free latest-split comparison for features that read other listings' prices) and has gone through a reviewed PR, serve and publish without asking, then tell Ben. Nothing from the building-zones line is served yet.

## 4. Where things live

- **Repo:** `gotnosocks/apartments` (public). Read `CLAUDE.md` first. Workstream notes in `docs/handoff/*.md`; Modal and job docs in `docs/model/modal.md` and `docs/thelio-jobs.md`; results notes in `docs/notes/`. The Gibbs sampler is `frontier/src/rentfrontier/gibbs.py`; model code in `b0.py` and neighbours.
- **thelio** (6-core Ryzen, 15 GB RAM, RTX 2060 Super 8 GB). Checkout `/home/ben/code/apartments`; master copy `/data1/apartments/serve/master`; data under `/data1/apartments/` (runs in `frontier/runs/`, scratch in `tmp/` — e.g. the explainer and coverage work in `tmp/zones-explainer/` — floor plans in `archive/floor-plans/`, external data in `external/`). Long jobs via `ops/job gpu|light`. Full-data fits run on Modal (A100). Threads drive thelio through a Remote Control session into `~/code/apartments`.
- **Website:** `apartments-site.service` on thelio, `http://thelio.tail3983e0.ts.net:8600` (tailnet only), with a `/new-jersey` page. It still serves an older model from before the building-zones line; check before saying what is served.
- **Timers:** every project timer on thelio has been paused since 2026-10-18 (pipeline build, StreetEasy backup, city fetch, Friday top-up scrape, dashboard build, Modal cleanup). Re-enable commands: `ops/paused-timers-2026-10-18.md` in the shared folder. Leave paused until Ben says otherwise.
- **Apartments project shared folder** `/mnt/project-files/`: `modeling/` (every results report), `handoff/` (this file, the 2026-10-20 takeover prompt, the 2026-10-15 project handoff), `goal-proposal/`, `research-review-fable/`, `data-pipeline/closing-report-2026-10-17.md`, `compute-direction-2026-10-17.md`, `gpu-inference-direction-2026-10-17.md`.

## 5. Model lineage

All fits from 2026-10-20 on use the **building-zones** structure: weekly market walk + season, bedroom and bath steps, flags (shared space, income-restricted, rent-stabilized), a level per zone (Manhattan / Brooklyn + Queens) plus a 1 km HSGP surface per zone, a level per building centred on its map value plus x'γ from building columns, and Student-t noise. Sampled with a blocked **Gibbs** sampler (4 chains, A100). NYC only: 1.71M training ads, 67,977 buildings. Comparisons use the latest time split (189,649 held-out ads).

Earlier history (2026-10-18 to 10-20): restart from a small baseline B0 (`modeling/baseline-model-proposal-2026-10-18.md`); B0.3 no-location design (#1156) converged; NJ added (`b0-results-2026-10-19-alldata-nj.md`); HSGP zone surfaces hard to sample under NUTS (`whitened-zones`, `location-options-2026-10-20.md`); building attributes without location (#1176/#1177, `b0-results-2026-10-20-building-attrs.md`); building-zones under NUTS failed (`b0-results-2026-10-20-building-effect.md`), so Ben asked for Gibbs (#1180).

| # | Fit (run) | Change | Key result | Report / explainer |
|---|---|---|---|---|
| 1 | `building-zones-gibbs-b0-latest-f1cd5984-dense-w650` (10-20) | Gibbs building-zones, no building features (incl. NJ) | Essentially converged, 9.5 min, $0.38; amplitudes 1.10/0.48/0.72, building shares 0.56/0.40. Write-up was docs PR #1181 (status not re-checked; no markdown report in `modeling/`). | https://claude.ai/artifact/6zLQxJV2zsBwuwM8gh1zyA (also https://claude.ai/artifact/PksAPKatiWxSzXopnhStkx, sampler tour) |
| 2 | `building-zones-attrs-b0-latest-9bd8c1a3-dense-w650` (#1182) | + roof height, elevator, condo, doorman; NYC only; 1 km | FT doorman +19.6%, condo +14.8%, PT doorman +12%, elevator +9.1%, roof height −0.7%/e-fold; zone gap 37%→30% | `building-zones-attrs-1km-results-2026-10-21.md`, https://claude.ai/artifact/G3KAZmnBb2gzPVMn6WnbSC |
| 3 | `building-zones-attrs-500m-…` | same at 500 m | Little extra detail outside Manhattan; amplitudes miss gate; not adopted (1 km kept) | `…-attrs-500m-results-…`, https://claude.ai/artifact/EqoGvZmqsixkJj7K3r2dyc |
| — | PR #1185 | 2 bed bath staircase capped at 3 full baths (49 rows) | Merged with Ben's go; no fit | — |
| 4 | `building-zones-front-b0-latest-9652d249-dense-w650` (#1186) | + street width bands, corner | Wide streets −2 to −3%, flat across bands; passes gate. **Ben: not convincingly additive; dropped.** | `…-frontage-results-…`, https://claude.ai/artifact/9bzEXWfAgjhsFcpTD6H7mT |
| 5 | `building-zones-unit-b0-latest-a3aec3ff-dense-w650` (#1190, note #1191) | base = #2 + bath cap; + unit size (3-layer fill + unknown/imputed flags), laundry, dishwasher, truck route | Size +2.4% per 10% over bedroom median; laundry in-unit +6.5%; dishwasher +2.1%; truck −4.2%; T 0.0622→0.0530; held-out +9,807 (SE 162) vs #2; passes gate | `…-unit-results-…`, https://claude.ai/artifact/KFZg6XZxycCjW6GKrUhi3w, data page https://claude.ai/artifact/PvBs8AxoZmFCJZd58ynrig |
| 6 | `building-zones-gym-b0-latest-f2d01c92-dense-w650` (#1192, note #1193) | − truck, + gym | Gym +7.6%, taken from doorman/elevator/condo and building levels; held-out −11 (SE 3); Ben ruled gym belongs (explanatory goal) | `…-gym-results-…`, https://claude.ai/artifact/TDXi9ALx3i7ji4TFopJEqa, data https://claude.ai/artifact/Mj7DNLFMQzus4fYcXehbqs |
| 7 | `building-zones-age-b0-latest-f023987f-dense-w1000` (#1194, note #1195) | + truck back, year-built bands, altered since 2000, ground-floor retail; 300 warmup / 1,000 sweeps | Truck holds −3.9% (newness doesn't explain it); pre-1900 +4.1%, 2010-on +4.0%, altered +3.8%, retail −1.9% (negative Shapley, flat held-out); held-out +31.7 (SE 18.4) vs #6; passes gate | `…-age-results-…`, https://claude.ai/artifact/NqN1Mbun8GxgqjPhbxFVms, data https://claude.ai/artifact/CaAoDoDPMjYrHqr6qUjosj |
| 8 | **`building-zones-floor`** (#1196 merged, note #1197) | + unit floor: two exact GPs on log floor (elevator capped at 47, walk-up at 6), pinned to 0 at floor 1; flags for top floor (by group), penthouse, garden, lower level, floor unknown (by group); sampler draws lengthscale with amplitude integrated out | **Best fit.** Held-out **+2,945 (SE 83)** vs #7, RMSE 0.1172→0.1154; passes gate (max R-hat 1.0097, min ESS 590). 18 min, $0.73. | `building-zones-floor-results-2026-10-21.md`, https://claude.ai/artifact/1HnpNRK5AJqHXnD5udwHg3, data https://claude.ai/artifact/FxkYoSW942AWctAVGrf1iF |

### The best fit in more detail (building-zones-floor)

- Elevator curve over floor 1: floor 2 +1.2%, 3 +1.33% (1.22 to 1.44), 4 +1.5%, 5 +2.1%, 10 +3.8%, 20 +6.7%, 30 +10.0%, 40 +13.8%, 47+ +19.5%. Climbs faster the higher you go. Low floors are pinned by data (50k to 80k ads each, ~0.2-point intervals).
- Walk-ups: slightly below floor 1 at every floor, about −0.2 points per flight, −0.9% at floor 5.
- Flags on top of the curve: penthouse +8.3%, garden +2.9%, elevator top floor +1.75%, walk-up top floor −0.3%, lower level −3.7% (only 564 training ads), elevator floor unknown +4.0%, walk-up floor unknown −0.55%.
- Lower level, garden and penthouse come from the unit label in the ad URL (e.g. "apt-LL2", "BSMT", "CELLAR", "PH", "GDN"), not from description text. Floor comes from the pipeline's `listed_floor`. Top floor = floor equals MapPLUTO's floor count (202,482 listings) or, where missing, the building's highest floor seen in ads (8,552).
- Elevator premium fell 6.8%→3.6% (the curve now carries part of it). Other columns moved ≤0.6 points.
- Penthouses went from a median 10.5% underpriced to 0.3%; 90% coverage 69%→79%.
- Weak spots: elevator ads with no floor fit slightly worse (−202 elpd; consider a better floor fill or splitting the flag by building height); floors 40+ now 3.3% too high (the 47 cap merges very tall floors).
- Building effects correlate 0.998 with #7 and the map 0.99998: floor explains within-building variation, which the building columns can't.
- Ben asked why log floor; answer given: log floor costs no compute and every floor still gets its own value; log only ties low floors more loosely than high ones. A linear-floor comparison fit was offered and needs his go.
- The explainer now has a "by floor" scene with each floor's exact value and a full table (added at Ben's request).

### What the current "master" design is

Building-zones, 1 km, NYC only, bath cap, with: roof height, elevator, condo, doorman (FT/PT/virtual), size (+flags), laundry, dishwasher, gym, truck route, year-built bands, altered since 2000, retail, and the floor curves and flags. That is exactly fit #8. Frontage is out. No fit in this line has been served.

### Unexplained-variance track (T = map + building level + error, demeaned within zone)

0.0622 (building features) → 0.0530 (+ size, laundry, dishwasher, truck) → 0.0511 (+ gym, − truck) → 0.0509 (+ truck, age, alteration, retail) → known-floor ads −3.9% further with floor. Shapley rise if removed (fit #7): size 0.0079, laundry 0.0037, gym 0.0037, dishwasher 0.0010, year built 0.0009, altered 0.0005, truck −0.0003, retail −0.0006.

### Findings worth carrying forward

- Neighbourhood lines carry no extra building variance beyond random areas of the same count; the jumps sit at wide streets. Building-level gap across 41 to 70 ft streets is still ~0.023 log points above narrow streets after size went in.
- Ben's strong prior: wide/noisy streets cost rent (he lived on 14th St and at 1st Ave & 88th). A free check found mid-block Manhattan avenue buildings sit 2.5 to 6% below side-street neighbours within 250 m (1st, 3rd, York, Lexington, Amsterdam), offset elsewhere. The frontage width bands didn't capture it; a better noise measure (traffic, 311 noise, truck route) is the open lead.
- Truck route −4% persists within every era and size band; whether it is a real discount or a marker of something unmeasured is open.
- Size fill: stated 26% of ads → 39% with same-unit relists → 45% with same-line fills; ~88% of fills within 10%. Floor plans could reach ~55%.
- Residual screen (fit #2): unused fields explained 39% of map + building + error; size, laundry, dishwasher, gym, year built and floor were the strong ones — all now in.
- Coverage for candidate building features (PLUTO, footprints, LPC, Manhattan-only HPD/DOB/rent-stabilization, cheap NYC Open Data feeds): `modeling/building-features-coverage-2026-10-21.md`. About 2% of buildings carry a doubtful PLUTO floor count (shared lots, the "8 Spruce" pattern).

## 6. Pending decisions for Ben

1. **Make the floor fit (#8) the new base model.** Recommended: yes — clearest held-out gain since size, passes the gate. Awaiting his go.
2. **Retail:** −1.9% premium but negative Shapley and flat held-out; a fit dropping it was proposed, needs his go.
3. **Linear vs log floor:** offered as a comparison fit, needs his go.
4. **Floor follow-ups:** a better fill for elevator ads with unknown floor (or split that flag by building height); revisit the 47-floor cap.
5. **Serving:** the website still serves an older model. Serving the building-zones line would need the selection routine and a scored comparison against the served model; raise with Ben when he wants the site updated.
6. **Older proposals still open:** honest intervals via grouped building holdouts; Matérn 3/2 vs SE kernel; a tax-block level between map and buildings (test for street-bounded variance); NJ floor counts from the tax roll (thelio branch `nj-storeys`); latent size, FARE Act natural experiment, simulated recovery, outside rent indexes (`modeling/baseline-backlog-2026-10-18.md`).

## 7. Open PRs and paused work

- **#1168 (`quarantine-v36`):** sets aside 197 NJ room shares and commercial ads. Tested, unmerged, waiting for Ben's word. Merging makes the old served fit unservable until a refit.
- **#1181:** docs write-up of Gibbs fit #1, left open on 2026-10-20 (check its state).
- **#1197:** results note for the floor fit (check whether merged).
- **#1141 (draft):** list columns for the fit-to-site path, to merge after the next publish.
- **Paused since 2026-10-18 at Ben's request (don't restart without his word):** NJ data cleanup; API pipeline rebuild and the overcounted-buildings review (waits on Ben's hand review; notes in `data-pipeline/overcount-review-notes.md`; 432 E 13th researched, 94 Barrow and 60 W 22nd next; scored unit matching measured but unused, ~30% wrong joins); fit-to-site rework; scraper and data collection (Friday top-up timer paused); GPU/Gibbs compute direction (Gibbs now built and in use).

## 8. First things to do

1. Read the repo's `CLAUDE.md`, `~/.claude/CLAUDE.md` on thelio, and this file.
2. Check live state on thelio: `git fetch && git log origin/master --oneline -20`; `gh pr list` (confirm #1168, #1181, #1197, #1141); `python3 ops/modal/cap.py`; `ops/job status`; `systemctl --user list-timers` (nothing from the project should be active).
3. Confirm the floor run's draws are in `/data1/apartments/frontier/runs/` and that its report and explainer links above resolve.
4. Ask Ben once, with a recommendation: make the floor fit the base, then which single next test (recommended candidates: a better noise/avenue measure for the wide-street gap, the elevator floor-unknown fill, or dropping retail). Until he answers, do only free checks, evidence-backed data corrections and write-ups.
