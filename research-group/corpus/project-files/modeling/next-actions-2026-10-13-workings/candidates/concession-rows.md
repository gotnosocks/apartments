# concession-rows — Keep coded-concession listings (2020+) with a coded months-free share instead of dropping them

**kind:** data fix (free check, then a dataset rebuild and one fit)

**what:** Data improvements: flag coded concessions instead of excluding them (exclusions at historical_dataset.py:266-269 and cohort.py:166-168). Carry months_free, lease_term_months and net_effective_rent as columns (analytical._rental_flags already reads pricing.monthsFree, netEffectiveRent and leaseTermMonths). Rebuild the 8 areas' cohorts and NB8 and quarantine-screen the new rows. Modeling: a pinned row split, so C's held-out audit_ids stay held out, the added rows train, and the fit pairs with C. Feature set `nb8c-nostuy-concession-v1` = nb8-nostuy-v1 + months_free_share (monthsFree / leaseTermMonths, 0 elsewhere). Concession rows keep their gross initial ask, so the target stays the ask; a net-effective target is Ben's call. One Modal fit of C on it, plus the new-building score on C's rows.

**weakness:** The 2020-26 sample drops coded-concession listings selectively. In 2021, 200+-row buildings conceded at 30.4% against 15.1% for small ones, and their walks sit 7.6-8.7 pp above small ones that year. When the target moved to the latest ask, text:concession moved from -1.0% to -3.6%.

**mechanism:** Large landlords offering free months kept gross asks up while their conceding listings were dropped. The remaining asks overstate those buildings' 2020-22 levels, and the walks and year noise absorb the gap. Keeping the rows with a coded months-free share lets a named term carry the gross-ask premium, so the walks and the market curve see the whole sample.

**evidence:**
- The cohort drops ads with monthsFree > 0 or netEffectiveRent > 0 (analytical.py:217-223; historical_dataset.py:266-269; cohort.py:166-168). StreetEasy codes concessions from 2020 (features.py:890-893).
- Chelsea funnel: 4,509 concession exclusions of 68,313 raw listings (research-backlog.md:1935-1941); about 18k NB8 rows (inferred).
- 2021 concession rates: 30.4% in 200+-row buildings vs 15.1% in 1-19-row buildings, worth 1.5-2.5 pp of the gap (research-review-fable-2026-10-08.md:254). The 7.6-8.7 pp 2021 walk gap (research-backlog.md:1455-1462).
- text:concession -1.0% -> -3.6% on the latest-ask target (newbuilding-2026-10-13.md:155-156).
- Data rules can only drop or modify rows (data.py:1177-1198), and the split is drawn on the dataset (splits.py:32-41), so adding rows needs a rebuild plus a pinned split. 'A data decision for Ben' (research-review-fable-2026-10-08.md:252).

**prediction:**
- psis_loo: +20 on C's training rows (80% -40 to +110); P(clears 2 SE) about 0.3. Gains are indirect, through better 2020-22 walks and market for big buildings.
- new_building: On C's rows: 11.9% +- 0.1, unchanged; 80/95 coverage unchanged +-0.3.
- new_unit: n/a (the 964 rows stay within +-1 pp).
- descriptive_share: -0.2 pp (80% -0.8 to +0.4), below the noise floor; 'building over time' falls 0.1-0.3 pp.
- other: Free check: about 18k droppable rows (11-28k), 85% or more from 2020 on; the drop rate in 200+-row buildings is about 2x that in 1-19-row buildings. C's 2021 walk rises with a building's 2020-22 drop rate: slope +5 to +15 pp, positive at 2 SE with P about 0.6. Fit: months_free_share coefficient +0.55 (+0.25 to +0.9), about +4.6% of gross ask per month free on a 12-month lease. The 2021 walk hump of 200+-row buildings falls to 6.0 pp (4.8-7.3). 2021 noise scales -4% (-12 to +5%).

**cost:** Modal about $2 (one fit + new-building score with a pinned split; about $4 if a control refit replaces the pin). Oxylabs $0 (the pricing JSON is archived); other $0. Data improvements: free check 2-3 h, rebuild and quarantine about 1.5-2 days; Modeling about 0.5 day for the pinned split and column. About 3 days elapsed. Ben's data decision on the target semantics.

**free_precheck:** On thelio, rent-blind except for the walk join. (a) Count coded-concession own ads that pass every other cohort rule, by year, area and building-row band, with monthsFree/leaseTermMonths coverage. (b) For buildings with 20 or more rows in 2020-22, regress C's posterior-mean 2021 walk (relative to 2019 H2) on the building's 2020-22 drop rate. Stop before the rebuild if (a) finds fewer than 5,000 rows or (b)'s slope is not positive at 2 SE.

**miss_criteria:** Free check: fewer than 5,000 rows, or a non-positive slope. Fit: the 2021 hump of 200+-row buildings falls by less than 1 pp, or the months-free coefficient is not positive at 2 SE, or PSIS-LOO on C's rows falls below -2 clustered SE.

**p_success:** 0.45

**expected_to_fail_reason:** About even odds. The free check already put concessions at only 1.5-2.5 pp of the 7.6-8.7 pp walk gap. PSIS-LOO on shared rows sees only indirect effects, and the added rows sit mostly in large buildings, where per-building trade-offs have failed the gate before.

**worth_it_anyway:** It removes the one documented selection in the training sample and gives a renter-facing explanation of what a free month does to the face rent. It is the prerequisite for any net-effective or final-ask target, and it explains the text:concession shift that the latest-ask fit exposed.

**rank_argument:** A known bias, with the data in hand and no Oxylabs cost, against Ben's high-quality-data principle. It ranks below the measurement and quality actions because its scored gains are small: the new-building miss is unchanged, and the descriptive-share move is under the floor.

**depends_on:** Ben's data decision (gross ask plus a coded column, or a net-effective target). A pinned row split or a control refit. Independent of the other candidates; size-completion's re-read would add outcome status for a later net-effective target.

**proposed_by:** ['data', 'outside view']

**merged_from:** ['concession-rows-kept']

**conflicts:** The outside view called restoring these rows the econometrically right fix but listed it among rejected ideas, to be folded into the next cohort rebuild, and framed it as net-effective rents. The data lens keeps the gross ask plus a coded months-free share and leaves the target to Ben. I kept the data lens's form.
