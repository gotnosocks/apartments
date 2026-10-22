# size-completion — Size completion: free check of GraphQL history-digest sizes, then one size fit (history sizes if real, otherwise the held predsize)

**kind:** new data source / data fix (free check; about $0.3 of Oxylabs re-read only if real; then one fit)

**what:** Data collection, free on thelio (about 2 h), using the 30-building pilot responses (data/probes/no-render-20261013/pilot/) and the Midtown West crawl's stored history bodies. Per listing id, compare the digest's livingAreaSize and monthsFree with the ad page's fields, and the digest's urlPath with NB8 unit ids. The Caroline is the decisive building: size is stated on 2% of its 1,238 rows, and it has 1,703 history rows. If the size leg survives and Ben types go: about 226 GETs (5,415 buildings at about 24 per GET), saved as a dated external table, then `nb8-nostuy-gqlsize-v1` (the digest's size where the row's own ad has none) and one Modal fit of C plus the new-building score. If the size leg dies: a free offset plug-in on C's draws (rest + beta_size x (fill - mean fill) on unknown-size rows). Only if it cuts those rows' new-building miss by 0.1 pp or more, run the held `m7-nocurves-floorslope-bednoise-dayfourier-bedtime-yearnoise-sizeunkslope nb8-nostuy-predsize-v1` (features.py:4698-4748), reporting case-a and case-b fills separately.

**weakness:** Size is unknown on about 63% of C's training rows (122,399 of 193,376), and the share of ads stating it fell from 41.5% (2010) to 20.5% (2026). Per-building size-unknown and bedroom slopes stand in for it (slopes are 4.1 pp of rent variance), and a new building cannot use them. New-building miss: 12.0% with size unknown vs 11.8% with size stated, a comparison confounded by building mix.

**mechanism:** If the digests carry a unit's size where its ad left it out, size moves from per-building patches into the named size feature on most rows and reaches the fixed part. Otherwise, a rent-blind predicted size gives the fixed part what a new building's own records hold, and the size-unknown slope should shrink. The same responses give StreetEasy's own unit paths (an identity audit) and each ad's status.

**evidence:**
- Digest FIELDS include livingAreaSize, monthsFree, leaseTermMonths, noFee, status, createdAt and offMarketAt (graphql_inventory.py:75-78); history JSON is stored (:158-168).
- liberty-toye: size null on only 6 of 625 history rows (no-render-past-rentals-2026-10-13.md:45-47). Our ad pages read the same field (granular_parse.py:188) and treat values <= 0 as unknown (attribute_evidence.py:139-142), so 'non-null' probably counts zeros (inferred).
- One GET covers 20-25 buildings (no-render:83-85): about 226 GETs, about $0.25 at about $1.1 per 1,000.
- predsize: fills 135,097 rows, sqft_unknown stays, reads no rents (features.py:4698-4748). Registered prediction -40 to +60 ELPD (config/predictions.jsonl:20). Fills mean -0.14, SD 0.21 (predictions-newbuilding-2026-10-13.md:46).
- Within-bedroom R^2 of predicted size: 0.46-0.84, or 0.65-0.89 with the building's other units; unstated rows rent 2.7% below their predicted size (size-predictability-2026-10-12.md:51-57, 122-126).
- A real-size analogue on a simpler model gained +653 +- 53 (research-plan.md:678-680). sizefill failed the gate at group R-hat 1.67 (prior-review-rent-model-review:243). The new-building score adds fslope_scale^2 x^2 per filled row (newbuilding.py:87-88).
- 30 pilot buildings: 1,066 API-only post-cutoff ads beside 5,857 matched (data-collection.md:33-40); 6.84% of same-unit pairs still jump more than 40% after unit-splits-v4 (cleaning.json).

