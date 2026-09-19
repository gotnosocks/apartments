# Elevator source corrections: completed refit

The corrected PyMC fit retains all **52,653 observations, 22,155 units, 1,129
buildings and 172 current listings**. It applies 98 reviewed historical elevator
corrections: 96 positive claims become negative and two structured/text conflicts
become unknown. Prices and membership are unchanged. The exact inverse restores
the selected price-basis-reviewed parent. Raw captures remain untouched.

The source, prior scales, sampler settings and implementation differences were
reviewed separately. Both fits use four chains, 4,000 warmup and 6,000 retained
draws, seed 20260924, nutpie/Numba diagonal adaptation, target acceptance .93,
shared Student-t noise and the same floor-increment/bathroom-balance model.
Elevator normalization changes its raw-contrast prior SD from .59216 to .58218;
the comparison is not presented as holding that induced prior exactly fixed.

## Numerical checks

The refit completed at **10:48:49 UTC on September 19**. All gates pass:

| Diagnostic family | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
| --- | ---: | ---: | ---: |
| Parameters | 1.00845 | 783 | 1,434 |
| Unit/bathroom contributions | 1.00185 | 1,096 | 2,021 |
| Joint floor contrasts | 1.00093 | 2,052 | 3,280 |

There are no divergences or tree-depth hits; minimum BFMI is .44066. All 16
supported category contrasts and all three joint elevator/reporting contrasts
also pass. Complete posterior, trace, source and code bindings are preserved.

## Contribution changes

The known no-elevator → elevator conditional association changes from
**+3.33% [2.33%, 4.35%] to +2.91% [1.88%, 3.96%]**. The median change is −.414
percentage points and the intervals overlap. This is a conditional model
association, not a causal renovation return or a personal willingness to pay.
The contrast combines the saved coefficient and each fit's actual normalization.
Its candidate bulk/tail ESS are 940/2,066 and R-hat is 1.00272.

Known no → unknown reporting changes from +1.42% [.92%, 1.92%] to
+1.24% [.75%, 1.72%]. Known yes → unknown changes from −1.85%
[−2.69%, −1.02%] to −1.64% [−2.52%, −.74%]. These are reporting-state
contrasts, not physical amenity premiums; unknown does not mean absence.

The six corrected buildings' common-reference median log offsets increase by
.01674 (120 West 25th), .01025 (120 West 20th), .00975 (124 West 25th), .00728
(126 West 25th), .00119 (259 West 19th) and .00054 (266 West 22nd). Their
before/after intervals overlap. The largest unit-offset movement, +.02079 log
points, is 259 West 19th #2NW: two historical observations are corrected from
positive to negative elevator claims, while its older observation remains unknown.
These are differences between independent posterior summaries; draws are not
paired to produce an interval for the change.

Category median changes stay below .131 percentage points. The largest adjacent
floor median change is .274 points (20→24); sparse upper-floor limitations
remain. This comparison supplies no new evidence that every floor term is needed.

## Residuals and reviewed movements

| Slice | Rows | Median absolute log residual, before → after | Median absolute fitted-dollar change |
| --- | ---: | ---: | ---: |
| All identical observations | 52,653 | .0349924 → .0349781 | $1.19 |
| Corrected observations | 98 | .0468606 → .0518848 | $94.76 |
| Current listings | 172 | .0242320 → .0246832 | $1.70 |

The correction does **not** uniformly reduce residual error. Corrected-row and
current median errors rise slightly. Source truth is not chosen to minimize
in-sample error; the justification for adopting the revised source is the
literal evidence and exact reviewed corrections.

The three largest current movements were reconstructed from both complete joint
posteriors; all contribution diagnostics pass:

| Advertisement | Asking rent | Earlier fitted median | Corrected fitted median |
| --- | ---: | ---: | ---: |
| 5116119, The Milan | $8,500 | $7,179.39 | $7,167.11 |
| 5150952, One High Line | $22,000 | $22,241.60 | $22,251.87 |
| 5133650, One High Line | $21,000 | $20,608.33 | $20,618.51 |

The maximum current movement is $12.28. For The Milan, a +.00174 change in the
building mean-log contribution is offset by smaller negative changes in the
intercept, reporting, unit and other terms; the net mean-log change is −.00134.
Its source bathroom-composition conflict and terrace/finish omissions remain
flagged. The small fitted movement does not resolve them or establish a bargain.

The largest common-row fitted movement is $714.24 for the previously reviewed
single-observation townhouse at 344 West 22nd, advertisement 4892020. Its unchanged
$42,500 ask is associated with a fitted median $30,625.84 → $31,340.08, but the
95% intervals remain extremely broad: [$10,477.45, $43,627.41] →
[$10,461.99, $43,650.25]. Its largest common-reference building-offset movement is
+.02418 log points. The source still has one unit and one observation; this is
not a precise correction or an independently identified building premium.
See the [earlier source and contribution review](chelsea-source-movement-review-2026-09-18.md)
for the weak building/unit separation and material Monte Carlo uncertainty.

All eight leading absolute current residual cases retain their identities. Their
source packets and joint posterior details were regenerated; all case diagnostics
pass. The ambiguous studio-versus-one-bedroom source case's conditional bedroom
scenario remains about +27.04% [26.52%, 27.55%]. That scenario does not adjudicate
its true layout. Existing bedroom/bathroom interpretation limits are preserved.

## Artifacts and next experiment

The selected fit/source pair is
`chelsea-bayesian-reviewed-elevator-disk-20260919` /
`chelsea-reviewed-elevator-analysis-20260919`, with
`chelsea-elevator-current-residual-source-review-20260919`. Selection is verified
through `apartments.main_analysis`; its configuration is the authoritative state.
The result is an evidence-corrected baseline, not proof of complete source accuracy.
Forty-two buildings still have opposing elevator reports.

Comparison artifacts under `data/model/`:

- `chelsea-reviewed-elevator-fit-comparison-20260919`
- `chelsea-reviewed-elevator-category-contrasts-20260919`
- `chelsea-elevator-current-contribution-movements-20260919`
- `chelsea-elevator-current-residual-source-review-20260919`

The [lower-floor interaction candidates](../model/lower-floor-elevator-interactions.md)
are a separate representation experiment on this same source. Their pooled model
has passed full-data compiled graph equivalence, but remains unfitted. Main-reader
integration must explicitly load its additional terms and joint floor/access
contrasts before it can become an analysis candidate.
