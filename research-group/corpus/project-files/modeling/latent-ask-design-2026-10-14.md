# From one price per ad to a latent ask per apartment

*Status: backlog research suggestion (Ben, 2026-10-14 09:25Z). No work is scheduled.*

*2026-10-14, AR(1) fit thread. This is a sketch, not a plan of record. Counts come from free, read-only checks on thelio against the archived captures behind C's 214,921 rows (per-row dump: /data1/apartments/tmp/arwalk/prov/events.jsonl on thelio). Costs are extrapolated from C's own fit times. Predictions are medians with rough ranges, written before any fit.*

## The idea

Today each ad becomes one row priced at one ask: the first ACTIVE price, or the end-of-day-one price once Data improvements ships its fix. Ben's ideal is different. Every apartment has a latent ask that moves over time, and every StreetEasy price event is a noisy observation of it.

## What the data gives us

- **Price observations:** about 382,000 once same-day duplicates and moves under 1% are collapsed, against 214,921 rows today. The raw count is 501,000; it is inflated by feeds that flip by a dollar, one of them 607 times.
  - 64.7% of ads have one price, 21.6% have two and 13.7% have three or more.
  - 61,375 rows come from unit pages, which list status events but no separate price changes. They undercount changes (1.32 vs 1.96 prices per ad), so the model needs a source flag.
- **Asks fall during a listing, and they fall systematically.** 72% of multi-price ads end below their first ask. The median first-to-last change is −3.4%, the p10 is −12.8% and the p90 is +8.0%. 70% of changes are cuts, with a median of 3%. The median time on market is 13 days (p90 55).

So the price changes in an ad are not independent draws around the latent price. They form a markdown path, and the model has to say so.

## Proposed structure

Latent ask for apartment *i* at time *t*, on the log scale. This is C's structure with the AR(1) building term:

```
log a_i(t) = x_i'β + b_j + w_j(t) + u_i + (area, season, year terms as in C)
             w_j: building AR(1), as in the arwalk fit
             u_i: unit level (C's unit term)
```

Each price event *e* of listing *l*, for apartment *i*, posted *d* days after the listing opened at *t₀*:

```
y_e = log a_i(t₀) + δ(d) + λ_l + ε_e
      δ(d): markdown curve over days on market (a 4-5 knot spline, δ(0) free)
      λ_l:  listing effect, i.e. how this landlord priced this ad (Student-t)
      ε_e:  event noise, heavy-tailed (typos land here as outliers)
```

- **What it buys.** It uses all of an ad's prices, with no first-versus-latest choice. It separates "this landlord overpriced this ad" (λ) from "this apartment is worth more" (u, b, w). That is an explanatory split, where today both are absorbed into one residual. δ(d) is directly interpretable as how much asks come down with time on market.
- **What it does not replace.** Ben's data-first rule still applies. Typos and mis-parsed prices get fixed in the data, and the heavy tails are a backstop, not the fix.
- **Deferred.** A per-unit AR(1) on top of u_i. Most units have one to three ads, so the building AR(1) plus a unit level is the parsimonious first step. Add it only if residuals show within-unit drift.

## Scoring under the evaluation framework

PSIS-LOO over events is not comparable with C's row-level LOO, because the targets differ. To compare on the same target:

- **Paired comparison.** Score every model on the log predictive density of each listing's priced row (the same row C models), leaving out the whole listing (grouped PSIS by listing). The latent model predicts that row by marginalising δ, λ and ε. Use a ~2 combined SE bar with lot-clustered SEs.
- **New buildings.** The per-building new-building scorer from PR #723, on the same rows.
- **New units.** A time-split refit against nominal 0.79/0.95 coverage.
- **On every run.** Descriptive share, plus predictive medians and intervals rather than means.

## Sequence and cost

| Step | What | Cost |
|---|---|---|
| 1 | Data improvements ships the fixed data version (in progress) | $0 |
| 2 | Refit C and the AR(1) model on it. The AR(1) runs as a longer chain with the joint ρ/σ_d sampler, so it converges | about $2 + $7 |
| 3 | Event table as its own data version: price events per listing, with same-day and sub-1% collapse rules and the source flag, through Data improvements' review | $0, a few hours |
| 4 | Event-layer model module (λ_l as a grouped effect, δ spline), with a CPU recovery test and a reviewed PR | $0, hours to a day |
| 5 | One fit at about 382,000 observations | $3 linear extrapolation; budget $5-8 for listing-effect mixing, plus a possible retry |

Total: about $15-25 of Modal over 2-4 days of limiter credit, with no new Oxylabs spend.

## Rough predictions (step 5 vs the step-2 AR(1) model, same scored rows)

- Listing-level lpd: +100 to +400 nats. Most of it comes from listings with 2 or more prices, whose latent level is better pinned.
- λ_l scale: 0.04-0.07. δ(0), the first ask above the eventual level: +2% to +4%.
- New-building miss: unchanged ±0.1 pp, since a new building has no events.
- Descriptive share: roughly −1 to −2 pp, as listing-specific pricing leaves the building and unit terms.

## Risks

- **Mixing.** About 76,000 multi-price listings add listing effects, and the AR(1) fit already mixed slowly.
- **Unit-page undercount.** It biases δ unless the source flag is in the model.
- **Event feeds.** Some reprice by a dollar many times; the sub-1% collapse rule matters.
