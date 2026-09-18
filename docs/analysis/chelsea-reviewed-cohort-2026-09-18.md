# Chelsea: source-scope revision and matched refit

This is the first cohort revision. The subsequent [interior-evidence iteration](chelsea-interior-evidence-2026-09-18.md)
records four further scope quarantines and the latest `-v3` fit.

The first residual-driven iteration quarantined **515 historical observations**
and refitted the same robust specification. All 13 fresh ACTIVE captures remain
in the fit. The retained cohort has **52,716 unit-months, 22,170 units and 1,136
buildings**. Raw observations and the parent analytical/model artifacts remain
unchanged.

On exactly the same retained rows, fitted values change by a median of only
**$2.36**, or **0.055%**. Residual error is essentially unchanged. The revision
improves the definition of the residential gross-rent cohort; it does not show a
large point-fit improvement from removing conspicuous errors.

## Cohort-wide screen and review decisions

The source screen covered all **53,218 historical observations** in the parent
analysis fit, reading **72,558 captured interpretations**, including 20,098
verified recovered descriptions. Consumed parquet shards were checked against
the historical source inventory. Recovered descriptions were checked against
raw-listing and body hashes and the observation's knowledge cutoff. This was a
read-only archive pass, with no new scraping.

The screen used source evidence independently of residual magnitude:

| Screen | Advertisements flagged | Quarantined |
| --- | ---: | ---: |
| Commercial-use words | 210 | 10 reviewed commercial offers |
| Explicit advertised-net-effective language | 503 | 503 unresolved gross-price-basis observations |
| Initial price changes at least fivefold within five minutes | 2 | 2 unstable initial-price targets |

There are 715 distinct flagged advertisements, with 920 flagged captures. Broad
commercial words alone do not cause exclusion. Many matches concern home offices,
nearby retail, or former commercial buildings converted to homes. Ten inspected
descriptions actually offer retail, office, gallery/artist-commercial or other
nonresidential space. Mixed live/work cases and incomplete descriptions remain
unresolved rather than automatically excluded.

The net-effective decision uses an exact allowlist of the 23 positive statement
forms reviewed in this frozen screen. New forms cannot silently expand the
decision set. This is a quarantine of an unresolved gross-price basis, not a
claim that all 503 structured prices are definitely net figures. The descriptions
were often captured later than the initial price events; the original gross
terms may require additional reconstruction. This also extends the existing
cohort's exclusion of known concession advertisements to explicit textual evidence.

The rapid-change screen requires the first price to match the modeled initial ask
and UTC calendar date, followed by a distinct event within 300 seconds and at
least a fivefold change. It found the same two cases that motivated the review:
$1,500 → $15,000 after 23 seconds, and $30,950 → $3,095 after 79 seconds. These
initial targets are quarantined; their raw prices have not been overwritten with
the later values. The narrow screen does not establish that no other price-entry
problems exist.

Every decision identifies the analytical observation and advertisement, action,
author, reason and source evidence. The decision bundle is bound to the exact
parent dataset. It changes membership only: no whole-unit removal, address
reassignment or inferred replacement rent. Its recording time becomes part of
the revised dataset/model knowledge cutoff. The excluded records are retained
with their decisions in `dataset/quarantined.jsonl`.

## Matched residual and contribution comparison

Both columns below evaluate the **same 52,716 retained observations**. The parent
model's metric on the original larger cohort is deliberately not the comparator.

| In-sample diagnostic | Parent fit | Revised fit |
| --- | ---: | ---: |
| Log RMSE | 0.122783 | 0.122811 |
| Median absolute percentage error, relative to ask | 6.168% | 6.179% |
| Mean absolute dollar residual | $484.88 | $485.02 |
| Current 13-capture median absolute percentage error | 5.888% | 5.921% |

The largest individual fitted-value change on retained rows is about $410,
despite the small median. That heterogeneity remains available in the saved
models and updated residual report.

| Conditional feature contrast | Parent fit | Revised fit |
| --- | ---: | ---: |
| Building laundry → in-unit laundry | +5.005% | +4.990% |
| Part-time → full-time doorman | +4.739% | +4.935% |
| Pets not allowed → allowed, restrictions unknown | +1.457% | +1.486% |
| Pets not allowed → approval required | +3.093% | +3.030% |
| Room AC → central AC | −0.750% | −0.768% |

These are contrasts under the chosen regularization and group effects, holding
other encoded inputs fixed. They are not causal effects or standalone renovation
returns. Small changes under this cohort revision do not override the earlier
penalty-sensitivity findings, especially the instability of doorman attribution.
The present fit includes 2025–2026 and current captures, so its numerical levels
also need not match earlier pre-2025 development fits.

The robust loss likely limited the influence of the most extreme prices; that
is an interpretation of the small fitted-value changes, not an independently
isolated causal result. The main benefit of this iteration is explicit source
scope and an auditable review path.

## Reproduction and checks

- Screen: `data/model/chelsea-analysis-scope-audit-20260918`.
- Decisions and their reproduction script:
  `data/model/chelsea-analysis-scope-decisions-20260918`.
- First revised fit: `data/model/chelsea-reviewed-analysis-20260918-v2`.
- Revision protocol SHA-256:
  `a3bda314c12bf8e56d9980deb810f08e4ebfa4df557331aea43f79d48a922587`.
- Updated [residual report](../../data/model/chelsea-reviewed-residuals-20260918/report.md).

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python -m models.refit_analysis_revision \
  --parent-model data/model/chelsea-current-analysis-20260918/model \
  --dataset data/model/chelsea-current-analysis-20260918/dataset \
  --decision-bundle data/model/chelsea-analysis-scope-decisions-20260918 \
  --output data/model/chelsea-reviewed-analysis-20260918-v2
```

The optimizer converged with relative objective change `2.38e-8`. All 52,716
portable fitted values match the scientific encoder within $0.000000000088.
The full suite passed **545 tests with two skipped**; targeted tests additionally
verified that quarantining an entire edge month updates training-date metadata.
The first development refit's parameter/results comparison is identical; v2
adds correct date-extent metadata behavior for such future cohort revisions.

Tests cover source-date/value/time/ratio checks, preserving ambiguous commercial
contexts, duplicate or mismatched decisions, retaining raw prices, fitting actual
revised rows, matched evaluation denominators and verified replay without refits.

Next priorities are to inspect remaining large residuals and audit recurring
omitted features, including duplex/layout, ceiling height and light. Unresolved
source prices and mixed-use/price-basis cases remain visible review work rather
than assumed corrections.
