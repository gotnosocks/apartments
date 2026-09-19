# Current listing source review after discovery

The new source audit covers **all 172 current rows** in the refreshed research
dataset. It verifies the raw bodies and own-listing identities against the
transformation's saved evidence. It checks structured asking rent, dated own-ad
price changes, narrowly labeled description rents, and wording that can indicate
concessions, furnished products, commercial use or laundry hookups.

One explicit description-rent disagreement was found: **5115645**, 249 West 29th
Street #3E, has structured asking rent **$6,950**, while its fee paragraph says
monthly rent and security deposit are $7,750. Its own structured price history
reports $7,750 on July 27 and $6,950 on September 16. The structured move-in deposit
also reports $6,950. This supports retaining the current structured ask under the
existing capture-price policy; it does not justify replacing it with the older
description amount. These fields share a source and are not independent evidence.
The inconsistency remains recorded for residual/source review.

The audit finds no disagreement between analytical and structured current prices,
no disagreement with the latest visible own-ad price event, and no invalid or
post-capture price events. Those checks do not establish transaction prices or
verify every dollar amount in free text; the description-rent matcher is narrow.

All **14 net-effective mentions** occur inside the same approval-standards clause
stating that approvals use gross rent. None independently says the displayed ask
is net. Tests ensure that a second net-effective statement outside that clause
would remain a separate finding.

The broader wording screen flags **19 listings for product language** and **three
for scope language**. Review distinguishes:

- Furnished shared rooftops/lounges from furnished apartments. Seventeen product
  cases concern shared facilities. Advertisement 5115645 offers furnishings for an
  increased fee; 5147241 explicitly offers furnished or unfurnished options. The
  latter does not establish whether both options use the same displayed price.
- A dressing room that could serve as an office (5082877) from a commercial rental.
- A one-bedroom residence permitting live/work use (5121207) from an offer that
  only supports commercial occupancy.
- A residentially described triplex currently used as an art gallery (4833587).
  The source claims residential zoning and describes a bedroom and kitchen, but
  that is not independent verification of its permitted use or present condition.
  Retain this as a scope/sensitivity case rather than applying a keyword exclusion.

No source values or cohort membership were changed by this audit. Optional-product
pricing and the gallery's current use remain explicit residual/sensitivity review
cases. Absence from this lexical screen is not evidence that a listing has no
measurement problems. The expanded cohort still needs its own accepted PyMC fit.

Evidence: `data/model/chelsea-current-source-audit-20260918`, including all 172
reviews, exact text offsets, own-ad price-event clocks, source-row/body/raw hashes
and frozen audit code. Six new tests cover dated versus future/conflicting price
events, wrong-advertisement rejection, invalid prices and approval-clause scope;
14 tests pass together with the cohort transformation checks.
