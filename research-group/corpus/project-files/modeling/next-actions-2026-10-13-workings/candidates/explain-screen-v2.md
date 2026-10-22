# explain-screen-v2 — Explanation screen v2: score candidate facts in points of new-building miss against the whole static building part, with lot and block folds and a ceiling for data already held

**kind:** measurement change

**what:** Modeling thread, free on thelio, one reviewed PR of about 1.5 days. (1) Reuse nb-lpd-clustered's per-row new-building file, with the 10/90/2.5/97.5 quantiles added. (2) explained.py gets a 'building part' target. Per building, it is the posterior mean of level + walk at each row's knot + bedroom premium + slopes x, averaged over the building's rows and weighted by 1/(posterior var + tau^2). It replaces the 2010-anchored level (explained.py:123-131). Slope and dynamic (walk since first knot) targets are added. (3) Folds grouped by tax lot and by 400 m block instead of random buildings (:85); 200 permutations instead of 50 (:44). (4) An offset rescore: fit each family to the per-row new-building residual with lot-grouped CV (WLS and LightGBM), add the out-of-fold prediction to the median, and report the change in the board miss (pp) and in 80/95 coverage with a lot-cluster bootstrap interval. (5) A ceiling family: every rent-blind as-of fact on the frame (PLUTO fields; building means of the base, coded and text flags; stabilized share; hpd, 311, retail, trees, crime, lines, elevfill, petsfill, predsize fills, lister kind), fitted by LightGBM with and without coordinates. Run on C for the 9 held families, the attrs-v1 finish words and the ceiling. Calibrate on the realized lines fit (306d7299), elevfill and bigbed. autoselect.screen_wins reads the v2 record once Ben agrees.

**weakness:** The screen that decides building families sees only the posterior-mean 2010-anchored level (10.2% of variance). It misses the walk (5.6%) and the slopes (4.1%), which the new-building score also redraws. Random building folds leak smooth spatial families. Its share needs square-root arithmetic before it says anything about the 11.9% board miss. Nine held fits (about $15-20, about 4 limiter days) wait with no estimate of what they would do to the new-building miss.

**mechanism:** The new-building median is the fixed part (rest = total - building - unit, newbuilding.py:230). So the right free question is: if this fact were in the fixed part, how far would the board miss fall? A lot-grouped CV regression of the per-row residual answers that directly in pp. The static target counts the full premium of late entrants, which the 2010 anchor splits between level and walk. Block folds stop neighbours from leaking spatial families. The ceiling says whether any combination of facts already held could reach the stopping rule's 0.5 pp.

**evidence:**
- explained.py:123-131: the target is kept['building'] (level only); :85 uses random building folds; :43-44 uses 5 folds and 50 permutations.
- Spatial leakage: the location surface scores R^2 0.758 on building folds against 0.54 on 400 m block folds (research-backlog.md:370).
- C's shares: building 10.2, building over time 5.6, slopes 4.1 (newbuilding-2026-10-13.md:53-61); the screen covers about half of the 19.9% held in building terms (inferred).
- Late entrants: level variance about 0.0145 vs walk variance 0.016-0.020 at the mean knot (reader finding 1); fitted step RMS 0.44% per half-year before the first row (research-backlog.md:306-314).
- C-era screen results: hpd 0.014 vs null_95 -0.001 (test_autoselect.py:574); crime -0.0004 (:586); elevfill 2.4%, lines 2.1% (prior-review-iteration-worth-it:25).
- Realized new-building misses for calibration: C 11.9, areatime 11.9, lines 12.0, nofloorslope 12.0 (newbuilding-2026-10-13.md:23, :41-45). The score takes about 1,120 s on thelio; LightGBM already runs there (size-predictability-2026-10-12.md:5-7).
- Sizing: about 9% of building variance per 0.5 pp (reader finding 8), closer to 14% of the static effect (inferred).

