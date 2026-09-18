# Chelsea: advertised interior features and residuals

Nine matched fits found **little additional fit improvement from ceiling height
and level count beyond reporting patterns**. The conditional advertised-height
slope is small and positive across the tested group penalties. The larger level
contrast is weakly separated from other luxury features and is not ready to be
presented as a general duplex or triplex premium.

The main reviewed analysis model remains
`data/model/chelsea-reviewed-analysis-20260918-v3`. This experiment is retained
as research; it does not replace that model or the portable scoring runtime.

## Evidence projection and source review

A conservative projection of the [interior screen](chelsea-interior-evidence-2026-09-18.md)
retains the same 52,712 observations, including all 13 current captures. It adds
advertised claims without changing prices, identities or original source clocks.
The new interpretation clock is `2026-09-18T18:24:08.929812+00:00`.

| Advertised claim | Known rows | Units | Buildings | Buildings with known-value variation |
| --- | ---: | ---: | ---: | ---: |
| Ceiling height | 1,793 | 1,065 | 330 | 117 |
| Level count | 874 | 515 | 240 | 8 |
| Floor-through wording | 724 | 441 | 192 | 0 |
| Skylight wording | 764 | 437 | 220 | 0 |

Unknown does not mean absent. Ceiling height is a scalar advertised somewhere in
the apartment; it can apply only to one room. Different accepted values across
captures, ambiguous measurements, scope conflicts or rejected candidates leave
the feature unknown. No current claim is propagated to another advertisement.
Historical descriptions were often captured later than the price events.

Development review inspected 40 deterministically selected cases—ten distinct
units per known feature—and nine rare/extreme-value or scope cases. This found
and corrected examples of window heights mistaken for ceiling heights, a child's
playroom mistaken for a duplex, floor elevation mistaken for level count, and
malformed dimensions. The final sample was inspected after those fixes; it is
not an independent population-precision estimate. The first projection artifact
is retained as a development version and was not fitted.

Strict filters also lose genuine claims. For example, the motivating current
advertisement 5153890 explicitly describes a duplex with an 18-foot skylit living
room, but the projection leaves its interior terms unknown because the text says
renovation is in progress. This experiment therefore does **not** resolve that
apartment's omitted-feature question. Refining feature-specific scope independently
of renovation status remains useful work.

## Matched comparison

Each group-penalty setting fits three variants on identical rows:

1. Existing layout, size, calendar, building/unit and amenity model.
2. That model plus indicators for whether usable interior evidence was reported.
3. The same reporting indicators plus known-only centered ceiling height and
   level count. Constant positive-only features have zero magnitude columns.

The building/unit penalties are `(2, 2)`, the existing `(10, 8)`, and `(50, 40)`.
Other penalties stay fixed. All results are descriptive in-sample diagnostics;
smaller group penalties naturally let building/unit effects fit the observed
prices more closely. Cross-row prediction and unseen-building performance are
not the objective of this comparison.

| Group penalties | Baseline log RMSE | Reporting log RMSE | Values log RMSE | Per advertised ceiling foot | Predominantly triplex vs duplex |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weaker: 2 / 2 | 0.094376 | 0.094293 | 0.094276 | +0.181% | +8.994% |
| Standard: 10 / 8 | 0.122325 | 0.122014 | 0.121983 | +0.268% | +11.702% |
| Stronger: 50 / 40 | 0.149607 | 0.149012 | 0.148975 | +0.316% | +15.232% |

At standard penalties, adding known magnitudes beyond reporting changes fitted
rent by a median absolute **$0.47**, with a maximum of **$2,953.50**. Overall
median absolute percentage residual is 6.1805% for baseline, 6.1746% for reporting,
and 6.1761% for values. These small, mixed changes do not establish a substantial
improvement in apartment comparisons. The values-versus-reporting comparison is
joint: it does not isolate the ceiling and level families individually.

Existing contrasts remain fairly similar. Building-to-in-unit laundry is
+4.998% in baseline and +4.912% with interior values; part-time-to-full-time
doorman is +4.930% and +4.983%. Their earlier identification and shrinkage
limitations still apply.

The level-count support is **one single-level row, 822 duplex rows and 51 triplex
rows**. Only eight buildings and one unit have known-value variation. Thus the
linear slope mainly reflects triplex versus duplex advertising; it cannot justify
a broadly supported single-level-to-duplex value. The ceiling slope likewise
describes an advertised association, not a causal value per added foot.

Floor-through and skylight support is positive-or-unknown. Their reporting terms
combine actual features, marketing choices and extraction selectivity; they do
not identify physical presence-versus-absence premiums. Reporting controls help
separate this issue from magnitude terms but do not remove all selection bias.

## Follow the changed residuals

Source review of the eight distinct units with the largest values-versus-reporting
fitted changes found that all advertise triplex layouts. Seven also advertise
private outdoor space. Examples include six terraces and 7,000 square feet of
outdoor space, a private garage plus garden, and a private pool and sauna.
The model does not currently represent those distinctions adequately.

Absolute residuals improved for three of those eight units and worsened for five.
For advertisement 4044056, the $29,500 ask already sat below the reporting fit;
adding the magnitude terms raised its fitted value from about $35,192 to $38,145.
For advertisement 3964188, the $29,950 ask was above the reporting fit, and the
new terms moved the fit from about $21,817 to $24,204. Neither direction proves
an error or a bargain. These cases show why a stable positive coefficient alone
is insufficient to validate its interpretation.

The next feature audit should distinguish **private versus shared outdoor space,
its area and type, and unit-specific versus shared elevator access**. Private
luxury facilities and ambiguous lease duration are additional review candidates.
Source review also identified unresolved price-basis wording in ads 3089130 and
2288458; no new source-price edits or cohort exclusions were applied here.

## Artifacts and checks

- Projection: `data/model/chelsea-interior-projection-20260918-v2`.
- Source review: `data/model/chelsea-interior-projection-review-20260918`.
- Nine fits: `data/model/chelsea-interior-experiment-20260918`.
- [Full fit/current-listing report](../../data/model/chelsea-interior-experiment-20260918/analysis/report.md).
- Eight changed-residual source reviews:
  `data/model/chelsea-interior-changed-review-20260918`.
- Protocol SHA-256:
  `c06ac9edb03af52e6699bca8eccd270ceaf1e1f77ed96e06174a185329fa17f8`.

All nine optimizations converged, with relative objective changes between
`2.19e-8` and `5.47e-8`. Saved coefficients reproduce every fit exactly. The
recomputed baseline matches the prior analysis fit within $0.006 over all 52,712
rows; the tiny difference is consistent with numerical sparse-solver assembly.
Exact projection and experiment replays completed without refitting. The full
suite passed **636 tests, with two skipped**.

```sh
OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  .venv/bin/python -m models.interior_experiment fit \
  --dataset data/model/chelsea-interior-projection-20260918-v2 \
  --review data/model/chelsea-interior-projection-review-20260918 \
  --output data/model/chelsea-interior-experiment-20260918
```
