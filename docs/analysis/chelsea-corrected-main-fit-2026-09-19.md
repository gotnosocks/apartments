# Corrected-source Bayesian fit selected for main analysis

The main analysis now uses the completed PyMC fit on the reviewed floor/laundry
source revision. Seventeen ambiguous floor claims and one false-positive
building-laundry claim are masked. All prices, source clocks, cohort identities
and 172 current observations are unchanged. The main selection changes because
these source corrections are accepted, not because residual error decreased.

The fit uses four nutpie/Numba CPU chains, 4,000 warmup and 6,000 retained draws
per chain. All parameter, unit/bathroom contribution and joint-floor diagnostic
gates pass, with zero divergences or tree-depth saturation and minimum BFMI .428.

| Diagnostic family | Maximum R-hat | Minimum bulk ESS | Minimum tail ESS |
| --- | ---: | ---: | ---: |
| Parameters | 1.00316 | 1,033 | 1,621 |
| Unit/bathroom contributions | 1.00173 | 1,292 | 2,161 |
| Joint floor contrasts | 1.00154 | 2,147 | 3,748 |

## Current listings and source reviews

Across all 172 current apartments, the median absolute fitted-rent change is
**$1.29**, and the largest is **$13.21**. The same eight cases remain the largest
absolute current residuals. Their contribution reports, literal evidence and
source-review notes were regenerated against this posterior and all case-level
diagnostics pass.

Advertisement 5155021 still has a studio/one-bedroom source conflict. Its recorded
studio fit is **$2,884 [95% interval $2,682–$3,126]**. The one-bedroom scenario is
**$3,664 [$3,408–$3,970]**, a conditional increase of about 27.03%. The scenario
does not resolve the actual bedroom count or establish a causal renovation value;
the missing-area encoding and fixed building/unit offsets still apply.

Actual-data Streamlit AppTest verifies all 172 table rows, all eight review notes,
the count-conflict warning, the displayed $3,664 scenario and its source-uncertainty
warning, with no exceptions. The tested selection bytes were then atomically
installed as `config/main-analysis.json`, and their manifest bindings rechecked.

## Historical movements and floor uncertainty

Overall median absolute log residual changes negligibly: .0350948→.0350891.
The median absolute fitted-rent change over the full 52,863-row cohort is $0.99.
These are in-sample quantities, not forecast performance.

Three cases were reconstructed under both full joint posteriors; all six
apartment-level diagnostic checks pass and grouped mean-log contributions add
exactly:

| Advertisement | Asking rent | Before fitted median | Corrected fitted median | Main interpretation |
| --- | ---: | ---: | ---: | --- |
| 4892020, 344 West 22nd | $42,500 | $30,097 | $30,723 | Sparse townhouse/building effect; broad uncertainty |
| 1306285, 222 West 16th | $3,800 | $3,721 | $3,545 | Disputed ninth-floor value becomes unknown |
| 4800947, 340 Ninth | $6,750 | $6,384 | $6,317 | False shared-laundry value becomes unknown |

The townhouse's 95% fitted interval remains approximately **$10,490–$43,615**.
Its largest mean-log movement is in the building term (+.01181); mean-log-rent
Monte Carlo standard errors are .00687 and .00618 in the two fits. The $627
median-dollar movement is not a precisely estimated correction effect. Its
description still supports review of whole-townhouse layout, garden and luxury
features; it is not a direct floor-data correction.

For the ninth-floor mask, encoded-feature contribution falls while reporting and
unit terms partly offset it. For the laundry mask, the reporting contribution
drives much of the movement. Neither should be described as a newly measured
physical amenity discount.

Removing the only ninth-floor observation changes the floor basis from 60 to 59
total features. Under the existing observed-level construction, the aggregate
8→10 prior log SD changes **.2121→.15**. The joint posterior association changes
from **+7.18% [−7.56%, +23.63%]** to **+5.87% [−8.00%, +21.15%]**. Both are broad
and span zero. This comparison mixes source and induced-prior changes; it is not
a prior-matched data-only experiment. Preserving joint prior variance across
changes in observed floor support is a useful next representation check.

## Saved products

- Main fit: `data/model/chelsea-bayesian-reviewed-corrections-floor-disk-20260919`.
- Source: `data/model/chelsea-reviewed-floor-masked-analysis-20260918`.
- Fit comparison: `data/model/chelsea-reviewed-corrections-fit-comparison-20260919`.
- Historical contribution review: `data/model/chelsea-corrected-fit-movement-review-20260919`.
- Current source notes: `data/model/chelsea-corrected-current-residual-source-review-20260919`.
- Actual page validation: `data/model/chelsea-corrected-main-page-validation-20260919`.

The frozen source-review and page-validation scripts now accept explicit input
and output paths for this refit. Older artifacts retain their original code and
remain available for comparison. The experimental expanded laundry measurements
have not been projected into this main fit.
