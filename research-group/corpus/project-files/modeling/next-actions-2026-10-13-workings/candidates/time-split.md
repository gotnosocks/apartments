# time-split — Time-split refit of C: as-of new-unit, seen-unit-forward and new-building coverage

**kind:** measurement change (one Modal fit; free row count first)

**what:** Modeling thread, about 1 day of code, then one fit on Ben's go. splits.py gains split 'time' (rows priced on or after T are held out), drawn after the rules. Post-T rows of buildings with no pre-T rows stay out of training and are scored by newbuilding's --holdout path (:400-482); today data.py:1195-1198 would move them into training, leaking post-T market data. summary.SPLITS (:83, :406-418) accepts 'time', and calibration.py gets a horizon-quarter breakdown. leaderboard.new_unit_coverage (:220-238) and the site's never-seen figure (website.md:7-8) read the time-split run. Queue: `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope nb8-nostuy-v1 --split time`, plus the $0.13 new-building holdout score.

**weakness:** The board and the site publish 67/89 new-unit coverage from 964 row-split by-product rows: units whose only training row a later rule removed. The framework requires a time-split refit (reader finding 4). No time split exists (splits.py:89-94), summary refuses other splits, and the latest split has no new units by construction. Several fixes wait for a yardstick: the two-component unit prior (2i), lister's +0.02, and the site's ~1.2x multiplier. No fit tests forward calibration of the trend and walks.

**mechanism:** An as-of split prices each post-cutoff ad with earlier data only, which is the deployment case. Truly new units are a natural mix of units that will relist and units that never return. Coverage on them tests the unit prior plus forward extrapolation of the trend, walks and year noise. Periods already span the whole frame (model.py:452), so post-T steps come from their priors. Coverage by horizon separates width errors from trend drift. The same fit gives a small genuine forward check of new buildings.

**evidence:**
- splits.py:89-94 has rows, units, latest and all; summary.py:83 SPLITS = ('rows', 'all'), refused at :406-418; calibration.py:19-23 already expects a time-split summary.
- data.py:1195-1198: held-out rows of unseen buildings move into training.
- leaderboard.py:220-238 and website.md:7-8: the 67/89 figure comes from the newest rows-split run ('row split, not a time-split').
- NB5-era held-out first listings: never relisted 0.619/0.869 (472 rows); relisted later 0.778/0.939 (3,487 rows); all 0.759/0.931 (research-backlog.md:1094-1100). Units with no training rows 0.63 at 80% (:995). 'An honest as-of new-unit coverage needs a time-split refit' (:1107).
- An earlier time split without a refit had only 44 recent first listings, at 0.705/0.909 (review-2026-10-08.md:232). The site multiplier is to come from the time split (:228-230, :316).
- 2026 holds 12,709 rows and first listings are 25% of 2026 rows (size-predictability-2026-10-12.md:136-137; research-backlog.md:38).
- Refit costs: holdout $1.61, latest-ask $2.05; summary timeouts have cost about $0.80 (brief; digest-model-measurement section 8). The units split refuses to run until it is drawn after the rules (run.py:360-368).

**prediction:**
- psis_loo: n/a: different training rows (shared_rows refuses the pair), and nothing is served from this fit.
- new_building: As-of new buildings (about 100-300 buildings, 150-4,000 rows depending on T): miss 13.5% (80% 10-17), 80/95 coverage 88/97 (80-95 / 93-98.5). The fit's in-sample new-building score: 11.9% (11.7-12.2), 80% coverage 90.6 (90-91.3). C's board numbers are unchanged.
- new_unit: As-of new units in seen buildings (about 2,000-9,000 rows, by T): 80/95 coverage 68/89 (80% 62-80 / 85-95); median miss 8.5% (7-10.5). Seen units forward: 77/94 (73-80 / 91.5-95.5), about 1 pp worse per quarter of horizon.
- descriptive_share: 26.0% (25.3-26.8) on pre-T rows; reported, not compared with C.
- other: Decisions: new-unit 80% coverage under 72-74 -> publish it, and run 2i and lister's coverage leg on this split, paired against this fit. 75/93 or better -> retire the new-unit defect, correct the site's 67/89, and use no 1.2x multiplier. Seen-unit forward 80% coverage under 74 -> a forward-variance problem the row split cannot show. nb-lpd-clustered's free stand-in agrees with the first post-T quarter within 3 pp (P 0.65).

**cost:** Modal $1.6-2.6 (fit + PSIS-LOO + summary + calibration) + $0.13 holdout score. Oxylabs $0; other $0. Modeling: about 1 day of code, tests and a reviewed PR; 2-3 days elapsed. Ben's go for the queue slot.

**free_precheck:** Count post-T rows by kind (seen unit / new unit in a seen building / new building) on the current rules for T = 2025-07-01, 2026-01-01 and 2026-04-01 (free). Use the latest T with at least 2,000 new-unit rows. If even 2025-07-01 gives fewer than 1,000, fall back to a units split drawn after the rules (a summary change, not as-of).

**miss_criteria:** A prediction miss if new-unit coverage falls outside 62-80 at 80% or outside 85-95 at 95%, or if the free stand-in and the time split differ by more than 5 pp. The action fails if the fit fails the gate, yields fewer than 1,000 new-unit rows, or summary cannot score post-T months.

**p_success:** 0.65

**expected_to_fail_reason:** I do not expect it to fail as a measurement. The risks: too few post-T new-unit rows at a late cutoff, a gate failure on the refit, and summary timeouts.

**worth_it_anyway:** Even if it reproduces 67/89, the site's published honesty figure becomes the framework's figure, every unit-width fix gets a yardstick, and forward coverage of seen units is measured for the first time.

**rank_argument:** This is the framework's mandated honest-uncertainty measurement, and it has never been built. The one proven range defect is published from a by-product sample. One fit decides at least three pending items (the site's 1.2x, 2i, lister's coverage claim) before money is spent on them. It ranks below the free instruments and the quality screen because it measures rather than improves, and the free stand-in gives an early hint.

**depends_on:** Ben's go for one fit. nb-lpd-clustered's free stand-in as the comparison point.

**proposed_by:** ['measurement', 'uncertainty']

**merged_from:** ['time-split-coverage', 'time-split']

**conflicts:** Cutoff: 2026-04-01 (about 9k held-out rows, about 2,300 new-unit rows; measurement) vs 2025-07-01 (about 20k, 5-9k; uncertainty). The free count picks the latest T with at least 2,000 new-unit rows. Prediction: the measurement lens expects the as-of figure near the board (68/89, 62-74), citing NB5 held-out singles at 0.62/0.87. The uncertainty lens expects 76/93 (72-80): it argues the 964 rows are enriched for bedroom-change splits and cites NB5 first listings at 0.759/0.931, though those units had later relistings in training, so they are not as-of. I kept the conservative median 68/89 and widened the 80% interval to 62-80 to cover both. The outside view deferred it as measurement-only.