**prediction:**
- psis_loo: History-size fit (P about 0.12 that the sizes are real): +100 (80% -30 to +500). predsize fit: +40 (80% -150 to +300), against the registered -40 to +60; gate-failure risk about 25%.
- new_building: History sizes: -0.15 pp (-0.5 to +0.05), with 80% coverage about 0.5 pp wider. predsize: -0.08 pp on all rows (+0.05 to -0.25), -0.12 on unknown-size rows (+0.05 to -0.40); 80/95 91.0/98.2 (90.6-91.6 / 98.0-98.4). Unconditional: about -0.05 pp.
- new_unit: predsize: +0.5 pp at 80% (-1 to +2.5) on the 964 rows, essentially unchanged. History sizes: n/a.
- descriptive_share: History sizes -0.6 pp (-1.6 to +0.2); predsize -0.3 pp (-0.9 to +0.3), below the noise floor. Unconditional about -0.1.
- other: Free check: The Caroline shows livingAreaSize > 0 on under 5% of digests (P 0.88), i.e. the digest mirrors the ad field with 0 placeholders. Midtown West digests match their own pages on 98% or more. monthsFree > 0 on 10-20% of 2020+ digests in large buildings, already on our pages. 1.2% (0.3-3%) of pilot NB8 rows disagree with the urlPath. API-only ads add 8% (3-18%) of rows in large buildings. predsize: sqft_unknown rises 3-8 pp; the size-unknown slope scale shrinks 10-40%.

**cost:** Modal $0 for the checks; about $2.25 for the one fit. Oxylabs $0 for the check; about $0.25-0.6 for about 226 GETs (+ about $6 if building ids must be fetched), on Ben's typed go. Other $0. Effort: Data collection about 2 h for the check and about 0.5 day for the re-read; Data improvements about 1 day per overlay; predsize needs about 2 h of analysis. 1-3 days elapsed.

**free_precheck:** The size leg dies if fewer than 10% of ads with no size on their own page gain one, or if fewer than 90% of overlaps agree within 5%. The predsize branch then needs the plug-in to cut unknown-size rows' new-building miss by 0.1 pp or more.

**miss_criteria:** Size leg: the digest sizes mirror the page field (the expected outcome, recorded as such). For either fit: the newly sized or filled rows' new-building miss falls by less than 0.1 pp (history) or 0.05 pp (predsize) while the descriptive share moves by less than 0.3 pp; or a gate failure; or PSIS-LOO below -150.

**p_success:** 0.2

**expected_to_fail_reason:** I expect it to fail. The digest's livingAreaSize is very likely the same attribute our ad pages read, with 0 for unstated sizes. predsize fills are built from fields C already uses, and the stated/unknown gap caps the new-building gain near 0.2 pp. A predicted regressor treated as known understates uncertainty, and a per-building slope on predicted x risks the gate.

**worth_it_anyway:** The check is free and settles the digest semantics the Midtown West and Brooklyn datasets will rely on. A re-read would also return every ad's RENTED / NO_LONGER_AVAILABLE / DELISTED status and offMarketAt (outcome data for a net-effective or final-ask target), an identity audit against StreetEasy's unit paths, and a count of unvouched ads. A predsize null retires latent size and imputation work, which both prior reviews once ranked first.

**rank_argument:** Size is the largest data gap by rows, and the check costs two hours; real digest sizes would be the biggest size lever. It ranks mid-list because the new-building gain is capped near 0.2 pp and the odds of real sizes are about 1 in 8.

**depends_on:** Nothing for the check; Ben's typed go for the GETs; Ben's release of the held predsize. Better read with nb-lpd-clustered's clustered SE (the unknown-row leg) and its A/A null (the descriptive leg), per the measurement lens. The identity leg (`unit-paths-v1`, about +80 ELPD) is a separate later fit if 0.5% or more of pilot rows disagree with the urlPath.

**proposed_by:** ['data', 'explanation']

**merged_from:** ['graphql-digest-check', 'predsize-fit']

**conflicts:** predsize timing is contested. The explanation lens would fit it after a 0.05 pp offset precheck. The data lens holds it unless the GraphQL size leg dies and the plug-in reaches 0.2 pp. The measurement lens says run it only after clustered SEs and the A/A null exist. The parsimony lens would run it only as a swap that retires the size-unknown slope. The outside view (generated-regressor problem) and the uncertainty lens (no width lever) reject it. I kept it as the conditional branch with a 0.1 pp gate: between 0.05 and 0.2, and about 2 clustered SE per the measurement lens. Size-leg survival thresholds: data lens (10% or more gain a size, 90% or more agree within 5%) vs explanation lens (25% or more of unknown rows, within 10%); kept the data lens's.
