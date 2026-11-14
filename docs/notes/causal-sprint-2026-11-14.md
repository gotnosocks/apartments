# Causal sprint plan (2026-11-14)

Ben set the direction for this sprint on 2026-11-14: model changes motivated by a different
causal account of how a rent is set, with data problems read as hints about causes the model
lacks. The Modal budget is $100. This note states the causal account L1 encodes, lists the
rival accounts I will test against it, ranks the backlog under that direction, and lays out the
order of the free checks and the paid fits. Each fit gets a note of its own with predictions
committed before launch. Nothing is launched by this note.

## The account L1 encodes

L1 (`drift-building-phase`, pool `drift-building-phase-b0-latest-9a7830fb-l1`) prices an ad in
these steps:

1. It adds up about 250 coefficients on the coded fields of the ad and the lot.
2. It adds a citywide weekly walk and a season term, shared by every ad in the city.
3. It adds a building level, drawn around a 1 km surface for the zone, and a quarterly path
   for the building.
4. It adds a lasting level for the unit, drawn from a normal around zero, and a slow drift
   for the unit.
5. It draws the ask around that sum with Student-t noise. The noise scale depends on the
   months since the unit's previous ad.

Read as a causal graph, the ask depends on the apartment's quality (coded fields, building,
unit), on the place, and on one citywide market. The landlord enters only through the noise
scale in step 5. Regulation, the kind of apartment within a building, the state of the listing
and the segment of the market have no arrow of their own.

## Rival accounts

For each account I give the arrow it adds, the evidence on hand, and the change to the model.
The elpd ranges are rough and get replaced by the predictions in each fit's note.

| | account | arrow added | evidence on hand | model change | graph changes |
|---|---|---|---|---|---|
| A | Units come in kinds | unit kind → lasting level, with a heavy tail | 74% of the 300 most extreme units read as real apartments with a quality their neighbours lack; L1T gained 4,095 ± 172 elpd and missed the gate on nu and unit_sd; 12 of the 36 false deals were units priced 14% to 39% over their own earlier asks | L1TKN (`drift-building-phase-unitkn`): Student-t unit level at 3 degrees of freedom, rows' nu held at 2 | yes, in the prior on unit quality |
| B | The ask is a move in a search | listing state → mean | a relist within 2 months asks 1.4% to 2.0% under L1's median, and 0.9% to 1.0% under after a delisting or pause (S3) | L2: a level per lease phase, then the previous ad's ending | yes |
| C | Segments are separate markets | bedroom group × zone → time path | segment paths worth 452 ± 50 elpd over a static offset in 2020 to 2023 (S1) | a walk per bedroom group per zone around the citywide walk | yes |
| D | Quality runs along a line | line (building × bedrooms × baths) → level | 15 of the 36 false deals had a building level set by pricier lines | LN1, after its `unit_sd` mixing is fixed | yes |
| E | Some rents are set by rule | regulation regime → mean and time path | stabilized units follow about 0.9 of the walk (S6); income-program ads ask 3.9% to 6.4% under L1 with 1.3 to 1.8 times the spread (S15, S16) | a regime term: income-program rows priced from tier, bedrooms and year; stabilized rows on a damped walk | yes |
| F | Quality changes in steps | renovation event → jump in unit level | none measured yet; the unit drift is smooth by construction | a step at a DOB filing between two ads | yes |
| G | Landlords price by policy | manager → co-movement | a building's asks move with its manager's other buildings as much as with its neighbours (S8); a lister level lost 233 ± 41 earlier | a path per manager | yes |
| H | Odd kinds only scatter more | none; noise scale by duplex, income, year | S7, S14, S15 | D1, I1, Y1 | no |

Account A goes first, for three reasons. Its gain is about ten times any other on hand. It
addresses the false deals directly: a unit with a few asks far under its building keeps more of
that distance under a heavy tail. And the comparisons among B to G should run on a base with
its tails already fitted, since a change scored on L1 can lose its gain once the unit level
takes up the same ads. The Bayesian Workflow book gives the same order: fit the tails, then
compare structures.

Account H leaves the graph as it is, so under this sprint's direction D1, I1 and Y1 drop to the
bottom of the fit list. A heavy-tailed unit level may also take up part of the duplex scatter,
and I will measure that for free on A's saved predictions before deciding whether D1 is still
worth a fit.

## Free checks, in order

1. **Unit history calibration.** On L1's and L1T's saved held-out predictions, I regress each
   held-out gap on the mean training gap of the same unit, by the number of training ads. A
   slope above zero means the fit uses too little of the unit's own record. This puts a number
   on the false-deal pattern and says how much of it account A removes.
2. **Market disagreement.** A deal by the model's count should leave the market fast. For
   held-out ads opened long enough ago to have a known ending, I take the days on market and
   the later cuts and compare them with the gap. Then I draw the ads on which the market and
   the model disagree most: a low ask by the model's median with a long stay and cuts, and a
   high ask gone in days. Sonnet readers get those ads and controls without the ask or the
   group, as in S16. A second outcome separates a missed quality from noise in the ask, which
   S16's draw on the gap alone could not do.
