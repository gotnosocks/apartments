# Floor–elevator support after label expansion

The expanded source improves support for lower-floor comparisons in both
elevator and walk-up buildings. It does not create evidence for a walk-up
effect above floor 6. This is a source-support audit, not a fitted interaction
or an estimate of an elevator premium.

The comparison uses the same 52,653 observations and 22,155 units before and
after the reviewed floor projection. Only the modeled listed-floor values
change; these combine explicit claims and label-derived proxies, neither of
which should be described as measured height above ground.

| Elevator evidence | Known-floor rows before → after | Distinct units before → after | Buildings before → after |
|---|---:|---:|---:|
| No elevator | 1,346 → 1,502 | 747 → 840 | 229 → 241 |
| Elevator | 21,454 → 26,575 | 7,889 → 10,087 | 338 → 360 |
| Unknown | 7,107 → 7,915 | 2,921 → 3,334 | 515 → 538 |

Groups are observation-level evidence categories. A unit or building can appear
in more than one group across its observations; the distinct counts must not
be added as disjoint populations. Repeated advertisements are not independent
units.

Both versions contain 42 buildings with opposing known elevator claims,
covering 2,143 observations and 889 units. A sensitivity audit excludes those
buildings from the support calculation without changing the fitted cohort or
adjudicating their claims. In the remaining buildings, both elevator groups
have observations on either side of thresholds 1 through 5. Walk-up buildings
spanning thresholds 1, 2, 3, 4, and 5 increase respectively from
26/81/81/53/5 to 31/88/90/63/7. Thus the floor-5-to-6 part remains much thinner
than the lower-floor comparisons. Neither source has walk-up observations
above floor 6.

The same-unit floor contrasts are almost entirely absent, as expected for a
largely fixed unit attribute. These data primarily compare different units
within buildings. A model with unit effects therefore depends on its pooling
assumptions for the floor association; this support table does not establish
identification independent of those assumptions or a causal effect.

For the next interaction experiment, focus the walk-up contrast on the shared
lower-floor support and assess pooling/prior sensitivity. Retain explicit
unknown-elevator handling and examine the opposing claims. Do not extrapolate
a fitted walk-up curve to high-rise floors as an empirically supported result.

Artifact: `data/model/chelsea-expanded-floor-elevator-support-20260919`.
The exact source hashes are embedded in `support.json`. Reproduce with
`uv run --frozen --no-sync python -m docs.analysis.scripts.compare_expanded_floor_support`.
The audit uses the existing `models.floor_elevator_support` summaries and does
not modify model code, data, or main-analysis selection.
