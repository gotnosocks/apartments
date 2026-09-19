# Source-refit movements: contribution review

The three largest distinct-unit movements in the completed
[source sensitivity comparison](chelsea-bayesian-source-revision-2026-09-18.md)
were reconstructed from both verified joint posteriors. All six apartment-level
contribution and fitted-log-rent diagnostic checks pass. This review does not
change model selection or any observed prices.

| Advertisement | Asking rent | Earlier fitted median | Revised fitted median | Largest mean-log contribution change |
| --- | ---: | ---: | ---: | --- |
| 4892020, 344 West 22nd Street | $42,500 | $31,136 | $29,239 | Building −0.03275 |
| 2936893, Chelsea House #7C | $6,950 | $6,128 | $6,418 | Bathroom reporting +0.05032 |
| 1376670, 227 West 17th Street | $35,000 | $23,237 | $23,029 | Building −0.00666 |

For the townhouse at 344 West 22nd Street, the building term accounts for almost
all of the −0.03289 change in posterior mean log rent. Encoded physical-feature
contributions together change by only +0.00024; the unit term changes by −0.00103.
Both datasets contain only **one observation, one advertisement and one unit**
for this building. Its building effect is therefore weakly supported separately
from the unit effect and this unusually expensive observation.

The fitted-rent 95% intervals are broad: **$10,587–$43,728** before the source
revision and **$10,313–$43,601** after it. The building log-effect intervals are
**−0.03385–1.34332** and **−0.05262–1.32935**. Its large dollar movement should not
be read as a precisely estimated correction. Garden and luxury-layout evidence
remain useful review leads, but this comparison did not fit those features and
cannot establish that they explain the shift.

For Chelsea House #7C, disputed bathroom composition was deliberately masked.
The largest movement is in the **unknown-composition reporting term**, rather
than a newly learned physical bathroom premium. The unit contribution partly
offsets it (−0.00402). This illustrates why reporting indicators need the same
skeptical review as amenities: changing how evidence is represented can move a
fitted rent even though the advertised apartment and price are unchanged.

For 227 West 17th Street, the smaller movement is primarily in the building
and unit terms (−0.00666 and −0.00157). Its fitted intervals also overlap broadly:
**$16,166–$32,167** and **$15,953–$32,187**.

These are additive **posterior mean log contributions**. Dollar medians and
quantiles do not decompose by adding these numbers. Draws from independent fits
are never paired, and no credible interval for a causal source-change effect is
claimed. Selecting the largest movements also makes this a diagnostic review,
not a representative estimate of sensitivity. The townhouse's Monte Carlo
standard errors for mean log rent are 0.00805 and 0.00656; numerical uncertainty
is material alongside its much larger posterior uncertainty.

Artifact: `data/model/chelsea-source-movement-review-20260918`. It contains the
six complete apartment reports, additive comparisons, diagnostic results,
source/fit/comparison hashes and frozen implementation. The publisher verifies
the fitted intervals against saved reports and checks contribution additivity.
Five tests cover identity, target, representation and additivity checks.

Reproduce with the fit's single-thread numerical environment:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --frozen --no-sync python \
  -m models.source_movement_review \
  --comparison data/model/chelsea-bayesian-source-sensitivity-20260918 \
  --reference data/model/chelsea-bayesian-bathrooms-long-20260918 \
  --candidate data/model/chelsea-bayesian-source-shared-disk-long-20260918 \
  --reference-dataset data/model/chelsea-reviewed-bathroom-projection-20260918 \
  --candidate-dataset data/model/chelsea-reviewed-scope-composition-projection-20260918 \
  --output data/model/chelsea-source-movement-review-20260918
```
