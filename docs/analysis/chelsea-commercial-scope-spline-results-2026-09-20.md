# Cumulative scope-review refit results

The nine-ad source revision passes a full matched PyMC refit and comparison
against the originally selected expanded-floor fit. The selected main model
has not changed; candidate UI and residual movement review remain pending.

All primary, derived-effect and floor diagnostic gates pass with four chains,
4,000 warmup and 6,000 retained draws per chain, zero divergences and zero
depth-limit hits. Exact archived-code checks accept only the reviewed source
loader and copying changes; model and sampling settings are unchanged.

## Matched residuals

| Identical retained cohort | Original median absolute log residual | Candidate | Median absolute fitted-price change |
| --- | ---: | ---: | ---: |
| All 52,644 observations | 0.03508110 | 0.03505974 | $1.02 |
| 172 capture-time active observations | 0.02438805 | 0.02434049 | $1.35 |
| Fixed 26-unit floor development panel | 0.02190247 | 0.02192675 | $1.16 |

Overall and captured-current medians improve slightly; the fixed floor panel
gets slightly worse. These are in-sample descriptive differences, not evidence
of predictive improvement or a uniform benefit. The nine excluded observations
are reported separately with original-fit residuals and are not used to claim
improvement by dropping difficult cases.

The largest absolute fitted-price shift is $660.37 for advertisement 4892020
(344 West 22nd, historical ask $42,500). Next are 1540611 (520 West 27th,
−$603.25) and 1171083 (109 West 28th, −$274.91). Capture-time active shifts peak
at $16.60. These larger movements need own-source review before attribution to
specific features. A deterministic movement-review input build is running.

## Contributions and fixed checks

All 54 matched floor contrasts, 32 bedroom contrasts and 16 amenity/category
contrasts pass diagnostics in both fits. All corresponding pointwise intervals
overlap descriptively; overlap does not establish equivalence or rule out
meaningful changes. Physical bedroom contrasts hold observed area and bathroom
composition fixed and include their coupled design terms.

The fixed eight-case residual development review passes, including all case
contribution diagnostics and the joint bedroom counterfactual. The unchanged
26-unit floor panel passes identity and reference-fit ancestry checks. It is a
coverage-development panel with two units per occupied floor/elevator cell,
not a representative market sample or held-out accuracy test.

## Verified artifacts

- Fit `chelsea-bayesian-commercial-scope-spline-disk-20260920`: manifest
  `a66e8d2e0b6f6515ab29dd729263f8c441417338a8bfaf4d871a90601db12776`.
- Comparison `chelsea-commercial-scope-spline-comparison-20260920`: manifest
  `60c873d873ad3f31be46066bfa217e354af21f8e5db7b79b4ec6bb055e928754`.
- Fixed floor panel `chelsea-commercial-scope-spline-floor-panel-comparison-20260920`:
  manifest `860497d8b0d5e45a3766bccaf0c2966641688063207effe6b7326ad7f6644eb2`.
- Fixed residual review `chelsea-commercial-scope-spline-fixed-residual-review-20260920`:
  manifest `016147de4a2c41ca72989467f1e33dc6a1282732f6ab512b9cd452d162f127bf`.

All paths are under `data/model/`. Full artifact hash verification passed;
comparison session 84842 and floor-panel session 98563 both exited successfully.
See the [source revision report](chelsea-commercial-scope-projection-2026-09-19.md)
for exact evidence, retained-row checks and remaining candidate validation.
