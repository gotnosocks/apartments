# Next actions for the model's explanations

*Planning thread, 2026-10-13. This is a plan only. No fits, crawls, LLM reads or data changes were run. Code references are to the repo at cb52b52. Every prediction below was written before any run. Each is a median with an 80% interval in brackets unless marked otherwise. "Inferred" means reasoning, not a measurement. The scoring follows the evaluation framework: Fable review §3 and the §10 preamble, as adopted in §8 of [research-review-2026-10-08.md](research-review-2026-10-08.md).*

## The plan

| # | Action | Kind | Who and effort | Money | Expect it to fail? |
|---|---|---|---|---|---|
| 1 | Score new buildings per building, with clustered SEs | Measurement change | Modeling, 1-1.5 days | $0 | No |
| 2 | Leak-free ceiling: how much data we already hold can explain | Measurement change | Modeling, 0.5-1 day after #1 | $0 | No. The likely answer is "not enough", which is still a decision |
| 3 | Photo quality screen: LLM grades of lead ad photos | New data source | Data improvements, 4-6 days; Modeling, 0.5-1 day | LLM about $35-45 to a verdict; Oxylabs $0-4 | **Yes**, P(pass) about 0.25 |
| 4 | Leave-East-Village-out refit | Measurement change, one fit | Modeling, about 0.5 day | Modal about $2.5 | No |
| 5 | GraphQL size check | Data fix behind a free gate | Data collection, 2-3 h | $0 (a fit and GETs only if it passes) | **Yes**, P(pass) about 0.1 |

Expected spend over about three weeks:
- Modal: about $3-8, mostly on gated fits.
- Oxylabs: under $1 expected.
- LLM: about $35-45, plus $200-260 only if the photo screen passes.

**Why this shape.** The 2026-10-12 model review set a stopping rule. If the new-building miss does not fall by 0.5 pp and the descriptive share does not fall by 2 pp, stop adding model terms and move the effort to size and quality data. None of the 11 candidates reviewed here has a median prediction that reaches either bar. Every model-term fit since C has scored 11.9-12.0% on new buildings.

