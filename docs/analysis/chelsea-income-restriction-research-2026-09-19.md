# Income restrictions as a residual-driven research lead

The selected expanded-floor fit's fourth and eighth largest absolute log
residuals among distinct units are Port10 advertisements 4761346 and 4758015.
Their historical initial asks are $1,556 and $1,192, versus fitted medians of
$5,952 and $4,032. Both own descriptions explicitly impose household-income
brackets and maximum annual incomes. These are product/eligibility differences,
not evidence that either price should be replaced by the fitted value.

The earlier source revision deliberately retained these unresolved cases.
The present model has no dedicated eligibility representation. Before proposing
a coefficient or changing scope, I screened the full selected cohort's linked
own-advertisement descriptions for related language.

## Reproducible lexical screen

The screen verified the source/evidence bundle file hashes and checked exact
observation, unit, advertisement and capture membership plus description hashes.
It scanned **71,813 own captures linked to 52,653 observations**, skipping 252
out-of-cohort evidence rows. Six recorded patterns cover explicit income
restrictions, maximum incomes, upper-bound wording, affordable housing, housing
lotteries and area-median-income language. Minimum-income and ordinary 40-times-
rent requirements alone do not trigger a match. This is a candidate screen,
not a restriction classifier or a recall-complete inventory.

There are **12 candidate observations, advertisements and units in five
buildings**. Match contexts were reviewed; only the two Port10 cases received
the full own-description review in this pass. The archive still provides the
complete descriptions for subsequent adjudication. Nonmatches remain
unclassified, rather than becoming unrestricted-rent observations. Repeating the
same command reproduced the immutable output exactly.

| Building | Advertisement | Initial ask | Fitted median | Log residual |
|---|---|---:|---:|---:|
| Port10 | 4761346 | $1,556 | $5,952 | −1.3417 |
| Port10 | 4758015 | $1,192 | $4,032 | −1.2187 |
| 425 W18 | 3705384 | $3,499 | $3,480 | +0.0054 |
| 425 W18 | 4160254 | $2,994 | $3,035 | −0.0135 |
| 228 W17 | 4276224 | $3,400 | $3,443 | −0.0124 |
| 456 W17 | 4488024 | $2,886 | $2,965 | −0.0270 |
| 139 Eighth Avenue | 4780384 | $4,500 | $4,085 | +0.0967 |
| 139 Eighth Avenue | 4810936 | $4,800 | $4,734 | +0.0138 |
| 139 Eighth Avenue | 4837062 | $5,100 | $5,259 | −0.0307 |
| 139 Eighth Avenue | 4817705 | $4,000 | $4,174 | −0.0426 |
| 139 Eighth Avenue | 4902655 | $5,200 | $5,247 | −0.0090 |
| 139 Eighth Avenue | 4968706 | $4,250 | $4,305 | −0.0130 |

The 139 Eighth Avenue descriptions mention HDFC/120% AMI eligibility; the 456
W17 description specifies 165% AMI and a rent-stabilized lease. These are source
claims, not independently verified legal classifications. They are not equivalent
to the Port10 wording or necessarily one common pricing mechanism. Smaller
residuals do not show an absence of a discount: building/unit effects can already
absorb persistent differences.

## Next research decision

First review the exact dated price events and restrictions for the Port10 cases.
The descriptions were captured later than the initial asking-price events;
their stated thresholds must not silently be assigned to earlier dates. Retain
the distinction between minimum applicant income, an upper eligibility ceiling,
rent regulation, and the rent actually offered. Do not infer an applicable rent
by dividing an income threshold by a guessed income-to-rent multiple.

Then adjudicate the 12 candidates and search for additional wording missed by
this screen. Record explicit, negated and unknown eligibility states with source
spans and clocks. If source support permits a model experiment, compare a
reviewed restriction/product representation against a clearly defined scope
sensitivity, using the same PyMC model, full sampling, contributions and residual
panels. A single discount shared across different programs has not earned its
place from these two residuals. No current observation, price, model parameter
or selected fit was changed by this screen.

## Artifacts

- Script: `docs/analysis/scripts/screen_income_restriction_language.py`.
- Output: `data/model/chelsea-income-restriction-language-screen-20260919`, with
  complete match spans, context, capture hashes, source-row hashes and patterns.
- Source manifest:
  `d244ca6710e080e18059f1b3279a373e187ea38fb4219c51deff7e49f4604717`.
- Description archive manifest:
  `79308dfdbefd7fe8a03630bdd048fa742d0f7cd3335b82f25da0575a9d9b7e08`.
- Fit manifest for the residual table:
  `26b5dd019416cbd39839c1a4c2c9278979dd6d68e09b449f28f4d7cf4f1f6c37`.

```bash
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.screen_income_restriction_language \
  --dataset data/model/chelsea-expanded-label-floor-analysis-20260919 \
  --evidence data/model/chelsea-refreshed-bayesian-descriptions-20260918 \
  --output data/model/chelsea-income-restriction-language-screen-20260919
```
