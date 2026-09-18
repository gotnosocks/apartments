# Chelsea: interior evidence and the next residual iteration

The interior screen covers the 52,716 observations in the first reviewed fit.
It found recurring ceiling-height, layout and skylight wording across the cohort,
not only in the motivating duplex listing. Source review also found four more
observations whose offer terms are incompatible with the standard rental cohort.
These were quarantined through a second versioned decision bundle before refitting.

## Evidence coverage

The read-only pass inspected 71,929 captures, including 19,858 recovered
interpretations. Resolved descriptions exist for 52,301 analytical rows. At least
one interior candidate occurs in 7,055 rows, with 9,570 matching captures.

| Candidate wording | Analytical rows | Distinct units | Buildings | Residual-queue rows | Current rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Numeric ceiling measurements | 3,990 | 2,253 | 434 | 9 | 2 |
| Levels, duplex or triplex | 1,986 | 993 | 347 | 7 | 3 |
| Floor-through / floor-thru | 1,072 | 614 | 230 | 1 | 0 |
| Skylight / skylit | 1,052 | 557 | 250 | 2 | 1 |

Categories overlap. Counts describe text candidates, not verified physical feature
prevalence. Repeated captures count once per analytical row in the table.
The screen preserves exact Unicode text offsets, context, measurement notation,
source identities and hashes, capture clocks, and recovered-description clocks.
It does not change model inputs. Unmentioned features remain unknown.

Advisory flags identify possible room-specific, shared/building, multiple-unit,
negated, hypothetical and renovation-related wording. Flags require interpretation:
“newly renovated” does not mean a renovation remains planned, and an unflagged
sentence is not automatically a verified unit assertion. Forty-five rows have
inch-mark measurements; 382 have mixed feet/inches, 38 have measurement ranges,
and 80 have differing height candidates within a captured description. These
categories overlap. No inch mark is silently converted to feet. Numeric words,
unusual separators, and some bound qualifiers are not fully normalized yet.

The motivating current advertisement **5153890** explicitly says duplex across
the fourth and fifth floors and 18-foot ceilings in a skylit living room. That
height is room-specific. It also says photos precede renovation and work is in
progress; its claimed readiness date does not verify completion. Current ads
5154603 and 5155651 also advertise duplex layouts. This is enough recurring
evidence to investigate a layout family, but it does not establish a price premium.

Floor-through candidates retain the requested spelling variants. The screen
makes no automatic street/courtyard or north/south exposure inference.

## Four additional scope decisions

Full-description inspection of the residual-queue matches supports these
observation-specific quarantines:

| Advertisement | Source evidence | Decision reason |
| --- | --- | --- |
| 2164893 | Exhibition galleries, receptionist/catalog station, offices and display/storage facilities | Nonresidential gallery offer |
| 3238122 | Explicit commercial condo loft configured as office space | Nonresidential office offer |
| 4293119 | Furnished flexible leases of 30+ days, duration-dependent custom pricing and vacation-rental terms | Furnished flexible-stay offer |
| 896891 | Furnished apartment available only Thursday through Sunday | Partial-week occupancy offer |

An inspected artist loft, advertisement 3263692, remains: its description explicitly
offers a studio/residence. Commercial-looking language alone is insufficient to
exclude it. Other unresolved source prices remain unresolved. No rent was replaced
with a value inferred from the model.

Decisions retain author, reason, exact quoted evidence, capture/body/raw-description
hashes, and recording time. They affect only the identified analytical observations.
Historical descriptions were often captured after initial price events, so these
are scope quarantines, not claims about a known dated conversion or renovation.
This review is agent adjudication of a bounded residual sample, not a complete
cohort scope audit or a population extraction-accuracy estimate.

## Reproducible artifacts

The revised fit contains **52,712 observations, 22,166 units and 1,135 buildings**,
including all 13 current captures. Comparing both fits on exactly these retained
rows, median absolute fitted-value change is **$0.32** (0.0078%); the maximum is
$158.86. Median absolute percentage residual is essentially unchanged at 6.18%.
The building-to-in-unit laundry contrast moves from 4.990% to 4.998%; part-time
to full-time doorman moves from 4.935% to 4.930%. These remain conditional,
regularization-dependent contrasts, not causal premiums. The four exclusions
improve target comparability without demonstrating a large model-fit improvement.

The fit converged at relative objective change `2.37e-8`. All 52,712 portable
fitted values agree with the scientific encoder within $0.000000000081. The
revision protocol SHA-256 is
`7439173da7e6973752829aa5347c239ed1257b2d65211c9478050fe9981a209c`.

- Screen and exact implementation:
  `data/model/chelsea-interior-evidence-20260918`.
- Decisions and reproduction script:
  `data/model/chelsea-interior-scope-decisions-20260918`.
- Second reviewed fit:
  `data/model/chelsea-reviewed-analysis-20260918-v3`.
- Updated [residual report](../../data/model/chelsea-interior-reviewed-residuals-20260918/report.md).

```sh
.venv/bin/python -m models.interior_feature_audit \
  --dataset data/model/chelsea-reviewed-analysis-20260918-v2/dataset \
  --archive /data1/apartments/archive/datasets/chelsea-granular-20260917-canonical-url-v1 \
  --historical data/exports/chelsea-serving-history-20260918-asof1600 \
  --recovery data/exports/chelsea-description-recovery-20260918 \
  --refresh data/probes/chelsea-candidate-refresh-20260918 \
  --residuals data/model/chelsea-reviewed-residuals-20260918 \
  --output data/model/chelsea-interior-evidence-20260918

OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python -m models.refit_analysis_revision \
  --parent-model data/model/chelsea-reviewed-analysis-20260918-v2/model \
  --dataset data/model/chelsea-reviewed-analysis-20260918-v2/dataset \
  --decision-bundle data/model/chelsea-interior-scope-decisions-20260918 \
  --output data/model/chelsea-reviewed-analysis-20260918-v3
```

The screen's exact rerun verified and reused the original artifact. The full
regression suite passed **572 tests, with two skipped**. New tests cover lexical
scope/measurement edge cases, Unicode separators, recovery identity and knowledge
clocks, current body tampering, whole-cohort source binding and deterministic replay.

## Next model comparison

Review a stratified sample across ordinary and residual-tail apartments before
converting candidates into model columns. Preserve room-specific heights, ranges,
conflicting captures and planned work. Compare a known-height magnitude term with
a reporting/missingness-only control, using the same retained cohort and fixed
building/unit shrinkage. Duplex and skylight positives with unknown negatives
initially support advertised-feature associations, not a clean physical
presence-versus-absence premium. Inspect both feature contrasts and residual
changes beyond the listings that motivated this audit.