So the plan does three things:
- It spends Modeling time first on the measurements that every later verdict depends on (#1, #2).
- It spends money on the one new data source with a plausible path to explaining building levels (#3).
- It then tests whether the explanations carry to an area the model has not seen (#4), and settles the last cheap size hypothesis (#5).

The concession-rows fit and the West Village NTA step were both refuted (see "Dropped").

## What Ben needs to decide first

1. **Does the 03:16Z hold also cover free thelio checks and the Data threads' counts?** Every action's first step waits on the answer. The hold is at docs/handoff/modeling.md:276-279. The standing free-check approval dates from 10-08. My recommendation is to allow free checks.
2. **Strike the held queue.** That is the areatime rerun, retail, noise, trees, crime, hpd, petsfill, lister and predsize.
   - Every reviewer rejected all of them as they stand.
   - Their screen shares are 1.2-2.4% or inside the null.
   - Areatime is a label crutch.
   - Striking them costs $0, saves about $17-20 and frees about 4 days on the fit limiter.
3. **Give one costed OK for #3**, capped at about $45 of LLM plus up to $4 of Oxylabs. It covers the URL probe, the pilot re-read and the 600-building photo sample.
4. **Free one fit slot for #4** (about $2.5) once #1 has landed.
5. **Resume autoselect for lines, then elevfill and bigbed.**
   - These are the only named-feature wins already paid for: lines +45 ± 16, elevfill +33 ± 14, bigbed +43 ± 18.
   - Those figures appear only in the brief and the prior review, not in a repo ledger, so run a dry run first.
   - Land the crutch guard (side check 5) before autoselect resumes.
6. **Is new-unit range honesty in scope now?** New-unit coverage is 67/89 on 964 by-product rows, the one proven range defect.
   - If yes, run the time split and the two-component unit prior (2i) back to back on a cutoff of about 2026-04-01.
   - If not, caption the site's 67/89 as a row-split by-product figure.

These are also Ben's, though less urgent:
- Which ask the model explains (first, latest or final), and how concession listings enter.
- Whether a label-free C may be fit and served even if its new-building miss rises.
- Whether to adopt the stopping rule formally.
- Rule changes: a clustered-SE tie tolerance, a 4-chain R-hat gate, and a 5% materiality bar against today's screen_wins.

---

## 1. Score new buildings per building, with clustered SEs

**What it is.** This is the slim slice of the new-building scoring proposal that both critics endorsed. It is one reviewed PR for the Modeling thread and runs free on thelio.

- **(a) Step 0, first, about 0.5 day.** The scorer has no year group and no origin switch, and it refuses to run from a dirty tree, which is why this takes half a day.
  - Add a listing-year group, and a first-knot walk origin kept off the board as a diagnostic only. The code is newbuilding.py `walk_origin` :95-104 and the groups at :253-263.
  - Rescore C, areatime and nofloorslope.
  - Read 80/95 coverage by listing-year band within each row bin, stratified by unitsres tercile and PLUTO class.
- **(b) A per-row file written beside result.json.** Today the scorer writes only result.json (newbuilding.py:578).
  - Fields: audit_id, building, bbl, knot and year, row bin, class, unitsres tercile, size-stated, y, median, building part, PIT and lpd.
  - lpd is the log of the draw-mean Student-t density, about 20 lines with no Gauss-Hermite step.
  - Add lot-cluster bootstrap SEs for building-weighted miss, coverage and lpd.
- **(c) Building- and lot-clustered SEs beside today's iid SE** in the paired PSIS-LOO (leaderboard.py:297 computes `d.std·√n` over rows) and in loo.py:305.
  - These are report-only. The tie tolerance stays unchanged until Ben decides.
  - Back-fill C against lines, elevfill, bigbed, areatime and nofloorslope.
- **(d) A 30-minute label figure.** Compute the row-weighted variance of C's neighbourhood term per draw (East Village is -13.2% against Chelsea) and the in-area miss that removing the labels implies.

Left out because each changes 0-1 decisions today: the A/A descriptive-null rule change, the autoselect flag, the same-target guard, the in-sample new-unit stand-in and the ledger restatement.

**Weakness it targets.**
- The new-building score is the board's only generalization number. It has no SE, no pairing and no per-row output, so effects of 0.1-0.3 pp cannot be called, and that is the size of every remaining candidate.
- Paired SEs treat rows as independent, but rows cluster within buildings. That overstates the precision for building-level families such as photo grades and amenity tiers.
- New-building coverage is too wide at 90.7/98.1. The leading suspect is the walk origin: a new building's walk is pinned at 0 at the panel's first knot (2010) unless `walk_anchor_data` is set (newbuilding.py:95-104, verified). Late rows would then carry about 15 years of walk variance.

**Prediction.**

| Measure | Prediction |
|---|---|
| Paired PSIS-LOO | n/a (no fit) |
| New-building miss and coverage | C reproduces 11.9% and 90.7/98.1, within 0.05 pp and 0.3 |
| 80% coverage, 2024-26 rows minus 2014-16 rows, within row bins | +4 to +5 pp (0 to +10) |
| First-knot origin, overall 80% coverage | 86-88.5 (82-90.5) |
| Clustered/iid SE ratio, building-level pairs | 1.4-1.5 (1.05-3.0) |
| C-era serving verdicts that change | 0 (0-1). Only bigbed can flip, because lines and elevfill pass the screen and are served as ties through screen_wins (autoselect.py:467-476) |
| Paired building-weighted lpd, lines vs C | +3 to +8 nats, lot-clustered SE 6-7 (3-13): a tie |
| In-area miss with labels removed, from (d) | 13.0-13.4% (inferred) |
| Descriptive share; new-unit coverage | Unchanged (26.1%; 67/89) |

**Cost.** Modal $0 on thelio, or about $0.65-0.80 if rescored on Modal instead. Oxylabs $0. Modeling 1-1.5 days, one reviewed PR and 3-6 h of thelio CPU.

**What counts as a miss.**
- The new code moves C's miss by more than 0.1 pp or its coverage by more than 0.3. That is a bug, and the action fails until it is fixed.
- The lot-clustered SE for lines vs C exceeds 15 nats, which means the score cannot resolve a 2% family.
- The year gap or the first-knot result lands outside the intervals above. These are recorded as prediction misses.
- A year gap under 2 pp together with a first-knot shift under 2 pp clears the walk origin. The over-width then lives in the slopes or the building scale.

**Why it ranks first.**
- Every later verdict in this plan reads its output. #2 needs the per-row residual. #3's gate and any photo fit need the clustered SEs. #4's coverage cannot be read until step 0 settles the walk origin.
- It also gates the only walk fit worth considering (see "Conditional follow-ons").
- It is free, and the tool is permanent.
- All three judges ranked it first.

**Expect it to fail?** No. P(all predictions hold) is about 0.6. The likeliest "failure" is a clustered/iid ratio under 1.2 (P about 0.2), and that would certify today's iid rule with evidence rather than assumption. While coverage stays over-wide, about half of any lpd gain is width rather than centre. So compare explanations on signed error or squared log error until step 0 has been read.

## 2. Leak-free explanation ceiling for data we already hold

**What it is.** The Modeling thread runs this free on thelio, 0.5-1 day after #1. It needs no PR and no autoselect change.

- Fit one lot-grouped LightGBM and one WLS. Each predicts two things:
  - C's per-row new-building residual, from #1's file;
  - each building's precision-weighted mean of C's per-row building part (newbuilding.py:216).
- Use only strictly as-of, rent-blind facts:
  - PLUTO as-of;
  - building means of the base, coded and desc-v1 finish flags, taken over strictly earlier ads;
  - elevfill, lines, hpd, stabilized share and lister;
  - predsize case a only.
- Run it with and without coordinates. Score in squared log error and in pp of board miss, with a lot-cluster bootstrap.
- The same run scores these as families on the static target: the desc-v1 finish words, #3's ever-coded amenity tier, predsize case a and the held families.
- **Correctness gate first:** with the old level target and random folds, the code must reproduce v1's hpd 1.4% and elevfill 2.4% within 0.3 pp.

Not built: the full v2 rebuild (three targets, block folds and the screen_wins wiring), per-fit pricing of the held queue, and the lines calibration test, whose 0.2 pp tolerance cannot fail.

**Weakness it targets.**
- No one knows whether facts already held could take meaningful error out of the building terms. That decides whether the next fit slots go to held data or to new data.
- Today's screen target is the 2010-anchored building level (explained.py:123-131, `levels = kept["building"]`, verified). It cannot see walks or slopes, so it would bias a photo screen toward a false null.
- `explained.building_means` averages over a building's later ads as well (explained.py:98-103). That leak would inflate a ceiling by 0.1-0.2 pp.

**Prediction.**

| Measure | Prediction |
|---|---|
| Paired PSIS-LOO; new-unit coverage | n/a. C's board is unchanged |
| Ceiling without coordinates, on the new-building miss | -0.3 to -0.35 pp (-0.1 to -0.75). P(at least 0.5 pp) 0.22-0.3; P(under 0.3 pp) 0.4-0.5 |
| Ceiling with coordinates | -0.6 to -0.8 pp (-0.3 to -1.4). The extra is location, so it is descriptive |
| Fall in the descriptive share implied if all of it were fitted | -0.7 to -0.9 pp. P(2 pp or more) 0.07-0.1 |
| Static-target shares, lot folds | elevfill about 2.2%, lines about 1.9%, hpd about 1.2%, predsize case a about 1.2%, finish words about 0.8% (0.1-2.5), amenity tier 1.5-2.5% |
| predsize case-a offset on unknown-size rows | -0.04 pp (0 to -0.15) |

**Decision rules, set now.**
- **0.5 pp or more, with a bootstrap lower bound above 0.3:** re-run it as a linear (WLS) ceiling on the top as-of columns, because LightGBM's interactions will not carry into C's linear fixed part. If the linear ceiling keeps 0.3 pp or more, propose one fixed-part feature-set fit (about $2.2) as its own action.
- **0.3-0.5 pp (the dead band):** no building-family fits from held data, and #3 goes ahead unchanged.
- **Under 0.3 pp:** no more building-family fits from held data in these 8 areas. The held queue is then struck with evidence.
- **predsize** gets a fit only if its case-a offset reaches 0.1 pp with an interval that excludes 0.

**Cost.** Modal $0. Oxylabs $0. Modeling 0.5-1 day.

**What counts as a miss.**
- The correctness gate fails.
- The ceiling without coordinates lands outside -0.1 to -0.75 pp.
- The all-row-means variant does not exceed the as-of ceiling. Treat that as a bug, and do not act on the ceiling.

**Why it ranks second.**
- It is the one free number that decides whether the stopping rule's 0.5 pp can be reached from held data, or only with new information.
- It builds the static target that #3's screen needs.
- It sits below #1 because it reads #1's per-row file.
- All three judges ranked it second.

**Expect it to fail?** Not as a measurement. The expected answer (P about 0.7) is that held data cannot reach 0.5 pp. That is still a decision: stop fitting building families from held data and move the effort to new data.

## 3. Photo quality screen

**What it is.** This is the photo arm only. Data improvements does the reads, and Modeling runs the screen.

**Step 0, free:**
- Count image URLs per building by row band and year.
- Count usable descriptions. This is expected to close the text arm, since only about 38% of singles have a description.
- Run the amenity-services check (2-4 h):
  - parse the services codes from the stored amenity JSON;
  - check whether a building's code set varies across ad dates, because a set that never varies is the signature of a 2026 snapshot;
  - build an ever-coded services tier to use as a control.
- Kill the arm if under 50% of 2014+ ads carry an image, or under 70% of buildings with 21+ rows have 2 or more image-bearing ads.

**Step 1, on one costed OK from Ben (LLM about $35-45, Oxylabs $0-4):**
- (a) Probe about 100 image URLs across 2014-2026 to confirm that old CDN keys still resolve.
- (b) Re-read the 680 pilot images on a rubric of finish 1-5, condition 1-4 and light 1-4, with two readers. Kill the arm if weighted kappa is under 0.5.
- (c) Grade a sample of 600 buildings with 21+ training rows:
  - stratified by PLUTO class family × area;
  - 2 ads from different units and years per building, 3 lead photos each, about 3,600 images;
  - a 20% second read.

**Screen:**
- Score building means on #2's static target, with lot folds and 200 permutations.
- Use the finish words, the amenity tier and doorman/elevator as controls.
- **Single gate:** a share of at least 5% and above null_95. The 5% bar is the one the 2026-10-12 review set.
- The original OR'd gates (a 150-small-building clause and an offset clause) are dropped, because they let false passes through to a paid full run.

**Only on a pass, with a second costed OK:**
- A full run matched to the screen: 2 ads per building, $200-260.
- As-of grades: the row's own ad first, then strictly earlier ads, as elevfill does.
- One fit of C on `nb8-nostuy-photoq-v1`, plus the new-building score.

**Weakness it targets.** About 20 of the 26.1% descriptive share is building terms that no named feature explains: building level 10.2, building over time 5.6 and building slopes 4.1. The alternatives look weak:
- Location looks saturated (19.5% of building variance and no held-out gain), though that was measured on NB3 only (side check 8).
- The held building families explain 1.2-2.4%.
- Size is capped near 0.1-0.2 pp.

Finish quality is the standard hedonic explanation, and it is the one missing.

**Prediction.**

| Measure | Prediction |
|---|---|
| Pilot weighted kappa | 0.6 (0.45-0.75) |
| r with C's building-plus-unit effect | 0.2 (0.05-0.35) |
| Amenity tier (control) share | 1.5-2.5% (0.3-5.5). P(5% or more) 0.1-0.15; P(snapshot signature) about 0.4 |
| Photo screen share | 3.5% (1-8%), SE about 1.7 pp near 5%. P(5% or more) about 0.3 |
| If fitted: paired PSIS-LOO | +40 (-20 to +120), building-clustered SE 25-40. P(clears 2 clustered SE) about 0.35 |
| If fitted: new-building miss | -0.15 pp (-0.4 to +0.05). The 1-5-row bin moves about -0.4 pp, which cannot be resolved |
| If fitted: new-building 80/95 coverage | Within 0.3 of 90.7/98.1 |
| If fitted: descriptive share | -0.4 pp (-0.9 to -0.1), at or below the 0.6-0.7 pp noise floor |
| If fitted: new-unit coverage | Unchanged (-1 to +1) |
| Unconditional (times P(pass)) | New-building miss about -0.04 pp; descriptive share about -0.1 pp |

**Cost.**
- To the screen verdict: LLM about $35-45; Oxylabs $0 if direct CDN fetch works, otherwise up to $4; Modal $0.
- On a pass: LLM $200-260 and Modal about $2.1-2.8 plus $0.13. If the feature is served, grading new ads costs about $80-250 a year.
- Effort: Data improvements 4-6 days, Modeling 0.5-1 day, 1.5-2 weeks elapsed.
- Approvals:
  - the costed OK (the 10-06 pilot OK does not cover a new re-read, docs/handoff/data-improvements.md:815);
  - a second OK for any full run;
  - the hold lifted for the fit.

**What counts as a miss.**
- The image-coverage kill fires, or the fetch path is dead for pre-2019 ads.
- Kappa is under 0.5.
- The screen share is under 5% or at or below null_95. Record this as a miss of "building levels are mostly finish quality".
- A share of 2-5% is recorded as ambiguous, not as a null. At kappa about 0.6, a true 8% reads near 5%.
- After a fit: the new-building miss falls by under 0.1 pp and PSIS-LOO is under 2 clustered SE.

**Why it ranks third.**
- It is the only candidate with a plausible path to moving building variance into a named feature a renter can read. That is Ben's explanatory-over-descriptive rule, and it is where the stopping rule sends the effort.
- It is the best information per dollar of any paid item, and it runs on Data improvements in parallel with Modeling.
- It is third, not first, because its screen needs #2's static target and any fit needs #1's clustered SEs.
- The robustness judge ranked the amenity check ahead of it as a separate action. Here that check is folded into step 0, because it is the control the photo screen needs.

**Open units question.** Two estimates disagree on how much a feature must explain to cut the miss by 0.5 pp. The readers said about 9% of building variance; the critics said 15-20%. That is a units mismatch: the whole building part against the level alone. The free oracle calibration (side check 3) settles it before the sample is read. If the critics' units hold, even a pass moves the miss about 0.15 pp, not 0.3.

**Expect it to fail?** Yes. P(screen pass) is about 0.25 (0.22-0.3 across judges). It is still worth running:
- About $40 tests the hypothesis that both 2026-10-12 reviews and the stopping rule rest on, before anyone spends $200-260 on full reads.
- A clear fail tells Ben to stop buying building-level explanation data for these 8 areas and to spend on contrast areas and size instead.
- A pass gives the model its first non-location explanation of building levels. It would enter through the fixed part, which is the only route to an unseen building's price.

## 4. Leave-East-Village-out refit

**What it is.**
- **Free first (Modeling, 1-2 h):**
  - C's in-sample new-building score restricted to East Village buildings, which is the baseline;
  - the signed error expected from C's EV label, written down beforehand (-13.2% against Chelsea, docs/model/newbuilding-2026-10-13.md:110).

  The label variance comes from #1(d).
- **Code (2-4 h):** `config/holdout/ev-lots-v1.tsv` listing every EV lot, and a `tune-holdout-ev-v1` rule beside `tune-holdout-lots-v1` (data.py:877-878).
- **Fit, on Ben's go:**
  - C's design on `nb7-nostuy-v1`, with that rule and the row split.
  - `nb7-nostuy-v1` is `nb8-nostuy-v1` without the EV indicator (features.py:4585 vs :4686).
  - The dataset stays NB8, because the dataset path is global (data.py:23).
- **Score it** with the existing `python -m rentfrontier.newbuilding --holdout` (score_holdout, newbuilding.py:400-483).
  - Report for EV buildings: the miss, the signed median error, the miss after removing that one offset, and 80/95 coverage by row bin and PLUTO class.
  - Compare each against the in-sample baseline, with #1's clustered SE.
- It is a tune rule, so it is never served or paired.

**Weakness it targets.**
- Nothing on the board measures whether the explanations carry to an area the model has not seen.
- The new-building score keeps the labels and the β fixed, so a label crutch can lower the miss without anyone seeing it.
- Labels are about 3.4 pp of the descriptive share (inferred), and EV's label alone is -13.2%.

**Prediction** (inferred, from the goal judge's miss-from-bias arithmetic with σ about 0.177).

| Measure | Prediction |
|---|---|
| In-area miss with labels removed (from #1d) | 13.0-13.4% |
| EV signed median error | -10% (-14% to -5%). Without its label the model overprices EV |
| Unadjusted EV miss vs the in-sample EV baseline | +2.5 pp (+1 to +4) |
| **Offset-adjusted gap** (the informative number) | +0.5 pp (-0.3 to +1.5), clustered SE about 0.4-0.6 pp |
| EV 80% coverage vs the baseline | About 5 pp lower (2-12). Read only after #1's step 0 |
| Paired PSIS-LOO | n/a (different rows; tune rule) |
| Descriptive share | Reported for the refit, not compared |
| New-unit coverage | n/a |

**Decision rules.**
- **Offset-adjusted gap within 1 SE:** β transfers. The only part that does not transfer is one area offset. Its size goes into the intervals for Midtown West and Brooklyn.
- **Gap of 2 SE or more:** the features are area-specific. Get contrast data before any more feature fits in these 8 areas, and stratify #3's sample to cover walk-up stock.
- **|signed error| of 6% or less:** the features carry most of the EV discount. That makes a label-free C worth a fit.

**Cost.** Modal about $1.3-2.1 plus $0.13 for the score. About $2.5 is expected, allowing a 20-30% chance of an R-hat rerun. Oxylabs $0. Modeling about 0.5 day. It needs Ben's go under the hold.

**What counts as a miss.**
- The offset-adjusted gap lands outside -0.3 to +1.5 pp.
- The signed error lands outside -14% to -5%.
- The gate fails after one retry with more draws.

**Why it ranks fourth.**
- It is the only test of Ben's generalization and no-crutch principles that one fit on held data can give now.
- It beats the proposed Midtown West external score, which:
  - lands in 2-4 weeks;
  - needs 3-5 engineering days;
  - is confounded by a new collection path;
  - has a building-clustered SE (about 1-1.4 pp) larger than its own 0.3-0.5 pp decision bands.
- It sits below #1-#3 because it measures how far the explanations reach rather than adding any.

**Dissent.** The robustness judge left this out, for three reasons:
- C's -13.2% label already prices most of the answer.
- The refit drops 31% of training rows (East Village is 66,483 of 215,156).
- East Village is walk-up heavy and the least size-stated area (14%), which mixes transfer with building mix.

I kept it because the offset-adjusted gap (whether β transfers) does not follow from the label arithmetic. Report by class to separate out the mix. If Ben prefers a test closer to Midtown West's scale, hold out Gramercy Park instead, for about 1 h more code.

**Expect it to fail?** Not as a measurement. The expected result is "β transfers apart from one area offset". That gives the first measured interval for an unseen area before Midtown West and Brooklyn are added.

## 5. GraphQL size check

**What it is.** Data collection runs this free on thelio, in 2-3 h, beside the Midtown West crawl.

- (1) Check whether archived modal inventory rows already render a size cell (src/streeteasy_archive/extract.py:211-235). If they do, the question is answered with no GETs.
- (2) Count livingAreaSize > 0 against 0 or null in the 30-building pilot digests (data/probes/no-render-20261013/pilot/) and the Midtown West history bodies.
  - Split the count by condo/co-op vs rental.
  - The Caroline is the decisive rental tower.
- (3) Same-unit consistency: compare the digest size on ads whose own page states none with that unit's stated sizes.

**Gate:** at least 10% of unstated ads gain a size within 5% of the same unit's stated sizes.

**Only then, on Ben's typed go:**
- about 226 GETs;
- a dated external table;
- `nb8-nostuy-gqlsize-v1`, which uses the digest size only where the row's own ad has none;
- one fit of C plus the score.

**Weakness it targets.** Size is unknown on about 63% of C's rows. Both 2026-10-12 reviews called size the biggest data lever. Per-building size slopes carry what the missing sizes do not.

**Prediction.**

| Measure | Prediction |
|---|---|
| P(the size leg survives the check) | 0.08-0.12. The Caroline is nonzero on under 5% of digests (P 0.85-0.9) |
| If real and fitted: paired PSIS-LOO | +150 to +250 (-30 to +600) |
| If fitted: new-building miss | -0.10 pp (-0.4 to +0.05); about -0.15 pp on newly sized rows |
| If fitted: new-building coverage | 80% coverage about 0.5 pp wider, through the size-slope term |
| If fitted: descriptive share | -0.3 to -0.5 pp (-1.5 to +0.4) |
| If fitted: new-unit coverage | Unchanged |
| Unconditional | About 0 on every board number |

**Cost.**
- The check: $0 Modal, $0 Oxylabs, 2-3 h.
- If the sizes are real: Oxylabs $0.25-0.6 (about $6 more if building ids must be fetched), Modal about $2.2 plus $0.13, and 1.5-2 engineering days.
- Expected: Oxylabs about $0.05 and Modal about $0.3.

**What counts as a miss.**
- The digest mirrors the page field. This is the expected outcome, and it is recorded as such.
- After a fit: the newly sized rows' new-building miss falls by under 0.1 pp and PSIS-LOO is under 2 clustered SE, or the gate fails.

**Why it ranks fifth.**
- The value and robustness judges both put it fifth.
- It is free, takes a few hours on a thread that is not the bottleneck, and settles the last cheap size hypothesis.
- It sits below #4 because P(real) is about 0.1 and a success moves the miss only about 0.1 pp.
- It ranks above three other contenders:
  - the time split, which measures new-unit width rather than explanation and would, with P about 0.7, only confirm the known defect;
  - the gated walk fit, a model term that #1 gates anyway;
  - a standalone amenity fit, which is folded into #3.

**Expect it to fail?** Yes, P(pass) is about 0.1. It is still worth running:
- It costs two hours and no money.
- A pass would be the biggest explanatory data win on record. The unitattrs analogue gained +653 ± 53 when unknown size fell from 65% to 52% of rows (docs/research-plan.md:678-680).
- A fail retires the hope, and it records how the digest treats 0 and null before more GraphQL collection relies on it.

---

## Conditional follow-ons

These are not ranked. Each is its own fit, run one at a time, after the hold lifts.

- **As-of feature-set fit**, about $2.2. Only if #2's linear ceiling keeps 0.3 pp or more, after LightGBM shows 0.5 pp or more.
- **Walk fit**, about $2.5-3.
  - **Gate:** only if #1's step 0 shows a within-bin year gap of 3 pp or more that tracks calendar time rather than bedroom or bath.
  - **Form:**
    - either a fixed-rho AR(1) at step 0's bootstrapped half-life;
    - or a Normal walk anchored at each building's first knot.

    Gibbs refuses anchors today (gibbs.py:344-363), so the anchored form needs 1-1.5 days of code. The anchored-walk gate failures on record were Student-t walks, not Normal ones (docs/research-plan.md:741-760).
  - **Prediction:**
    - PSIS-LOO +25 (-150 to +300).
    - New-building miss 0.0 pp (±0.1), which is fixed by construction.
    - 80/95 coverage moves from 90.7/98.1 to 88.5/97.6 (85.5-90.5 / 96.5-98.2), and the 1-5-row bin from 77.8 to about 76.
    - Descriptive share -0.1 to -0.2 pp. This is a zero-sum shift: building over time falls from 5.6 to about 4.3 and building level rises by about the same.
    - New-unit coverage unchanged.
  - **Expected to fail more often than not.** P(reaching the fit) is about 0.55, and P(a coverage gain of 1.5 pp or more, given the fit) about 0.6, so about 0.33 overall. When the gate passes it is still worth running, because fixing the origin makes #1's lpd a clean explanation score.
- **gqlsize fit** if #5 passes. **photoq fit** if #3 passes.
- **Later:**
  - A Midtown West holdout-lots refit on NB9 (about $2), before any NB9 fit, through the same `--holdout` scorer.
  - The time split and 2i back to back, on a cutoff of about 2026-04-01, once Ben puts new-unit honesty in scope.
    - Any cutoff on or before 2026-01-01 leaves C's 2026 noise cells prior-only (model.py:258-282).
    - Predicted new-unit coverage on that cutoff is 69-71/90.

## Free side checks

These are unranked and suit the Modeling and Data threads under the standing free-check approval. The completeness critic raised all of them, and none went through the adversarial critics.

1. **Coefficient stability.**
   - Compare every coefficient and contrast in C against the held-out-lots refit, the latest-ask fit, lines and nofloorslope.
   - Express each move in C's posterior SDs, against the about 0.33 SD that a 10% building subsample predicts.
   - docs/project-intent.md:67-71 makes this the primary validation, and nothing in the plan measures it.
   - In the latest-ask fit, on the same rows, 82 of 223 parameters moved by more than 1 SD (newbuilding-2026-10-13.md:152-160).
2. **Repoint the outcomes file.**
   - `listing_outcomes.OUTCOMES_FILE` (listing_outcomes.py:28-31) and `RULE_SOURCES['tune-finalask-v1']` (data.py:1050-1052) still name `20261008-afb3446`. The latest-ask fit uses `20261013-57c2a78`.
   - Repoint both.
   - Add a note retracting the final-ask readings: the East Village swing, the 21.6% descriptive share and the 58 of 115 coefficient moves.
3. **Oracle units calibration.**
   - On C's draws, add s × each building's building part to `rest`, for s = 0.05, 0.1 and 0.2.
   - Recompute the new-building miss, then restate every screen share in the same units.
   - This settles the 9% vs 15-20% question that sets #3's gate.
4. **Count place terms as labels.** `variance.py` counts only `('neighbourhood', 'area_market_curve')` as labels (:79-82). NTA, bump or surface terms would therefore lower the descriptive share without explaining anything. Fix this before any label-free or location test is read.
5. **Crutch guard in autoselect before it resumes.**
   - `BLOCKED` matches only feature-set names (autoselect.py:99-113).
   - A model term that wins PSIS-LOO clearly (such as the areatime rerun at +401) would be served with no descriptive check.
6. **Counts behind three rejected data fixes.**
   - Floor: `row_floor` drops label floors wherever PLUTO numfloors is missing, because the comparison against NaN is false (features.py:2716-2723). An unknown floor is the costliest missing field: singles' residual SD is 22.9% with floor unknown against 15.5% with it known.
   - PLUTO v3: how many of its changes are real rather than re-estimates. It changed features on 27,564 rows and was served unpaired.
   - FARE Act (2025-06-11) and HSTPA (2019-06-14): the residual shift by lister type and no_fee. The code handles neither.
7. **unit-labels-v10.**
   - It won its exploration pair at +49.2 ± 21.9, its full fit was lost in the queue resets, and it is not in DATA_RULES.
   - First check whether v15 already joins its 126 groups.
8. **Re-score location saturation on NB8.** All the "location is saturated" evidence comes from NB3 (three areas, 2,907 buildings). NB8 adds East Village, NoMad, Flatiron, Gramercy Park and Stuy Town.

## Dropped, and why

- **Concession rows with a months-free term: refuted.**
  - Under the gross-ask target the months-free term absorbs the conceding rows, so the walks and the 2021 hump do not move.
  - months_free comes from 2026 end-state captures, which is a leak.
  - The only measured analogue (text:concession, about -1%) contradicts the sign of the prior.
  - Target semantics are Ben's call.
- **West Village NTA step: refuted.** It is a label term by construction, so it cannot move the new-building miss or the descriptive share. The decision it was meant to settle (dropping the areatime rerun) is free now.
- **Family bedroom curve.** In elevator and condo stock 2BR barely loads on it, which contradicts its fixed loadings. It is not nested in C, it changes three things in one fit, and no explanation metric moves.
- **Midtown West external score, as specified.** Its SEs exceed its own decision bands, it needs 3-5 engineering days and it lands in 2-4 weeks. #4 and a later NB9 holdout refit replace it.
- **Time split now.** Deferred, not dropped. It measures width rather than explanation, and its decisions need a unit-width fit that no top action proposes. See decision 6.
- **Sampled-rho AR(1) walk.** It needs 4-6 days of Gibbs code and carries about a 0.4 first-try gate risk. The fixed-rho or anchored form under "Conditional follow-ons" replaces it.
- **Amenity tier as its own fit.** P(clearing 5%) is about 0.1. In the 2026-09-18 Chelsea ablation, coded doorman values added -0.06 pp, and the codes probably come from 2026 snapshots. It survives as #3's control.
- **The full explanation-screen v2 and the extras of the new-building scoring proposal.** They flip 0-1 verdicts today and cost 2.5-4 Modeling days.
- **The held queue.** See decision 2.
- **Label-free C (locnolabel).** This was not dropped on merit. It is Ben's values call (see the decisions above), and it is best read after #4 and side check 4.

## Sequencing

- **Day 0, Ben:** decisions 1-3.
- **Days 1-2, free and in parallel:**
  - Modeling: #1's step 0, then the per-row file and clustered SEs, then the label figure. Also #4's EV baseline, holdout TSV and rule.
  - Data improvements: #3's step 0 counts and the amenity tier.
  - Data collection: #5.
- **Days 2-4:**
  - #2 on #1's per-row file.
  - On the OK, #3's URL probe and pilot re-read.
- **Fits, one at a time after the hold lifts:**
  - #4's EV refit comes first. Its coverage is read after step 0.
  - Then any gated follow-ons, in this order: the walk fit, gqlsize, the as-of feature set, then photoq after a pass and the full run.
- **Weeks 2-3:** #3's sample read and screen on #2's target, with a verdict around days 10-14.

## How this plan was made

1. **Readers.** Four readers digested the repo at cb52b52 (model, scoring, ledger, data and handoff docs) and the two 2026-10-12 reviews.
2. **Proposers.** Six proposers, each with a different lens (explanation, uncertainty, data, parsimony, measurement, outside view), drafted 24 candidates, which were merged into 11.
3. **Critics.** Two adversarial critics took each candidate, one on evidence and one on cost and feasibility. They checked its claims against the code. All 11 came back weakened, and 2 were refuted.
4. **Judges.** Three judges ranked the candidates under different priorities: Ben's goal, value per dollar and per week, and robustness. A completeness critic then looked for gaps.

All three judges put #1 first and #2 second, and all three included the photo screen. The robustness judge put the free amenity check ahead of the photo screen; here it is folded in.

Slots 4 and 5 were split:

| Judge | Slot 4 | Slot 5 |
|---|---|---|
| Ben's goal | East Village refit | Time split |
| Value per dollar and per week | Gated walk fit | Size check |
| Robustness | Size check (its slot 5; its slot 3 was the amenity check) | |

I chose the East Village refit for #4 (with the robustness judge's dissent above) and the size check for #5. The walk fit became a gated follow-on, and the time split a decision for Ben.

The candidate write-ups, critiques and judge rankings are in [next-actions-2026-10-13-workings/](next-actions-2026-10-13-workings/).
