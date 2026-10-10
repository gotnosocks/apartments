# Pre-registered predictions: Data improvements' nb8 sets (2026-10-10)

Written 2026-10-10 20:25Z, before these fits land, under the evaluation framework of
[the research review](research-review-fable-2026-10-08.md) (§3 and the §10 preamble). A miss is
recorded as a miss.

## Scoring

- **Paired PSIS-LOO:** each set against `nb8-nostuy-v1` with the same model, on the rows both
  keep (`leaderboard.paired_loo`). For calibration, Modeling's nb8 nta fit against its base gave a
  paired SE of 4.0 and a combined Monte Carlo error of 15.3, so the ~2 SE bar is about 30 to 35
  ELPD. "Clears" below means the change clears that bar.
- **Explained share:** for building-level sets, the share of building-level variance the set
  explains, compared with a permutation null. The null is the same columns permuted across
  buildings, one fit per family, run only if the LOO is close.
- **Coefficients:** reported as posterior medians with 90% intervals, in percent of rent.
- **Leakage:** none of these sets reads rent, so no time-split check is needed.

## Already fitted before this was written: not pre-registered

`nb8-nostuy-lines-v1` and `nb8-nostuy-elevfill-v1` have LOO outputs on thelio (14:01 and 14:40
ET, on the nosizeslope model). I have not opened them. Predictions written now would not be
pre-registered, so none are given. They are reported without a prediction.

## Predictions

| Set | Direction (median, 90% interval) | ΔELPD vs base | Clears ~2 SE? | Where it should move |
|---|---|---|---|---|
| `nb8-nostuy-retail-v1` (log1p storefronts, and restaurants/cafes/bars, nearby in the Storefront Registry's first year) | Food places small +, storefronts small −, each within ±2% per unit of log1p | −10 to +30 | No (nb3: +11 ± 15, +7 ± 15) | East Village and NoMad buildings on commercial avenues; the explained share is within the permutation null |
| `nb8-nostuy-noise-v1` (311 street/nightlife and construction complaints within about a block in the year before) | Street/nightlife −0.5% to −2% per doubling; construction 0 to −1% | −10 to +25 | No | East Village and the West Village nightlife blocks; mostly absorbed by the building level and walk |
| `nb8-nostuy-trees-v1` (log1p live street trees nearby, latest census a week before the listing) | More trees → higher rent, 0 to +1.5% per unit of log1p | −10 to +20 | No | Quiet side streets in WV, GV and Gramercy; within the null |
| `nb8-nostuy-crime-v1` (log1p felonies reported nearby in the year before) | More felonies → lower rent, −0.5% to −3% per unit of log1p | 0 to +40 | Borderline, most likely not | East Village, and the edges of Chelsea toward the West Side; collinear with neighbourhood, so neighbourhood terms shrink |
| `nb8-nostuy-hpd-v1` (Class B/C violations in the past year, per apartment) | "Many" violations −2% to −6%; "a few" −0.5% to −2% | 0 to +50, central +20 | Borderline, the most likely of the six to clear | Walk-up stock in EV, WV and GV; the term varies within a building over time, so it can score where the building level can't; explained share above the null |
| `nb8-nostuy-petsfill-v1` (pets updated from ad text) | Ordering not_allowed < no_dogs < approval_required ≈ allowed; not_allowed −1% to −4% against allowed; no_dogs between them | −5 to +35, central +10 | No, most likely a tie | The 121k filled rows (16.8k from the row's own ad, 104.7k from the building's earlier ads), mostly East Village and Chelsea. Most fills are constant within a building, so the building level already holds much of this |

## What would change my reading

- **A clear loss on any set** (below −2 SE) means the features fight a term already in the base.
  Likely candidates are neighbourhood for crime and the building level for petsfill.
- **petsfill clearing the bar** would mean pet policy varies within buildings more than I assume,
  through condo units and changes of owner.
- **hpd failing** would mean building condition is already captured by the building level and
  pre-war / walk-up. Its explained share against the null then decides whether it is worth
  keeping for explanation at equal LOO.