**prediction:**
- psis_loo: n/a: no fit; C's PSIS-LOO is unchanged.
- new_building: C's board number is unchanged (11.9%, 90.7/98.1). Offset rescores on C: each held family between 0 and -0.12 pp, median -0.03 (lines -0.05, elevfill -0.06, hpd -0.04, lister -0.03, noise -0.02; retail, trees, crime and petsfill 0.00 +- 0.02). predsize fills: -0.08 pp on all rows, -0.12 on unknown-size rows. Ceiling without coordinates: -0.4 pp (80% -0.15 to -0.8); with coordinates -0.8 pp (-0.45 to -1.3), where the extra is location and so descriptive. The lines offset lands within 0.2 pp of the realized lines change.
- new_unit: n/a
- descriptive_share: C is unchanged at 26.1%. The no-coordinate ceiling implies -1.0 pp (80% -0.4 to -2.0), probably short of the stopping rule's -2 pp.
- other: v2 static-target shares on C with lot folds: elevfill 2.3% (1.2-3.5); lines 2.0% on lot folds and 1.2% (0.4-2.2) on block folds; hpd 1.2% (0.4-2.0); predsize fills 1.5% (0.3-4); attrs-v1 1.0% (0.2-3); crime and trees at or below null_95. On areatime, the dynamic target's variance is 10-30% below C's. Decisions it changes: held families with an offset weaker than -0.05 pp and no v2 pass leave the queue (crime, trees, retail, petsfill, probably noise; saves about $9-11 and 2-3 limiter days). A ceiling under 0.3 pp -> stop building-family fits from existing data and spend on new information. A ceiling of 0.5 pp or more -> its top interactions define one fixed-part feature set.

**cost:** Modal $0 (thelio, standing free-check approval); Oxylabs $0; other $0. Effort: Modeling, about 1.5 days of code plus a reviewed PR, and 2-4 h of thelio compute per run. No new approvals beyond Ben's nod for screen_wins to read v2.

**free_precheck:** It is itself free. Correctness gate: with the level-only target and random folds, v2 must reproduce v1's hpd 1.4% and elevfill 2.4% within +-0.3 pp.

**miss_criteria:** Any of: the lines offset differs from the realized lines change by more than 0.2 pp (the tool is uncalibrated); the no-coordinate ceiling falls outside -0.15 to -0.8 pp; more than two held families show an offset of -0.15 pp or larger.

**p_success:** 0.5

**expected_to_fail_reason:** About even odds. An offset holds C's other terms fixed, while a refit re-estimates them together, so it may be off by 0.1-0.2 pp against lines, the one realized family. How much nonlinear PLUTO and ad-fact structure C's linear fixed part misses is unknown (4-16% of the static effect).

**worth_it_anyway:** It puts every future building or unit fact in the board's own units at no Modal cost. Even if the offset is biased, the lot-fold, whole-building-part screen fixes two known blind spots: walks and slopes are invisible to it today, and random folds leak spatial families. The ceiling settles whether the stopping rule's 0.5 pp can be reached from data already held, which is Ben's next decision.

**rank_argument:** Free, about a day and a half, and it prices the 9 held fits before they spend $15-20. It says whether existing data or new information (quality-reads) is the route, and it gives the quality and amenity screens their target. It replaces the square-root guesswork behind every building-family prediction.

**depends_on:** Nothing strictly. Shares the per-row file with nb-lpd-clustered. Needs the draws of C, lines, areatime and nofloorslope on thelio.

**proposed_by:** ['explanation']

**merged_from:** ['explain-screen-v2']

**conflicts:** The measurement lens rejected 'explained share v2' (lot or spatial folds, 200 permutations, new target): few verdicts would flip, and the post-fit new-building lpd has more power. I kept it because this version's pre-fit offset rescore (pp of board miss) and ceiling are new, and that objection does not cover them. The data lens (photo screen step 4) and the outside view (amenity tier) independently asked for the same static or time-averaged building target and lot folds.
