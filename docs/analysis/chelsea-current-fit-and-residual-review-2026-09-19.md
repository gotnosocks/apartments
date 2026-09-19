# Current Chelsea fit and residual review

The 52,863-observation PyMC floor-increment fit completed successfully, including
recovery of its existing draws from a stalled trace reader. No resampling was
needed. The verified report covers 22,189 units, 1,131 buildings and **172 current
captured listings**. Four chains retain 6,000 draws each after 4,000 warmup.

| Diagnostic family | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
|---|---:|---:|---:|
| Model parameters | 1.00593 | 905 | 1,617 |
| Unit and bathroom contributions | 1.00541 | 1,245 | 2,132 |
| Joint floor contrasts | 1.00211 | 1,795 | 3,506 |

All gates pass, with zero divergences or maximum-depth hits and minimum BFMI
0.437. The complete fit is `data/model/chelsea-bayesian-current-floor-disk-20260918`;
the source/posterior-verified report is
`data/model/chelsea-bayesian-current-floor-review-20260918/report.html`.

Median absolute fitted log residual is 0.03509 across the full cohort. Among the
172 current rows it is 0.02458; median absolute ask-versus-fit difference is
2.48%. Four current asks differ from their fitted medians by more than 10%.
These are **in-sample** residuals: current asks participated in fitting and unit
effects absorb persistent unexplained attributes. They are not prediction-error
estimates, proof of a good deal or evidence that the model has explained every
feature.

## Eight largest current absolute log residuals

Every case below was reviewed against its captured description. Its individual
joint-posterior contribution diagnostics pass.

| Advertisement | Ask | Fitted median | Ask / fit − 1 | Source finding |
|---|---:|---:|---:|---|
| 5155021, 251 West 26th #2B | $3,450 | $2,885 | +19.6% | Structured studio conflicts with explicit one-bedroom description |
| 5116119, The Milan | $8,500 | $7,174 | +18.5% | Previously masked bathroom composition conflict; private terrace is a candidate omitted attribute |
| 5155202, 244 West 16th | $4,000 | $3,487 | +14.7% | Explicit first-floor apartment and renovation claims absent from floor/condition modeling |
| 5161975, 303 West 21st | $4,850 | $4,266 | +13.7% | Studio description agrees; area unknown; no new numeric correction established |
| 5159492, 239 West 26th | $3,750 | $4,129 | −9.2% | Renovation and windowed kitchen/bath are candidate attributes; no count conflict |
| 5128483, 777 Sixth | $4,963 | $5,460 | −9.1% | Building template and recurring fees; 32-story building wording is not the unit floor |
| 5115645, 249 West 29th | $6,950 | $6,326 | +9.9% | Private elevator, loft height/layout, third floor and south exposure; description rent remains stale |
| 5163034, 232 West 24th | $5,800 | $5,291 | +9.6% | First-floor and renovation claims; in-unit laundry already represented |

The full records, source hashes, captures and decompositions are in
`data/model/chelsea-current-residual-source-review-20260918/cases.jsonl`.
This is a residual-selected development review, not independent validation of
new features. Proposed attributes need source-scope validation and matched
model comparisons before coefficient interpretation.

## Studio versus one-bedroom source conflict

For 5155021, the own captured listing has `bedroomCount=0` and `roomCount=1`;
the parser and analytical row preserve those values. Its description begins
“Chelsea 1 Bedroom at this price?!” and describes a queen-sized bedroom.
It also says the photos are of the same line. The captured media has no floor
plans or video. Those claims do not establish the actual apartment layout.

Under the fitted joint posterior, changing only reported bedrooms from zero to
one gives:

| Conditional scenario | Median modeled rent | 95% credible interval |
|---|---:|---:|
| Studio encoding | $2,885 | $2,684–$3,133 |
| One-bedroom encoding | $3,665 | $3,411–$3,980 |

The joint scenario difference is $780 [$725, $847], or 27.03%
[26.52%, 27.54%]. Date, building and unit offsets and unspecified source inputs
remain fixed. Area is unreported, so the model uses its bedroom-specific
reference-area encoding; this is not a fixed-square-footage renovation value.
The scenario does not refit the unit effect, establish a causal bedroom premium
or identify which source count is correct. Withhold a bargain/premium conclusion
for this listing while the contradiction remains unresolved.

Scenario evidence:
`data/model/chelsea-current-residual-source-review-20260918/bedroom-source-scenario.json`.

## Broader bedroom wording screen

A screen of all 172 current captured descriptions identifies 20 rows with an
explicit numbered bedroom phrase differing from the structured count. Manual
scope review classifies 13 as building-wide inventory, two as fractional layout
marketing plus building inventory, two as denied conversions, one as an
alternative layout, one as a flex/alcove studio, and one as the unresolved
5155021 contradiction. Decimal wording is preserved as `1.5`, never accidentally
parsed as five bedrooms or automatically converted into an integer correction.

Evidence: `data/model/chelsea-current-bedroom-claim-review-20260918`. This limited
phrase screen does not prove that all other bedroom counts are accurate. It
motivates tests of alcoves, dens/home offices and convertible layouts separately
from reported bedroom thresholds, with special care around building templates
and conversion restrictions.

The main analysis now selects this verified current fit, with its exact source
archive and the eight source reviews bound in `config/main-analysis.json`.
The table and selected-apartment/scenario views display the review notes and
count-conflict warnings. Real-data AppTest verified all 172 current listings,
eight notes and the $3,665 one-bedroom scenario without model/evidence mocks.
The 17 historical floor masks and one laundry correction are published as a
later source revision and have not yet been fitted. The GPU
benchmark continues on the original matched source/model; no backend ranking is
established.

Exact research scripts are saved in `docs/analysis/scripts/` and in the artifacts.
Run from this checkout with `PYTHONPATH=.`, `UV_CACHE_DIR=/tmp/apartments-uv-cache`,
`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` and `uv run --frozen --no-sync python`.
