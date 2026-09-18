# Chelsea category contrasts and feature-prior sensitivity

The accepted baseline and half-feature-prior fits give almost identical laundry and common doorman comparisons. Sparse HVAC categories move more. This tests one prior choice; the observation likelihood and building/unit priors remain unchanged.

Both fits use the same 52,711 observations, all 13 current captures, source measurements, feature design and model implementation. The feature coefficient prior multiplier changes from 1 to 0.5. The independently sampled half-prior fit uses seed 20260919 and 2,000 warmup draws per chain versus baseline seed 20260918 and 1,000 warmup draws. Each accepted fit retains four chains of 4,000 posterior draws. No posterior draws are paired across fits.

The comparison verifies identical category contrast vectors, known/unknown counts, endpoint rows/units/buildings and overlap. All 16 supported contrasts pass their own joint R-hat and bulk/tail effective-sample-size gates in both fits. The intervals below are conditional posterior associations in advertised asking rent, with building, unit, date, area and all other encoded features held fixed. They are not causal values of installing or changing an amenity.

| Recorded-category comparison | Baseline % [95% CrI] | Half feature-prior scale % [95% CrI] | Median shift, percentage points |
|---|---:|---:|---:|
| In-building → in-unit laundry | +2.399 [2.051, 2.741] | +2.397 [2.055, 2.749] | −0.002 |
| Part-time → full-time doorman | +1.930 [0.184, 3.699] | +1.901 [0.188, 3.693] | −0.029 |
| Full-time → virtual doorman | +4.209 [3.321, 5.122] | +4.211 [3.327, 5.141] | +0.002 |
| Central AC → mini-split | +6.907 [−1.722, 16.856] | +5.539 [−2.440, 14.373] | −1.367 |
| Mini-split → PTAC | −8.954 [−18.837, 1.910] | −7.183 [−16.447, 2.951] | +1.771 |

The largest absolute median shift is 1.771 percentage points for mini-split versus PTAC. Each endpoint has only eight observations, seven units and five buildings, with no shared buildings. Both intervals include zero. None of the 16 comparisons changes its interval classification as entirely positive, entirely negative or including zero; this is descriptive and does not establish equivalence between fits.

Laundry has substantial measured overlap: 21,850 in-building observations versus 15,765 in-unit observations, 285 buildings reporting both categories and 1,411 units appearing in both categories over the captured records. Those repeated-unit contrasts can reflect actual changes, listing differences or measurement problems; they are not a controlled intervention.

Doorman evidence is more constrained. Part-time and full-time have 641 and 13,241 observations respectively, but only six shared buildings and three shared units. Virtual and full-time have only four shared buildings and two shared units. The positive virtual-versus-full-time association persists under this feature-prior change. It remains a prompt to examine source labels, omitted building attributes and allocation between category/building/unit effects, not evidence that a virtual service intrinsically commands a higher price. Explicitly recorded no-doorman status has just 13 observations; the 35,930 observations with unknown doorman reporting are not treated as no-doorman units.

The artifacts contain every supported pair, exact source/fit/protocol/report bindings, design vectors, support counts and derived diagnostics. The independent comparison assigns no credible interval or probability to the difference between fit medians. Existing serving models remain unchanged.

- Baseline: `data/model/chelsea-bayesian-category-contrasts-20260918`
- Half feature-prior scale: `data/model/chelsea-bayesian-category-prior-half-20260918`
- Complete comparison: `data/model/chelsea-bayesian-category-sensitivity-20260918/comparison.md`
- Machine-readable comparison: `data/model/chelsea-bayesian-category-sensitivity-20260918/comparison.json`
- Reproduction: `models/bayesian_category_contrasts.py` and `models/bayesian_category_sensitivity.py`

Five category-contrast tests and eight independent-comparison tests cover joint covariance, known-category encoding, support, convergence withholding, exact comparison membership and rejection of changes to the estimand or model specification.
