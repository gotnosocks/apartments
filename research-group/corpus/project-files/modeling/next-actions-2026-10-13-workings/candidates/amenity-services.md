# amenity-services — Building services from StreetEasy's coded amenity lists already archived (pool, concierge, garage, gym, roof deck): extract, fill as of each date, screen, fit only if it clears 5%

**kind:** data fix (free extraction and screen; one fit only if gated)

**what:** Data improvements (about 1 day): extend listing_extras.record_extras (:36-56) to keep every code in propertyDetails amenities, sharedOutdoorSpaceTypes and features. granular_parse.py:192-193 already stores them; analytical.py:61-74 maps only elevator, washer/dryer, laundry, doorman, central AC and pets. Count the vocabulary, its coverage and its within-building variation over time. Build an as-of fill (strictly earlier days, as elevfill.py:12 does) of the unmapped services: concierge, gym, pool, garage/parking/valet, shared roof deck, storage, bike room, package room, playroom, live-in super, lounge. Enter one family, an amenity tier (none / 1-2 / 3-5 / 6+ / unknown), as `nb8-nostuy-amentier-v1`. Screen free on C against the static building part (explain-screen-v2 target, lot folds, 200 permutations) with the offset rescore. Run one Modal fit plus the new-building score only if the share exceeds max(5%, null_95).

**weakness:** The new-building miss is 11.9% (17.3% in 1-5-row buildings) and moves only through the fixed part, yet building service quality is unmeasured except through gym and roof-deck regexes on the minority of ads with text (features.py:224-225). The building level (10.2%) absorbs it, and a new building cannot use that.

**mechanism:** In hedonic rental models the building's amenity package is the standard building-quality proxy. Beyond era, class and size, it separates new luxury towers from older doorman stock. Services appear on a new building's first ad, so the tier enters the fixed part, carries over to an unseen building, and gives a reason renters understand.

**evidence:**
- The codes are present: a Chelsea ad lists ELEVATOR, DOORMAN, CONCIERGE, GYM and PARKING (chelsea-expanded-fit-residual-research-2026-09-19.md:36). amenities_json is non-empty on 93.7% of Chelsea rental captures (chelsea-granular-quality-2026-09-16.md:107). Unknown source fields can be extracted without re-scraping (granular-dataset.md:76).
- Only six codes are mapped (analytical.py:61-74; attribute_evidence.py:156-176); listing_extras.py:36-54 has no amenities field.
- Record codes carry signal: nb-coded-v1 +109.4 +- 30.7 (feature-tests.md:50).
- Building offsets the level now only describes: Walker Tower +60.3%, The Cortland +57.1%, One High Line +50.4% (chelsea-group-effects-2026-09-18.md:11-13; older model, illustration only).
- C-era building families: elevfill 2.4%, lines 2.1%, hpd 1.4%, stabilization 1.2% of building variance; by the sqrt(1-s) arithmetic, 5% moves the miss about -0.3 pp. The prior review's materiality bar is 5% (prior-review-rent-model-review).

**prediction:**
- psis_loo: If fitted: +30 (80% -20 to +100); clears 2 clustered SE with P about 0.3.
- new_building: If fitted: -0.10 pp (80% 0 to -0.25), and -0.3 to -0.8 pp in the 1-5 and 6-20-row bins; 80/95 coverage +-0.3.
- new_unit: n/a (a building family; +-1 pp on the 964 rows).
- descriptive_share: If fitted: -0.25 pp (80% -0.6 to +0.05), below the noise floor.
- other: Screen: 2.5% of the static building effect (80% 0.8-6%), with null_95 at most 0.5%. It beats the null with P about 0.85 and clears 5% with P about 0.2. Offset -0.12 pp (-0.03 to -0.3). 60-90% of rows carry an unmapped code, and codes are constant within 80% or more of buildings, so the as-of fill is needed. If fitted: the tier is monotone; 6+ vs none is worth +4 to +10% beyond doorman, elevator and era; pool, concierge and garage +2 to +6% each; the post-1990 era coefficients shrink.

**cost:** Modal $0 for the extraction and screen; about $2.25 if it passes. Oxylabs $0; other $0. Data improvements about 1 day (extraction, as-of fill, feature set, tests, PR); Modeling one queue slot. Ben's release for the fit.

**free_precheck:** Kill if fewer than 50% of rows carry any unmapped code after the as-of fill. Then the screen: no fit unless the share exceeds max(5%, null_95).

**miss_criteria:** Screen at or below max(5%, null_95): stop, with no fit (a prediction miss only if under 0.8%). After a fit: the new-building miss falls by less than 0.05 pp and the descriptive share by less than 0.15 pp.

**p_success:** 0.3

**expected_to_fail_reason:** I expect it to fail the 5% bar. Every building family so far has landed at 1.2-2.4%. Doorman, elevator, era, class, size and the gym, outdoor and luxury text flags already carry much of the tier. Listers enter the codes, so 'missing' is noisy, and management-listed buildings look richer than broker-listed ones.

**worth_it_anyway:** The data is free and the work takes about a day. It tests the classic hedonic building-quality proxy. A pass gives renters a named answer (what a building with a pool or concierge asks); a fail moves building-quality effort to the LLM reads, backed by evidence.

**rank_argument:** It is the cheapest building-quality family outside saturated location, with no LLM or Oxylabs cost, and better odds than the held retail, noise, trees and crime sets. It ranks below quality-reads because its expected size is screen-passer scale (about 0.1 pp of miss).

**depends_on:** Data improvements' extraction PR; explain-screen-v2's static target (soft; the time-averaged premium can stand in); Ben's release for the fit.

**proposed_by:** ['outside view', 'explanation']

**merged_from:** ['building-amenity-tier', 'amenity-codes']

**conflicts:** Form: a count tier (outside view) vs a family of per-code indicators (explanation); kept the tier (fewer coefficients, robust to sparse codes) and report per-code effects in the screen. Gate: 5% (outside view, the prior review's materiality bar) vs at least 1.5% with an offset of -0.05 pp (explanation); kept 5%. Screen median: 3.5% (outside view) vs 2.5% (explanation); kept 2.5%. Fit PSIS-LOO +40 vs +30, miss -0.15 vs -0.10, descriptive -0.35 vs -0.25; kept the smaller. Coverage kill: 50% (outside view) vs 40% (explanation); kept 50%.
