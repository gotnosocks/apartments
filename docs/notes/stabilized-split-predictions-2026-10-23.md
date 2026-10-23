# The stabilized discount split by building age, tax-bill registration and period: predictions, 2026-10-23

This test answers objection 5 on the research board (`20261023T031332Z-conference-open-objections-to-the-building-zones-fl`). The base model gives ads whose text says "rent stabilized" a single coefficient, about -2.4% on log rent. Reviewers suspect that number blends two kinds of unit:

- 421-a new construction, stabilized by its tax abatement and leased near market rent;
- older stock under the 1969 and 1974 laws, where a legal rent can sit far below market.

I wrote these predictions before running anything except row counts.

## Design

I fit an ordinary least squares regression on log latest ask, with no Bayesian model and no Modal time. The rows are those of the frontier dataset `b0-b3ddebf19af1dc1e-alldata-v36-dense-nyc`, with furnished, short-term and shared-space ads left out.

- Fixed effects: building, calendar month of the latest-ask day, and bedrooms by full baths.
- The stabilized text flag enters alone and interacted with three building-level splits:
  1. year built, from `external/building-age/20261021-3a64aa22`, in three bins: before 1974, 1974 to 2007, and 2008 on;
  2. stabilized units on the lot's DOF tax bill (`external/rentstab/20261008-b487c8a`, Manhattan lots, in the ad's year or the nearest year on file), as none or some;
  3. the ad's latest-ask day before or after 2019-06-14, when the Housing Stability and Tenant Protection Act ended vacancy decontrol and the vacancy bonus.
- With the building fixed effect, each coefficient compares flagged and unflagged ads inside the same building. Building-level splits enter only through their interaction with the flag.
- Standard errors are clustered two ways, by building and by week of the latest-ask day.
- A permutation null shuffles the flag among ads of the same building 200 times and refits, giving the null spread of each interaction.

The tax-bill split covers Manhattan lots only, so I fit it on the Manhattan rows. The age and period splits use every row.

## Predictions

- The pooled within-building flag coefficient falls between -1% and -5%.
- In buildings built 2008 on, mostly 421-a rentals, the flag coefficient falls between -2% and +2%, and its 95% interval includes 0.
- In buildings built before 1974, the flag coefficient falls between -3% and -12%, and it sits below the 2008-on coefficient by more than 2 clustered SE and beyond the 95th percentile of the permutation null.
- On Manhattan lots with no stabilized units on the tax bill, the flag coefficient falls between -1% and +1%, as those flags come from ads that misuse the term or describe units the tax bills miss. On lots with stabilized units it is 1 to 5 points lower.
- After 2019-06-14, the pre-1974 flag coefficient is 1 to 4 points lower than before, since a vacancy no longer lets the owner raise the legal rent toward market. The 2008-on coefficient changes by under 1.5 points.
- Fewer than 1 in 5 flagged ads fall in buildings with no flagged-unflagged contrast, and those ads drop out of the within-building estimate.

If the splits don't separate, I'll report the single coefficient as the better description and record the misses here.
