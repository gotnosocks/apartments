# Capture-time active listing review

Full-description review of all five capture-time active observations flagged by
the commercial-language screen supports no scope exclusions. “Current” here
means active when captured, not verified availability today.

Advertisement 5082877 describes a dressing room usable as a home office.
Advertisements 5091291, 5091292, 5122323 and 5112590 describe residential
apartments with shared amenities, including event space. Shared fifteenth-floor
terrace language does not establish an apartment's floor. These five records
span three distinct full descriptions; classifications concern offered product
language, not legal occupancy.

The latter four ads explicitly say the shown price is base rent and advertise a
required community amenity fee of $90 per resident per month. This is a
capture-scoped advertised claim. Household size is unknown, so no all-in total
is assigned and no asking rent is corrected. Optional parking, storage and pet
fees and usage-based electricity are separate. Even when historical ads share
the exact description, the fee is not assigned to historical prices without
effective-date evidence.

This motivates a separate renter-cost comparison: base rent plus supported
mandatory charges, with resident count supplied explicitly. Keep base asking
rent and fee-inclusive cost distinguishable in modeling and residual analysis.

## Evidence and reproducibility

The artifact `data/model/chelsea-current-commercial-match-review-20260920`
contains full descriptions, every retained association, literal evidence spans,
manual dispositions and four capture-bound fee research records. Its manifest
SHA-256 is `4d4913a1888bcf55978e1263efc48a1b662c9e554ad4fc7384e1b6b20cb4ba4e`.
The helper `docs/analysis/scripts/review_current_commercial_matches.py` checks
the exact input manifest, all five captured-current identities, description
hashes and literal spans. An identical replay and full artifact verification
passed. No source or model values changed.

Together with the earlier 37 priority descriptions, this leaves 506 full-text
groups unreviewed. The five active observations are completely reviewed for
this screen; the historical cohort is not.
