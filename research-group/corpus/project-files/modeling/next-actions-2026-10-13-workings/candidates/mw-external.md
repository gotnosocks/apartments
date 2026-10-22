# mw-external — Midtown West as an unseen-area test of C, with a labels-redrawn (features-only) new-building rung, scored before any Midtown West fit

**kind:** measurement change (code plus free scoring; rides the running crawl)

**what:** (1) Modeling (0.5-1 day): a newbuilding.py rung, 'new building, features only'. Per draw, the place terms (variance.LABELS plus any NTA or location-bump group) are replaced by their row-weighted mean, and the between-area variance is added. Back-fill it free on C, areatime and lines within the 8 areas. (2) `python -m rentfrontier.newbuilding --external <dataset> <run>`, reusing score_holdout's appended-buildings path (newbuilding.py:400-460). Validate it by reproducing the held-out-lots refit's 12.20% / 91.2 / 98.1 within 0.05 pp. (3) Data collection finishes the Midtown West crawl (#717). Data improvements builds its cohort and the nb8-nostuy-v1 columns (registry, MapPLUTO releases, footprints, GTFS lines, elevfill, quarantine), which any NB9 needs anyway. Exclude buildings already in NB8 (One Hudson Yards and others). (4) Score C's kept draws on Midtown West buildings on both rungs (the standard rung prices them at the Chelsea reference), then lines and nofloorslope on the same rows. Report miss, signed median error, 80/95 coverage and PIT by row band, sub-area (Hell's Kitchen, Hudson Yards, Midtown West core) and year, plus the miss after removing one leave-one-building-out area offset. Pre-register in predictions-newbuilding. Rule: no fit that includes Midtown West before this score.

**weakness:** Every explanation number is in-sample to 8 adjacent areas. The new-building score keeps the labels, the area curves and a fixed part tuned on these same buildings, so a label crutch can lower the miss and nothing sees it: areatime gained +401 with the miss unchanged at 11.9%. Several subway-line premiums are geography proxies. Nothing measures transfer to an unseen area, though the goal is a model that generalizes.

**mechanism:** C's fixed part is what prices a new building. Redrawing the place terms asks 'price this building from its features and the market alone', which measures how much accuracy depends on being told the neighbourhood. Midtown West buildings carry no label, so they are the real-world version. Explanatory features should transfer and geography proxies should not. If the features-only rung predicts the Midtown West result, it is validated as the board's explanation score.

**evidence:**
- newbuilding.py:216-230: rest = total - building - unit keeps the labels and area curves fixed. variance.py:81: LABELS = ('neighbourhood', 'area_market_curve'). features.py:4686-4691: Flatiron, Gramercy, NoMad and East Village are measured against Chelsea.
- areatime +401 +- 37 with the new-building miss at 11.9% (research-plan.md:20; newbuilding-2026-10-13.md:43); summary.py:416-418 refuses area_time runs.
- Within NB8, the 1, A/C/E and 4/5/6 premiums are 'all geography proxies' (data-improvements.md:780-781); Midtown West sits on the A/C/E, the 1 and the 7.
- The crawl was registered Oct 13 with --graphql-inventory --graphql-unit-paths for StreetEasy areas 124, 146 and 152 (commit cb52b52, #717); 241 buildings were in scope by 16:30Z. Unit and ad pages are still fetched, so the rows carry text and amenities (data-collection.md:14).
- research-plan.md:866: One Hudson Yards and other new towers are already in the data.
- The held-out-lots validation stayed inside NB8: 12.20% vs 12.09% (newbuilding-2026-10-13.md:73-74). Location features are retested when a neighbourhood is added (feature-tests.md:6). Brooklyn restart: about 76k pages, about $84-94 (data-collection.md:41-55).

**prediction:**
- psis_loo: n/a: no fit.
- new_building: In-area features-only rung on C: 12.9% (12.3-14.0) vs 11.9%; 89/97.5 (86-92 / 96.5-98.5); East Village rows worst (+3 to +5 pp). areatime vs C on this rung: 0.0 pp (-0.1 to +0.2); lines -0.05 (-0.2 to +0.1). Midtown West, standard rung, buildings absent from NB8: miss 13.0% (80% 11.6-17); 80/95 coverage 88/97 (72-92 / 89-98.5); signed error +2% (-5 to +10). 1-5-row Midtown West buildings 18% (14-23). After one area offset 12.4% (11.2-13.6). The features-only rung lands within 0.5 pp of the standard rung. lines vs C on Midtown West +0.15 pp (-0.4 to +0.6); nofloorslope +-0.1.
- new_unit: n/a
- descriptive_share: n/a (no fit). Labels are about 3.4 of C's 26.1 pp (inferred).
- other: Decisions: an in-area features-only miss of 13.5% or more -> adopt the rung as the board's explanation score and test a label-free C; 12.4% or less -> labels are not the crutch, so target building terms. Midtown West 80% coverage of 88 or less -> judge any narrowing (walk-ar1) on Midtown West too; 90 or more -> narrowing is safe. An offset-adjusted Midtown West miss of 12.9% or less -> Brooklyn becomes the location-contrast test; 13.4% or more -> quality data before new areas. lines worse on Midtown West by 0.3 pp or more -> do not serve lines on PSIS-LOO alone. areatime earns no features-only credit (P about 0.85).

**cost:** Modal $0 on thelio ($0.13-0.26 on Modal). Oxylabs $0 beyond the running, approved crawl (whose own cost is undocumented). Other $0. Modeling 1-1.5 days; Data improvements about 2 days for the Midtown West build (needed for NB9 anyway). About 1 week elapsed, bounded by the crawl. No new approvals.

**free_precheck:** Back-fill the features-only rung on C first: if its in-area miss is under 12.3%, keep the rung off the board and run only the Midtown West score. Validate --external on the held-out-lots refit's buildings. When the crawl ends, count Midtown West rows and buildings absent from NB8 that pass the cohort rules, the quarantine and a lot match. Postpone if there are fewer than 3,000 rows or 100-150 buildings.

**miss_criteria:** C's in-area features-only miss falls outside 12.3-14.0%; the Midtown West standard-rung miss falls outside 11.6-17%, or its 80% coverage outside 72-92; lines vs C falls outside -0.4 to +0.6 pp; Midtown West is fitted before it is scored; or there are fewer than 100 new Midtown West buildings or 3,000 rows.

**p_success:** 0.45

**expected_to_fail_reason:** Timing and yield risk. The crawl's cost and yield are undocumented and the build takes about 2 days. Some Hudson Yards towers are already in NB8, which leaves a smaller, Hell's Kitchen-heavy sample. A large area offset may dominate the miss, and the biases of Hell's Kitchen (cheaper) and Hudson Yards (luxury) may cancel. With seven label values, the between-area population is a convention until Midtown West validates it.

**worth_it_anyway:** Even if Midtown West is late, the in-area rung quantifies now how much of C's 11.9% rests on labels. That is the number Ben's no-crutch rule lacks, and it settles areatime on explanation. Midtown West then becomes the external yardstick for every later explanatory fit, and it measures what a new area buys before Brooklyn's $84-94.

**rank_argument:** It is the only generalization test in the plan. It is nearly free because the crawl and the dataset are being paid for anyway. It gates the largest pending data spend (Brooklyn) and decides areatime and any NTA step on explanation. It ranks below the candidates above because it measures rather than adds explanation and is bounded by the crawl.

**depends_on:** The Midtown West crawl (#717) and Data improvements' build; nb-lpd-clustered for the pointwise lpd and pairing; scoring before the first fit that includes Midtown West. A separate small fix: summary.py should accept area_time runs (:416-418) so areatime gets a descriptive share. Brooklyn's go waits on this result.

**proposed_by:** ['data', 'measurement']

**merged_from:** ['midtown-west-external-test', 'features-only-mw']

**conflicts:** Standard-rung Midtown West miss: 13.0% (11.6-15.5; data) vs 15% (12.5-19; measurement); kept 13.0 and widened the upper end to 17. Coverage: 88/97.3 (data) vs 83/95 (measurement); kept 88/97 and widened the lower end. The data lens scored only the standard rung; the measurement lens added the features-only rung and made it depend on nb-lpd. Kept the measurement lens's p of 0.45 over the data lens's 0.55.
