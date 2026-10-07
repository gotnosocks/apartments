# Leak-free feature evaluation

Ben, 2026-10-05: feature evaluations must be leak-free, and the scoring procedure may change to achieve that.

## The leak

A score is leak-free when the row being scored contributes its rent to the fit only as the held-out target. It must not reach the fit through another row's covariates, and it must not shape a data rule.

PSIS-LOO approximates leaving one row out of a fit on all rows. If a feature of row B is computed from row A's rent, then leaving A out still leaves A's rent in the fit, through B's covariate. The score of A is then partly a lookup.

`nb-prevprice-v1` (#211) is the example. Each listing's covariate is the unit's previous listing's last price over that listing's initial ask, so it contains the previous row's target. Paired against `nb-coded-v1` on PSIS-LOO (x-2060-100w600d-nb-cb1-q5 at a2b00d4), the rows split as follows:

| rows | n | paired ΔELPD |
|---|---|---|
| all | 77,815 | +746.9 ± 40.7 |
| a later row of the unit exists (its ask feeds that row's covariate) | 44,867 | +637.9 ± 33.3 |
| the unit's last listing | 32,948 | +108.9 ± 23.4 |

Rows that no other covariate can see gain about a seventh of the headline.

## The latest-listing split

`--split latest` (`splits.latest_split`) holds out the most recent listing of a random set of re-listed units, 10% of all rows, with the usual seed. Units whose two latest listings share a date are not drawn. It is drawn after the data rules (`splits.AFTER_RULES`), on merged units and kept rows. The model is fitted on everything else, and held-out rows are scored as usual (`heldout.npz`, ELPD per row).

- **Leak-free for unit history.** No training row comes after a held-out row in its unit. So no training covariate built from the same unit's earlier listings (previous asks, repricing, gaps) can contain a held-out rent.
- **Legitimate past information is kept.** A held-out row's own covariates may read its unit's earlier listings, because those are known when it is listed.
- **It is the site's task.** It scores the next listing of an apartment the model already knows, with that apartment's own unit effect learned from its earlier listings.
- **It costs one fit per design**, the same as an exploration fit (`SPLIT=latest` in `drive.sh`).

Every reader of a run (summary, loo, explain, rentmap, rescore, variance, projection) rebuilds its rows through `data.split_and_rules`, which keeps the run's order. That is rules first for the latest split, and split first for the others.

**Limits.**
- **Power:** under the current rules the split scores 8,648 rows (10%) against PSIS-LOO's 77,815, so paired standard errors are about three times larger. Effects of the size of #211's real gain (about +109 ± 23 on last listings under PSIS-LOO) resolve; small ones may not. When the interval straddles zero, K disjoint groups of the same last listings (K fits per design, each last listing held out once, still leak-free) buy power at K times the cost.
- **Time skew:** latest listings sit mostly in recent months, where the market curve and walks have the least data after them. So the split mixes a feature's value with near-term extrapolation. It is the score for features that read earlier rents, not a general replacement for PSIS-LOO: changes to time structure (walk spacing, bedroom curves) score differently here.

Designs are compared paired, on the held-out rows both runs share: the per-row ELPD difference, its sum, and the standard error from the row spread plus the chains' Monte Carlo error. Both arms must use the same data rules so that they hold out the same rows.

## Which score a feature needs

- **Reads no other row's rent** (every merged feature set today): PSIS-LOO on the frontier, unchanged.
- **Reads earlier rents of the same unit** (`nb-prevprice-v1`): judged on the latest split. These sets are listed in `features.READS_EARLIER_RENTS`, and `autoselect.why_not` refuses them, so their inflated PSIS-LOO can never select a served model. Serving one needs a selection rule on the latest split first.
- **Reads other units' rents** (building or block price aggregates, none so far): the latest split is not enough, because a later listing in the same building could read a held-out rent. Such a feature needs a time-forward split (hold out every row after a date). Build that split before merging such a feature.

## Audit of merged features (2026-10-05)

- **Features:** no feature set reads `asking_rent` or `log_rent`. A grep of `features.py` and `descriptions.py` finds none. `relist-v1` reads only the dates of the unit's earlier listings. Text flags read the row's own ad. Lot, registry, transit, noise and HPD features read external files, and the as-of sets date them by the listing.
- **Model:** the model uses rents only as the target and as the offset, which is the mean training log rent. Under PSIS-LOO the offset includes the left-out row with weight 1/77,815, and both arms share it.
- **Listing-record fields (`nb-coded-v1`):** these are read from each listing's last capture, so a field could have been edited after the listing date. That is the listing's own later information, not another row's rent; the same holds for the description evidence. They change between captures in under 1% of listings (see the as-of check below).
- **Data rules chosen with rents in view:** quarantines from residual and high-k reviews (q-v3, q-v4) were picked by looking at rents. They are judged on shared rows (`cleaning-scored-on-shared-rows`). That compares models on the same rows, but it does not make the choice of rows leak-free. A rule found that way should be confirmed on rows held out from the review that produced it.

## Results (2026-10-05)

Exploration tier (x-2060-100w600d-nb-cb1-q5, Gibbs), on the latest split at 56b2d7b, with the Oct 1 cohort and the current rules (unit-labels-v3, quarantine-v5, bedrooms-ad-v2, baths-ad-v2, fields-review-v1). 8,648 held-out latest listings, paired:

| design | vs nb-coded-v1 | Chelsea | West Village |
|---|---|---|---|
| nb-prevprice-v1 (price change and repricing count) | **+68.5 ± 15.1** | +34.0 ± 12.2 | +34.4 ± 8.8 |
| nb-prevprice-v2 (repricing count only) | +24.2 ± 7.0 | +5.4 ± 5.9 | +18.9 ± 3.6 |

v1 against v2: +44.2 ± 13.1.

A first run (05bfae7) had measured +72.8 and +26.3. Review then found a self-leak: a current-capture row shares its advertisement with that ad's initial-ask row, so its "previous listing" was its own ad. That affected 70 rows, 28 of them held out. The feature now reads the latest earlier row of another advertisement, and builds both terms from that ad's price-change record alone, never from frame rents. On PSIS-LOO the pre-fix feature (a2b00d4) had shown +746.9.

Next: a full-tier pair on the latest split (the served design with and without nb-prevprice-v1, on the Oct 5 cohort) decides whether it is served (Modeling's selection path).

## As-of check: listing-record fields

`nb-coded-v1` reads each listing's last capture. Across the 29,602 listings captured more than once, the coded outdoor types change between captures in 0.66% of listings and the room count in 0.96%. (Computed with `listing_extras.record_extras` over every capture in both granular crawls' `listing_observations`.) The last capture is therefore, in effect, the listing's own as-of record.

## Serving a design that reads earlier rents

Ben approved this path on 2026-10-05. `autoselect` refuses feature sets in `features.READS_EARLIER_RENTS`; `python -m rentfrontier.latestselect` serves one instead when:

1. a full-tier latest-split run of the served design (the reference) and one of the candidate design (same model, the new feature set) both pass the gate, on the current dataset and rules;
2. the candidate's paired held-out ELPD beats the reference by more than two SE;
3. a full-tier rows-split run of the candidate design meets every other autoselect condition (gate, hardware, window, dataset, rules).

`--write <summary bundle>` writes the selection for the rows-split run. Its reason gives the latest-split comparison, and its `latest_pair` field names the two runs. Its PSIS-LOO is recorded, but not as a comparison.

**prevprice removed (Ben, 2026-10-07).** nb3-prevprice-v2 was served from 2026-10-07 (#392) on a +84.2 ± 17.5 latest-split win. Ben removed it by hand as semantically invalid: the correction from the unit's previous listing's repricing has no time dependence, so a cut from years ago counts like one from last month. The coded-v2 selection was restored, with the removal recorded in `config/main-analysis.json` (`manual_removal`). Every feature set with `prevprice` in its name is blocked (`autoselect.BLOCKED`): `autoselect` and `latestselect` both refuse it, whatever it scores.
