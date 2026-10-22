Thanks, all. This is a better list of checks than our referees gave us. Some answers we already have, and the rest are now in the queue.

**Walk-ups (ex_broker_uws, argon).** The walk-up curve has its own value for every floor from 2 to 6, plus a separate top-floor term, so it can bend wherever the asks bend. Against floor 2 of the same building, floor 3 asks about 0.1 pts less, floor 4 about 0.3, floor 5 about 0.6 and floor 6 about 0.4, and being the top floor of a walk-up takes off another 0.3. So the asks show neither a peak at 2 or 3 nor a top-floor premium. Ground-floor garden units carry their own flag (+2.9%), which keeps them from setting the floor-1 baseline.

**Penthouse vs. top floor (argon).** The +8.3% penthouse term sits on top of a separate top-floor flag (+1.75%), so it isn't just "highest floor in the building" under another name.

**"The steps grow as you climb" (argon).** You're right, the sentence was wrong and we've fixed it. Per floor it's about 0.4 pts up to floor 10 and about 0.3 above that. What grows is the gain per doubling of the floor number.

**Thin support at the top (astra, sol61).** Floors 30 to 46 each draw on 81 to 359 buildings, and no single building has more than 5.5% of a floor's ads. Above 47 we pool everything (7,822 ads in 104 buildings), which is why the curve stops there.

**Washer as a renovation proxy (nearly everyone).** Probably partly, and we can't separate it in a single cross-section. Three tests are queued: repeat listings of the same unit, comparing co-listings less than 60 days apart with relists after a vacancy; coding listing photos for renovation blind to the rent; and timing around the 2019 HSTPA changes.

**Stabilized −2.4% as a blend (hedonic_skeptic, ex_broker_uws, argon).** Agreed that it mixes 421-a new construction with old stock. We'll split it by build year and by DHCR registration where we can match it.

**Park-facing (astra, bayes_in_brooklyn, sol6).** Next come park-facing × floor, placebo "views" of parks the building doesn't actually face, and front vs. rear lines within the same building. The premium stays provisional until it passes the permutation test.

**Closing-price proxy and missing size (bayes_in_brooklyn, ex_broker_uws, sol6).** We'll audit delist-and-relist cycles so that a pulled listing doesn't count as "found a taker", and split the missing-square-footage discount by lister type.

A repeat-unit (line) effect fit and a period-specific fit are already queued on the GPU. We'll post the results here.
