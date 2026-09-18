# Chelsea: current refit and residual-driven source review

Following the clarified emphasis on feature contributions and residuals, the
model was refitted with **53,218 historical unit-months plus 13 fresh ACTIVE
captures**. The fit contains 53,231 observations, 22,256 units and 1,140 buildings.
The fresh captures cover 13 units in 12 buildings. This is a bounded pilot sample,
not complete current-market coverage.

Current listings are intentionally in the fit. Their residuals are descriptive
diagnostics rather than out-of-sample bargain estimates. Historical rows keep
their own dated attributes and initial asks; current rows use capture-time gross
asks. No attributes were backfilled across historical dates.

The [analysis guide](../model/current-analysis.md) documents the commands and
interpretation. The [generated residual report](../../data/model/chelsea-residual-review-20260918/report.md)
lists the current cases and both historical residual tails.

## First source audit

The queue contains 53 observations: the largest positive and negative log
residuals from 20 distinct units per tail, plus all 13 current captures. Ten
advertisements were inspected in this first targeted pass, using **18 hash-verified
archived responses**. Historical descriptions were linked to verified recovery
records where necessary. The two current cases used the newly refreshed bodies.
No additional scraping was needed.

| Advertisement | Residual signal | Source finding | Interpretation |
| --- | --- | --- | --- |
| 4818139 | $1,500 ask vs $18,673 fitted | Price changes to $15,000 after 23 seconds | Strong initial-entry correction candidate; the first historical price is a problematic modeling target |
| 2276984 | $30,950 vs $2,850 | Price changes to $3,095 after 79 seconds | Same mechanism in the opposite direction |
| 1483859 | $25,000 vs $3,890 | Explicit retail-space lease description | Commercial space in the residential cohort |
| 2555574 | $36,000 vs $4,005 | Cafe/retail sublet with commercial terms | Commercial space in the residential cohort |
| 2956338 | $1,200 vs $5,449 | Chelsea canonical identity conflicts with a North Riverdale description; rent explicitly described as net effective | Identity and price-basis conflict; correct address and gross rent unresolved |
| 652674 | $28,681 vs $3,429 | Very short full-floor description | Not enough evidence to call it commercial or replace its price |
| 2477915 | $46,917 vs $7,518 | Repeated source price, generic apartment/building description | Suspicious but no supported replacement |
| 4979243 | $999 vs $3,614 | Minimal studio description and consistent price | Cannot distinguish error, restricted rent or another omitted context |
| 5153890 | $7,000 vs $5,754 | Duplex, very high ceilings, skylight, fireplace and advertised renovation; size missing | Plausible omitted-feature/missing-size case, with renovation completion unverified |
| 5155650 | $8,200 vs $9,639 | Three bedrooms, two baths, laundry and elevator; size missing | Current negative residual remains unexplained by the available text |

The two rapid price changes are supported by matching histories in two archived
captures each. They suggest data-entry corrections, but the raw first-price
events are real source observations. A subsequent modeling rule should explicitly
handle transient initial asks rather than pretend those source events never
existed. Similar events must be audited across the cohort, not just corrected
where a residual happens to be large.

The commercial cases are supported by explicit descriptions, not inferred from
price or unit labels alone. A residential-use filter must distinguish an offered
retail/office space from an apartment near shops or with a home office. The
unresolved full-floor case is a useful guard against overbroad exclusion.

The duplex case is an example of a potential model-feature gap. Its description
supports advertised layout and ceiling/light characteristics, but does not supply
verified square footage or confirm that the advertised renovation was complete
at capture. A feature iteration should audit comparable source language across
more units and retain those distinctions.

These are agent-reviewed, residual-selected cases. They are not a random sample,
a human-labeled accuracy estimate, or proof that the proposed feature additions
will improve interpretation. **No corrections or exclusions have yet been applied
from these findings.** The next iteration is to implement and evaluate the
supported price/scope policies across the cohort, then compare residuals and
feature contrasts after refitting.

## Evidence and verification

- Analysis fit: `data/model/chelsea-current-analysis-20260918`.
- Analysis protocol SHA-256:
  `82ce3bd4e1433dbf5a7d1ca1e59b79b41c0d03cf60f2b3cc368f3176f01c4fe8`.
- Residual queue and grouped contributions:
  `data/model/chelsea-residual-review-20260918`.
- Source evidence, body hashes, descriptions and reproduction script:
  `data/model/chelsea-residual-source-evidence-20260918`.
- Reviewed findings, interpretations and proposed next actions:
  `data/model/chelsea-residual-findings-20260918`.

The refit converged with relative objective change `2.37e-8`. All 53,231 portable
fitted values match the scientific encoder to within $0.000000000073. The full
regression suite passed **540 tests, with two skipped**. The analysis fit replayed
without refitting, and the residual report replayed against its completed bundle.
These checks establish reproducibility and implementation consistency, not the
correctness of every source observation or the identification of every feature.

The separate 420-fit unfamiliar-building experiment was prepared but no fits
were launched. It is deferred because its forecasting objective is secondary to
the current residual/feature-analysis direction.
