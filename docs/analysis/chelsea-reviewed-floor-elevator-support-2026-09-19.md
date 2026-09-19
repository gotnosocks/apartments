# Floor and elevator support after source corrections

The current corrected source still supports only a narrow floor–elevator
interaction experiment. The 52,653-row elevator revision has 349 observations
with an explicit advertised floor. No unit-label inference or physical-height
assumption is introduced here.

| Elevator evidence | Known-floor rows | Units | Buildings |
| --- | ---: | ---: | ---: |
| Explicit no | 112 | 85 | 49 |
| Explicit yes | 123 | 97 | 53 |
| Unknown | 114 | 95 | 51 |

Only thresholds 2, 3, 4 and 5 have observations on both sides in both known
elevator groups. These are broad threshold comparisons, not necessarily
adjacent-floor contrasts. They establish necessary support, not identification
of every separate increment or comparability of apartment quality.

## Sensitivity to opposing elevator reports

Forty-two buildings still have both positive and negative elevator claims.
A support-only sensitivity excludes these buildings in full: 2,143 rows and
889 units, including 21 known-floor rows from 17 units in seven buildings.
This is not an adjudication that all their claims are wrong, an assumption of
constant access over time, or a change to the modeling cohort.

| Threshold `k` | All buildings: no / yes elevator buildings spanning threshold | Excluding opposing claims: no / yes |
| --- | ---: | ---: |
| 2 | 7 / 3 | 6 / 3 |
| 3 | 10 / 5 | 8 / 5 |
| 4 | 10 / 6 | 9 / 6 |
| 5 | 1 / 6 | 0 / 6 |

The only no-elevator building spanning threshold 5 is **350 West 18th Street**,
which also has opposing elevator reports. The sixth-floor tail has only two
no-elevator units: advertisement 2094316 there, and advertisement 2300836 at
240 West 15th Street. I checked all their attached descriptions: both explicitly
advertise the sixth floor and a walk-up. These are literal source claims;
they do not resolve the other advertisements' building-access conflicts.

The only source unit spanning floor thresholds 4 and 5 in the elevator group
is the previously reviewed identity at **115 West 23rd Street, #63**. Its
advertisements 4582906 and 4930926 say fourth and sixth floor respectively;
structured bedroom counts are one and three. The three attached captures retain
those contradictory floor claims. That apparent within-unit variation must not
be presented as evidence of an apartment changing physical floors or a clean
repeated-unit floor comparison. No replacement value was inferred.

At every observed threshold from 6 upward, the naive elevator×floor-threshold
column still duplicates the floor main-effect column: every observation above
the threshold has positive elevator evidence. The 12 duplicate products cannot
identify separate floor and interaction contributions. Adding a prior would
allocate an otherwise inseparable effect rather than supply evidence.

## Implication for the next experiment

Do not add an unrestricted interaction for every floor threshold. The first
candidate should concentrate on the lower-floor range represented on both sides
in both groups, and compare a small number of terms against the accepted base
model on the identical source. Treat threshold 5 as a fragile tail sensitivity,
not a well-supported extra increment. Preserve unknown status explicitly, examine
actual joint floor contrasts rather than raw coefficients, and report any change
to their induced priors. Building and unit effects remain competing explanations.
An unrestricted physical-height interaction still lacks measured height.

The exact source audit is
`data/model/chelsea-reviewed-elevator-floor-support-20260919`. It preserves
normalized row witnesses, the building/unit identities on both sides of each
threshold, the full-source counts, and the labelled sensitivity. Seven focused
tests cover known/unknown separation, distinct-unit counting, same-unit floor
variation, whole-building exclusions, source-only operation and idempotent output.

Literal review evidence is
`data/model/chelsea-floor-interaction-witness-review-20260919`: four observations
and five captures, linked to the exact current dataset, description archive and
support audit. The review applies no source patch and does not modify the running
fit. The earlier 52,704-row support report remains a historical artifact.

```sh
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m models.floor_elevator_support \
  --dataset data/model/chelsea-reviewed-elevator-analysis-20260919 \
  --output data/model/chelsea-reviewed-elevator-floor-support-20260919
UV_CACHE_DIR=/tmp/apartments-uv-cache uv run --frozen --no-sync python \
  -m docs.analysis.scripts.review_floor_interaction_witnesses
```

The [follow-up source review](chelsea-floor-access-conflicts-2026-09-19.md) checks
all 20 positive ads and seven negative examples in the seven floor-relevant
conflicting buildings. Original-payload replay preserves their elevator values;
one newly reviewed price/address conflict yields an unapplied gross-basis
quarantine recommendation. No running model inputs are changed.
