# Cumulative scope-review refit results

The nine-ad source revision passes a full matched PyMC refit and comparison
against the originally selected expanded-floor fit. The selected main model
has not changed. Candidate UI validation and the absolute-residual tail review
are complete; reviewed source issues still require subsequent projection work.

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
All 27 cases are now reviewed. Eleven reuse prior adjudications only after
exact observation-row and description-record equality checks; sixteen have new
full-description reviews. The verified review manifest is
`84dcb32bafd0cd94ea796d2a788f98d9c523101099fa4f8e4ebf339aa4293002`
in `chelsea-commercial-scope-movement-review-20260920`.

The largest price-shift cases include a whole townhouse (4892020), an explicitly
mixed live/work offer (1540611), and a month-to-month rental (1171083). The latter
two warrant terms/scope sensitivity, not automatic commercial-only exclusion.
Private pools, car lifts, terraces, furnished short leases and en-suite bathrooms
appear elsewhere in the panel. These are research leads rather than explanations
proven by the fitted residuals.

Two new bathroom composition conflicts are verified against archived raw data:

- **1741581:** analytical four full baths and zero half baths versus explicit
  prose two baths and two powder rooms in a triplex.
- **4730943:** analytical two full baths and two half baths versus a layout
  summary of two full baths and one powder room. A later studio/full-bath phrase
  makes room enumeration ambiguous, so no automatic count replacement is justified.

The unusual two-bedroom/3.5-bath composition for **4681420** is explicitly
corroborated by its description. **2851560** supplies 3,840 interior square feet
despite missing analytical area. Neither claim is yet a time-resolved physical
measurement. These distinctions matter before attributing unusually large unit
effects to unmodeled amenities. Both bathroom cases and the missing-area case
were verified against all four attached raw captures and their archived HTML.
The raw descriptions were encoded references; reparsing resolves the exact
reviewed text while every non-description payload field remains identical.
Evidence bundle `chelsea-movement-measurement-review-20260920` has manifest
`31e0312b6b18523d6207ec553b42839e3fc6d76ea8da1d92bf00db2ab5bd6237`.
Identical replay passes. No count or area correction has been applied.

A separate deterministic top-15 distinct-unit absolute-residual input build is
complete. Every selected source row and capture record exactly matches a case
in the previously reviewed tail panel; all fifteen adjudications were carried
forward with the new ranks and residuals. The movement panel is selected by
changes between fits and does not substitute for this residual-tail check.

Tail input manifest: `d20c4decb25e8f07d92c1aa661c45e547939d3b5fa284a92816df894d44a7265`.
Tail review manifest: `9781220f989be741e24a893e6bf2220e75fb799760be311f14a6d4aa35d9d6a3`.
Unresolved price/identity cases, income-restricted offers, an SRO/shared-bathroom
case and retrospective attribute timing remain unresolved. Reuse verifies
unchanged evidence, not correctness of these observations.

The candidate page validation also completed successfully: 52,644 rows,
172 capture-time active rows, 35,989 known-floor rows and eight reviewed cases.
Its source-conflict warning survives the counterfactual interaction and the
selected main configuration remains unchanged. Validation manifest:
`b03cf16a8358418c550c9bf7f125552b3ecacce0567a62fabf76803891662724`.
The next source revision should incorporate reviewed location exclusions and
the prepared direct-floor evidence, preserving unresolved measurement conflicts
explicitly rather than allowing model convergence to stand in for data review.

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
