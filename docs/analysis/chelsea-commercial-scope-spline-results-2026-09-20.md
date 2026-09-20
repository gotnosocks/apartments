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
specific features. The deterministic 27-case movement-review input build is
complete (manifest `cd8d5229dd8dc83ec3058ebe9f7828422caab22b5b913c83a2da70c8ac546031`).
Eleven cases have exactly matching observation rows and description records in
the previous movement panel; sixteen require new case review. Review remains
in progress.

### Newly verified location conflict

The fifth largest building-contribution movement example, advertisement
2938067, exposes an unresolved location association. Both archived captures
(45451 and 122998) report **322 7th Avenue #3F, Manhattan ZIP 10001**, while
their complete descriptions identify **Park Slope**, the G/F station, Prospect
Park and Brooklyn Public Library. Raw listing IDs, payload hashes, description
hashes and complete source capture membership all match the review input.

Its historical initial ask is $2,275; the candidate fitted value is $3,634.91
(latent 95% interval $2,700.05–$4,714.77), up $27.45 from the reference fit.
The source contradiction, rather than that residual or price movement, supports
an exact-ad location-conflict quarantine. No replacement address, price or floor
has been inferred, and no sibling advertisements are implicated by this finding.
The proposed quarantine is recorded but **not applied** to either model source.

Verified evidence bundle `chelsea-2938067-location-review-20260920` has manifest
`e69a5bd1af646ff887b564294ed13beaa4a3ff9189a4c34ce498828c1e890042`.
It includes both raw payload witnesses, the reviewed case, literal spans and
the reproducible verification script. The nine-ad candidate still contains
this unresolved case; main-model promotion remains pending the broader review.

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
