# Building attributes, NYC only: results (converged)

*Fit 2026-10-20. This is the converged normal-walk model with no location term (base fit ea4bcbd6), plus five building attributes coded as 12 columns, each with a Normal(0, 0.5) prior. NJ is dropped, at Ben's request, until its data are as good as NYC's. The model is in PR #1176, the NYC-only dataset in #1177 (`b0-30b3edae310c2fae-alldata-v36-dense-nyc`: 1,896,486 rows, with 72,598 NJ rows set aside), and the budget estimate fix in #1178. Nothing on the served model or the site changed.*

## The attributes

The per-building snapshot is `/data1/apartments/external/building-attrs/20261020-0a7254f/attrs.parquet` on thelio. It comes from MapPLUTO and the StreetEasy ad fields.

| Attribute | Coding | Source |
|---|---|---|
| Floors | log floors, plus an unknown flag | the building's ads first, then PLUTO. PLUTO gets towers on shared lots wrong (8 Spruce: 8 floors in PLUTO, 76 in the ads) |
| Elevator | yes / no / unknown | the ads first, then the PLUTO building class |
| Doorman | full time / part time / virtual / none stated | ads |
| Tenure | condo / co-op / rental | PLUTO building class |
| Era | before 1980 / 1980–2004 / 2005 on / unknown | PLUTO year built |

**How they were chosen.** On held-out buildings, these five explain 23% of the base fit's between-building residual variance, and 7.5% within neighbourhoods. Two candidates were dropped because they add under 0.3% within a neighbourhood, so they mostly stand in for location:
- landmark or historic district;
- unit count.

## Run

- Run `building-attrs-b0-latest-041e6aa9-dense-w1500`, fit-only, one seed.
- 16 chains, 1500 warmup steps and 500 draws.
- 25 min, $1.00 (settled ledger figure).
- **Converged:** max R-hat 1.004 (τ), min ESS 2,108, 0 divergences while sampling.

## Building premiums (posterior medians)

| # | Term | Predicted | Result |
|---|---|---|---|
| B1 | Elevator | +6 to +22% | **+12.2%**, hit |
| B2 | Condo building | +6 to +22% | +5.9%, narrow miss |
| B3 | Co-op building | +3 to +16% | 0.0%, miss |
| B4 | A building e times as tall (roughly 5 → 14 floors) | +6 to +16% | **+13.4%**, hit |
| B5 | Full-time doorman | −2 to +12% | +6.7%, hit |
| B6 | Virtual doorman | −9 to +1% | −1.8%, hit |
| B7 | Built 2005 on (against before 1980) | −18 to −3% | −2.5%, narrow miss |

- Part-time doorman came out at +9.4%, above full-time.
- Built 1980–2004 came out at −1.6%.

**The intervals are too narrow.** Every 90% interval is under 0.5 points wide, but the model treats each ad as independent, and ads in one building share a lot. The real uncertainty on each building term is much wider.

**Co-op and the era terms probably carry location.** The model has no location term. The newest buildings sit disproportionately in cheaper areas, and co-ops in specific neighbourhoods.

## The unit terms moved (predictions missed)

I expected the building terms to change little else. Instead the bedroom and bath terms moved by more than the 4 points allowed (B9):

| Term | Base fit | This fit |
|---|---|---|
| 1 → 2 beds | +1.5% | **+14.2%** |
| Studio → 1 bed | +20.7% | +25.5% |
| Second full bath, 2 beds | +67% | **+37%** |
| 4 beds, 1 bath against 2 | −28.7% | −24.3% |

The new values are much closer to the location fits (1 → 2 beds +13.6% and a second bath on a 2-bed +43% in the whitened-zones fit). That points to the base fit's bedroom and bath terms partly standing in for building type and location. Extra baths and bedrooms go with newer elevator buildings.

## Noise, walk and tails

| | Base (NYC rows) | This fit |
|---|---|---|
| σ by group | 0.236, 0.282, 0.284, 0.341 | 24–33% lower (B8 predicted 3–12%: miss) |
| ν | 21.5 | 6.9 |
| Plain residual sd | 0.301 | 0.245 (−19%) |
| τ | 0.0116 | 0.0074 (−36%; B10 miss) |
| 2020 trough | −24.2% | −22.5% (B10 hit) |

Because ν fell so far, the σ values don't compare one for one; the plain residual sd is the fairer comparison.

## Where the variance went (free local checks, residuals at posterior medians)

| | Base | This fit |
|---|---|---|
| Spread between buildings (buildings with 5+ ads) | 0.280 | 0.248 |
| Spread within a building | 0.149 | 0.130 |

- **Between buildings:** the drop is about what the screen predicted.
- **Within a building:** the new columns are constant inside a building, so this drop has to come from the re-estimated bedroom and bath terms. They now fit the differences between units in the same building better. That supports the new unit terms being closer to what each quality is worth, but it isn't proof.

## Caveats

- Fit-only: there is no PSIS-LOO and no grouped building holdout. So this isn't scored for model selection and isn't served.
- The intervals are too narrow, as above.
- There is no location term. Some building premiums still carry neighbourhood.

## Possible next steps (none launched; the hold applies)

1. **Add the building attributes to the building-effect model.** Each building's level would be centred on what its attributes predict, as well as on the surface. That should shrink what the building levels and the surface have to carry, which bears on the sampling problem.
2. **Fix the narrow intervals.** Use a building random effect or grouped held-out scoring before trusting the building premiums' precision.
3. **NJ:** the tax roll's storey codes raise known NJ floor counts from 30% to 77% of NJ rows. That work is parked on the local branch `nj-storeys` on thelio.
