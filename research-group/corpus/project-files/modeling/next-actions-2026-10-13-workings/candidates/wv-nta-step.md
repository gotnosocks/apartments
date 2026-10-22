# wv-nta-step — West Village 2020-NTA 2022 step and drift in place of the held areatime rerun

**kind:** free check then fit (feature set)

**what:** Modeling or Data improvements. Step 0 (free, about 30 min): on C, compute the WV-NTA minus Chelsea premium (level + walk + mean residual) by year, as research-backlog.md:855-868 did on NB5. Step 1 (about 0.5 day): feature set `nb8-nostuy-wvstep-v1` = nb8-nostuy-v1 plus two columns in feature group 'neighbourhood', so variance.py counts them as labels: 'WV NTA x from 2022-01' and 'WV NTA x years since 2022-01'. WV NTA is the 2020 NTA 'West Village' from NTA_FILE (features.py:1688-1690, :3536-3541), which includes 98 GV-labelled buildings; the set reads no rents. Fit C's design on it, rows split, plus the new-building score, in place of the held 'areatime rerun' line (research-plan.md:20).

**weakness:** The held areatime rerun would add about 469 label-curve latents (7 areas x 67 quarters) for +401 +- 37 that left the new-building miss at 11.9%. Its curves count as labels, summary.py refuses area_time runs, and autoselect would serve it on PSIS-LOO alone. Meanwhile C carries the one documented area-time signal, the WV 2022 repricing (WV - Chelsea -0.9 in 2021 -> +5.1 in 2026), in per-building walks.

**mechanism:** A dated, local repricing of the 2020 WV NTA polygon from 2022: a step plus a drift. Location coefficients were stable before and after, and the step and drift follow the geocode, not the label. Two parameters state the one finding that the quarterly label curves spread across about 469 latents.

**evidence:**
- research-backlog.md:860-868: WV - Chelsea flat 2014-21 (slope +0.01), then +1.6 (2022), +2.3, +2.6, +3.6, +5.1 (2026).
- research-backlog.md:752-770: 98 GV-labelled buildings inside the WV NTA have level +9.6 +- 1.2 and drift +5.3 +- 2.4; 'both the step and the drift follow the geocode'.
- research-backlog.md:575-589: location coefficients stable 2014-19 vs 2022-26. research-review-fable-2026-10-08.md:283 (#9a): 'only the WV step clears 2 SE'.
- research-plan.md:20: areatime +401 +- 37, with a unit at R-hat 1.066; rerun held. newbuilding-2026-10-13.md:43: its miss is 11.9%.
- variance.py:79-81: LABELS = ('neighbourhood', 'area_market_curve'); an NTA term in another group would slip out of the descriptive share (loophole).

**prediction:**
- psis_loo: +130 (80% +30 to +320) vs C; paired SE about 25-35; clears 2 SE with P about 0.65. It captures about 33% of areatime's +401 (8-80%).
- new_building: Miss -0.03 pp (80% -0.10 to +0.02); coverage +-0.2 pp.
- new_unit: n/a
- descriptive_share: -0.1 pp (80% -0.5 to +0.3) with the columns in the label group; 'building over time' falls 0.2-0.6 pp as walk variance moves to a label.
- other: Step +2.5 pp at 2022 (+1 to +4.5), drift +0.8 pp/yr (+0.3 to +1.3). The 98 GV-labelled buildings' post-2022 walks shrink toward 0. Free check: the 2025-26 WV-NTA minus Chelsea gap on C is +4 to +7 pp. Decision: if the step captures 40% or more of areatime's gain with 2 parameters, drop the areatime rerun.

**cost:** Modal about $2.1 (fit + $0.13 score). Oxylabs $0; other $0. About 0.5 day in features.py plus the 30-min check, then one fit; 1-2 days elapsed. Ben's go and his call on dropping the areatime rerun; gate, autoselect, PR.

**free_precheck:** The WV-NTA minus Chelsea premium by year on C. Kill if the 2025-26 gap is under 2 pp on NB8.

**miss_criteria:** Gain under 2 clustered SE vs C; step plus drift at 2026 outside +2 to +9 pp; under 15% of areatime's +401 captured; or the new-building miss worsens by more than 0.05 pp.

**p_success:** 0.65

**expected_to_fail_reason:** I expect it to win PSIS-LOO but to do nothing for the new-building miss: it is a place term, counted as labels. The 2022 date and polygon were chosen by free checks on these same rows, so the gain is optimistic. areatime's +401 may come mostly from the other areas' curves, in which case the step captures under 15%.

**worth_it_anyway:** Even a shortfall bounds how much of areatime's +401 is the WV repricing and how much is seven label curves describing noise. That decides whether areatime is one finding or a crutch, and it puts the WV result into the model as one readable, dated coefficient.

**rank_argument:** It is the parsimonious answer to the held areatime rerun: 2 dated parameters for the only area-time signal with evidence, against about 469 label latents that summary.py cannot summarize. It has high odds, but it is a descriptive place term, so it ranks below actions that add explanation or honest width.

**depends_on:** Ben's go and his decision to replace the held areatime rerun with this test (or run both and compare on shared rows). mw-external's features-only rung judges both on explanation.

**proposed_by:** ['parsimony']

**merged_from:** ['wv-nta-step']

**conflicts:** The data, explanation and outside-view lenses each rejected the areatime rerun as a label crutch and said only a single reshaped WV NTA step would be a candidate. The explanation lens warns that NTA terms outside the label group are a descriptive-share loophole, which this avoids by putting the columns in 'neighbourhood'. The parsimony lens left expected_to_fail blank; filled here.