3. **Regime check for account E.** On the income-program rows, I compare the spread of the ask
   around a table by tier, bedrooms and year with its spread around L1's median. If the table
   wins by a wide margin, location and quality carry little for those rows and a regime term is
   the right form.
4. **Line contrast for account D.** Within buildings with several lines, I measure the share of
   the held-out squared gap explained by the line's training gaps, with the (n-1)/n correction
   of `duplex-within-building-2026-11-14.md`.
5. **GPU rehearsals** on the 741-building subsample for every module before it goes to Modal
   (PR #1392 holds the first set).

Each check gets predictions before it runs. Readers and summaries run on Sonnet or Haiku.

## Fits and the budget

Every fit is 3 containers of 2 chains on the latest split, pooled and scored against its base
on the shared held-out ads with `rentfrontier.drift_score`.

| order | fit | base | estimate | launch condition |
|---|---|---|---|---|
| 1 | L1TKN (account A) | L1 | $11 | none; its note and predictions are on master |
| 2 | L2 (account B) | the winner of 1 | $11.50 | rehearsal passes on the new base |
| 3 | segment paths (account C) | the winner of 1 | $12.50 | lengthscales pass a rehearsal |
| 4 | the best of D, E, F, G and anything the checks turn up | the winner of 1 | $12 | its free check clears its bar |
| 5 | the accepted terms together, if more than one is accepted | the winner of 1 | $12 | |
| 6 | market and backtest fits of the final model, Price now, Deals | | $24 | the final model passes the gate |

That comes to $83, and I hold the other $17 for a failed start or a second fit under step 4.
I keep the spend sheet at `/data1/apartments/tmp/sprint-20261114/spend.md` from the ledger.

## Rules for accepting a change

The latest split has scored dozens of screens and fits, so a gain on it is worth less than its
SE suggests. For this sprint:

- A term is accepted when its pooled fit passes the gate and gains more than 4 SE over its
  base. Between 2 and 4 SE it is provisional, and I keep it only if it also gains on ads the
  split has never scored.
- Before accepting, I read the pointwise elpd differences. A gain carried by a few dozen ads
  is a tail fix and gets recorded as one.
- Every candidate is scored on the same held-out ads as its base, with equal chain counts.
- I log every screen and fit in `docs/research-record.md`, the nulls included, so the count of
  forks stays visible.
- For the final model I score ads opened after the snapshot of 2026-11-09, if the collection
  has them, as a check on ads no fit or screen has used.

## The backlog, ranked

Ranked by whether the item changes the causal graph, then by its value for deals, then by cost.

**Fit candidates, graph changes**

1. L1TKN, the heavy-tailed unit level.
2. L2, the level per lease phase, with the previous ad's ending behind it.
3. Segment paths by bedroom group and zone.
4. LN1, the line level. It needs a fix for the ridge between `unit_sd` and the drift scales.
5. A regulation regime for income-program and stabilized units. This replaces I1 and the
   TODO item on stabilized units following a share of the area path.
6. Renovation steps from DOB filings.
7. A path per manager, or per neighbourhood (`drift-local`, not refit since the building
   path's sampler was fixed).
8. The 2020 and 2021 concession gap term by building.

**Data validity, free, before the next dataset build**

9. P1, PLUTO as of the ad's date. Every drift fit reads the 26v2 release for every row.
10. H1, studios coded on units of 5 or more rooms, and the bedroom-count caution.
11. Net-effective asks and the free-months text column.
12. Label rule v18, the `label_key` extension, shared labels and the ledger fixes from the
    unit reads.
13. Nonresidential rows, sublets, blank forms, Brooklyn misjoins.
14. Text columns for empty coded fields, stated outdoor size.

**Checks on the scoring itself**

15. Ads after the snapshot as a fresh test set, then a new market snapshot and refit.
16. Backtests on 2024-11-10 and 2025-05-10.
17. A hash-keyed latest split.

**Fit candidates, graph unchanged**

18. D1, I1, Y1, the unit scales U1, U3 and U4, the first-ad noise factor, the level's degrees
    of freedom.
19. A second pass on the sampler.

**Closed or parked**

c3 and L1 are done. School zones stay tabled. Floor plan and photo reads wait for Ben's word on
OxyLabs photo fetches. The outdoor-space level (S7) and competing supply (S4) scored under 50
elpd and stay closed.

## Method notes from the two references

From Murphy's Model Discovery Agent I take the loop: keep a pool of rival structures with
their scores, spend the next experiment on the one where the rivals' predictions differ most,
and ask for a new structure only after a predictive check fails. Here a free screen plays the
part of a cheap experiment and a Modal fit the part of a costly one. Its appendix reports a
selector that compared scores from different splits and picked overfitted models, which is the
reason for the same-ads rule above. From the Bayesian Workflow case studies I take the
reporting of the elpd difference with its SE, the reading of pointwise differences before a
win is accepted, and the order of tails before structure.
